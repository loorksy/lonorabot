"""Immutable broker-market authority shared by tools and financial execution."""

from typing import Any, cast

from lonora_core.user_error import LonoraError
from sqlalchemy.ext.asyncio import AsyncSession

from .schema import AgentRow


def assert_market_binding(
    agent: AgentRow, account_id: str | None = None, symbol: str | None = None
) -> None:
    if agent.trading_account_id is None and agent.trading_symbol is None:
        return  # Existing identities retain their previous behaviour.
    if not agent.trading_account_id or not agent.trading_symbol:
        raise LonoraError("agent_trading_binding_invalid", 409)
    if account_id is not None and account_id != agent.trading_account_id:
        raise LonoraError("agent_trading_account_mismatch", 409)
    if symbol is not None and symbol != agent.trading_symbol:
        raise LonoraError("agent_trading_symbol_mismatch", 409)


def assert_payload_binding(agent: AgentRow, payload: Any) -> None:
    if isinstance(payload, dict):
        mapping = cast(dict[str, Any], payload)
        assert_market_binding(
            agent, mapping.get("account_id") or None, mapping.get("symbol") or None
        )
        for value in mapping.values():
            if isinstance(value, (dict, list)):
                assert_payload_binding(agent, value)
    elif isinstance(payload, list):
        for item in cast(list[Any], payload):
            assert_payload_binding(agent, item)


async def agent_binding(session: AsyncSession, owner_id: str, agent_id: str) -> AgentRow:
    agent = await session.get(AgentRow, agent_id)
    if agent is None or agent.owner_id != owner_id:
        raise LonoraError("agent_not_found", 404)
    return agent


def binding_context(agent: AgentRow) -> str:
    if not agent.trading_account_id or not agent.trading_symbol:
        return ""
    import json

    return (
        "<immutable_trading_market>"
        + json.dumps(
            {
                "account_id": agent.trading_account_id,
                "broker_symbol": agent.trading_symbol,
                "policy": "This agent's account and exact broker symbol were chosen by its owner at creation and cannot change. Use them in all market, chart, watch, goal and trade tools. Never strip suffixes or use another market. Do not ask to change this binding; a different market requires a different bot. Child agents inherit it. Delegation cannot bypass financial authority.",
            },
            ensure_ascii=False,
        )
        + "</immutable_trading_market>"
    )
