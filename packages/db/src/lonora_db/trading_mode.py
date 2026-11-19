"""The agent's one trading switch, Full or Ask (mandate 4.1, 4.2).

Only the owner's tap on the fixed Mandate card sets Full. Any agent may switch itself to
Ask, and Lonora may switch a team agent to Ask; switching to Ask needs no confirmation.
Every change takes the per-agent authority lock, the lock the execution door holds while
it reads the mode at send, so a request either sends under the old mode or is decided
under the new one.
"""

from typing import Literal, cast

from lonora_contracts.trading import TradingMode
from lonora_core.user_error import LonoraError
from sqlalchemy.ext.asyncio import AsyncSession

from .authority_lock import authority_lock
from .events import emit
from .schema import AgentRow

# Who changes the mode: the owner's tap on the Mandate card, the agent itself, or Lonora.
ModeChanger = Literal["owner_tap", "agent", "lonora"]


async def _agent(session: AsyncSession, owner_id: str, agent_id: str) -> AgentRow:
    agent = await session.get(AgentRow, agent_id, populate_existing=True)
    if agent is None or agent.owner_id != owner_id:
        raise LonoraError("agent_not_found", 404)
    return agent


async def trading_mode(session: AsyncSession, owner_id: str, agent_id: str) -> TradingMode:
    """The stored mode, read fresh (the door calls it under the authority lock)."""
    agent = await _agent(session, owner_id, agent_id)
    return "full" if agent.trading_mode == "full" else "ask"


async def set_trading_mode(
    session: AsyncSession, owner_id: str, agent_id: str, mode: TradingMode, *, by: ModeChanger
) -> TradingMode:
    if mode == "full" and by != "owner_tap":
        raise LonoraError("trading_mode_full_owner_only", 403)
    await authority_lock(session, agent_id)
    agent = await _agent(session, owner_id, agent_id)
    if agent.trading_mode != mode:
        agent.trading_mode = mode
        await session.flush()
        await refresh_mandate_cards(session, owner_id, agent_id)
        if mode == "full":
            from .trade_approvals import withdraw_pending

            # Decided again under Full; a card is never executed because of a mode change.
            await withdraw_pending(session, owner_id, agent_id, mode)
        emit(
            session,
            owner_id,
            "agent.trading_mode.updated",
            agent_id=agent_id,
            payload={"agent_id": agent_id, "trading_mode": mode, "by": by},
        )
    return cast(TradingMode, agent.trading_mode)


async def refresh_mandate_cards(session: AsyncSession, owner_id: str, agent_id: str) -> None:
    """The agent's Mandate cards read its mode live: tell their conversations it changed."""
    from sqlalchemy import select

    from .owner_actions import owner_action_event
    from .schema import OwnerActionRow

    for row in await session.scalars(
        select(OwnerActionRow).where(
            OwnerActionRow.owner_id == owner_id,
            OwnerActionRow.subject == "trading_mode:" + agent_id,
            OwnerActionRow.status.in_(["pending", "confirmed"]),
        )
    ):
        await owner_action_event(session, row)
