"""The owner's own attestations, shared by the owner routes.

Each function is the single implementation behind one owner-session action, whether the
owner reaches it from a settings page, the API or a card in the conversation. None of
them is reachable from an agent tool.
"""

from typing import Any

from lonora_contracts.trading import OperationResolution
from lonora_core.user_error import LonoraError
from lonora_db.events import emit
from lonora_db.schema import TradingJournalRow
from lonora_db.trading_journal import resolve_operation
from sqlalchemy.ext.asyncio import AsyncSession

from .operation_events import resolution_event


async def attest_operation(
    session: AsyncSession,
    owner_id: str,
    operation_id: str,
    resolution: OperationResolution,
    actor: dict[str, Any],
) -> TradingJournalRow:
    """Owner attestation for an uncertain operation; it never resends.

    Executed or Not executed clears the block; Unknown is recorded and keeps it.

    The original receipt and evidence stay on the row and the attestation is a durable
    event (``trading.operation_resolved``).
    """
    from .opportunities import sync_opportunity_execution

    row = await resolve_operation(session, owner_id, operation_id, resolution, actor)
    if row.status == "ambiguous":
        # Unknown: the owner's answer is recorded; the operation stays uncertain (6.3).
        emit(
            session,
            owner_id,
            "trading.operation_answered",
            payload={
                "operation_id": row.operation_id,
                "outcome": resolution.outcome,
                "broker_confirmed": False,
            },
        )
        return row
    await resolution_event(session, row)
    if row.request.get("thesis_id"):
        # Release or settle the thesis link now, not on the next maintenance pass.
        try:
            await sync_opportunity_execution(session, row)
        except LonoraError as error:
            if error.code != "opportunity_not_found":
                raise
    return row
