from datetime import datetime, timedelta

from lonora_adapters.brokers.base import BrokerManager
from lonora_contracts.domain import utcnow
from lonora_contracts.runs import Lease
from lonora_contracts.trading import TradeRequest
from lonora_db.client import Database
from lonora_db.schema import RunRow, TradingJournalRow
from lonora_db.trading_journal import mark_reconciliation_attempt, persist_result
from sqlalchemy import ColumnElement, and_, or_, select


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
                            (TradingJournalRow.status == "submitted")
                            & (TradingJournalRow.submitted_at < now - timedelta(seconds=60))
                        ),
                        observation_due(now),
                    )
                    .order_by(TradingJournalRow.updated_at, TradingJournalRow.operation_id)
                    .limit(50)
                )
            ).all()
        )
    resolved = 0
    for row in rows:
        try:
            if row.status == "submitted" and row.result.get("details", {}).get("lease"):
                lease = Lease.model_validate(row.result["details"]["lease"])
                async with db.sessions() as session:
                    run = await session.get(RunRow, lease.run_id)
                    if (
                        run is not None
                        and run.lease_owner == lease.owner
                        and run.lease_fence == lease.fence
                        and run.status in {"leased", "running"}
                        and run.lease_expires_at is not None
                        and run.lease_expires_at > utcnow()
                    ):
                        continue
            # Reconciliation observes evidence only. Never resubmit an uncertain request,
            # including a persisted submission left behind by a terminated process.
            broker = await brokers.get(row.owner_id, row.account_id)
            result = await broker.reconcile(
                row.operation_id, TradeRequest.model_validate(row.request)
            )
            if result.status not in {"confirmed", "failed"}:
                continue
            if result.operation_id != row.operation_id:
                continue
            async with db.sessions() as session, session.begin():
                changed = await persist_result(
                    session, row.operation_id, result.status, result.model_dump(mode="json")
                )
        except Exception:
            # One unavailable broker or malformed receipt must not starve other accounts.
            continue
        finally:
            async with db.sessions() as session, session.begin():
                await mark_reconciliation_attempt(session, row.operation_id)
        resolved += int(changed)
    return resolved
