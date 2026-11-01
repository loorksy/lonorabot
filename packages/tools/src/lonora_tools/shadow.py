from typing import Any

from lonora_contracts.shadow import PerformanceRead, ShadowCommand, ShadowRead
from lonora_contracts.trading import TradeRequest
from lonora_db.agent_binding import agent_binding, assert_market_binding
from lonora_trading.shadow import execute_shadow, shadow_data, shadow_rows

from .base import Tool
from .context import ToolContext


async def command(context: ToolContext, args: dict[str, Any]) -> dict[str, Any]:
    body = ShadowCommand.model_validate(args)
    request = TradeRequest.model_validate(body.model_dump(exclude={"decision_id", "operation_id"}))
    request.operation_id = context.resource_id
    result = await execute_shadow(
        context.db,
        context.brokers,
        context.owner_id,
        context.agent_id,
        context.thread_id,
        context.lease,
        request,
        body.decision_id,
    )
    return {**result.model_dump(mode="json"), "mode": "shadow", "execution_authorized": False}


async def read(context: ToolContext, args: dict[str, Any]) -> dict[str, Any]:
    body = ShadowRead.model_validate(args)
    async with context.db.sessions() as session:
        agent = await agent_binding(session, context.owner_id, context.agent_id)
        assert_market_binding(agent, body.account_id, body.symbol)
        symbol = body.symbol or (
            agent.trading_symbol
            if not body.account_id or body.account_id == agent.trading_account_id
            else None
        )
    rows = await shadow_rows(
        context.db, context.owner_id, context.agent_id, body.account_id, symbol
    )
    return {
        "mode": "shadow",
        "trades": [shadow_data(row) for row in rows[: body.limit]],
        "monetary_pnl_available": False,
    }


async def performance(context: ToolContext, args: dict[str, Any]) -> dict[str, Any]:
    from lonora_trading.performance import performance_snapshot

    body = PerformanceRead.model_validate(args)
    async with context.db.sessions() as session:
        agent = await agent_binding(session, context.owner_id, context.agent_id)
        assert_market_binding(agent, body.account_id, body.symbol)
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
            "Inspect actual persisted decision/outcome quality with explicit live or shadow mode. Separate analysis, entry, management and execution; small samples remain insufficient, returns are not profit/correctness, and no safety rules change.",
            PerformanceRead,
            performance,
            True,
        ),
        Tool(
            "market_shadow_execute",
            "Create/manage a virtual trade from actual recorded decision and current broker data. Requires persisted Shadow mode. Never submits any broker mutation; all receipts are explicitly virtual.",
            ShadowCommand,
            command,
        ),
        Tool(
            "market_shadow_read",
            "Read this Agent's persistent virtual positions/orders and four separate quality dimensions; never interpret virtual results as live broker positions or P&L.",
            ShadowRead,
            read,
            True,
        ),
    ]
