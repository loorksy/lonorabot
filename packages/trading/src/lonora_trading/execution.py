import asyncio
from collections.abc import Awaitable, Callable

from lonora_adapters.brokers.base import BrokerManager
from lonora_contracts.broker import BrokerConnection
from lonora_contracts.domain import utcnow
from lonora_contracts.execution_quality import ExecutionQuality
from lonora_contracts.runs import Lease
from lonora_contracts.tasks import TaskState
from lonora_contracts.trading import TradeRequest, TradeResult
from lonora_contracts.trading_goal import GoalExecution
from lonora_core.trading_control import require_trading
from lonora_core.user_error import LonoraError
from lonora_db.agent_binding import assert_market_binding, require_financial_agent
from lonora_db.broker_sessions import BrokerSessionRepository
from lonora_db.client import Database
from lonora_db.runs import require_lease
from lonora_db.schema import RunRow, TicketRow, TradeApprovalRow, TradingJournalRow
from lonora_db.trading_journal import persist_result, reserve_operation
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from .controls import read_controls
from .execution_quality import actual_execution, evaluate_execution, execution_policy
from .goals import guard_goal_execution
from .goals_market import fresh_goal_evidence
from .idempotency import trade_fingerprint
from .manual_activity import material_state
from .preflight import preflight


def receipt(row: TradingJournalRow) -> TradeResult:
    if row.result and row.status != "submitted":
        return TradeResult.model_validate(row.result)
    return TradeResult(
        operation_id=row.operation_id, status="ambiguous", code="operation_in_progress"
    )


async def require_goal_lineage(
    session: AsyncSession,
    lease: Lease,
    goal: GoalExecution | None,
    owner_id: str | None = None,
    request: TradeRequest | None = None,
) -> None:
    origin_run = await require_lease(session, lease)
    if owner_id is not None:
        await require_financial_agent(session, owner_id, origin_run.agent_id)
    if origin_run.model_metadata.get("authority") == "observe_only":
        raise LonoraError("observe_only_execution_forbidden", 403)
    await require_task_authority(session, origin_run)
    if owner_id is not None and request is not None:
        assert_market_binding(
            await require_financial_agent(session, owner_id, origin_run.agent_id),
            request.account_id,
            request.symbol,
        )
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
        if ancestor.model_metadata.get("authority") == "observe_only":
            raise LonoraError("observe_only_execution_forbidden", 403)
        await require_task_authority(session, ancestor)
        if owner_id is not None and request is not None:
            assert_market_binding(
                await require_financial_agent(session, owner_id, ancestor.agent_id),
                request.account_id,
                request.symbol,
            )
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


async def require_task_authority(session: AsyncSession, run: RunRow) -> None:
    if run.model_metadata.get("execution_mode") == "shadow":
        raise LonoraError("shadow_execution_forbidden", 403)
    task_id = run.model_metadata.get("task_id")
    if not task_id:
        return
    row = await session.get(TicketRow, task_id)
    if row is None or row.agent_id != run.agent_id or row.thread_id != run.thread_id:
        raise LonoraError("task_run_mismatch", 409)
    state = TaskState.model_validate(row.state.get("task"))
    if state.control_requested or state.status in {"paused", "cancelled", "completed", "failed"}:
        raise LonoraError("task_execution_stopped", 409)


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
                await require_goal_lineage(session, lease, goal, owner_id, request)
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
        planned_snapshot = await preflight(broker, request)
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
        quality: ExecutionQuality | None = None

        async def before_send() -> None:
            nonlocal send_authorized, quality
            if send_authorized:
                raise LonoraError("operation_send_already_authorized", 409)
            if authorization:
                await authorization()
            snapshot = await preflight(broker, request)
            policy = await execution_policy(self.db, owner_id, request.account_id)
            quality = evaluate_execution(
                request, snapshot, policy, planned_quote=planned_snapshot.quote
            )
            if quality.state != "executable":
                raise LonoraError(quality.reasons[0], 409)
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
                recovery = connection.state.get("broker_recovery")
                if recovery and recovery.get("status") != "connected":
                    raise LonoraError("broker_reconciliation_required", 409)
                if lease:
                    await require_lease(session, lease, lock=True)
                    await require_goal_lineage(session, lease, goal, owner_id, request)
                    approvals = await session.scalars(
                        select(TradeApprovalRow).where(
                            TradeApprovalRow.owner_id == owner_id,
                            TradeApprovalRow.run_id == lease.run_id,
                            TradeApprovalRow.status == "approved",
                        )
                    )
                    target = (
                        next(
                            (
                                position
                                for position in snapshot.positions
                                if position.id == request.position_id
                            ),
                            None,
                        )
                        if request.position_id
                        else next(
                            (order for order in snapshot.orders if order.id == request.order_id),
                            None,
                        )
                    )
                    key = request.account_id + (
                        ":position:" + request.position_id
                        if request.position_id
                        else ":order:" + request.order_id
                        if request.order_id
                        else ""
                    )
                    for approval in approvals:
                        if (
                            any(
                                item.get("operation_id") == request.operation_id
                                for item in approval.requests
                            )
                            and key in approval.broker_snapshot
                        ):
                            if approval.broker_snapshot[key] != (
                                material_state(target) if target else None
                            ):
                                raise LonoraError("trade_approval_broker_state_changed", 409)
                from .opportunities import require_entry_thesis

                await require_entry_thesis(session, owner_id, request)
                if goal:
                    await guard_goal_execution(
                        session, owner_id, goal, request, lease, goal_evidence
                    )
                row = await session.get(TradingJournalRow, request.operation_id)
                if row is None or row.status != "submitted":
                    raise LonoraError("operation_not_submitted", 409)
                row.result = {
                    **row.result,
                    "details": {
                        **row.result.get("details", {}),
                        "execution_quality": quality.model_dump(mode="json"),
                    },
                }
            send_authorized = True

        cancelled = False
        try:
            # A dedicated account advisory lock serializes different operation
            # IDs across workers, without blocking owner control/config changes.
            # Adapter snapshots use independent sessions; don't lock their rows.
            async with self.db.sessions() as account_lock, account_lock.begin():
                await account_lock.execute(
                    text("SELECT pg_advisory_xact_lock(hashtextextended(:key, 0))"),
                    {"key": f"execution:{owner_id}:{request.account_id}"},
                )
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
                # The adapter's before_send callback is the mutation boundary.
                # A failure before it authorizes submission is known not sent.
                status="ambiguous" if send_authorized else "failed",
                code=error.code,
            )
        except Exception:
            # Transport or SDK failures are not evidence of non-execution.
            result = TradeResult(
                operation_id=request.operation_id,
                status="ambiguous",
                code="broker_result_ambiguous",
            )
        result.details = {
            **result.details,
            "execution_quality": actual_execution(request, result, quality),
        }
        async with self.db.sessions() as session, session.begin():
            row = await session.get(TradingJournalRow, request.operation_id, with_for_update=True)
            if row is not None and row.status not in {"confirmed", "failed"}:
                row.result = {
                    **row.result,
                    "details": {
                        **row.result.get("details", {}),
                        "execution_quality": result.details["execution_quality"],
                    },
                }
            await persist_result(
                session, request.operation_id, result.status, result.model_dump(mode="json")
            )
            row = await session.get(TradingJournalRow, request.operation_id)
            assert row is not None
            result = receipt(row)
        if request.thesis_id:
            from .opportunities import sync_opportunity_execution

            async with self.db.sessions() as session, session.begin():
                journal = await session.get(TradingJournalRow, request.operation_id)
                assert journal is not None
                try:
                    await sync_opportunity_execution(session, journal)
                except LonoraError as error:
                    if error.code != "opportunity_not_found":
                        raise
        if cancelled:
            raise asyncio.CancelledError
        return result
