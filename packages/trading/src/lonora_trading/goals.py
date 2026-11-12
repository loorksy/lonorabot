from __future__ import annotations

import copy
from collections.abc import Awaitable, Callable
from typing import TYPE_CHECKING, Any

from lonora_adapters.brokers.base import BrokerManager
from lonora_contracts.account import Order, Position
from lonora_contracts.domain import utcnow
from lonora_contracts.runs import Lease, RunRequest
from lonora_contracts.trading import (
    IN_PROGRESS_STATUSES,
    TERMINAL_STATUSES,
    TradeRequest,
    TradeResult,
)
from lonora_contracts.trading_goal import GoalExecution
from lonora_core.user_error import LonoraError
from lonora_db.agent_permissions import effective_permission
from lonora_db.client import Database
from lonora_db.goal_scope import require_goal_agent
from lonora_db.runs import create_run, locked_run_thread, require_lease, run_data
from lonora_db.schema import (
    AgentRow,
    GoalDecisionRow,
    RunRow,
    TradeApprovalRow,
    TradingGoalRow,
    TradingJournalRow,
)
from lonora_db.trading_goals import owned_goal, planned_step, update_goal_state
from lonora_session.idempotency import stable_id
from sqlalchemy import exists, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from .account_authority import authority_snapshot, covering_authority, provisional_voice
from .goals_market import fresh_goal_evidence
from .goals_targets import resolve_trade
from .idempotency import trade_fingerprint
from .manual_activity import material_state

if TYPE_CHECKING:
    from .execution import ExecutionService


def advance_state(goal: TradingGoalRow, state: dict[str, Any]) -> None:
    current = state.get("current_step")
    if current and state["steps"].get(current, {}).get("status") == "completed":
        state.pop("code", None)
    next_step = next(
        (
            step["id"]
            for step in goal.payload["steps"]
            if state["steps"][step["id"]]["status"] != "completed"
        ),
        None,
    )
    if next_step:
        state["current_step"] = next_step
    elif state["status"] not in {"paused", "cancelled"}:
        state["status"] = "completed"


def matches_declared_trade(goal: TradingGoalRow, step_id: str, request: TradeRequest) -> bool:
    template = planned_step(goal, step_id).trade
    if template is None:
        return False
    planned = template.model_dump(mode="json", exclude={"target_step_id", "operation_id"})
    actual = request.model_dump(mode="json", exclude={"operation_id"})
    if template.target_step_id:
        field = "position_id" if "position" in template.action else "order_id"
        planned.pop(field, None)
        actual.pop(field, None)
    return planned == actual


async def goal_requires_approval(session: AsyncSession, goal: TradingGoalRow, run: RunRow) -> bool:
    """A Goal is a plan under the Agent's current trading level, never a grant.

    Live steps follow the level like any trade: No trading refuses, Ask me needs the
    owner's exact approval, On its own sends inside a covering signed grant (a step
    outside it asks instead, see ``execute_goal_step``).
    """
    await require_goal_agent(session, goal, run)
    level = await effective_permission(session, goal.owner_id, run.agent_id)
    if level == "analysis":
        raise LonoraError("agent_analysis_only", 403)
    return level != "autonomous" or await provisional_voice(session, run)


async def require_supervised_approval(
    session: AsyncSession, goal: TradingGoalRow, run: RunRow, request: TradeRequest
) -> None:
    if not await goal_requires_approval(session, goal, run):
        return
    approvals = await session.scalars(
        select(TradeApprovalRow).where(
            TradeApprovalRow.owner_id == goal.owner_id,
            TradeApprovalRow.agent_id == goal.agent_id,
            TradeApprovalRow.run_id == run.id,
            TradeApprovalRow.status == "approved",
        )
    )
    if not any(
        len(row.requests) == 1
        and TradeRequest.model_validate(row.requests[0]).operation_id == request.operation_id
        and trade_fingerprint(TradeRequest.model_validate(row.requests[0]))
        == trade_fingerprint(request)
        for row in approvals
    ):
        raise LonoraError("trade_approval_required", 409)


async def guard_goal_execution(
    session: AsyncSession,
    owner_id: str,
    context: GoalExecution,
    request: TradeRequest,
    lease: Lease | None,
    evidence: dict[str, Any] | None = None,
) -> None:
    if lease is None:
        raise LonoraError("goal_lease_required", 409)
    run = await require_lease(session, lease)
    goal = await owned_goal(session, owner_id, context.goal_id, True)
    if goal.state.get("status") != "active":
        raise LonoraError("goal_not_active", 409)
    if goal.agent_id != run.agent_id or goal.thread_id != run.thread_id:
        raise LonoraError("goal_run_mismatch", 409)
    if context.plan_version != goal.state.get("plan_version", 1):
        raise LonoraError("goal_plan_changed", 409)
    await require_supervised_approval(session, goal, run, request)
    step = planned_step(goal, context.step_id)
    if not matches_declared_trade(goal, step.id, request):
        raise LonoraError("goal_plan_changed", 409)
    decision = await session.get(GoalDecisionRow, context.decision_id, with_for_update=True)
    if (
        decision is None
        or decision.goal_id != goal.id
        or decision.step_id != step.id
        or decision.attempt != context.attempt
    ):
        raise LonoraError("goal_decision_mismatch", 409)
    if decision.operation_id != request.operation_id or trade_fingerprint(
        TradeRequest.model_validate(decision.request)
    ) != trade_fingerprint(request):
        raise LonoraError("goal_decision_mismatch", 409)
    if goal.state["steps"][step.id]["status"] != "executing":
        raise LonoraError("goal_step_unavailable", 409)
    if evidence is not None:
        decision.evidence = {**decision.evidence, "before_send": evidence}
        decision.updated_at = utcnow()


async def sync_goal_decision(db: Database, operation_id: str, *, settle: bool = False) -> bool:
    async with db.sessions() as session:
        decision = await session.scalar(
            select(GoalDecisionRow).where(GoalDecisionRow.operation_id == operation_id)
        )
        if decision is None:
            return False
        goal_id, decision_id = decision.goal_id, decision.id
    async with db.sessions() as session, session.begin():
        goal = await session.get(TradingGoalRow, goal_id, with_for_update=True)
        decision = await session.get(GoalDecisionRow, decision_id, with_for_update=True)
        journal = await session.get(TradingJournalRow, operation_id)
        if goal is None or decision is None or journal is None:
            return False
        if journal.status in IN_PROGRESS_STATUSES and not settle and decision.run_id:
            run = await session.get(RunRow, decision.run_id)
            if (
                run is not None
                and run.status in {"leased", "running"}
                and run.lease_expires_at
                and run.lease_expires_at > utcnow()
            ):
                return False
        result = journal.result or TradeResult(
            operation_id=operation_id, status="ambiguous", code="operation_in_progress"
        ).model_dump(mode="json")
        # A resolution (owner attestation or a vanished target) settles uncertainty but is
        # not broker confirmation: the Goal stays blocked for an explicit owner decision,
        # never an automatic retry.
        status = journal.status if journal.status in TERMINAL_STATUSES else "ambiguous"
        if decision.status == status and decision.result == result:
            return False
        decision.status, decision.result, decision.updated_at = status, result, utcnow()
        state = copy.deepcopy(goal.state)
        step_state = state["steps"][decision.step_id]
        step_state.update(
            status="completed" if status == "confirmed" else "blocked",
            operation_id=operation_id,
            result=result,
        )
        if status != "confirmed" and state["status"] not in {"paused", "cancelled"}:
            state["status"] = "blocked"
            state["code"] = (
                "goal_reconciliation_required"
                if status == "ambiguous"
                else "goal_trade_resolved_without_confirmation"
                if status == "resolved"
                else "goal_trade_failed"
            )
        elif status == "confirmed" and state["status"] == "blocked":
            state["status"] = "active"
            state.pop("code", None)
        advance_state(goal, state)
        update_goal_state(session, goal, state)
        return True


async def recover_goals(db: Database) -> int:
    from lonora_db.item_failures import ItemGuard, blocked

    async with db.sessions() as session:
        pending = list(
            await session.execute(
                select(GoalDecisionRow.operation_id, GoalDecisionRow.owner_id)
                .where(
                    GoalDecisionRow.status.in_(["executing", "submitted", "ambiguous"]),
                    ~blocked("goal_decision", GoalDecisionRow.operation_id),
                )
                .limit(100)
            )
        )
    # A goal decision mirrors a financial operation: it backs off but is never quarantined.
    decisions = ItemGuard(db, "goal_decision", quarantine_after=None)
    await decisions.prepare(operation_id for operation_id, _ in pending)
    recovered = 0
    for operation_id, owner_id in pending:

        async def sync(operation_id: str = operation_id) -> bool:
            return await recover_decision(db, operation_id)

        recovered += int(bool(await decisions.run(operation_id, owner_id, sync)))
    async with db.sessions() as session:
        waiting = list(
            await session.scalars(
                select(TradingGoalRow)
                .where(
                    TradingGoalRow.state["status"].as_string() == "waiting",
                    TradingGoalRow.state["code"].as_string() == "goal_target_pending",
                    # A goal without its conversation or agent cannot be reviewed again.
                    TradingGoalRow.thread_id.is_not(None),
                    exists(select(AgentRow.id).where(AgentRow.id == TradingGoalRow.agent_id)),
                    ~blocked("goal_target", TradingGoalRow.id),
                )
                .limit(100)
            )
        )
    targets = ItemGuard(db, "goal_target", quarantine_after=None)
    await targets.prepare(goal.id for goal in waiting)
    for goal in waiting:

        async def review(goal: TradingGoalRow = goal) -> bool:
            return await restore_target_review(db, goal)

        recovered += int(bool(await targets.run(goal.id, goal.owner_id, review)))
    return recovered + await settle_orphaned_goals(db)


async def settle_orphaned_goals(db: Database) -> int:
    """Cancel, once, goals whose conversation or agent is gone (deleted before this rule).

    A delete settles its goals itself; this only repairs goals orphaned earlier, so they
    stop claiming to wait and are never retried through the failure ledger.
    """
    from lonora_db.trading_goals import TERMINAL_GOAL_STATUSES, settle_orphaned_goal

    status = TradingGoalRow.state["status"].as_string()
    async with db.sessions() as session, session.begin():
        orphans = list(
            await session.scalars(
                select(TradingGoalRow)
                .where(
                    or_(status.is_(None), status.not_in(sorted(TERMINAL_GOAL_STATUSES))),
                    or_(
                        TradingGoalRow.thread_id.is_(None),
                        ~exists(select(AgentRow.id).where(AgentRow.id == TradingGoalRow.agent_id)),
                    ),
                )
                .order_by(TradingGoalRow.id)
                .limit(100)
                .with_for_update(skip_locked=True)
            )
        )
        return sum(int(settle_orphaned_goal(session, goal)) for goal in orphans)


async def recover_decision(db: Database, operation_id: str) -> bool:
    async with db.sessions() as session:
        decision = await session.scalar(
            select(GoalDecisionRow).where(GoalDecisionRow.operation_id == operation_id)
        )
        journal = await session.get(TradingJournalRow, operation_id)
        if decision is None:
            return False
        goal_id, decision_id = decision.goal_id, decision.id
        run = await session.get(RunRow, decision.run_id) if decision.run_id else None
        live = bool(
            run is not None
            and run.status in {"leased", "running"}
            and run.lease_expires_at
            and run.lease_expires_at > utcnow()
        )
    if journal is None and decision.status == "executing" and not live:
        async with db.sessions() as session, session.begin():
            goal = await session.get(TradingGoalRow, goal_id, with_for_update=True)
            current = await session.get(GoalDecisionRow, decision_id, with_for_update=True)
            if (
                goal is not None
                and current is not None
                and await session.get(TradingJournalRow, operation_id) is None
            ):
                current.status = "planned"
                state = copy.deepcopy(goal.state)
                state["steps"][current.step_id]["status"] = "pending"
                update_goal_state(session, goal, state)
                return True
        return False
    return await sync_goal_decision(db, operation_id)


async def restore_target_review(db: Database, goal: TradingGoalRow) -> bool:
    from lonora_db.schema import RoutineRow

    step_id = str(goal.state["current_step"])
    identifier = goal.state["steps"][step_id].get("target_review_id")
    async with db.sessions() as session:
        routine = await session.get(RoutineRow, identifier) if identifier else None
    if routine is not None:
        return False
    await wait_for_goal_target(db, goal.owner_id, goal.id, step_id)
    return True


async def wake_goal(
    db: Database, owner_id: str, goal_id: str, step_id: str | None = None
) -> dict[str, Any]:
    await recover_goals(db)
    async with db.sessions() as session:
        original = await owned_goal(session, owner_id, goal_id)
        agent_id, thread_id = original.agent_id or "", original.thread_id or ""
    async with db.sessions() as session, session.begin():
        run = await create_run(
            session,
            owner_id,
            RunRequest(
                agent_id=agent_id,
                thread_id=thread_id,
                trigger="goal",
                prompt="Continue this saved trading goal. Read its current plan, evidence, and actual broker state. Use goal tools to persist progress; no unlinked trades.",
                metadata={"goal_id": goal_id, "step_id": step_id},
            ),
        )
        return run_data(run)


async def execute_goal_step(
    db: Database,
    brokers: BrokerManager,
    executor: ExecutionService,
    owner_id: str,
    goal_id: str,
    step_id: str | None,
    lease: Lease,
    note: str = "",
    evidence_refs: list[str] | None = None,
    approval_gate: Callable[[TradeRequest], Awaitable[dict[str, Any] | None]] | None = None,
) -> dict[str, Any]:
    # Observe authoritative broker data anew on every wake, never the triggering quote alone.
    async with db.sessions() as session:
        goal = await owned_goal(session, owner_id, goal_id)
        origin = await require_lease(session, lease)
        if origin.agent_id != goal.agent_id or origin.thread_id != goal.thread_id:
            raise LonoraError("goal_run_mismatch", 409)
        step = planned_step(goal, step_id)
        existing_id = stable_id(
            goal.id, f"decision:{step.id}:attempt:{goal.state['steps'][step.id].get('attempt', 1)}"
        )
        previous = await session.get(GoalDecisionRow, existing_id)
        if previous is not None and previous.result:
            return {
                "decision_id": previous.id,
                "operation_id": previous.operation_id,
                "result": previous.result,
                "deduplicated": True,
            }
        if step.trade is None:
            raise LonoraError("goal_trade_step_required", 409)
        level_asks = await goal_requires_approval(session, goal, origin)
    expected_plan_version = int(goal.state.get("plan_version", 1))
    try:
        evidence = await fresh_goal_evidence(db, brokers, owner_id, goal_id, step.id, lease.run_id)
    except LonoraError as error:
        if error.code == "goal_target_not_observed":
            return await wait_for_goal_target(db, owner_id, goal_id, step.id, lease)
        raise
    expected_attempt = int(goal.state["steps"][step.id].get("attempt", 1))
    operation_id = stable_id(goal.id, f"step:{step.id}:attempt:{expected_attempt}")
    try:
        request = await resolve_trade(db, brokers, owner_id, goal_id, step.trade, operation_id)
    except LonoraError as error:
        if error.code == "goal_target_not_observed":
            return await wait_for_goal_target(db, owner_id, goal_id, step.id, lease)
        raise
    account_authority_id: str | None = None
    expected_target: dict[str, Any] | None = None
    async with db.sessions() as session:
        current = await require_lease(session, lease)
        autonomous = await effective_permission(session, owner_id, current.agent_id) == "autonomous"
    if autonomous and not level_asks:
        # Every term of the grant decides, the owner's own ticket included: a step the
        # grant does not fully cover asks the owner instead of failing at the executor.
        facts = await authority_snapshot(
            await brokers.get(owner_id, request.account_id), request.account_id
        )
        async with db.sessions() as session:
            current = await require_lease(session, lease)
            account_authority_id = await covering_authority(
                session, owner_id, current, request, facts
            )
    # The ladder is monotonic: under "On its own" a step no active grant covers asks the
    # owner with an approval card, exactly like "Ask me", instead of being refused.
    needs_approval = level_asks or account_authority_id is None
    if needs_approval:
        if approval_gate is None:
            raise LonoraError("trade_approval_required", 409)
        pending_approval = await approval_gate(request)
        if pending_approval is not None:
            return pending_approval
    if request.position_id:
        target = next(
            (p for p in evidence.get("positions", []) if p.get("id") == request.position_id),
            None,
        )
        expected_target = material_state(Position.model_validate(target)) if target else None
    elif request.order_id:
        target = next(
            (p for p in evidence.get("orders", []) if p.get("id") == request.order_id), None
        )
        expected_target = material_state(Order.model_validate(target)) if target else None
    async with db.sessions() as session, session.begin():
        run, _ = await locked_run_thread(session, lease)
        goal = await owned_goal(session, owner_id, goal_id, True)
        step = planned_step(goal, step.id)
        if step.trade is None:
            raise LonoraError("goal_trade_step_required", 409)
        if goal.agent_id != run.agent_id or goal.thread_id != run.thread_id:
            raise LonoraError("goal_run_mismatch", 409)
        if goal.state.get("current_step") != step.id:
            raise LonoraError("goal_step_order", 409)
        attempt = int(goal.state["steps"][step.id].get("attempt", 1))
        operation_id = stable_id(goal.id, f"step:{step.id}:attempt:{attempt}")
        decision_id = stable_id(goal.id, f"decision:{step.id}:attempt:{attempt}")
        existing = await session.get(GoalDecisionRow, decision_id)
        if existing and existing.result:
            return {
                "decision_id": existing.id,
                "operation_id": operation_id,
                "result": existing.result,
                "deduplicated": True,
            }
        if goal.state.get("status") != "active":
            raise LonoraError("goal_not_active", 409)
        if await goal_requires_approval(session, goal, run) != level_asks:
            raise LonoraError("agent_permission_changed", 409)
        await require_supervised_approval(session, goal, run, request)
        if (
            attempt != expected_attempt
            or int(goal.state.get("plan_version", 1)) != expected_plan_version
            or not matches_declared_trade(goal, step.id, request)
        ):
            raise LonoraError("goal_plan_changed", 409)
        run.model_metadata = {
            **run.model_metadata,
            "goal_id": goal.id,
            "step_id": step.id,
            "plan_version": expected_plan_version,
        }
        decision = existing or GoalDecisionRow(
            id=decision_id,
            goal_id=goal.id,
            owner_id=owner_id,
            step_id=step.id,
            attempt=attempt,
            run_id=run.id,
            operation_id=operation_id,
            request=request.model_dump(mode="json"),
            evidence={
                "rationale": note,
                "evidence_refs": evidence_refs or [],
                "observation": evidence,
                "plan_version": expected_plan_version,
            },
            status="executing",
        )
        if existing and trade_fingerprint(
            TradeRequest.model_validate(existing.request)
        ) != trade_fingerprint(request):
            raise LonoraError("goal_decision_mismatch", 409)
        session.add(decision)
        state = copy.deepcopy(goal.state)
        state.pop("code", None)
        state["steps"][step.id].update(
            status="executing", operation_id=operation_id, decision_id=decision_id
        )
        update_goal_state(session, goal, state)
        context = GoalExecution(
            goal_id=goal.id,
            step_id=step.id,
            decision_id=decision_id,
            attempt=attempt,
            plan_version=int(state.get("plan_version", 1)),
        )

    async def require_approved_goal() -> None:
        if needs_approval:
            if approval_gate is None or await approval_gate(request) is not None:
                raise LonoraError("trade_approval_unavailable", 409)

    try:
        result = await executor.execute(
            owner_id,
            request,
            lease,
            goal=context,
            authorization=require_approved_goal if needs_approval else None,
            account_authority_id=account_authority_id,
            expected_target=expected_target,
        )
    except LonoraError as error:
        async with db.sessions() as session, session.begin():
            await require_lease(session, lease, lock=True)
            goal = await owned_goal(session, owner_id, goal_id, True)
            decision = await session.get(GoalDecisionRow, decision_id, with_for_update=True)
            journal = await session.get(TradingJournalRow, operation_id)
            if decision is not None and journal is None:
                decision.status = "failed"
                decision.result = {
                    "operation_id": operation_id,
                    "status": "failed",
                    "code": error.code,
                }
                state = copy.deepcopy(goal.state)
                state["steps"][step.id].update(status="blocked", code=error.code)
                if state["status"] not in {"paused", "cancelled"}:
                    state["status"] = "blocked"
                update_goal_state(session, goal, state)
        await sync_goal_decision(db, operation_id, settle=True)
        raise
    finally:
        await sync_goal_decision(db, operation_id, settle=True)
    return {
        "decision_id": decision_id,
        "operation_id": operation_id,
        "result": result.model_dump(mode="json"),
    }


async def wait_for_goal_target(
    db: Database, owner_id: str, goal_id: str, step_id: str, lease: Lease | None = None
) -> dict[str, Any]:
    from lonora_contracts.routines import RoutineCreate
    from lonora_db.routines import create_routine, routine_data
    from lonora_db.transactions import owned_thread

    async with db.sessions() as session:
        original = await owned_goal(session, owner_id, goal_id)
        thread_id = original.thread_id or ""
    async with db.sessions() as session, session.begin():
        await owned_thread(session, owner_id, thread_id, lock=True)
        if lease:
            await require_lease(session, lease, lock=True)
        goal = await owned_goal(session, owner_id, goal_id, True)
        if (
            goal.state.get("status") not in {"active", "waiting"}
            or goal.state.get("current_step") != step_id
        ):
            raise LonoraError("goal_not_active", 409)
        state = copy.deepcopy(goal.state)
        identifier = stable_id(
            goal.id, f"target-review:{step_id}:plan:{state.get('plan_version', 1)}"
        )
        routine = await create_routine(
            session,
            owner_id,
            goal.agent_id or "",
            RoutineCreate(
                prompt="Recheck the confirmed entry target for this saved goal. No entry resubmission: use goal_wait or goal_step_execute for the CURRENT target-dependent step, resolving actual broker IDs.",
                interval_seconds=60,
                goal_id=goal.id,
                step_id=step_id,
            ),
            identifier,
        )
        state["steps"][step_id].update(
            status="waiting",
            target_review_id=routine.id,
            target_review_plan_version=state.get("plan_version", 1),
        )
        state["status"], state["code"] = "waiting", "goal_target_pending"
        update_goal_state(session, goal, state)
        from lonora_db.trading_goals import goal_data

        return {
            "goal": goal_data(goal),
            "wake_source": routine_data(routine),
            "waiting": True,
            "code": "goal_target_pending",
        }
