"""Frozen Goal execution scope; legacy Goals remain live, never reinterpreted."""

from lonora_contracts.shadow import ExecutionMode
from lonora_core.user_error import LonoraError
from sqlalchemy.ext.asyncio import AsyncSession

from .agent_binding import require_financial_agent
from .schema import AgentRow, RunRow, TradingGoalRow


def goal_mode(goal: TradingGoalRow) -> ExecutionMode:
    value = goal.state.get("execution_mode", "live")
    if value not in {"live", "shadow"}:
        raise LonoraError("goal_execution_mode_invalid", 409)
    return "shadow" if value == "shadow" else "live"


async def require_goal_agent(
    session: AsyncSession, goal: TradingGoalRow, run: RunRow | None = None
) -> AgentRow:
    mode = goal_mode(goal)
    agent = await require_financial_agent(
        session, goal.owner_id, goal.agent_id or "", execution_mode=mode
    )
    if run is not None and (
        run.agent_id != agent.id or run.model_metadata.get("execution_mode", "live") != mode
    ):
        raise LonoraError("execution_mode_changed", 409)
    return agent
