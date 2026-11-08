"""Propose an owner action card in the conversation. Agents propose; only the owner acts.

The card is validated against current state, deduplicated per agent and effect, and
capped per agent. What the owner sees on it is derived on the server from the records it
names; nothing the agent writes appears on it. No tool can confirm a card: the owner's
tap goes to an owner-session route that runs the existing owner function, and widening
money limits needs the owner's passkey there.
"""

from typing import Any

from lonora_contracts.owner_actions import OwnerActionProposal
from lonora_core.user_error import LonoraError
from lonora_db.owner_actions import card_facts, live_status, propose
from lonora_db.runs import require_lease
from lonora_db.transactions import owned_thread

from .base import Tool
from .context import ToolContext


async def propose_card(context: ToolContext, args: dict[str, Any]) -> dict[str, Any]:
    proposal = OwnerActionProposal.model_validate(args)
    async with context.db.sessions() as session, session.begin():
        run = await require_lease(session, context.lease)
        if run.agent_id != context.agent_id:
            raise LonoraError("agent_run_mismatch", 409)
        origin = run.model_metadata.get("origin_thread_id") or context.thread_id
        thread = await owned_thread(session, context.owner_id, origin)
        if thread.agent_id not in {context.agent_id, None}:
            raise LonoraError("agent_thread_mismatch", 409)
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
        return {
            "owner_action": {
                "id": row.id,
                "kind": row.kind,
                "status": live_status(row),
                "expires_at": row.expires_at.isoformat(),
            },
            "already_shown": not created,
            "shown_in_conversation": row.thread_id == thread.id,
            # The owner decides on the card; nothing has changed yet.
            "owner_must_tap": True,
            "passkey_required": passkey,
            "execution_authorized": False,
        }


def tools() -> list[Tool]:
    return [
        Tool(
            "owner_action_propose",
            "Put a one-tap owner action card in this conversation for an action only the "
            "owner may take; nothing changes until the owner taps it. Kinds: resume_trading "
            "(new trading is stopped and the owner wants it back), lift_restriction "
            "(restriction_id of an active or scheduled pause the owner wants lifted), "
            "resolve_operation (operation_id of an ambiguous operation; the owner answers "
            "executed / not executed / still unknown) and set_account_limits (account_id "
            "with set_limits amounts in the account currency or percentages, and/or "
            "remove_limits; currency when setting an amount for the first time). Lowering "
            "or adding a limit is one tap; raising or removing one needs the owner's "
            "passkey. The card shows only server facts; say in one line what it does. A "
            "repeated proposal returns the card already shown; at most five of yours wait "
            "at once.",
            OwnerActionProposal,
            propose_card,
            replay_safe=True,
        ),
    ]
