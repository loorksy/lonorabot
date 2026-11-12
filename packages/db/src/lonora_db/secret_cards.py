"""The Secret card (VISION.md 7.2, 10.3): how a credential reaches Lonora.

The agent chooses the card's label and fields (each a key, the name agents use, and a
label the owner reads); the server sets where the values go. The owner's values go
straight to the encrypted store in the same transaction that settles the card; the card,
its events and the conversation keep only the keys. The agent learns "saved".
"""

from collections.abc import Awaitable, Callable
from typing import Any

from lonora_contracts.owner_actions import OwnerActionProposal
from lonora_core.user_error import LonoraError
from sqlalchemy.ext.asyncio import AsyncSession

from .schema import OwnerActionRow
from .secrets import WORKSPACE

# Writes one value to the encrypted store in the caller's transaction; returns its id.
SecretWriter = Callable[[AsyncSession, str, str, str], Awaitable[str]]


def secret_card_payload(proposal: OwnerActionProposal) -> tuple[str, dict[str, Any]]:
    """A card the agent raised: its own label and fields, for the workspace."""
    assert proposal.label is not None and proposal.secret_fields is not None
    fields = [field.model_dump(mode="json") for field in proposal.secret_fields]
    keys = sorted(field["key"] for field in fields)
    return "secret:" + WORKSPACE + ":" + ",".join(keys), {
        "label": proposal.label,
        "fields": fields,
        "destination": WORKSPACE,
    }


def secret_facts(payload: dict[str, Any], agent_name: str | None) -> dict[str, Any]:
    """What the card shows: its label and fields, where the values go, and who asked."""
    return {
        "label": payload["label"],
        "fields": payload["fields"],
        "destination": payload["destination"],
        "agent_name": agent_name,
    }


async def save_values(
    session: AsyncSession, row: OwnerActionRow, values: dict[str, str], write: SecretWriter
) -> dict[str, Any]:
    """Store the owner's values for exactly the card's fields; the card's result keeps
    the keys only."""
    keys = [field["key"] for field in row.payload["fields"]]
    if set(values) != set(keys):
        raise LonoraError("owner_action_secret_values_invalid", 422)
    for key in keys:
        await write(session, key, values[key], row.payload["destination"])
    return {"saved": keys, "destination": row.payload["destination"]}


def saved_prompt(row: OwnerActionRow) -> str:
    """The agent's next run after the owner saved: the keys (checked names), never a
    value and never the agent's own label."""
    keys = ", ".join(row.result.get("saved", []))
    return (
        f"The owner saved {keys} on your Secret card as {row.result.get('destination')} "
        "secrets; you never see their values. Continue the work that needed them now, then "
        "tell the owner in one line what you did."
    )
