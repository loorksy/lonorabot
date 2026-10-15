"""Owner-selected virtual mode; switching mode never enables autonomy."""

from typing import Literal

from fastapi import APIRouter, Depends, Request
from lonora_auth.identity import OwnerIdentity
from lonora_contracts.shadow import AgentExecutionMode, PerformanceRead
from lonora_db.agent_binding import assert_market_binding
from lonora_db.agents import agent_data
from lonora_db.events import emit
from lonora_db.schema import TradingGoalRow
from lonora_db.transactions import owned_agent
from sqlalchemy import select

from ..middleware.auth import require_owner, runtime

router = APIRouter(prefix="/agents")


@router.get("/{agent_id}/performance")
async def performance(
    request: Request,
    agent_id: str,
    execution_mode: Literal["live", "shadow"],
    account_id: str | None = None,
    symbol: str | None = None,
    owner: OwnerIdentity = Depends(require_owner),
):
    from lonora_trading.performance import performance_snapshot

    db = runtime(request).db
    async with db.sessions() as session:
        agent = await owned_agent(session, owner.id, agent_id)
        assert_market_binding(agent, account_id, symbol)
        params = PerformanceRead(
            execution_mode=execution_mode,
            account_id=agent.trading_account_id or account_id,
            symbol=agent.trading_symbol or symbol,
        )
    return await performance_snapshot(db, owner.id, agent_id, params)


@router.get("/{agent_id}/shadow-trades")
async def trades(
    request: Request,
    agent_id: str,
    account_id: str | None = None,
    symbol: str | None = None,
    owner: OwnerIdentity = Depends(require_owner),
):
    from lonora_trading.shadow import shadow_data, shadow_rows

    db = runtime(request).db
    async with db.sessions() as session:
        agent = await owned_agent(session, owner.id, agent_id)
        assert_market_binding(agent, account_id, symbol)
        account_id = agent.trading_account_id or account_id
        symbol = agent.trading_symbol or symbol
    rows = await shadow_rows(db, owner.id, agent_id, account_id, symbol)
    return {"mode": "shadow", "trades": [shadow_data(row) for row in rows[:100]]}


@router.put("/{agent_id}/execution-mode")
async def update_mode(
    request: Request,
    agent_id: str,
    body: AgentExecutionMode,
    owner: OwnerIdentity = Depends(require_owner),
):
    async with runtime(request).db.sessions() as session, session.begin():
        agent = await owned_agent(session, owner.id, agent_id, lock=True)
        if agent.execution_mode != body.execution_mode:
            agent.execution_mode = body.execution_mode
            goals = await session.scalars(
                select(TradingGoalRow)
                .where(
                    TradingGoalRow.owner_id == owner.id,
                    TradingGoalRow.agent_id == agent.id,
                    TradingGoalRow.state["status"].as_string() == "active",
                )
                .with_for_update()
            )
            for goal in goals:
                goal.state = {
                    **goal.state,
                    "autonomous": False,
                    "status": "paused",
                    "code": "execution_mode_changed",
                }
                goal.version += 1
            emit(
                session,
                owner.id,
                "agents.updated",
                agent_id=agent.id,
                payload={"id": agent.id, "execution_mode": agent.execution_mode},
            )
        return agent_data(agent)
