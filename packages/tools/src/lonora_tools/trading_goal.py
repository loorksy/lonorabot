import copy
from typing import Any

from lonora_contracts.domain import utcnow
from lonora_contracts.routines import RoutineCreate
from lonora_contracts.trading import TradeRequest, TradeResult
from lonora_contracts.trading_goal import (
    GoalControl,
    GoalCreate,
    GoalPlanUpdate,
    GoalReference,
    GoalStepNote,
)
from lonora_core.user_error import LonoraError
from lonora_db.goal_scope import require_goal_agent
from lonora_db.market_watches import MarketWatchRepository
from lonora_db.routines import create_routine, routine_data
from lonora_db.runs import locked_run_thread, require_lease
from lonora_db.schema import EffectReceiptRow, GoalDecisionRow, TradingGoalRow
from lonora_db.trading_goals import (
    control_goal,
    create_goal,
    decision_data,
    goal_data,
    owned_goal,
    planned_step,
    update_goal_state,
    update_plan,
)
from lonora_db.transactions import resource_data
from lonora_session.idempotency import request_hash, stable_id
from lonora_trading.goals import (
    advance_state,
    execute_goal_step,
    recover_goals,
    wait_for_goal_target,
)
from lonora_trading.goals_market import fresh_goal_evidence
from lonora_trading.goals_targets import resolve_condition
from sqlalchemy import select

from .base import Tool
from .context import ToolContext
from .memory import Empty


class GoalProposal(GoalCreate):
    agent_id: str = ""
    thread_id: str = ""


class GoalPlan(GoalPlanUpdate):
    goal_id: str


class GoalToggle(GoalReference):
    version: int
    action: str


async def create(context: ToolContext, args: dict[str, Any]) -> dict[str, Any]:
    body = GoalCreate.model_validate(
        {**args, "agent_id": context.agent_id, "thread_id": context.thread_id, "autonomous": False}
    )
    async with context.db.sessions() as session, session.begin():
        run, _ = await locked_run_thread(session, context.lease)
        goal = await create_goal(session, context.owner_id, body, context.resource_id)
        await require_goal_agent(session, goal, run)
        run.model_metadata = {
            **run.model_metadata,
            "goal_id": goal.id,
            "step_id": goal.state["current_step"],
            "plan_version": goal.state.get("plan_version", 1),
        }
        return goal_data(goal)


async def read(context: ToolContext, args: dict[str, Any]) -> dict[str, Any]:
    await recover_goals(context.db)
    async with context.db.sessions() as session:
        from lonora_db.trading_goals import goal_read_thread

        source_thread = await goal_read_thread(session, await require_lease(session, context.lease))
        rows = list(
            await session.scalars(
                select(TradingGoalRow)
                .where(
                    TradingGoalRow.owner_id == context.owner_id,
                    TradingGoalRow.agent_id == context.agent_id,
                    TradingGoalRow.thread_id == source_thread,
                )
                .order_by(TradingGoalRow.created_at.desc())
                .limit(31)
            )
        )
        return {
            "goals": [
                {
                    "id": row.id,
                    "title": row.payload["title"],
                    "objective": str(row.payload["objective"])[:256],
                    "agent_id": row.agent_id,
                    "thread_id": row.thread_id,
                    "status": row.state.get("status"),
                    "autonomous": row.state.get("autonomous", False),
                    "execution_mode": row.state.get("execution_mode", "live"),
                    "current_step": row.state.get("current_step"),
                    "plan_version": row.state.get("plan_version", 1),
                    "account_id": row.payload["account_id"],
                    "symbol": row.payload["symbol"],
                    "step_count": len(row.payload["steps"]),
                }
                for row in rows[:30]
            ],
            "more_available": len(rows) > 30,
            "details_tool": "goal_read",
        }


async def read_goal(context: ToolContext, args: dict[str, Any]) -> dict[str, Any]:
    await recover_goals(context.db)
    async with context.db.sessions() as session:
        from lonora_db.trading_goals import goal_read_thread

        source_thread = await goal_read_thread(session, await require_lease(session, context.lease))
        goal = await owned_goal(session, context.owner_id, args["goal_id"])
        if goal.agent_id != context.agent_id or goal.thread_id != source_thread:
            raise LonoraError("goal_run_mismatch", 409)
        step = planned_step(goal, args.get("step_id"))
        return {
            "id": goal.id,
            "title": goal.payload["title"],
            "objective": goal.payload["objective"],
            "status": goal.state["status"],
            "autonomous": goal.state.get("autonomous", False),
            "execution_mode": goal.state.get("execution_mode", "live"),
            "plan_version": goal.state.get("plan_version", 1),
            "limits": {
                key: goal.payload.get(key)
                for key in ("account_id", "symbol", "maximum_volume", "max_trade_actions")
            },
            "step": step.model_dump(mode="json"),
            "state": goal.state["steps"][step.id],
            "plan": [
                {"id": value["id"], "title": value["title"], "kind": value["kind"]}
                for value in goal.payload["steps"]
            ],
        }


async def read_decisions(context: ToolContext, args: dict[str, Any]) -> dict[str, Any]:
    await recover_goals(context.db)
    async with context.db.sessions() as session:
        from lonora_db.trading_goals import goal_read_thread

        source_thread = await goal_read_thread(session, await require_lease(session, context.lease))
        goal = await owned_goal(session, context.owner_id, args["goal_id"])
        if goal.agent_id != context.agent_id or goal.thread_id != source_thread:
            raise LonoraError("goal_run_mismatch", 409)
        step = planned_step(goal, args.get("step_id"))
        rows = list(
            await session.scalars(
                select(GoalDecisionRow)
                .where(GoalDecisionRow.goal_id == goal.id, GoalDecisionRow.step_id == step.id)
                .order_by(GoalDecisionRow.created_at.desc())
                .limit(3)
            )
        )
        result: list[dict[str, Any]] = []
        for row in rows:
            data = decision_data(row)
            evidence = dict(data["evidence"])
            for field in ("observation", "before_send"):
                if isinstance(evidence.get(field), dict):
                    item = dict(evidence[field])
                    evidence[field] = {
                        **item,
                        "positions": item.get("positions", [])[:5],
                        "orders": item.get("orders", [])[:5],
                    }
            data["evidence"] = evidence
            result.append(data)
        return {
            "goal_id": goal.id,
            "step_id": step.id,
            "decisions": result,
            "evidence_note": "Account and exact decision receipt retained; position/order evidence lists capped at five per observation. Full owner API history remains available.",
        }


async def plan(context: ToolContext, args: dict[str, Any]) -> dict[str, Any]:
    async with context.db.sessions() as session, session.begin():
        run, _ = await locked_run_thread(session, context.lease)
        goal = await owned_goal(session, context.owner_id, args["goal_id"])
        if goal.agent_id != run.agent_id or goal.thread_id != run.thread_id:
            raise LonoraError("goal_run_mismatch", 409)
        return goal_data(
            await update_plan(
                session,
                context.owner_id,
                goal.id,
                GoalPlanUpdate.model_validate(
                    {key: value for key, value in args.items() if key != "goal_id"}
                ),
            )
        )


async def complete(context: ToolContext, args: dict[str, Any]) -> dict[str, Any]:
    async with context.db.sessions() as session:
        original = await owned_goal(session, context.owner_id, args["goal_id"])
        source = planned_step(original, args.get("step_id"))
        plan_version = original.state.get("plan_version", 1)
    observation = (
        await fresh_goal_evidence(
            context.db,
            context.brokers,
            context.owner_id,
            original.id,
            source.id,
            context.lease.run_id,
        )
        if source.kind == "watch" and source.condition and source.condition.kind != "calendar"
        else None
    )
    async with context.db.sessions() as session, session.begin():
        run, _ = await locked_run_thread(session, context.lease)
        goal = await owned_goal(session, context.owner_id, args["goal_id"], True)
        if goal.agent_id != run.agent_id or goal.thread_id != run.thread_id:
            raise LonoraError("goal_run_mismatch", 409)
        if goal.state.get("status") != "active":
            raise LonoraError("goal_not_active", 409)
        step = planned_step(goal, args.get("step_id"))
        if goal.state.get("plan_version", 1) != plan_version:
            raise LonoraError("goal_plan_changed", 409)
        if (
            step.kind == "watch"
            and source.condition
            and source.condition.kind == "calendar"
            and run.model_metadata.get("watch_id") != goal.state["steps"][step.id].get("watch_id")
        ):
            raise LonoraError("goal_watch_evidence_required", 409)
        if step.kind == "trade":
            raise LonoraError("goal_trade_confirmation_required", 409)
        if step.id != goal.state.get("current_step"):
            raise LonoraError("goal_step_order", 409)
        state = copy.deepcopy(goal.state)
        state["steps"][step.id].update(
            status="completed",
            note=args["note"],
            evidence_refs=args.get("evidence_refs", []),
            observation=observation,
        )
        advance_state(goal, state)
        update_goal_state(session, goal, state)
        return goal_data(goal)


async def wait(context: ToolContext, args: dict[str, Any]) -> dict[str, Any]:
    async with context.db.sessions() as session:
        original = await owned_goal(session, context.owner_id, args["goal_id"])
        planned = planned_step(original, args.get("step_id"))
    try:
        resolved_condition = (
            await resolve_condition(
                context.db, context.brokers, context.owner_id, original.id, planned.condition
            )
            if planned.condition
            else None
        )
    except LonoraError as error:
        if error.code == "goal_target_not_observed":
            return await wait_for_goal_target(
                context.db, context.owner_id, original.id, planned.id, context.lease
            )
        raise
    async with context.db.sessions() as session, session.begin():
        run, _ = await locked_run_thread(session, context.lease)
        goal = await owned_goal(session, context.owner_id, args["goal_id"], True)
        if goal.agent_id != run.agent_id or goal.thread_id != run.thread_id:
            raise LonoraError("goal_run_mismatch", 409)
        if goal.state.get("status") != "active":
            raise LonoraError("goal_not_active", 409)
        step = planned_step(goal, args.get("step_id"))
        if (
            step.id != goal.state.get("current_step")
            or goal.state["steps"][step.id]["status"] != "pending"
        ):
            raise LonoraError("goal_step_unavailable", 409)
        state = copy.deepcopy(goal.state)
        identifier = stable_id(goal.id, f"wait:{step.id}:plan:{state.get('plan_version', 1)}")
        if resolved_condition is not None:
            config = {
                **resolved_condition.model_dump(mode="json"),
                "goal_id": goal.id,
                "step_id": step.id,
            }
            existing = await session.get(MarketWatchRepository.row_type, identifier)
            row = existing or await MarketWatchRepository().create(
                session,
                context.owner_id,
                config,
                agent_id=context.agent_id,
                thread_id=context.thread_id,
                resource_id=identifier,
            )
            if (
                resolved_condition.condition == "opened"
                and state["steps"][step.id].get("target_review_id")
                and not row.state
            ):
                row.state = {"last_value": "0"}
            state["steps"][step.id]["watch_id"] = row.id
            resource = resource_data(row)
        elif step.review_interval_seconds is not None:
            row = await create_routine(
                session,
                context.owner_id,
                context.agent_id,
                RoutineCreate(
                    prompt=f"Review saved goal {goal.id}, step {step.id}. Continue its plan with fresh broker evidence.",
                    interval_seconds=step.review_interval_seconds,
                    goal_id=goal.id,
                    step_id=step.id,
                ),
                identifier,
            )
            state["steps"][step.id]["routine_id"] = row.id
            state["steps"][step.id]["routine_plan_version"] = state.get("plan_version", 1)
            resource = routine_data(row)
        else:
            raise LonoraError("goal_wait_source_required", 409)
        state["steps"][step.id]["status"] = "waiting"
        state["status"] = "waiting"
        state.pop("code", None)
        update_goal_state(session, goal, state)
        return {"goal": goal_data(goal), "wake_source": resource}


async def execute(context: ToolContext, args: dict[str, Any]) -> dict[str, Any]:
    from .trade import approved_execution

    # Optional "current step" must resolve once per tool effect. Replaying a
    # completed call must not silently select the next financial step/attempt.
    async with context.db.sessions() as session, session.begin():
        origin, _ = await locked_run_thread(session, context.lease)
        goal = await owned_goal(session, context.owner_id, args["goal_id"], True)
        await require_goal_agent(session, goal, origin)
        key = "goal-step-call:" + context.resource_id
        receipt = await session.get(EffectReceiptRow, key)
        intent = request_hash(args)
        if receipt:
            frozen = receipt.result
            if frozen["intent"] != intent:
                raise LonoraError("operation_id_conflict", 409)
        else:
            step = planned_step(goal, args.get("step_id"))
            frozen = {
                "intent": intent,
                "step_id": step.id,
                "attempt": int(goal.state["steps"][step.id].get("attempt", 1)),
                "plan_version": int(goal.state.get("plan_version", 1)),
            }
            session.add(EffectReceiptRow(key=key, result=frozen))
        decision_id = stable_id(
            goal.id, f"decision:{frozen['step_id']}:attempt:{frozen['attempt']}"
        )
        prior = await session.get(GoalDecisionRow, decision_id)
        if prior and prior.result:
            from lonora_db.schema import TradeApprovalRow
            from lonora_db.trade_approvals import approval_event

            approval = await session.get(
                TradeApprovalRow,
                stable_id(context.lease.run_id, "approval:" + context.call_id),
                with_for_update=True,
            )
            if approval and approval.status == "approved":
                approval.status, approval.results, approval.updated_at = (
                    "completed",
                    [prior.result],
                    utcnow(),
                )
                approval_event(session, approval)
            return {
                "decision_id": prior.id,
                "operation_id": prior.operation_id,
                "result": prior.result,
                "deduplicated": True,
            }
        if (
            int(goal.state.get("plan_version", 1)) != frozen["plan_version"]
            or int(goal.state["steps"].get(frozen["step_id"], {}).get("attempt", 1))
            != frozen["attempt"]
        ):
            raise LonoraError("goal_plan_changed", 409)
        args = {**args, "step_id": frozen["step_id"]}

    approval_id = None
    approved_request: TradeRequest | None = None

    async def gate(request: TradeRequest) -> dict[str, Any] | None:
        nonlocal approval_id, approved_request
        proposal = await approved_execution(context, [request], gate_only=True)
        if not proposal.get("approved"):
            return proposal
        approval_id, approved_request = proposal["approval_id"], request
        return None

    async def finish_approval(value: dict[str, Any]) -> None:
        if not approval_id:
            return
        from lonora_db.schema import TradeApprovalRow
        from lonora_db.trade_approvals import approval_event

        async with context.db.sessions() as session, session.begin():
            await require_lease(session, context.lease, lock=True)
            row = await session.get(TradeApprovalRow, approval_id, with_for_update=True)
            if (
                row is None
                or row.owner_id != context.owner_id
                or row.run_id != context.lease.run_id
            ):
                raise LonoraError("trade_approval_mismatch", 409)
            if row.status == "approved":
                row.status, row.results = "completed", [value]
                approval_event(session, row)

    try:
        result = await execute_goal_step(
            context.db,
            context.brokers,
            context.trading,
            context.owner_id,
            args["goal_id"],
            args.get("step_id"),
            context.lease,
            args.get("note", ""),
            args.get("evidence_refs", []),
            approval_gate=gate,
        )
    except LonoraError as error:
        if approved_request is not None and error.code != "stale_lease":
            await finish_approval(
                TradeResult(
                    operation_id=approved_request.operation_id, status="failed", code=error.code
                ).model_dump(mode="json")
            )
        raise
    if approval_id and result.get("result"):
        await finish_approval(result["result"])

    return result


async def toggle(context: ToolContext, args: dict[str, Any]) -> dict[str, Any]:
    if args["action"] not in {"pause", "resume", "cancel"}:
        raise LonoraError("goal_control_invalid", 409)
    async with context.db.sessions() as session, session.begin():
        run, _ = await locked_run_thread(session, context.lease)
        goal = await owned_goal(session, context.owner_id, args["goal_id"])
        if goal.agent_id != run.agent_id or goal.thread_id != run.thread_id:
            raise LonoraError("goal_run_mismatch", 409)
        return goal_data(
            await control_goal(
                session,
                context.owner_id,
                goal.id,
                GoalControl(version=args["version"], action=args["action"]),
                owner_authorized=False,
            )
        )


def tools() -> list[Tool]:
    return [
        Tool(
            "goal_create",
            "Persist a trading goal and ordered plan in this same agent/chat. Saving a plan grants no authority; live actions follow current Agent permission and exact signed account scope. Do not promise profits.",
            GoalProposal,
            create,
            replay_safe=True,
        ),
        Tool(
            "goal_list",
            "Catalog saved goal statuses and current steps for this agent/chat; use goal_read and goal_decisions for exact plans and confirmations.",
            Empty,
            read,
            True,
        ),
        Tool(
            "goal_read",
            "Read the full selected/current goal step, exact declared financial parameters and plan headers on demand.",
            GoalReference,
            read_goal,
            True,
        ),
        Tool(
            "goal_decisions",
            "Read actual confirmations, ambiguity, exact requests and bounded broker evidence for one goal step.",
            GoalReference,
            read_decisions,
            True,
        ),
        Tool(
            "goal_plan",
            "Update pending plan steps version-safely; executed steps are immutable and changed plans disable financial autonomy.",
            GoalPlan,
            plan,
        ),
        Tool(
            "goal_step_complete",
            "Record analysis/watch/review completion and cited evidence. Cannot mark a trade completed; only actual broker confirmation can do that.",
            GoalStepNote,
            complete,
        ),
        Tool(
            "goal_wait",
            "Wait on the planned condition or scheduled review using existing server watches/routines. Wakes the same agent and goal; never places a trade directly.",
            GoalReference,
            wait,
        ),
        Tool(
            "goal_step_execute",
            "Execute the exact current step in its frozen live/shadow Goal mode with fresh evidence. Live steps follow current Agent permission: analysis prohibits mutations, supervised needs exact approval, autonomous needs matching signed AccountAuthority. Global Trading ON is independently required; Shadow only mutates virtual state. Fixed step/attempt identity across runs; ambiguity blocks retries.",
            GoalStepNote,
            execute,
            financial=True,
            replay_safe=True,
        ),
        Tool(
            "goal_control",
            "Pause, resume or cancel this saved goal. This tool cannot enable financial autonomy or expand financial limits.",
            GoalToggle,
            toggle,
        ),
    ]
