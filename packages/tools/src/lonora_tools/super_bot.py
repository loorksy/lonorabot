from typing import Any, Literal

from lonora_contracts.domain import Contract
from lonora_contracts.super_bot import SuperBotProposal
from lonora_core.user_error import LonoraError
from lonora_db.runs import require_lease
from lonora_db.schema import EffectReceiptRow, SuperBotRequestRow
from lonora_db.super_bot import authority_lock, owned_request, propose, request_data, stop_request
from lonora_session.idempotency import request_hash
from sqlalchemy import select

from .base import Tool
from .context import ToolContext
from .memory import Empty


class Stop(Contract):
    action: Literal["pause", "stop"] = "pause"


async def proposal(context: ToolContext, args: dict[str, Any]) -> dict[str, Any]:
    body = SuperBotProposal.model_validate(args)
    digest = request_hash(body.model_dump(mode="json"))
    async with context.db.sessions() as session, session.begin():
        await require_lease(session, context.lease, lock=True)
        key = "super-bot-proposal:" + context.resource_id
        receipt = await session.get(EffectReceiptRow, key)
        if receipt:
            if receipt.result["intent"] != digest:
                raise LonoraError("super_bot_proposal_conflict", 409)
            return request_data(
                await owned_request(session, context.owner_id, receipt.result["request_id"])
            )
        row = await propose(session, context.owner_id, context.agent_id, body)
        session.add(EffectReceiptRow(key=key, result={"intent": digest, "request_id": row.id}))
        return request_data(row)


async def status(context: ToolContext, args: dict[str, Any]) -> dict[str, Any]:
    async with context.db.sessions() as session:
        rows = await session.scalars(
            select(SuperBotRequestRow)
            .where(
                SuperBotRequestRow.owner_id == context.owner_id,
                SuperBotRequestRow.agent_id == context.agent_id,
            )
            .order_by(SuperBotRequestRow.created_at.desc())
            .limit(10)
        )
        return {"requests": [request_data(row) for row in rows]}


async def stop(context: ToolContext, args: dict[str, Any]) -> dict[str, Any]:
    async with context.db.sessions() as session, session.begin():
        await require_lease(session, context.lease, lock=True)
        await authority_lock(session, context.agent_id)
        rows = list(
            await session.scalars(
                select(SuperBotRequestRow)
                .where(
                    SuperBotRequestRow.owner_id == context.owner_id,
                    SuperBotRequestRow.agent_id == context.agent_id,
                    SuperBotRequestRow.status.in_(["pending", "activated"]),
                )
                .order_by(SuperBotRequestRow.goal_id)
            )
        )
        for row in rows:
            await stop_request(
                session, row, "paused" if args.get("action", "pause") == "pause" else "disabled"
            )
        return {"requests": [request_data(row) for row in rows], "positions_closed": False}


def tools() -> list[Tool]:
    return [
        Tool(
            "super_bot_propose",
            "Prepare a persistent Super Bot activation card for an existing goal. This grants NO authority. The owner must review the frozen permissions and complete cryptographically verified device authentication in the UI. Never claim activation from this pending result or from spoken/typed approval.",
            SuperBotProposal,
            proposal,
        ),
        Tool(
            "super_bot_status",
            "Read this Agent's authoritative Super Bot requests and active authority. Global Trading ON/OFF and Emergency Stop still independently govern execution.",
            Empty,
            status,
            True,
        ),
        Tool(
            "super_bot_stop",
            "Immediately pause/stop this Agent's Super Bot authority without device authentication. Never close broker positions as a side effect.",
            Stop,
            stop,
        ),
    ]
