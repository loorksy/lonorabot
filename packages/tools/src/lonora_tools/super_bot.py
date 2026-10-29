from typing import Any, Literal

from lonora_contracts.domain import Contract
from lonora_contracts.super_bot import SuperBotProposal
from lonora_core.user_error import LonoraError
from lonora_db.conversation_locale import conversation_locale
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
        await authority_lock(session, context.agent_id)
        await require_lease(session, context.lease, lock=True)
        locale = await conversation_locale(session, context.owner_id, context.thread_id)
        summary = (
            "طلب التفعيل جاهز للمراجعة وتأكيد هويتك من الجهاز. لم يُفعّل التداول التلقائي بعد."
            if locale == "ar"
            else "The activation request is ready for review and device authentication. Automatic trading is not enabled yet."
        )
        key = "super-bot-proposal:" + context.resource_id
        receipt = await session.get(EffectReceiptRow, key)
        if receipt:
            if receipt.result["intent"] != digest:
                raise LonoraError("super_bot_proposal_conflict", 409)
            data = request_data(
                await owned_request(session, context.owner_id, receipt.result["request_id"])
            )
            return {
                **data,
                "owner_summary": summary if data["status"] == "pending" else "",
                "internal_ids_are_private": True,
            }
        row = await propose(session, context.owner_id, context.agent_id, body)
        session.add(EffectReceiptRow(key=key, result={"intent": digest, "request_id": row.id}))
        return {**request_data(row), "owner_summary": summary, "internal_ids_are_private": True}


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
        await authority_lock(session, context.agent_id)
        await require_lease(session, context.lease, lock=True)
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
            "Prepare a legacy Super Bot request for an existing goal. This never grants current financial permission. Live trading follows the Agent permission selector and matching signed AccountAuthority; never claim activation from a pending result or chat agreement.",
            SuperBotProposal,
            proposal,
        ),
        Tool(
            "super_bot_status",
            "Read this Agent's historical Super Bot request state. This does not establish current financial permission or active AccountAuthority. Global Trading ON/OFF and Emergency Stop independently govern execution.",
            Empty,
            status,
            True,
        ),
        Tool(
            "super_bot_stop",
            "Pause/stop this Agent's legacy Super Bot Goal requests. Does not revoke separate AccountAuthority; use current permission controls for that. Never close broker positions as a side effect.",
            Stop,
            stop,
        ),
    ]
