"""Observe-only recovery of journaled financial operations; nothing here sends or resends.

The maintenance loop settles what durable evidence can settle and leaves the rest
explicitly uncertain:

- An abandoned ``reserved`` row never crossed the send boundary. It is released to
  ``failed`` with ``send_state="not_sent"`` without any broker call; the release and the
  executor's reserved->submitted transition share the journal row lock.
- A ``submitted`` row whose sender is gone, or an ``ambiguous`` row, is observed through
  the adapter's correlated reconciliation (exact operation identity) and, for set-type
  management actions, by comparing the broker target with the requested change
  (``target_state``). The sender is proven gone when the account send lock is free while
  the row is still ``submitted`` (the executor persists every outcome under that lock).
  Inconclusive *or unavailable* evidence makes it ``ambiguous``, so an operation whose
  broker can no longer be observed is still settled by an owner attestation.
- A ``confirmed`` row whose resulting state was not yet verified is re-read until it is
  ``verified`` or the verification window ends as ``unverified``.
"""

import asyncio
from datetime import datetime, timedelta
from typing import Any, cast

from lonora_adapter_kit.broker import BrokerAdapter
from lonora_adapters.brokers.base import BrokerManager
from lonora_contracts.account import Order, Position
from lonora_contracts.domain import utcnow
from lonora_contracts.execution_quality import ExecutionSnapshot
from lonora_contracts.runs import Lease
from lonora_contracts.trading import TradeRequest, TradeResult
from lonora_db.client import Database
from lonora_db.schema import RunRow, TradingJournalRow
from lonora_db.trading_journal import (
    mark_reconciliation_attempt,
    persist_result,
    release_reservation,
)
from sqlalchemy import ColumnElement, and_, or_, select, text

from .operation_events import operation_event, send_state
from .target_state import TARGET_STATE_ACTIONS, target_state_receipt
from .verification import verify_effect

# A fenced sender waiting for the account send lock keeps its reservation; once its
# lease is gone (or, without a lease, after a longer bound) the reservation is abandoned.
RESERVATION_GRACE = timedelta(seconds=60)
UNLEASED_RESERVATION_GRACE = timedelta(minutes=5)
SUBMISSION_GRACE = timedelta(seconds=60)
# A confirmed effect whose resulting state still differs after this long is reported as
# acknowledged but unverified; it is never resent or reinterpreted as failure.
VERIFICATION_WINDOW = timedelta(minutes=15)
VERIFICATION_INTERVAL = timedelta(seconds=30)


def send_lock_key(owner_id: str, account_id: str) -> str:
    """The advisory lock the executor holds from its send boundary to its final outcome."""
    return f"execution:{owner_id}:{account_id}"


async def sender_gone(db: Database, row: TradingJournalRow) -> bool:
    """Proof that a ``submitted`` row's sender stopped, leased or not.

    The executor takes the account send lock before its send boundary and persists the
    final outcome before releasing it. A row still ``submitted`` while that lock can be
    taken therefore has no sender left. A busy lock (this or another operation of the
    account is in flight) proves nothing; the row is observed again on a later pass.
    """
    async with db.sessions() as session, session.begin():
        acquired = await session.scalar(
            text("SELECT pg_try_advisory_xact_lock(hashtextextended(:key, 0))"),
            {"key": send_lock_key(row.owner_id, row.account_id)},
        )
        if not acquired:
            return False
        current = await session.get(TradingJournalRow, row.operation_id)
        return current is not None and current.status == "submitted"


def observation_due(now: datetime) -> ColumnElement[bool]:
    # Every observation costs broker RPC quota. Fresh uncertainty is checked each pass;
    # operations that stay unresolved rotate progressively slower instead of every 10 seconds.
    submitted, attempted = TradingJournalRow.submitted_at, TradingJournalRow.updated_at
    return or_(
        submitted > now - timedelta(minutes=5),
        and_(submitted > now - timedelta(hours=1), attempted <= now - timedelta(minutes=1)),
        and_(submitted > now - timedelta(days=1), attempted <= now - timedelta(minutes=10)),
        attempted <= now - timedelta(hours=1),
    )


async def sender_alive(db: Database, row: TradingJournalRow, now: datetime) -> bool:
    """Whether the fenced run that journaled this operation may still be sending it."""
    raw = row.result.get("details", {}).get("lease")
    if not raw:
        return False
    lease = Lease.model_validate(raw)
    async with db.sessions() as session:
        run = await session.get(RunRow, lease.run_id)
    return bool(
        run is not None
        and run.lease_owner == lease.owner
        and run.lease_fence == lease.fence
        and run.status in {"leased", "running"}
        and run.lease_expires_at is not None
        and run.lease_expires_at > now
    )


def reservation_abandoned(row: TradingJournalRow, alive: bool, now: datetime) -> bool:
    if alive:
        return False
    leased = bool(row.result.get("details", {}).get("lease"))
    grace = RESERVATION_GRACE if leased else UNLEASED_RESERVATION_GRACE
    return row.submitted_at is None or row.submitted_at <= now - grace


def before_send_target(row: TradingJournalRow, request: TradeRequest) -> Position | Order | None:
    """The target as the send boundary observed it, from server-captured evidence."""
    evidence: Any = row.result.get("details", {}).get("execution_evidence", {})
    before: Any = (
        cast(dict[str, Any], evidence).get("before_send") if isinstance(evidence, dict) else None
    )
    snapshot: Any = (
        cast(dict[str, Any], before).get("snapshot") if isinstance(before, dict) else None
    )
    if not isinstance(snapshot, dict):
        return None
    data = cast(dict[str, Any], snapshot)
    key, identity = (
        ("positions", request.position_id) if request.position_id else ("orders", request.order_id)
    )
    if identity is None:
        return None
    for item in cast(list[Any], data.get(key) or []):
        if isinstance(item, dict) and cast(dict[str, Any], item).get("id") == identity:
            try:
                return (Position if key == "positions" else Order).model_validate(item)
            except ValueError:
                return None
    return None


async def observe_operation(
    broker: BrokerAdapter,
    row: TradingJournalRow,
    state: tuple[list[Position], list[Order], datetime] | None = None,
) -> TradeResult | None:
    """A conclusive receipt from broker evidence for a possibly-sent operation, or None.

    ``state`` is (positions, orders, read start time) from a broker read taken after the
    operation's send boundary, reused by the account observer instead of reading again.
    """
    request = TradeRequest.model_validate(row.request)
    receipt = await broker.reconcile(row.operation_id, request, submitted_at=row.submitted_at)
    if receipt.operation_id == row.operation_id and receipt.status in {"confirmed", "failed"}:
        return receipt
    if request.action not in TARGET_STATE_ACTIONS:
        return None
    if state is None:
        # The read must start after the time it is credited with, never before.
        started = utcnow()
        async with asyncio.timeout(15):
            state = await broker.positions(), await broker.orders(), started
    positions, orders, observed_at = state
    if len(positions) > 1000 or len(orders) > 1000:
        return None  # A truncated view is not proof that a target is absent.
    deals: list[dict[str, Any]] | None = None
    if request.action == "cancel_order":
        start = (row.submitted_at or observed_at) - timedelta(minutes=5)
        try:
            async with asyncio.timeout(15):
                deals = await broker.history(start, observed_at, 1000)
            if len(deals) >= 1000:
                deals = None
        except Exception:
            deals = None
    return target_state_receipt(
        row.operation_id,
        request,
        positions,
        orders,
        submitted_at=row.submitted_at,
        observed_at=observed_at,
        deals=deals,
        before=before_send_target(row, request),
    )


async def settle(db: Database, operation_id: str, receipt: TradeResult) -> bool:
    async with db.sessions() as session, session.begin():
        changed = await persist_result(
            session, operation_id, receipt.status, receipt.model_dump(mode="json")
        )
        if changed:
            saved = await session.get(TradingJournalRow, operation_id)
            assert saved is not None
            await operation_event(session, saved)
    return changed


async def mark_interrupted(db: Database, operation_id: str) -> None:
    """A possibly-sent operation whose sender stopped before persisting any outcome."""
    async with db.sessions() as session, session.begin():
        current = await session.get(TradingJournalRow, operation_id, with_for_update=True)
        if current is None or current.status != "submitted":
            return
        await persist_result(
            session,
            operation_id,
            "ambiguous",
            TradeResult(
                operation_id=operation_id,
                status="ambiguous",
                code="execution_interrupted_after_send",
                details={"send_state": send_state(current)},
            ).model_dump(mode="json"),
        )
        await operation_event(session, current)


async def reconcile_ambiguous(db: Database, brokers: BrokerManager) -> int:
    now = utcnow()
    async with db.sessions() as session:
        rows = list(
            (
                await session.scalars(
                    select(TradingJournalRow)
                    .where(
                        (TradingJournalRow.status == "ambiguous")
                        | (
                            TradingJournalRow.status.in_(["submitted", "reserved"])
                            & (TradingJournalRow.submitted_at < now - SUBMISSION_GRACE)
                        ),
                        observation_due(now),
                        TradingJournalRow.execution_mode == "live",
                    )
                    .order_by(TradingJournalRow.updated_at, TradingJournalRow.operation_id)
                    .limit(50)
                )
            ).all()
        )
    resolved = 0
    for row in rows:
        changed = False
        try:
            alive = row.status != "ambiguous" and await sender_alive(db, row, utcnow())
            if row.status == "reserved":
                # Provably unsent: release it without asking the broker anything.
                if reservation_abandoned(row, alive, utcnow()):
                    async with db.sessions() as session, session.begin():
                        released = await release_reservation(
                            session, row.operation_id, "sender_stopped_before_send"
                        )
                        if released is not None:
                            await operation_event(session, released)
                            changed = True
                continue
            if alive:
                continue
            if row.status == "submitted" and not await sender_gone(db, row):
                continue
            # Reconciliation observes evidence only. Never resubmit an uncertain request,
            # including a persisted submission left behind by a terminated process.
            receipt: TradeResult | None = None
            try:
                broker = await brokers.get(row.owner_id, row.account_id)
                receipt = await observe_operation(broker, row)
            except Exception:
                # An unreachable broker, a history limit or a malformed receipt is not
                # evidence either way. The operation stays uncertain, but an abandoned
                # submission still becomes ambiguous below, where the owner can settle it.
                receipt = None
            if receipt is not None:
                changed = await settle(db, row.operation_id, receipt)
            elif row.status == "submitted":
                await mark_interrupted(db, row.operation_id)
        except Exception:
            # One unavailable broker or malformed receipt must not starve other accounts.
            continue
        finally:
            async with db.sessions() as session, session.begin():
                await mark_reconciliation_attempt(session, row.operation_id)
            resolved += int(changed)
    return resolved


def verification_started(verification: dict[str, Any], fallback: datetime) -> datetime:
    value = verification.get("pending_since") or verification.get("observed_at")
    try:
        return datetime.fromisoformat(str(value)) if value else fallback
    except ValueError:
        return fallback


async def recheck_verifications(db: Database, brokers: BrokerManager) -> int:
    """Re-read broker state for acknowledged effects still awaiting state verification.

    Returns how many reached a final verification state. Each recheck is a read; the
    confirmed broker receipt and all earlier evidence stay unchanged.
    """
    now = utcnow()
    async with db.sessions() as session:
        rows = list(
            (
                await session.scalars(
                    select(TradingJournalRow)
                    .where(
                        TradingJournalRow.status == "confirmed",
                        TradingJournalRow.execution_mode == "live",
                        TradingJournalRow.result["details"]["verification"]["status"].as_string()
                        == "pending",
                        TradingJournalRow.updated_at <= now - VERIFICATION_INTERVAL,
                    )
                    .order_by(TradingJournalRow.updated_at, TradingJournalRow.operation_id)
                    .limit(50)
                )
            ).all()
        )
    settled = 0
    for row in rows:
        try:
            details = row.result.get("details", {})
            previous = cast(dict[str, Any], details.get("verification") or {})
            started = verification_started(previous, row.updated_at)
            request = TradeRequest.model_validate(row.request)
            receipt = TradeResult.model_validate(row.result)
            snapshot = details.get("execution_evidence", {}).get("before_send", {}).get("snapshot")
            before = ExecutionSnapshot.model_validate(snapshot) if snapshot else None
            broker = await brokers.get(row.owner_id, row.account_id)
            verification = await verify_effect(broker, request, receipt, before)
            verification = {
                **verification,
                "pending_since": started.isoformat(),
                "attempts": int(previous.get("attempts", 1)) + 1,
            }
            if verification["status"] == "pending" and utcnow() - started >= VERIFICATION_WINDOW:
                verification = {
                    **verification,
                    "status": "unverified",
                    "code": "broker_state_not_verified_in_window",
                }
        except Exception:
            continue
        async with db.sessions() as session, session.begin():
            journal = await session.get(TradingJournalRow, row.operation_id, with_for_update=True)
            if (
                journal is None
                or journal.status != "confirmed"
                or journal.result.get("details", {}).get("verification", {}).get("status")
                != "pending"
            ):
                continue
            journal.result = {
                **journal.result,
                "details": {**journal.result.get("details", {}), "verification": verification},
            }
            journal.updated_at = utcnow()
            if verification["status"] != "pending":
                settled += 1
                await operation_event(session, journal)
    return settled
