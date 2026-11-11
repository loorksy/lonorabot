from typing import Any

from lonora_contracts.domain import Contract
from lonora_contracts.reactions import REACTION_EMOJIS
from lonora_core.user_error import LonoraError
from lonora_db.schema import MessageRow
from pydantic import Field
from sqlalchemy import select

from .base import Tool, eager_for
from .context import ToolContext


class PeerInput(Contract):
    agent_id: str
    task: str = Field(min_length=1, max_length=8000)


class ReactInput(Contract):
    # Omit it to react to the owner message this turn answers (the usual case).
    message_id: str | None = Field(default=None, min_length=1, max_length=36)
    # One of the six quick reactions; null or empty removes this agent's reaction.
    emoji: str | None = Field(default=None, max_length=16)


async def send(context: ToolContext, args: dict[str, Any]) -> dict[str, Any]:
    from lonora_agent.collaboration.peer_messages import delegate_peer

    return await delegate_peer(context, args["agent_id"], args["task"])


async def react(context: ToolContext, args: dict[str, Any]) -> dict[str, Any]:
    from lonora_db.reactions import agent_reaction
    from lonora_db.runs import require_lease

    async with context.db.sessions() as session, session.begin():
        run = await require_lease(session, context.lease)
        message_id = args.get("message_id")
        if not message_id:
            # The owner message this turn answers: ids are never shown to the model.
            message_id = await session.scalar(
                select(MessageRow.id).where(
                    MessageRow.thread_id == context.thread_id,
                    MessageRow.seq == run.input_seq,
                    MessageRow.role == "user",
                )
            )
            if message_id is None:
                raise LonoraError("message_not_found", 404)
        return await agent_reaction(
            session,
            context.owner_id,
            context.agent_id,
            context.thread_id,
            message_id,
            args.get("emoji") or None,
        )


def tools() -> list[Tool]:
    return [
        Tool(
            "peer_send",
            "Ask an existing owned agent for help. Its outcome returns durably to this run/thread.",
            PeerInput,
            send,
            eager=eager_for("coordination"),
        ),
        Tool(
            "message_react",
            "React to the owner's message you are answering (omit message_id) with one quick "
            "emoji ("
            + " ".join(REACTION_EMOJIS)
            + "); it replaces your previous reaction there, and a null or empty emoji removes "
            "it. React only when it is genuinely fitting, for example acknowledging a request "
            "you are about to do. Never react to every message, and a reaction never replaces "
            "an answer the owner is waiting for. Call and system notices take no reaction.",
            ReactInput,
            react,
            replay_safe=True,
        ),
    ]
