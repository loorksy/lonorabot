import asyncio
from collections.abc import Awaitable, Callable
from typing import Any

from lonora_adapters.brokers.base import BrokerManager
from lonora_contracts.broker import BrokerConnection
from lonora_contracts.domain import utcnow
from lonora_contracts.execution_quality import ExecutionQuality, ExecutionSnapshot
from lonora_contracts.risk_limits import RiskAssessment
from lonora_contracts.runs import Lease
from lonora_contracts.shadow import ExecutionMode
from lonora_contracts.tasks import TaskState
from lonora_contracts.trading import (
    IN_PROGRESS_STATUSES,
    TERMINAL_STATUSES,
    TradeRequest,
    TradeResult,
)
from lonora_contracts.trading_goal import GoalExecution
from lonora_core.trading_control import require_trading
from lonora_core.user_error import LonoraError
from lonora_db.agent_binding import assert_market_binding, require_financial_agent
from lonora_db.broker_sessions import BrokerSessionRepository
from lonora_db.client import Database
from lonora_db.runs import require_lease
from lonora_db.schema import RunRow, TicketRow, TradingJournalRow
from lonora_db.super_bot import authority_lock
from lonora_db.trade_approvals import require_approved_target_current
from lonora_db.trading_journal import persist_result, reserve_operation
from lonora_db.trading_restrictions import restriction_lock
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from .account_authority import management_target, require_account_execution
from .admission import may_reduce_risk, require_operation_scope, risk_reducing
from .agent_permission import require_operation_permission
from .controls import read_controls
from .execution_quality import actual_execution, evaluate_execution, execution_policy
from .goals import guard_goal_execution
from .goals_market import fresh_goal_evidence
from .idempotency import trade_fingerprint
from .journal import execution_evidence
from .manual_activity import material_state
from .operation_events import operation_event
from .preflight import preflight
from .reconciliation import send_lock_key
from .restrictions import AdmissionBlocked, require_unrestricted
from .risk_limits import assess_risk, risk_operations
from .verification import verify_effect

BROKER_OUTCOMES = frozenset({"confirmed", "failed", "ambiguous"})


def not_sent(request: TradeRequest, code: str) -> TradeResult:
    """A known outcome: the persisted send boundary was never crossed."""
    return TradeResult(
        operation_id=request.operation_id,
        status="failed",
        code=code,
        details={"send_state": "not_sent"},
    )


def receipt(row: TradingJournalRow) -> TradeResult:
    if row.result and row.status not in IN_PROGRESS_STATUSES:
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
    *,
    execution_mode: ExecutionMode = "live",
) -> None:
    origin_run = await require_lease(session, lease)
    if owner_id is not None:
        await require_financial_agent(
            session, owner_id, origin_run.agent_id, execution_mode=execution_mode
        )
    if (
        origin_run.trigger == "subagent"
        or origin_run.model_metadata.get("authority") == "observe_only"
    ):
        raise LonoraError("observe_only_execution_forbidden", 403)
    await require_task_authority(session, origin_run, execution_mode=execution_mode)
    if owner_id is not None and request is not None:
        assert_market_binding(
            await require_financial_agent(
                session, owner_id, origin_run.agent_id, execution_mode=execution_mode
            ),
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
        if (
            ancestor.trigger == "subagent"
            or ancestor.model_metadata.get("authority") == "observe_only"
        ):
            raise LonoraError("observe_only_execution_forbidden", 403)
        await require_task_authority(session, ancestor, execution_mode=execution_mode)
        if owner_id is not None and request is not None:
            assert_market_binding(
                await require_financial_agent(
                    session, owner_id, ancestor.agent_id, execution_mode=execution_mode
                ),
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


async def require_task_authority(
    session: AsyncSession, run: RunRow, *, execution_mode: ExecutionMode = "live"
) -> None:
    if run.model_metadata.get("execution_mode", "live") != execution_mode:
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
        account_authority_id: str | None = None,
        expected_target: dict[str, Any] | None = None,
    ) -> TradeResult:
        async with self.db.sessions() as session:
            if lease:
                await require_goal_lineage(session, lease, goal, owner_id, request)
            previous = await session.get(TradingJournalRow, request.operation_id)
            if previous:
                if (
                    previous.execution_mode != "live"
                    or previous.owner_id != owner_id
                    or previous.request_hash != trade_fingerprint(request)
                ):
                    raise LonoraError("idempotency_conflict", 409)
                return receipt(previous)
            if lease:
                origin = await require_lease(session, lease)
                await require_operation_permission(
                    session, owner_id, origin, request, account_authority_id
                )
            connection = await BrokerSessionRepository().get(session, owner_id, request.account_id)
            connection_version = connection.version
        if authorization:
            await authorization()
        controls = await read_controls(self.db)
        if not may_reduce_risk(request):
            require_trading(controls)
        broker = await self.brokers.get(owner_id, request.account_id)
        planned_snapshot = await preflight(broker, request)
        # Global OFF/Emergency Stop and unresolved operations stop new risk, not exits.
        # The final decision is repeated against a fresh target inside before_send.
        planned_reducing = risk_reducing(request, management_target(planned_snapshot, request))
        require_trading(controls, risk_reducing=planned_reducing)
        async with self.db.sessions() as session, session.begin():
            if lease:
                origin = await require_lease(session, lease)
                await authority_lock(session, origin.agent_id)
                await require_operation_permission(
                    session, owner_id, origin, request, account_authority_id
                )
            connection = await BrokerSessionRepository().get(
                session, owner_id, request.account_id, lock=True
            )
            if connection.version != connection_version:
                raise LonoraError("broker_connection_changed", 409)
            configuration = BrokerConnection.model_validate(connection.payload)
            if not configuration.enabled:
                raise LonoraError("broker_disabled", 409)
            leased_run = await require_lease(session, lease, lock=True) if lease else None
            if account_authority_id:
                if leased_run is None:
                    raise LonoraError("account_authority_run_required", 403)
                await require_account_execution(
                    session,
                    owner_id,
                    leased_run,
                    request,
                    account_authority_id,
                    planned_snapshot,
                    expected_target,
                )
            if goal:
                await guard_goal_execution(session, owner_id, goal, request, lease)
            await require_operation_scope(
                session,
                owner_id,
                request,
                reducing=planned_reducing,
                recovery=connection.state.get("broker_recovery"),
                send_locked=False,
            )
            # Fail fast on an owner restriction; the decisive check repeats at the send
            # boundary, so a restriction created while this request waits still applies.
            await require_unrestricted(
                session,
                owner_id,
                request,
                agent_id=leased_run.agent_id if leased_run else None,
                reducing=planned_reducing,
            )
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
            # Reserved is durable identity only. The send boundary below atomically
            # moves it to submitted; recovery proves an abandoned reservation unsent.
            journal.status = "reserved"
            journal.submitted_at = utcnow()
            journal.result = TradeResult(
                operation_id=request.operation_id,
                status="reserved",
                code="operation_in_progress",
                details={
                    "lease": lease.model_dump() if lease else None,
                    "execution_evidence": {
                        "planned": execution_evidence(
                            planned_snapshot, request, mode="live", phase="planned", goal=goal
                        )
                    },
                    "execution": {
                        "run_id": leased_run.id if leased_run else None,
                        "agent_id": leased_run.agent_id if leased_run else None,
                        "provider": configuration.provider,
                        "broker_account_id": configuration.account_id,
                        **(
                            {"account_authority_id": account_authority_id}
                            if account_authority_id
                            else {}
                        ),
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

        # Restrictions govern agent-originated operations; None is the owner's manual path.
        restricted_agent = leased_run.agent_id if leased_run else None
        send_authorized = False
        quality: ExecutionQuality | None = None
        before_snapshot: ExecutionSnapshot | None = None

        async def record_block(
            evidence: dict[str, Any], *, before_send: dict[str, Any] | None = None
        ) -> None:
            # A blocked decision is a historical fact: persist why before returning.
            async with self.db.sessions() as session, session.begin():
                if lease:
                    await require_lease(session, lease, lock=True)
                row = await session.get(
                    TradingJournalRow, request.operation_id, with_for_update=True
                )
                if row is not None and row.status == "reserved":
                    details = row.result.get("details", {})
                    row.result = {
                        **row.result,
                        "details": {
                            **details,
                            **evidence,
                            "execution_evidence": {
                                **details.get("execution_evidence", {}),
                                **({"before_send": before_send} if before_send else {}),
                            },
                        },
                    }

        async def before_send() -> None:
            nonlocal send_authorized, quality, before_snapshot
            if send_authorized:
                raise LonoraError("operation_send_already_authorized", 409)
            if authorization:
                await authorization()
            snapshot = await preflight(broker, request)
            before_snapshot = snapshot
            reducing = risk_reducing(request, management_target(snapshot, request))
            policy = await execution_policy(self.db, owner_id, request.account_id)
            quality = evaluate_execution(
                request, snapshot, policy, planned_quote=planned_snapshot.quote
            )
            observed = execution_evidence(
                snapshot, request, mode="live", phase="before_send", goal=goal, policy=policy
            )
            if quality.state != "executable":
                # Persist the actual failed gate; no broker mutation is authorized.
                await record_block(
                    {"execution_quality": quality.model_dump(mode="json")},
                    before_send=observed,
                )
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
            require_trading(await read_controls(self.db), risk_reducing=reducing)
            # Owner monetary limits, from fresh broker economics under this account's send
            # lock. Risk-reducing requests are never blocked by a limit.
            risk = None
            if not reducing and policy.risk.configured:
                async with self.db.sessions() as session:
                    operations = await risk_operations(
                        session, owner_id, request.account_id, exclude=request.operation_id
                    )
                risk = await assess_risk(
                    broker,
                    request,
                    snapshot,
                    policy.risk,
                    reducing=reducing,
                    operations=operations,
                )
                if risk.state == "blocked":
                    await record_block(
                        {
                            "risk_assessment": risk.model_dump(mode="json"),
                            "admission_block": {
                                "code": risk.reasons[0],
                                "reasons": risk.reasons,
                            },
                        },
                        before_send=observed,
                    )
                    raise LonoraError(risk.reasons[0], 409)
            try:
                await final_admission(snapshot, reducing, observed, goal_evidence, risk, quality)
            except AdmissionBlocked as blocked:
                await record_block({"admission_block": blocked.evidence}, before_send=observed)
                raise
            send_authorized = True

        async def final_admission(
            snapshot: ExecutionSnapshot,
            reducing: bool,
            observed: dict[str, Any],
            goal_evidence: dict[str, Any] | None,
            risk: RiskAssessment | None,
            quality: ExecutionQuality,
        ) -> None:
            """The decisive checks and the reserved -> submitted transition, in one commit."""
            async with self.db.sessions() as session, session.begin():
                if lease:
                    # Match owner downgrade/signature lock ordering: authority
                    # first, then Run/approval/Goal rows. No network call runs
                    # while the final permission decision holds this lock.
                    origin = await require_lease(session, lease)
                    await authority_lock(session, origin.agent_id)
                    await require_operation_permission(
                        session, owner_id, origin, request, account_authority_id
                    )
                connection = await BrokerSessionRepository().get(
                    session, owner_id, request.account_id
                )
                if not BrokerConnection.model_validate(connection.payload).enabled:
                    raise LonoraError("broker_disabled", 409)
                if connection.version != connection_version:
                    raise LonoraError("broker_connection_changed", 409)
                # Under the account send lock every other reservation is provably
                # unsent and every other submitted operation has lost its sender:
                # submitted and ambiguous operations on this market block new risk.
                await require_operation_scope(
                    session,
                    owner_id,
                    request,
                    reducing=reducing,
                    recovery=connection.state.get("broker_recovery"),
                    send_locked=True,
                )
                if lease:
                    await require_lease(session, lease, lock=True)
                    await require_goal_lineage(session, lease, goal, owner_id, request)
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
                    await require_approved_target_current(
                        session,
                        owner_id,
                        lease.run_id,
                        request,
                        material_state(target) if target else None,
                    )
                    if account_authority_id:
                        leased_run = await require_lease(session, lease)
                        await require_account_execution(
                            session,
                            owner_id,
                            leased_run,
                            request,
                            account_authority_id,
                            snapshot,
                            expected_target,
                        )
                # Owner restrictions: held shared against concurrent creation, so this
                # operation either commits its send authorization before a restriction
                # exists or sees it here. Queued work is decided now, not when queued.
                await restriction_lock(session, owner_id, request.account_id, shared=True)
                await require_unrestricted(
                    session, owner_id, request, agent_id=restricted_agent, reducing=reducing
                )
                from .opportunities import require_entry_thesis

                await require_entry_thesis(session, owner_id, request)
                if goal:
                    await guard_goal_execution(
                        session, owner_id, goal, request, lease, goal_evidence
                    )
                row = await session.get(
                    TradingJournalRow, request.operation_id, with_for_update=True
                )
                if row is None or row.status != "reserved":
                    # Recovery already proved this abandoned reservation unsent.
                    raise LonoraError("operation_reservation_released", 409)
                row.status = "submitted"
                row.submitted_at = row.updated_at = utcnow()
                row.result = {
                    **row.result,
                    "status": "submitted",
                    "details": {
                        **row.result.get("details", {}),
                        # Durable conservative budget consumption: the final
                        # checks allowed a broker mutation. A rejected broker
                        # attempt or crash after this point cannot restore a
                        # standing grant's lifetime action budget.
                        "execution": {
                            **row.result.get("details", {}).get("execution", {}),
                            "send_authorized": True,
                            "risk_reducing": reducing,
                        },
                        "execution_quality": quality.model_dump(mode="json"),
                        "execution_evidence": {
                            **row.result.get("details", {}).get("execution_evidence", {}),
                            "before_send": observed,
                        },
                        **({"risk_assessment": risk.model_dump(mode="json")} if risk else {}),
                    },
                }
                await operation_event(session, row)

        def outcome_of(error: BaseException) -> TradeResult:
            # The adapter's before_send callback is the mutation boundary: it persists send
            # authorization before the adapter may send. Any failure or interruption before
            # it returned is known not sent; after it, transport, SDK and cancellation
            # failures are not evidence of non-execution and stay uncertain.
            if isinstance(error, LonoraError):
                return (
                    TradeResult(
                        operation_id=request.operation_id, status="ambiguous", code=error.code
                    )
                    if send_authorized
                    else not_sent(request, error.code)
                )
            if send_authorized:
                return TradeResult(
                    operation_id=request.operation_id,
                    status="ambiguous",
                    code="broker_result_ambiguous",
                )
            return not_sent(
                request,
                "operation_interrupted_before_send"
                if isinstance(error, asyncio.CancelledError)
                else "broker_unavailable_before_send",
            )

        async def conclude(outcome: TradeResult) -> TradeResult:
            outcome.details = {
                **outcome.details,
                "execution_quality": actual_execution(request, outcome, quality),
            }
            async with self.db.sessions() as session, session.begin():
                row = await session.get(
                    TradingJournalRow, request.operation_id, with_for_update=True
                )
                if row is not None and row.status not in TERMINAL_STATUSES:
                    row.result = {
                        **row.result,
                        "details": {
                            **row.result.get("details", {}),
                            "execution_quality": outcome.details["execution_quality"],
                        },
                    }
                changed = await persist_result(
                    session, request.operation_id, outcome.status, outcome.model_dump(mode="json")
                )
                row = await session.get(TradingJournalRow, request.operation_id)
                assert row is not None
                if changed:
                    await operation_event(session, row)
                return receipt(row)

        cancelled = False
        result: TradeResult | None = None
        final: TradeResult | None = None
        try:
            # A dedicated account advisory lock serializes different operation
            # IDs across workers, without blocking owner control/config changes.
            # Adapter snapshots use independent sessions; don't lock their rows.
            async with self.db.sessions() as account_lock, account_lock.begin():
                await account_lock.execute(
                    text("SELECT pg_advisory_xact_lock(hashtextextended(:key, 0))"),
                    {"key": send_lock_key(owner_id, request.account_id)},
                )
                try:
                    result = await broker.execute(request, before_send)
                    if result.operation_id == request.operation_id and send_authorized:
                        if result.status == "confirmed":
                            # Persist the real acknowledgment before another external
                            # read. A crash during verification must not erase it or
                            # reopen permission to send the mutation again.
                            result.details = {
                                **result.details,
                                "execution_quality": actual_execution(request, result, quality),
                            }
                            async with self.db.sessions() as saved, saved.begin():
                                if await persist_result(
                                    saved,
                                    request.operation_id,
                                    result.status,
                                    result.model_dump(mode="json"),
                                ):
                                    acknowledged = await saved.get(
                                        TradingJournalRow, request.operation_id
                                    )
                                    assert acknowledged is not None
                                    await operation_event(saved, acknowledged)
                            verification = await verify_effect(
                                broker, request, result, before_snapshot
                            )
                            async with self.db.sessions() as saved, saved.begin():
                                journal = await saved.get(
                                    TradingJournalRow, request.operation_id, with_for_update=True
                                )
                                if (
                                    journal
                                    and journal.status == "confirmed"
                                    and journal.result.get("broker_id") == result.broker_id
                                ):
                                    journal.result = {
                                        **journal.result,
                                        "details": {
                                            **journal.result.get("details", {}),
                                            "verification": verification,
                                        },
                                    }
                                    journal.updated_at = utcnow()
                                    # A pending verification is rechecked by the
                                    # reconciliation loop (recheck_verifications) until
                                    # verified or unverified; the owner sees it waiting.
                                    await operation_event(saved, journal)
                            result.details = {
                                **result.details,
                                "verification": verification,
                            }
                    if (
                        result.operation_id != request.operation_id
                        or not send_authorized
                        # An adapter reports a broker outcome; lifecycle states are the
                        # journal's.
                        or result.status not in BROKER_OUTCOMES
                    ):
                        result = TradeResult(
                            operation_id=request.operation_id,
                            status="ambiguous",
                            code="broker_result_mismatch",
                        )
                except asyncio.CancelledError as error:
                    cancelled = True
                    result = outcome_of(error)
                except Exception as error:
                    result = outcome_of(error)
                # Persist the final outcome while this account's send lock is still held.
                # Under the lock, any other operation of this account still "submitted"
                # has provably lost its sender: admission and recovery rely on that, and
                # a sibling waiting for the lock sees this outcome, not a stale row.
                final = await conclude(result)
        except asyncio.CancelledError as error:
            # Interrupted while waiting for the lock, or while concluding under it.
            cancelled = True
            result = outcome_of(error) if result is None else result
        except Exception as error:
            result = outcome_of(error) if result is None else result
        if final is None:
            assert result is not None
            final = await conclude(result)
        result = final
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
