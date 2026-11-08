"""Model-selected escalation consumes existing meaningful owner attention."""

from typing import Any

from lonora_contracts.incoming_calls import IncomingCallRequest
from lonora_db.attention import attention_data
from lonora_db.owner_profile import reach_me_policy
from lonora_db.runs import require_lease
from lonora_db.schema import AttentionRow
from lonora_voice.incoming import call_data, request_call
from sqlalchemy import select

from .base import Tool
from .context import ToolContext
from .memory import Empty

REACH_ME_RECOVERY = {
    "message": "The owner asked to be messaged instead of called: write the update in this "
    "conversation once.",
    "notify": "The owner asked for a notification instead of a call: keep the attention item "
    "and write one short update in this conversation.",
    "activity": "The owner asked not to be interrupted: keep it in the activity record and "
    "this conversation without calling.",
}


async def request(context: ToolContext, arguments: dict[str, Any]) -> dict[str, Any]:
    async with context.db.sessions() as session, session.begin():
        await require_lease(session, context.lease, lock=True)
        channel = (await reach_me_policy(session, context.owner_id)).channel
        if channel != "call":
            # The owner's reach-me preference decides the channel, not the Agent.
            return {
                "ok": False,
                "code": "owner_prefers_other_channel",
                "reach_me": channel,
                "recovery": REACH_ME_RECOVERY[channel],
                "execution_authorized": False,
            }
        row = await request_call(
            session,
            context.owner_id,
            arguments["attention_id"],
            arguments["reason"],
            agent_id=context.agent_id,
            thread_id=context.thread_id,
        )
        return {
            "call": call_data(row),
            "native_delivery": row.state.get("delivery", "pending"),
            "execution_authorized": False,
        }


async def read(context: ToolContext, arguments: dict[str, Any]) -> dict[str, Any]:
    async with context.db.sessions() as session:
        rows = await session.scalars(
            select(AttentionRow)
            .where(
                AttentionRow.owner_id == context.owner_id,
                AttentionRow.agent_id == context.agent_id,
                AttentionRow.thread_id == context.thread_id,
                AttentionRow.status == "ready",
            )
            .order_by(AttentionRow.updated_at.desc())
            .limit(20)
        )
        return {"attention": [attention_data(row) for row in rows]}


def tools() -> list[Tool]:
    return [
        Tool(
            "owner_attention_list",
            "Read meaningful current attention in this agent/thread before deciding whether contacting the owner is necessary.",
            Empty,
            read,
            read_only=True,
            poller=True,
        ),
        Tool(
            "owner_call_request",
            "Request an incoming conversation for a current meaningful attention item owned by this "
            "agent and thread. Requires reach-me call, enrolled device, allowed category, quiet-hours "
            "and rate policy. Delivery may be unavailable; a persisted request is not proof the device "
            "rang. Accepting never authorizes financial operations. Ordinary updates stay in chat.",
            IncomingCallRequest,
            request,
            replay_safe=True,
        ),
    ]
