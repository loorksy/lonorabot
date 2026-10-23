from __future__ import annotations

import copy
from collections.abc import Awaitable, Callable
from typing import TYPE_CHECKING, Any

from lonora_adapters.brokers.base import BrokerManager
from lonora_contracts.domain import utcnow
from lonora_contracts.runs import Lease, RunRequest
from lonora_contracts.trading import TradeRequest, TradeResult
from lonora_contracts.trading_goal import GoalExecution
from lonora_core.user_error import LonoraError
from lonora_db.client import Database
from lonora_db.goal_scope import goal_mode, require_goal_agent
from lonora_db.runs import create_run, locked_run_thread, require_lease, run_data
from lonora_db.schema import (
    GoalDecisionRow,
    RunRow,
    SuperBotRequestRow,
    TradeApprovalRow,
    TradingGoalRow,
    TradingJournalRow,
)
from lonora_db.super_bot import require_goal_authority
from lonora_db.trading_goals import (
    owned_goal,
    planned_step,
    require_autonomous_limits,
    update_goal_state,
)
from lonora_session.idempotency import stable_id
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from .account_authority import provisional_voice
from .goals_market import fresh_goal_evidence
from .goals_targets import resolve_trade
from .idempotency import trade_fingerprint

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
    """A signed supervised plan can prepare a card, never execute unattended."""
    await require_goal_agent(session, goal, run)
    grant_id = goal.state.get("super_bot_request_id")
    if grant_id:
        grant = await session.get(SuperBotRequestRow, grant_id)
        if grant and grant.status == "activated" and grant.mode == "advisory":
            raise LonoraError("super_bot_advisory_only", 403)
    if run.trigger in {"user", "group"} or await provisional_voice(session, run):
        return True
    if goal.state.get("autonomous", False):
        require_autonomous_limits(goal)
        await require_goal_authority(session, goal)
        return False
    if not grant_id:
        raise LonoraError("goal_autonomy_required", 409)
    await require_goal_authority(session, goal, mode="supervised")
    return True


async def require_supervised_approval(
    session: AsyncSession, goal: TradingGoalRow, run: RunRow, request: TradeRequest
) -> None:
    if run.trigger in {"user", "group"} or not await goal_requires_approval(session, goal, run):
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
    await goal_requires_approval(session, goal, run)
    await require_supervised_approval(session, goal, run, request)
    if goal.state.get("autonomous", False):
        require_autonomous_limits(goal)
        await require_goal_authority(session, goal)
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
        if journal.status == "submitted" and not settle and decision.run_id:
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
        status = journal.status if journal.status in {"confirmed", "failed"} else "ambiguous"
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
                "goal_reconciliation_required" if status == "ambiguous" else "goal_trade_failed"
            )
        elif status == "confirmed" and state["status"] == "blocked":
            state["status"] = "active"
            state.pop("code", None)
        advance_state(goal, state)
        update_goal_state(session, goal, state)
        return True


async def recover_goals(db: Database) -> int:
    async with db.sessions() as session:
        pending = list(
            await session.scalars(
                select(GoalDecisionRow.operation_id)
                .where(GoalDecisionRow.status.in_(["executing", "submitted", "ambiguous"]))
                .limit(100)
            )
        )
    recovered = 0
    for operation_id in pending:
        async with db.sessions() as session:
            decision = await session.scalar(
                select(GoalDecisionRow).where(GoalDecisionRow.operation_id == operation_id)
            )
            journal = await session.get(TradingJournalRow, operation_id)
            if decision is None:
                continue
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
                    recovered += 1
            continue
        recovered += int(await sync_goal_decision(db, operation_id))
    async with db.sessions() as session:
        waiting = list(
            await session.scalars(
                select(TradingGoalRow)
                .where(
                    TradingGoalRow.state["status"].as_string() == "waiting",
                    TradingGoalRow.state["code"].as_string() == "goal_target_pending",
                )
                .limit(100)
            )
        )
    from lonora_db.schema import RoutineRow

    for goal in waiting:
        step_id = str(goal.state["current_step"])
        identifier = goal.state["steps"][step_id].get("target_review_id")
        async with db.sessions() as session:
            routine = await session.get(RoutineRow, identifier) if identifier else None
        if routine is None:
            await wait_for_goal_target(db, goal.owner_id, goal.id, step_id)
            recovered += 1
    return recovered


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
        needs_approval = await goal_requires_approval(session, goal, origin)
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
    if needs_approval:
        if approval_gate is None:
            raise LonoraError("trade_approval_required", 409)
        pending_approval = await approval_gate(request)
        if pending_approval is not None:
            return pending_approval
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
        if await goal_requires_approval(session, goal, run) != needs_approval:
            raise LonoraError("super_bot_scope_changed", 409)
        await require_supervised_approval(session, goal, run, request)
        if goal.state.get("autonomous", False):
            require_autonomous_limits(goal)
            await require_goal_authority(session, goal)
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
                "execution_mode": goal_mode(goal),
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
        if goal_mode(goal) == "shadow":
            from .shadow import execute_shadow

            result = await execute_shadow(
                db,
                brokers,
                owner_id,
                goal.agent_id or "",
                goal.thread_id or "",
                lease,
                request,
                goal=context,
                authorization=require_approved_goal if needs_approval else None,
            )
        else:
            result = await executor.execute(
                owner_id,
                request,
                lease,
                goal=context,
                authorization=require_approved_goal if needs_approval else None,
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
