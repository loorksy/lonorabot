"""Propose an owner action card in the conversation. Agents propose; only the owner acts.

The card is validated against current state, deduplicated per agent and effect, and
capped per agent. What the owner sees on it is derived on the server from the records it
names; the only agent words on a card are a Secret card's label, field labels and the
details the agent gave from chat, each shown as the agent's. No tool can confirm a card:
the owner's tap goes to an owner-session route that runs the existing owner function.
There is no grant card.
"""

from typing import Any

from lonora_contracts.owner_actions import OwnerActionProposal
from lonora_core.user_error import LonoraError
from lonora_db.agent_binding import agent_binding
from lonora_db.owner_actions import card_facts, live_status, propose
from lonora_db.runs import require_lease
from lonora_db.schema import OwnerActionRow, RunRow, ThreadRow
from lonora_db.transactions import owned_thread
from sqlalchemy.ext.asyncio import AsyncSession

from .base import EffectStage, Tool
from .context import ToolContext


async def mandate_target(
    context: ToolContext, proposal: OwnerActionProposal
) -> OwnerActionProposal:
    """Whose mode the Mandate card switches: the proposer's own, or any agent for Lonora."""
    target = proposal.agent_id or context.agent_id
    async with context.db.sessions() as session:
        proposer = await agent_binding(session, context.owner_id, context.agent_id)
        if target != context.agent_id and proposer.role != "personal":
            raise LonoraError("owner_action_trading_mode_agent_forbidden", 403)
        await agent_binding(session, context.owner_id, target)
    return proposal.model_copy(update={"agent_id": target})


# What a card's live status says the proposal did: the owner is asked until he taps it.
CARD_EFFECT: dict[str, EffectStage] = {"pending": "requested", "confirmed": "confirmed"}


def card_summary(
    row: OwnerActionRow, created: bool, thread_id: str, passkey: bool
) -> dict[str, Any]:
    status = live_status(row)
    return {
        "owner_action": {
            "id": row.id,
            "kind": row.kind,
            "status": status,
            "expires_at": row.expires_at.isoformat(),
        },
        # The stored card, not proof the owner saw it.
        "effect": CARD_EFFECT.get(status, "failed"),
        "repeated": not created,
        "stored_in_thread": row.thread_id == thread_id,
        # The owner decides on the card; nothing has changed yet.
        "owner_must_tap": True,
        "passkey_required": passkey,
        "execution_authorized": False,
    }


async def card_scope(context: ToolContext, session: AsyncSession) -> tuple[RunRow, ThreadRow]:
    """The Run and the conversation a card of this Run belongs in."""
    run = await require_lease(session, context.lease)
    if run.agent_id != context.agent_id:
        raise LonoraError("agent_run_mismatch", 409)
    origin = run.model_metadata.get("origin_thread_id") or context.thread_id
    thread = await owned_thread(session, context.owner_id, origin)
    if thread.agent_id not in {context.agent_id, None}:
        raise LonoraError("agent_thread_mismatch", 409)
    return run, thread


async def propose_card(context: ToolContext, args: dict[str, Any]) -> dict[str, Any]:
    proposal = OwnerActionProposal.model_validate(args)
    if proposal.kind == "trading_mode":
        proposal = await mandate_target(context, proposal)
    async with context.db.sessions() as session, session.begin():
        run, thread = await card_scope(context, session)
        row, created = await propose(
            session,
            context.owner_id,
            proposal,
            card_id=context.resource_id,
            agent_id=context.agent_id,
            thread_id=thread.id,
            run_id=run.id,
        )
        # Fenced after the conversation lock: the thread-before-run order of message admission.
        await require_lease(session, context.lease, lock=True)
        _, passkey = await card_facts(session, row, row.updated_at)
        return card_summary(row, created, thread.id, passkey)


def tools() -> list[Tool]:
    return [
        Tool(
            "owner_action_propose",
            "Put a one-tap owner action card in this conversation for an action only the "
            "owner may take; nothing changes until the owner taps it. Kinds: trading_mode (the "
            "Mandate card: the owner switches an agent between Full and Ask, and only this tap "
            "sets Full; show it when the owner asks for an agent with full authority; optional "
            "agent_id, Lonora's for any agent), "
            "settle_operation (operation_id of an ambiguous operation; the owner "
            "answers executed / not executed / unknown; Executed or Not executed releases "
            "its hold, Unknown keeps it held and the card pending) and secret, "
            "the Secret card: the owner's values go straight to the encrypted store and you "
            "learn only the names saved. Ask non-secret details in chat first. To connect "
            "something, give target: mcp_server (name, unless service x for an X MCP "
            "server), news_feed or economic_calendar (name; for these three the owner types "
            "the address, which may carry a key, and a server's optional token), "
            "brave_search (web search key) or model_provider (name: the provider id; for "
            "openai_compatible the owner types the base URL with the key); a trading "
            "account is broker_connect. Any other "
            "credential: label and secret_fields, each a key (the name it is saved under), a "
            "label, and secret false only for a value safe to show while typed; write the "
            "labels in the owner's language. There is no grant card. The card "
            "shows server facts (a Secret card also your label, field labels and the details "
            "you gave); say in one line what it does. A repeated proposal returns the card "
            "already stored; at most five of yours wait at once.",
            OwnerActionProposal,
            propose_card,
            replay_safe=True,
        ),
    ]
