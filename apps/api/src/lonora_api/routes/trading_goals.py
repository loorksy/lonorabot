from typing import Any

from fastapi import APIRouter, Depends, Request
from lonora_auth.identity import OwnerIdentity
from lonora_contracts.trading_goal import GoalControl, GoalCreate, GoalPlanUpdate, GoalWake
from lonora_db.schema import GoalDecisionRow, TradingGoalRow
from lonora_db.trading_goals import (
    control_goal,
    create_goal,
    decision_data,
    goal_data,
    owned_goal,
    update_plan,
)
from lonora_trading.goals import recover_goals, wake_goal
from sqlalchemy import select

from ..middleware.auth import require_owner, runtime

router = APIRouter(prefix="/trading/goals")


@router.get("")
async def list_goals(
    request: Request,
    agent_id: str | None = None,
    thread_id: str | None = None,
    owner: OwnerIdentity = Depends(require_owner),
) -> list[dict[str, Any]]:
    rt = runtime(request)
    await recover_goals(rt.db)
    async with rt.db.sessions() as session:
        query = select(TradingGoalRow).where(TradingGoalRow.owner_id == owner.id)
        if agent_id:
            query = query.where(TradingGoalRow.agent_id == agent_id)
        if thread_id:
            query = query.where(TradingGoalRow.thread_id == thread_id)
        return [
            goal_data(row)
            for row in await session.scalars(
                query.order_by(TradingGoalRow.created_at.desc()).limit(200)
            )
        ]


@router.post("", status_code=201)
async def create(
    request: Request, body: GoalCreate, owner: OwnerIdentity = Depends(require_owner)
) -> dict[str, Any]:
    async with runtime(request).db.sessions() as session, session.begin():
        return goal_data(await create_goal(session, owner.id, body, owner_authorized=True))


@router.get("/{goal_id}")
async def read(
    request: Request, goal_id: str, owner: OwnerIdentity = Depends(require_owner)
) -> dict[str, Any]:
    await recover_goals(runtime(request).db)
    async with runtime(request).db.sessions() as session:
        return goal_data(await owned_goal(session, owner.id, goal_id))


@router.post("/{goal_id}/control")
async def control(
    request: Request, goal_id: str, body: GoalControl, owner: OwnerIdentity = Depends(require_owner)
) -> dict[str, Any]:
    await recover_goals(runtime(request).db)
    async with runtime(request).db.sessions() as session, session.begin():
        return goal_data(await control_goal(session, owner.id, goal_id, body))


@router.put("/{goal_id}/plan")
async def plan(
    request: Request,
    goal_id: str,
    body: GoalPlanUpdate,
    owner: OwnerIdentity = Depends(require_owner),
) -> dict[str, Any]:
    async with runtime(request).db.sessions() as session, session.begin():
        return goal_data(await update_plan(session, owner.id, goal_id, body))


@router.post("/{goal_id}/wake", status_code=201)
async def wake(
    request: Request, goal_id: str, body: GoalWake, owner: OwnerIdentity = Depends(require_owner)
) -> dict[str, Any]:
    return await wake_goal(runtime(request).db, owner.id, goal_id, body.step_id)


@router.get("/{goal_id}/decisions")
async def decisions(
    request: Request, goal_id: str, owner: OwnerIdentity = Depends(require_owner)
) -> list[dict[str, Any]]:
    await recover_goals(runtime(request).db)
    async with runtime(request).db.sessions() as session:
        await owned_goal(session, owner.id, goal_id)
        return [
            decision_data(row)
            for row in await session.scalars(
                select(GoalDecisionRow)
                .where(GoalDecisionRow.goal_id == goal_id)
                .order_by(GoalDecisionRow.created_at)
                .limit(200)
            )
        ]
