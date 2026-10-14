import copy
from typing import Any

from lonora_contracts.domain import utcnow
from lonora_contracts.runs import RunRequest
from lonora_contracts.trading_goal import GoalControl, GoalCreate, GoalPlanUpdate, GoalStep
from lonora_core.user_error import LonoraError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from .broker_sessions import BrokerSessionRepository
from .events import emit
from .schema import GoalDecisionRow, TradingGoalRow
from .transactions import owned_agent, owned_thread, resource_data


async def owned_goal(
    session: AsyncSession, owner_id: str, goal_id: str, lock: bool = False
) -> TradingGoalRow:
    query = select(TradingGoalRow).where(
        TradingGoalRow.owner_id == owner_id, TradingGoalRow.id == goal_id
    )
    if lock:
        query = query.with_for_update().execution_options(populate_existing=True)
    row = await session.scalar(query)
    if row is None:
        raise LonoraError("goal_not_found", 404)
    return row


def goal_data(row: TradingGoalRow) -> dict[str, Any]:
    data = resource_data(row)
    data["step_states"] = [
        {**step, **row.state.get("steps", {}).get(step["id"], {})}
        for step in row.payload.get("steps", [])
    ]
    return data


def planned_step(row: TradingGoalRow, step_id: str | None = None) -> GoalStep:
    identifier = step_id or row.state.get("current_step")
    step = next((item for item in row.payload.get("steps", []) if item["id"] == identifier), None)
    if step is None:
        raise LonoraError("goal_step_not_found", 404)
    return GoalStep.model_validate(step)


def update_goal_state(session: AsyncSession, row: TradingGoalRow, state: dict[str, Any]) -> None:
    row.state = state
    row.version += 1
    row.updated_at = utcnow()
    emit(
        session,
        row.owner_id,
        "goals.updated",
        agent_id=row.agent_id,
        thread_id=row.thread_id,
        payload={"id": row.id, "status": state.get("status")},
    )


async def create_goal(
    session: AsyncSession,
    owner_id: str,
    request: GoalCreate,
    goal_id: str | None = None,
    *,
    owner_authorized: bool = False,
) -> TradingGoalRow:
    thread = await owned_thread(session, owner_id, request.thread_id, lock=True)
    await owned_agent(session, owner_id, request.agent_id)
    if thread.agent_id and thread.agent_id != request.agent_id:
        raise LonoraError("agent_thread_mismatch", 409)
    await BrokerSessionRepository().get(session, owner_id, request.account_id)
    if goal_id:
        existing = await session.get(TradingGoalRow, goal_id)
        if existing:
            if existing.owner_id != owner_id:
                raise LonoraError("goal_not_found", 404)
            return existing
    payload = request.model_dump(mode="json")
    payload.pop("autonomous", None)
    row = TradingGoalRow(
        owner_id=owner_id,
        agent_id=request.agent_id,
        thread_id=thread.id,
        payload=payload,
        state={
            "status": "active",
            "autonomous": request.autonomous if owner_authorized else False,
            "plan_version": 1,
            "current_step": request.steps[0].id,
            "steps": {step.id: {"status": "pending", "attempt": 1} for step in request.steps},
        },
    )
    if goal_id:
        row.id = goal_id
    if row.state["autonomous"]:
        require_autonomous_limits(row)
    session.add(row)
    await session.flush()
    emit(
        session,
        owner_id,
        "goals.created",
        agent_id=row.agent_id,
        thread_id=row.thread_id,
        payload={"id": row.id},
    )
    return row


def require_autonomous_limits(row: TradingGoalRow) -> None:
    financial = [
        GoalStep.model_validate(step)
        for step in row.payload.get("steps", [])
        if step["kind"] == "trade"
    ]
    if len(financial) > int(row.payload.get("max_trade_actions", 1)):
        raise LonoraError("goal_action_limit", 409)
    for step in financial:
        if step.trade and step.trade.action in {
            "buy",
            "sell",
            "buy_limit",
            "sell_limit",
            "buy_stop",
            "sell_stop",
        }:
            maximum = row.payload.get("maximum_volume")
            if maximum is None or step.trade.volume is None:
                raise LonoraError("goal_volume_limit_required", 409)
            from decimal import Decimal

            if step.trade.volume > Decimal(str(maximum)):
                raise LonoraError("goal_volume_limit", 409)


async def control_goal(
    session: AsyncSession,
    owner_id: str,
    goal_id: str,
    body: GoalControl,
    *,
    owner_authorized: bool = True,
) -> TradingGoalRow:
    if not owner_authorized and any(
        value is not None
        for value in (body.autonomous, body.maximum_volume, body.max_trade_actions)
    ):
        raise LonoraError("goal_owner_control_required", 409)
    row = await owned_goal(session, owner_id, goal_id, True)
    if row.version != body.version:
        raise LonoraError("version_conflict", 409)
    state = copy.deepcopy(row.state)
    if state.get("status") in {"cancelled", "completed"}:
        raise LonoraError("goal_terminal", 409)
    if body.action == "resume":
        pending = await session.scalar(
            select(GoalDecisionRow.id)
            .where(
                GoalDecisionRow.goal_id == row.id,
                GoalDecisionRow.status.in_(["ambiguous", "submitted", "executing"]),
            )
            .limit(1)
        )
        if pending:
            raise LonoraError("goal_reconciliation_required", 409)
        current_step = state.get("current_step")
        failed = (
            await session.scalar(
                select(GoalDecisionRow).where(
                    GoalDecisionRow.goal_id == row.id,
                    GoalDecisionRow.step_id == current_step,
                    GoalDecisionRow.attempt == state["steps"][current_step].get("attempt", 1),
                    GoalDecisionRow.status == "failed",
                )
            )
            if current_step
            else None
        )
        if failed:
            if not owner_authorized:
                raise LonoraError("goal_owner_retry_required", 409)
            # Explicit owner resume starts a NEW attempt after a proved rejection only.
            state["steps"][current_step] = {"status": "pending", "attempt": failed.attempt + 1}
            state.pop("code", None)
        state["status"] = "active"
    else:
        state["status"] = "paused" if body.action == "pause" else "cancelled"
    if body.maximum_volume is not None or body.max_trade_actions is not None:
        row.payload = {
            **row.payload,
            **(
                {"maximum_volume": str(body.maximum_volume)}
                if body.maximum_volume is not None
                else {}
            ),
            **(
                {"max_trade_actions": body.max_trade_actions}
                if body.max_trade_actions is not None
                else {}
            ),
        }
    if body.autonomous is not None:
        if body.autonomous:
            require_autonomous_limits(row)
        state["autonomous"] = body.autonomous
    if body.action == "cancel":
        state["autonomous"] = False
    if body.action == "resume" and state.get("autonomous"):
        require_autonomous_limits(row)
    update_goal_state(session, row, state)
    return row


async def update_plan(
    session: AsyncSession, owner_id: str, goal_id: str, body: GoalPlanUpdate
) -> TradingGoalRow:
    row = await owned_goal(session, owner_id, goal_id, True)
    if row.version != body.version:
        raise LonoraError("version_conflict", 409)
    if row.state.get("status") in {"cancelled", "completed"}:
        raise LonoraError("goal_terminal", 409)
    payload = {**row.payload, "steps": [step.model_dump(mode="json") for step in body.steps]}
    GoalCreate.model_validate({**payload, "autonomous": False})
    protected = set(
        await session.scalars(
            select(GoalDecisionRow.step_id).where(GoalDecisionRow.goal_id == row.id)
        )
    )
    old = {step["id"]: step for step in row.payload["steps"]}
    new = {step["id"]: step for step in payload["steps"]}
    if any(new.get(key) != old[key] for key in protected):
        raise LonoraError("goal_executed_step_immutable", 409)
    state = copy.deepcopy(row.state)
    state["steps"] = {
        step.id: state["steps"].get(step.id, {"status": "pending", "attempt": 1})
        for step in body.steps
    }
    state["current_step"] = next(
        (step.id for step in body.steps if state["steps"][step.id]["status"] != "completed"),
        body.steps[-1].id,
    )
    state["plan_version"] = int(state.get("plan_version", 1)) + 1
    # A changed financial plan cannot inherit authorization for its previous intent.
    if row.payload["steps"] != payload["steps"]:
        state["autonomous"] = False
        state.pop("code", None)
        if state["status"] == "waiting":
            state["status"] = "active"
            state["steps"][state["current_step"]]["status"] = "pending"
    row.payload = payload
    update_goal_state(session, row, state)
    return row


async def bind_goal_run(session: AsyncSession, owner_id: str, request: RunRequest) -> None:
    goal_id = request.metadata.get("goal_id")
    if not goal_id:
        return
    goal = await owned_goal(session, owner_id, str(goal_id), True)
    if goal.agent_id != request.agent_id or goal.thread_id != request.thread_id:
        raise LonoraError("goal_run_mismatch", 409)
    if goal.state.get("status") not in {"active", "waiting"}:
        raise LonoraError("goal_not_active", 409)
    step = planned_step(goal, request.metadata.get("step_id"))
    state = copy.deepcopy(goal.state)
    if state.get("current_step") != step.id:
        raise LonoraError("goal_step_unavailable", 409)
    if state["steps"][step.id]["status"] in {"blocked", "completed", "executing"}:
        raise LonoraError("goal_step_unavailable", 409)
    request.metadata = {
        **request.metadata,
        "goal_id": goal.id,
        "step_id": step.id,
        "plan_version": state.get("plan_version", 1),
    }
    state["status"] = "active"
    if state["steps"][step.id]["status"] == "waiting":
        state["steps"][step.id]["status"] = "pending"
    state["current_step"] = step.id
    update_goal_state(session, goal, state)


def decision_data(row: GoalDecisionRow) -> dict[str, Any]:
    return {
        "id": row.id,
        "goal_id": row.goal_id,
        "step_id": row.step_id,
        "attempt": row.attempt,
        "run_id": row.run_id,
        "operation_id": row.operation_id,
        "status": row.status,
        "request": row.request,
        "evidence": row.evidence,
        "result": row.result,
        "created_at": row.created_at.isoformat(),
        "updated_at": row.updated_at.isoformat(),
    }
