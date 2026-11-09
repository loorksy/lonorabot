"""Observable financial operation lifecycle, projected only from the durable journal row.

Every journal transition that changes what the owner should see (send boundary crossed,
broker outcome, reconciliation, verification, owner attestation) emits one
``trading.operation_updated`` event in the same transaction, so clients can show
"Awaiting broker confirmation" and refresh without polling. Events carry facts from the
row; they never grant authority or trigger execution.
"""

from typing import Any, Literal, cast

from lonora_contracts.trading import UNRESOLVED_STATUSES
from lonora_db.events import emit
from lonora_db.schema import RunRow, TradingJournalRow
from sqlalchemy.ext.asyncio import AsyncSession

SendState = Literal["not_sent", "sent", "unknown"]


def _details(row: TradingJournalRow) -> dict[str, Any]:
    details = (row.result or {}).get("details", {})
    return cast(dict[str, Any], details) if isinstance(details, dict) else {}


def _execution(row: TradingJournalRow) -> dict[str, Any]:
    execution = _details(row).get("execution")
    return cast(dict[str, Any], execution) if isinstance(execution, dict) else {}


def send_state(row: TradingJournalRow) -> SendState:
    """Whether the persisted send boundary was crossed, never inferred from a broker reply.

    ``sent`` means the boundary authorized the broker mutation, so it may have reached the
    broker. Rows without the server-owned execution record (legacy) stay ``unknown``.
    """
    if row.status == "reserved" or _details(row).get("send_state") == "not_sent":
        return "not_sent"
    if _execution(row).get("send_authorized") is True:
        return "sent"
    # This executor persists send authorization before an adapter may send, so its own
    # receipts rejected before the boundary are known unsent.
    if row.status == "failed" and _execution(row):
        return "not_sent"
    return "unknown"


def verification_status(row: TradingJournalRow) -> str | None:
    verification = _details(row).get("verification")
    if isinstance(verification, dict):
        value = cast(dict[str, Any], verification).get("status")
        return value if isinstance(value, str) else None
    return None


def awaiting_broker_confirmation(row: TradingJournalRow) -> bool:
    """Sent, but the broker outcome or its resulting account state is not yet established."""
    return row.status in UNRESOLVED_STATUSES or (
        row.status == "confirmed" and verification_status(row) == "pending"
    )


def lifecycle(row: TradingJournalRow) -> dict[str, Any]:
    resolution = _details(row).get("resolution")
    return {
        "send_state": send_state(row),
        "verification_status": verification_status(row),
        "awaiting_broker_confirmation": awaiting_broker_confirmation(row),
        "resolution": resolution if isinstance(resolution, dict) else None,
    }


async def operation_event(session: AsyncSession, row: TradingJournalRow) -> None:
    """Emit one owner-visible transition fact in the transaction that made it durable."""
    execution = _execution(row)
    run_id = execution.get("run_id") if isinstance(execution.get("run_id"), str) else None
    agent_id = execution.get("agent_id") if isinstance(execution.get("agent_id"), str) else None
    thread_id = None
    if run_id:
        run = await session.get(RunRow, run_id)
        if run is not None:
            origin = run.model_metadata.get("origin_thread_id")
            thread_id = origin if isinstance(origin, str) and origin else run.thread_id
    state = lifecycle(row)
    resolution = cast(dict[str, Any], state["resolution"] or {})
    emit(
        session,
        row.owner_id,
        "trading.operation_updated",
        thread_id=thread_id,
        agent_id=agent_id,
        run_id=run_id,
        payload={
            "operation_id": row.operation_id,
            "account_id": row.account_id,
            "symbol": row.request.get("symbol"),
            "action": row.request.get("action"),
            "status": row.status,
            "code": (row.result or {}).get("code"),
            "send_state": state["send_state"],
            "verification_status": state["verification_status"],
            "awaiting_broker_confirmation": state["awaiting_broker_confirmation"],
            "resolution_source": resolution.get("source"),
            "transition_id": ":".join(
                (row.status, str(state["verification_status"]), row.updated_at.isoformat())
            ),
        },
    )


async def resolution_event(session: AsyncSession, row: TradingJournalRow) -> None:
    """Durable audit fact for an owner attestation; events are never deleted."""
    resolution = cast(dict[str, Any], lifecycle(row)["resolution"] or {})
    emit(
        session,
        row.owner_id,
        "trading.operation_resolved",
        payload={
            "operation_id": row.operation_id,
            "account_id": row.account_id,
            "symbol": row.request.get("symbol"),
            "action": row.request.get("action"),
            "outcome": resolution.get("outcome"),
            "statement": resolution.get("statement"),
            "broker_reference": resolution.get("broker_reference"),
            "actor": resolution.get("actor"),
            "resolved_at": resolution.get("resolved_at"),
            "prior_code": _details(row).get("prior_receipt", {}).get("code"),
        },
    )
    await operation_event(session, row)
