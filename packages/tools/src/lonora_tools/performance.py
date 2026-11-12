from typing import Any

from lonora_contracts.execution_quality import PerformanceRead
from lonora_db.agent_binding import agent_binding

from .base import Tool
from .context import ToolContext


async def performance(context: ToolContext, args: dict[str, Any]) -> dict[str, Any]:
    from lonora_trading.performance import performance_snapshot

    body = PerformanceRead.model_validate(args)
    async with context.db.sessions() as session:
        agent = await agent_binding(session, context.owner_id, context.agent_id)
        body = body.model_copy(
            update={
                "account_id": body.account_id or agent.trading_account_id,
                "symbol": body.symbol
                or (
                    agent.trading_symbol
                    if not body.account_id or body.account_id == agent.trading_account_id
                    else None
                ),
            }
        )
    return await performance_snapshot(context.db, context.owner_id, context.agent_id, body)


def tools() -> list[Tool]:
    return [
        Tool(
            "market_performance_read",
            "Your results from broker-confirmed closes: per judgment label of the opening "
            "order, the count and net realized P&L per account currency; plus a count per "
            "management label. unpriced counts closes whose P&L the broker deals do not give; "
            "they add nothing to the net, and a null net means none is known.",
            PerformanceRead,
            performance,
            True,
        ),
    ]
