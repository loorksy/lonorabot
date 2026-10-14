import asyncio
from collections.abc import Awaitable, Callable

from lonora_adapters.brokers.base import BrokerManager
from lonora_contracts.broker import BrokerConnection
from lonora_contracts.domain import utcnow
from lonora_contracts.runs import Lease
from lonora_contracts.trading import TradeRequest, TradeResult
from lonora_contracts.trading_goal import GoalExecution
from lonora_core.trading_control import require_trading
from lonora_core.user_error import LonoraError
from lonora_db.broker_sessions import BrokerSessionRepository
from lonora_db.client import Database
from lonora_db.runs import require_lease
from lonora_db.schema import RunRow, TradingJournalRow
from lonora_db.trading_journal import persist_result, reserve_operation
from sqlalchemy.ext.asyncio import AsyncSession

from .controls import read_controls
from .goals import guard_goal_execution
from .goals_market import fresh_goal_evidence
from .idempotency import trade_fingerprint
from .preflight import preflight


def receipt(row: TradingJournalRow) -> TradeResult:
    if row.result and row.status != "submitted":
        return TradeResult.model_validate(row.result)
    return TradeResult(
        operation_id=row.operation_id, status="ambiguous", code="operation_in_progress"
    )


async def require_goal_lineage(
    session: AsyncSession, lease: Lease, goal: GoalExecution | None
) -> None:
    origin_run = await require_lease(session, lease)
    linked_goal = origin_run.model_metadata.get("goal_id")
    ancestor = origin_run
    seen = {origin_run.id}
    for _ in range(16):
        if not ancestor.parent_run_id:
            break
        if ancestor.parent_run_id in seen:
            raise LonoraError("goal_run_ancestry_invalid", 409)
        seen.add(ancestor.parent_run_id)
        ancestor = await session.get(RunRow, ancestor.parent_run_id)
        if ancestor is None:
            raise LonoraError("goal_run_ancestry_invalid", 409)
        if ancestor.model_metadata.get("goal_id"):
            raise LonoraError("goal_delegated_trade_forbidden", 409)
    else:
        raise LonoraError("goal_run_ancestry_invalid", 409)
    if linked_goal and (
        goal is None
        or goal.goal_id != linked_goal
        or goal.step_id != origin_run.model_metadata.get("step_id")
    ):
        raise LonoraError("goal_step_required", 409)


class ExecutionService:
    def __init__(self, db: Database, brokers: BrokerManager):
        self.db, self.brokers = db, brokers

    async def execute(
        self,
        owner_id: str,
        request: TradeRequest,
        lease: Lease | None = None,
        *,
        goal: GoalExecution | None = None,
        authorization: Callable[[], Awaitable[None]] | None = None,
    ) -> TradeResult:
        async with self.db.sessions() as session:
            if lease:
                await require_goal_lineage(session, lease, goal)
            previous = await session.get(TradingJournalRow, request.operation_id)
            if previous:
                if previous.owner_id != owner_id or previous.request_hash != trade_fingerprint(
                    request
                ):
                    raise LonoraError("idempotency_conflict", 409)
                return receipt(previous)
            connection = await BrokerSessionRepository().get(session, owner_id, request.account_id)
            connection_version = connection.version
        if authorization:
            await authorization()
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
            if goal:
                await guard_goal_execution(session, owner_id, goal, request, lease)
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
                        **(
                            {
                                "goal_id": goal.goal_id,
                                "step_id": goal.step_id,
                                "decision_id": goal.decision_id,
                                "attempt": goal.attempt,
                            }
                            if goal
                            else {}
                        ),
                    },
                },
            ).model_dump(mode="json")

        send_authorized = False

        async def before_send() -> None:
            nonlocal send_authorized
            if send_authorized:
                raise LonoraError("operation_send_already_authorized", 409)
            if authorization:
                await authorization()
            goal_evidence = (
                await fresh_goal_evidence(
                    self.db,
                    self.brokers,
                    owner_id,
                    goal.goal_id,
                    goal.step_id,
                    lease.run_id if lease else None,
                )
                if goal
                else None
            )
            require_trading(await read_controls(self.db))
            async with self.db.sessions() as session, session.begin():
                connection = await BrokerSessionRepository().get(
                    session, owner_id, request.account_id
                )
                if not BrokerConnection.model_validate(connection.payload).enabled:
                    raise LonoraError("broker_disabled", 409)
                if connection.version != connection_version:
                    raise LonoraError("broker_connection_changed", 409)
                if lease:
                    await require_lease(session, lease, lock=True)
                    await require_goal_lineage(session, lease, goal)
                if goal:
                    await guard_goal_execution(
                        session, owner_id, goal, request, lease, goal_evidence
                    )
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
                    "trade_approval_unavailable",
                    "trade_approval_request_changed",
                    "tool_call_superseded",
                    "trading_disabled",
                    "emergency_stop",
                    "stale_lease",
                    "broker_disabled",
                    "broker_connection_changed",
                    "broker_numeric_precision_loss",
                    "order_not_found",
                    "goal_not_active",
                    "goal_autonomy_required",
                    "goal_condition_unmet",
                    "goal_condition_stale",
                    "goal_plan_changed",
                    "goal_step_unavailable",
                    "goal_watch_evidence_required",
                    "goal_volume_limit",
                    "goal_volume_limit_required",
                    "goal_action_limit",
                    "goal_delegated_trade_forbidden",
                    "goal_run_ancestry_invalid",
                    "goal_decision_mismatch",
                    "goal_run_mismatch",
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
