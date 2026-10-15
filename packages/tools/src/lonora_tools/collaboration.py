import hashlib
import json
from typing import Any

from lonora_contracts.collaboration import (
    CollaborationCreate,
    CollaborationFinish,
    CollaborationReference,
    CollaborationState,
)
from lonora_contracts.domain import utcnow
from lonora_core.user_error import LonoraError
from lonora_db.collaboration import CollaborationRepository, invite
from lonora_db.events import emit
from lonora_db.runs import locked_run_thread, require_lease
from lonora_db.schema import EffectReceiptRow, RunRow
from lonora_db.transactions import resource_data
from sqlalchemy import select

from .base import Tool
from .context import ToolContext


async def start(context: ToolContext, args: dict[str, Any]) -> dict[str, Any]:
    async with context.db.sessions() as session, session.begin():
        run, thread = await locked_run_thread(session, context.lease)
        key = context.effect_key + ":collaboration"
        intent = hashlib.sha256(json.dumps(args, sort_keys=True).encode()).hexdigest()
        previous = await session.get(EffectReceiptRow, key)
        if previous:
            if previous.result.get("intent", intent) != intent:
                raise LonoraError("collaboration_intent_conflict", 409)
            return resource_data(
                await CollaborationRepository().get(
                    session, context.owner_id, previous.result["session_id"]
                )
            )
        result = await invite(
            session,
            context.owner_id,
            thread,
            run,
            args["participant_ids"],
            args["subject"],
            message_id=context.call_id,
            session_id=args.get("session_id"),
        )
        session.add(
            EffectReceiptRow(key=key, result={"session_id": result["id"], "intent": intent})
        )
        return result


async def inspect(context: ToolContext, args: dict[str, Any]) -> dict[str, Any]:
    async with context.db.sessions() as session:
        row = await CollaborationRepository().get(session, context.owner_id, args["session_id"])
        if row.agent_id != context.agent_id:
            raise LonoraError("collaboration_host_required", 403)
        data = resource_data(row)
        state = CollaborationState.model_validate(row.state)
        run = await require_lease(session, context.lease)
        requested = run.model_metadata.get("collaboration_round_id")
        round = next(
            (r for r in state.rounds if r.id == requested),
            state.rounds[-1] if state.rounds else None,
        )
        if round:
            outcomes = await session.scalars(
                select(RunRow).where(RunRow.id.in_(round.participant_run_ids))
            )
            data["round_outcomes"] = [
                {
                    "run_id": r.id,
                    "agent_id": r.agent_id,
                    "status": r.status,
                    "result": (r.result or "")[:2000],
                    "error_code": r.error_code,
                    "source_message_id": r.model_metadata.get("collaboration_return_message_id"),
                }
                for r in outcomes
            ]
        return data


async def finish(context: ToolContext, args: dict[str, Any]) -> dict[str, Any]:
    async with context.db.sessions() as session, session.begin():
        await require_lease(session, context.lease)
        row = await CollaborationRepository().get(
            session, context.owner_id, args["session_id"], lock=True
        )
        if row.agent_id != context.agent_id or row.thread_id != context.thread_id:
            raise LonoraError("collaboration_host_required", 403)
        state = CollaborationState.model_validate(row.state)
        if any(item.status in {"invited", "working"} for item in state.participants):
            raise LonoraError("collaboration_participants_pending", 409)
        if state.status == "completed":
            return resource_data(row)
        if state.status == "cancelled":
            raise LonoraError("collaboration_closed", 409)
        state.status = "completed"
        state.final_result, state.conflicts = args["final_result"], args.get("conflicts", [])
        row.state = state.model_dump(mode="json")
        row.version += 1
        row.updated_at = utcnow()
        emit(
            session,
            context.owner_id,
            "collaboration.completed",
            thread_id=row.thread_id,
            agent_id=row.agent_id,
            payload={"id": row.id, "version": row.version},
        )
        return resource_data(row)


def tools() -> list[Tool]:
    return [
        Tool(
            "collaboration_start",
            "Invite selected owned agents to contribute evidence in their own scoped peer runs. Real outcomes return as attributed guests in this conversation. No authority is shared.",
            CollaborationCreate,
            start,
        ),
        Tool(
            "collaboration_inspect",
            "Read actual participant status and attributed results without waiting for all participants. Conflicts require evidence analysis, never majority voting.",
            CollaborationReference,
            inspect,
            True,
        ),
        Tool(
            "collaboration_finish",
            "Close a completed evidence discussion with a bounded synthesis and material conflicts. Never invent participant evidence or treat majority voting as a trading decision. This does not grant execution authority.",
            CollaborationFinish,
            finish,
        ),
    ]
