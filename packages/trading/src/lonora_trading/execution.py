import asyncio

from lonora_adapters.brokers.base import BrokerManager
from lonora_contracts.domain import utcnow
from lonora_contracts.runs import Lease
from lonora_contracts.trading import TradeRequest, TradeResult
from lonora_core.trading_control import require_trading
from lonora_core.user_error import LonoraError
from lonora_db.broker_sessions import BrokerSessionRepository
from lonora_db.client import Database
from lonora_db.runs import require_lease
from lonora_db.schema import TradingJournalRow
from lonora_db.trading_journal import persist_result, reserve_operation

from .controls import read_controls
from .idempotency import trade_fingerprint
from .preflight import preflight


class ExecutionService:
    def __init__(self, db: Database, brokers: BrokerManager):
        self.db, self.brokers = db, brokers

    async def execute(
        self, owner_id: str, request: TradeRequest, lease: Lease | None = None
    ) -> TradeResult:
        async with self.db.sessions() as session:
            previous = await session.get(TradingJournalRow, request.operation_id)
            if previous:
                if previous.owner_id != owner_id or previous.request_hash != trade_fingerprint(
                    request
                ):
                    raise LonoraError("idempotency_conflict", 409)
                return (
                    TradeResult.model_validate(previous.result)
                    if previous.result
                    else TradeResult(
                        operation_id=request.operation_id,
                        status="ambiguous",
                        code="operation_in_progress",
                    )
                )
        require_trading(await read_controls(self.db))
        broker = await self.brokers.get(owner_id, request.account_id)
        await preflight(broker, request)
        async with self.db.sessions() as session, session.begin():
            await BrokerSessionRepository().get(session, owner_id, request.account_id, lock=True)
            if lease:
                await require_lease(session, lease, lock=True)
            journal, fresh = await reserve_operation(
                session,
                owner_id,
                request.operation_id,
                request.account_id,
                trade_fingerprint(request),
                request.model_dump(mode="json"),
            )
            if not fresh:
                if journal.result:
                    return TradeResult.model_validate(journal.result)
                return TradeResult(
                    operation_id=request.operation_id,
                    status="ambiguous",
                    code="operation_in_progress",
                )
            journal.status = "submitted"
            journal.submitted_at = utcnow()

        async def before_send() -> None:
            require_trading(await read_controls(self.db))
            async with self.db.sessions() as session:
                if lease:
                    await require_lease(session, lease)
                row = await session.get(TradingJournalRow, request.operation_id)
                if row is None or row.status != "submitted":
                    raise LonoraError("operation_not_submitted", 409)

        cancelled = False
        try:
            result = await broker.execute(request, before_send)
        except asyncio.CancelledError:
            cancelled = True
            result = TradeResult(
                operation_id=request.operation_id,
                status="ambiguous",
                code="broker_result_ambiguous",
            )
        except TimeoutError:
            result = TradeResult(
                operation_id=request.operation_id,
                status="ambiguous",
                code="broker_result_ambiguous",
            )
        except LonoraError as error:
            result = TradeResult(
                operation_id=request.operation_id,
                status="failed"
                if error.code
                in {
                    "trading_disabled",
                    "emergency_stop",
                    "stale_lease",
                    "position_not_found",
                    "order_not_found",
                }
                else "ambiguous",
                code=error.code,
            )
        async with self.db.sessions() as session, session.begin():
            await persist_result(
                session, request.operation_id, result.status, result.model_dump(mode="json")
            )
        if cancelled:
            raise asyncio.CancelledError
        return result
