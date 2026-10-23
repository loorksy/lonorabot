"""Model-selected escalation consumes existing meaningful owner attention."""

from typing import Any

from lonora_contracts.incoming_calls import IncomingCallRequest
from lonora_db.attention import attention_data
from lonora_db.runs import require_lease
from lonora_db.schema import AttentionRow
from lonora_voice.incoming import call_data, request_call
from sqlalchemy import select

from .base import Tool
from .context import ToolContext
from .memory import Empty


async def request(context: ToolContext, arguments: dict[str, Any]) -> dict[str, Any]:
    async with context.db.sessions() as session, session.begin():
        await require_lease(session, context.lease, lock=True)
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
        ),
        Tool(
            "owner_call_request",
            "Request an incoming conversation for a current meaningful attention item owned by this "
            "agent and thread. Requires owner opt-in, enrolled device, allowed category, quiet-hours "
            "and rate policy. Delivery may be unavailable; a persisted request is not proof the device "
            "rang. Accepting never authorizes financial operations. Ordinary updates stay in chat.",
            IncomingCallRequest,
            request,
            replay_safe=True,
        ),
    ]
