import asyncio

from lonora_adapters.brokers.base import BrokerManager
from lonora_contracts.broker import BrokerConnection
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


def receipt(row: TradingJournalRow) -> TradeResult:
    if row.result and row.status != "submitted":
        return TradeResult.model_validate(row.result)
    return TradeResult(
        operation_id=row.operation_id, status="ambiguous", code="operation_in_progress"
    )


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
                return receipt(previous)
            connection = await BrokerSessionRepository().get(session, owner_id, request.account_id)
            connection_version = connection.version
        require_trading(await read_controls(self.db))
        broker = await self.brokers.get(owner_id, request.account_id)
        await preflight(broker, request)
        async with self.db.sessions() as session, session.begin():
            connection = await BrokerSessionRepository().get(
                session, owner_id, request.account_id, lock=True
            )
            if connection.version != connection_version:
                raise LonoraError("broker_connection_changed", 409)
            configuration = BrokerConnection.model_validate(connection.payload)
            if not configuration.enabled:
                raise LonoraError("broker_disabled", 409)
            leased_run = await require_lease(session, lease, lock=True) if lease else None
            journal, fresh = await reserve_operation(
                session,
                owner_id,
                request.operation_id,
                request.account_id,
                trade_fingerprint(request),
                request.model_dump(mode="json"),
            )
            if not fresh:
                return receipt(journal)
            journal.status = "submitted"
            journal.submitted_at = utcnow()
            journal.result = TradeResult(
                operation_id=request.operation_id,
                status="submitted",
                code="operation_in_progress",
                details={
                    "lease": lease.model_dump() if lease else None,
                    "execution": {
                        "run_id": leased_run.id if leased_run else None,
                        "agent_id": leased_run.agent_id if leased_run else None,
                        "provider": configuration.provider,
                        "broker_account_id": configuration.account_id,
                    },
                },
            ).model_dump(mode="json")

        send_authorized = False

        async def before_send() -> None:
            nonlocal send_authorized
            if send_authorized:
                raise LonoraError("operation_send_already_authorized", 409)
            require_trading(await read_controls(self.db))
            async with self.db.sessions() as session:
                connection = await BrokerSessionRepository().get(
                    session, owner_id, request.account_id
                )
                if not BrokerConnection.model_validate(connection.payload).enabled:
                    raise LonoraError("broker_disabled", 409)
                if connection.version != connection_version:
                    raise LonoraError("broker_connection_changed", 409)
                if lease:
                    await require_lease(session, lease)
                row = await session.get(TradingJournalRow, request.operation_id)
                if row is None or row.status != "submitted":
                    raise LonoraError("operation_not_submitted", 409)
            send_authorized = True

        cancelled = False
        try:
            result = await broker.execute(request, before_send)
            if result.operation_id != request.operation_id or not send_authorized:
                result = TradeResult(
                    operation_id=request.operation_id,
                    status="ambiguous",
                    code="broker_result_mismatch",
                )
        except asyncio.CancelledError:
            cancelled = True
            result = TradeResult(
                operation_id=request.operation_id,
                status="ambiguous",
                code="broker_result_ambiguous",
            )
        except LonoraError as error:
            result = TradeResult(
                operation_id=request.operation_id,
                status="failed"
                if not send_authorized
                and error.code
                in {
                    "trading_disabled",
                    "emergency_stop",
                    "stale_lease",
                    "broker_disabled",
                    "broker_connection_changed",
                }
                else "ambiguous",
                code=error.code,
            )
        except Exception:
            # Transport or SDK failures are not evidence of non-execution.
            result = TradeResult(
                operation_id=request.operation_id,
                status="ambiguous",
                code="broker_result_ambiguous",
            )
        async with self.db.sessions() as session, session.begin():
            await persist_result(
                session, request.operation_id, result.status, result.model_dump(mode="json")
            )
            row = await session.get(TradingJournalRow, request.operation_id)
            assert row is not None
            result = receipt(row)
        if cancelled:
            raise asyncio.CancelledError
        return result
