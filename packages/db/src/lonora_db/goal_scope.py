"""Goal execution scope: only live Goals run (Shadow trading is removed, Q57)."""

from lonora_core.user_error import LonoraError
from sqlalchemy.ext.asyncio import AsyncSession

from .agent_binding import require_financial_agent
from .schema import AgentRow, RunRow, TradingGoalRow


async def require_goal_agent(
    session: AsyncSession, goal: TradingGoalRow, run: RunRow | None = None
) -> AgentRow:
    # A Goal or Run recorded in the removed Shadow mode is never reinterpreted as live.
    if goal.state.get("execution_mode", "live") != "live":
        raise LonoraError("goal_execution_mode_invalid", 409)
    agent = await require_financial_agent(session, goal.owner_id, goal.agent_id or "")
    if run is not None and (
        run.agent_id != agent.id or run.model_metadata.get("execution_mode", "live") != "live"
    ):
        raise LonoraError("execution_mode_changed", 409)
    return agent
