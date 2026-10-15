"""Immutable broker-market authority shared by tools and financial execution."""

import json
from typing import Any, cast

from lonora_contracts.agent_scope import AgentRole, AgentScope
from lonora_core.user_error import LonoraError
from sqlalchemy.ext.asyncio import AsyncSession

from .schema import AgentRow

BINDING_POLICY = (
    "account_id and broker_symbol were chosen when this bot was created and cannot change. "
    "Use these exact values in every market, chart, watch, goal and trade tool. "
    "Never ask which pair, account, or symbol, and never ask the owner to repeat or retype it. "
    "If the owner omits the pair, use this binding. Letter case is not a different symbol. "
    "Never strip suffixes or use another market. A different market requires a different bot. "
    "Child agents inherit this binding. Delegation cannot bypass financial authority. "
    "Trade approval is only the Approve or Reject button on the card inside the call. "
    "Never ask for a spoken or typed yes. Speech and chat text are not approval."
)


def scope_data(agent: AgentRow) -> dict[str, Any]:
    role = cast(AgentRole, agent.role or "legacy")
    return AgentScope(
        role=role,
        account_id=agent.trading_account_id,
        broker_symbol=agent.trading_symbol,
        visibility="owner_accounts"
        if role == "personal"
        else "bound_market"
        if agent.trading_account_id
        else "delegated_research"
        if role == "delegated"
        else "legacy",
        execution_authority="none" if role == "delegated" else "existing_server_controls",
    ).model_dump(mode="json")


def same_binding(value: object, bound: str | None) -> bool:
    return (
        isinstance(bound, str) and isinstance(value, str) and value.casefold() == bound.casefold()
    )


def assert_market_binding(
    agent: AgentRow, account_id: str | None = None, symbol: str | None = None
) -> None:
    if agent.trading_account_id is None and agent.trading_symbol is None:
        if agent.role not in {None, "personal", "delegated", "legacy"}:
            raise LonoraError("agent_trading_binding_invalid", 409)
        # This guard governs visibility only. Financial paths additionally call
        # require_financial_agent; an empty binding never grants authority.
        return
    if not agent.trading_account_id or not agent.trading_symbol:
        raise LonoraError("agent_trading_binding_invalid", 409)
    if account_id is not None and not same_binding(account_id, agent.trading_account_id):
        raise LonoraError("agent_trading_account_mismatch", 409)
    if symbol is not None and not same_binding(symbol, agent.trading_symbol):
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


async def require_financial_agent(
    session: AsyncSession, owner_id: str, agent_id: str
) -> AgentRow:
    """Enforce persisted authority across identity ancestry, not model instructions.

    Personal/root legacy identities retain existing approval-based execution.
    A research delegation and every descendant remain nonfinancial even when
    reached through a later independent run or a forged financial proposal.
    """
    agent = await agent_binding(session, owner_id, agent_id)
    current = agent
    seen: set[str] = set()
    for _ in range(32):
        if current.id in seen:
            raise LonoraError("agent_ancestry_invalid", 409)
        seen.add(current.id)
        if current.role == "delegated" or (
            current.parent_id and not current.trading_account_id and not current.trading_symbol
        ):
            raise LonoraError("delegated_financial_authority_forbidden", 403)
        assert_market_binding(current)
        if not current.parent_id:
            return agent
        current = await agent_binding(session, owner_id, current.parent_id)
    raise LonoraError("agent_ancestry_invalid", 409)


def binding_context(agent: AgentRow) -> str:
    if agent.role == "delegated":
        return (
            "<delegated_research_scope>"
            "You are a temporary delegated research agent. Use authorized read-only account and "
            "market tools only for the bounded assigned task. You cannot propose or execute broker "
            "mutations, enable autonomous trading, or create trading goals. Return evidence to the "
            "requesting agent. Creating children or collaborating never transfers financial authority."
            "</delegated_research_scope>"
        )
    if agent.role == "personal":
        return (
            "<personal_agent_scope>"
            "You are the owner's default Personal Agent. Read authorized owner accounts and exact "
            "broker symbols relevant to the current request. Retrieve bounded context; do not inject "
            "all market/account history. Discover specialists by structured account/symbol bindings, "
            "never their names. If none exists, analyze directly. Owner-wide visibility is NOT "
            "autonomous execution authority. Every mutation still requires the existing server "
            "approval, risk, scope, global trading and emergency controls. Never claim owner intent "
            "for external trades. Account-level observations have one conversational owner: you."
            "</personal_agent_scope>"
        )
    if not agent.trading_account_id or not agent.trading_symbol:
        return ""
    return (
        "<immutable_trading_market>"
        + json.dumps(
            {
                "account_id": agent.trading_account_id,
                "broker_symbol": agent.trading_symbol,
                "policy": BINDING_POLICY,
            },
            ensure_ascii=False,
        )
        + "</immutable_trading_market>"
    )
