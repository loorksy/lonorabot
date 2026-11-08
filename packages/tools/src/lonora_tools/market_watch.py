from decimal import Decimal
from typing import Any

from lonora_contracts.domain import Contract, utcnow
from lonora_contracts.market_watch import Watch
from lonora_db.market_watches import (
    MarketWatchRepository,
    WatchAction,
    control_watch,
    update_watch,
)
from lonora_db.runs import require_lease
from lonora_db.schema import EventRow, MarketWatchRow
from lonora_db.threads import report_thread
from lonora_db.transactions import resource_data
from pydantic import AwareDatetime, Field
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from .base import Tool, eager_for
from .context import ToolContext
from .memory import Empty
from .restrictions import owner_message_id


async def keyed_watch(
    session: AsyncSession, context: ToolContext, key: str
) -> MarketWatchRow | None:
    """This Agent's live watch for a dedupe key, serialized per Agent and key."""
    if session.get_bind().dialect.name == "postgresql":
        await session.execute(
            text("SELECT pg_advisory_xact_lock(hashtextextended(:key, 0))"),
            {"key": "watch-dedupe:" + context.agent_id + ":" + key},
        )
    return await session.scalar(
        select(MarketWatchRow)
        .where(
            MarketWatchRow.owner_id == context.owner_id,
            MarketWatchRow.agent_id == context.agent_id,
            MarketWatchRow.payload["dedupe_key"].as_string() == key,
            MarketWatchRow.payload["enabled"].as_boolean().is_(True),
        )
        .order_by(MarketWatchRow.created_at.desc())
        .limit(1)
        .with_for_update()
    )


async def create(context: ToolContext, args: dict[str, Any]) -> dict[str, Any]:
    async with context.db.sessions() as session, session.begin():
        run = await require_lease(session, context.lease, lock=True)
        row = await session.get(MarketWatchRepository.row_type, context.resource_id)
        if row is not None:
            return resource_data(row)
        key = args.get("dedupe_key")
        existing = await keyed_watch(session, context, key) if isinstance(key, str) else None
        if existing is not None:
            # Compare what would be stored, server-filled fields included.
            if existing.payload == await MarketWatchRepository().stored_payload(
                session, context.owner_id, context.agent_id, args
            ):
                return {**resource_data(existing), "deduplicated": True}
            # A changed condition replaces the live watch for this key, never adds one.
            existing.payload = {**existing.payload, "enabled": False}
            existing.state = {**existing.state, "code": "watch_replaced"}
            existing.version += 1
            existing.updated_at = utcnow()
            session.add(
                EventRow(
                    owner_id=context.owner_id,
                    agent_id=existing.agent_id,
                    thread_id=existing.thread_id,
                    kind="market_watches.updated",
                    payload={"id": existing.id, "version": existing.version},
                )
            )
        # A wake's watch belongs to the Agent's conversation, like one set up in chat;
        # a Task's watch stays with the Task's own work.
        row = await MarketWatchRepository().create(
            session,
            context.owner_id,
            args,
            agent_id=context.agent_id,
            thread_id=context.thread_id
            if run.model_metadata.get("task_id")
            else await report_thread(session, run),
            resource_id=context.resource_id,
        )
        if run.model_metadata.get("task_id"):
            row.state = {
                **row.state,
                "task_id": run.model_metadata["task_id"],
                "task_run_id": run.id,
            }
        return resource_data(row)


async def read(context: ToolContext, args: dict[str, Any]) -> dict[str, Any]:
    async with context.db.sessions() as session:
        return {
            "watches": [
                resource_data(row)
                for row in await MarketWatchRepository().list(
                    session, context.owner_id, context.agent_id
                )
            ]
        }


class WatchReference(Contract):
    watch_id: str = Field(min_length=1, max_length=36)


class WatchUpdate(WatchReference):
    expires_at: AwareDatetime | None = Field(
        default=None, description="New expiry with a timezone offset, e.g. the session close."
    )
    clear_expiry: bool = Field(default=False, description="Watch until cancelled.")
    level: Decimal | None = Field(default=None, description="New price or indicator level.")


async def steer(context: ToolContext, watch_id: str, action: WatchAction) -> dict[str, Any]:
    async with context.db.sessions() as session, session.begin():
        run = await require_lease(session, context.lease, lock=True)
        row = await control_watch(
            session,
            context.owner_id,
            watch_id,
            action,
            agent_id=context.agent_id,
            owner_message=await owner_message_id(session, run) is not None,
        )
        return {
            **resource_data(row),
            "undo": "watch_resume" if action != "resume" else "watch_pause",
        }


async def cancel(context: ToolContext, args: dict[str, Any]) -> dict[str, Any]:
    return await steer(context, WatchReference.model_validate(args).watch_id, "cancel")


async def pause(context: ToolContext, args: dict[str, Any]) -> dict[str, Any]:
    return await steer(context, WatchReference.model_validate(args).watch_id, "pause")


async def resume(context: ToolContext, args: dict[str, Any]) -> dict[str, Any]:
    return await steer(context, WatchReference.model_validate(args).watch_id, "resume")


async def update(context: ToolContext, args: dict[str, Any]) -> dict[str, Any]:
    params = WatchUpdate.model_validate(args)
    async with context.db.sessions() as session, session.begin():
        await require_lease(session, context.lease, lock=True)
        row = await update_watch(
            session,
            context.owner_id,
            params.watch_id,
            agent_id=context.agent_id,
            expires_at=params.expires_at,
            clear_expiry=params.clear_expiry,
            level=params.level,
        )
        return resource_data(row)


def tools() -> list[Tool]:
    return [
        Tool(
            "watch_create",
            "Persist a server-side price, indicator, position, account, calendar or composite dynamic watch. A dynamic relationship detector compares this exact symbol with related_symbol on the same account, using closed-bar relationship_window evidence and relationship_states. It wakes this agent to reassess and never trades. One live watch per dedupe_key.",
            Watch,
            create,
            replay_safe=True,
            eager=eager_for("market"),
        ),
        Tool(
            "watch_list",
            "Read this agent's durable market watches.",
            Empty,
            read,
            True,
            poller=True,
        ),
        Tool(
            "watch_cancel",
            "Stop one of your own watches; its record stays, and watch_resume undoes it.",
            WatchReference,
            cancel,
            replay_safe=True,
        ),
        Tool(
            "watch_pause",
            "Pause one of your own watches until watch_resume.",
            WatchReference,
            pause,
            replay_safe=True,
        ),
        Tool(
            "watch_resume",
            "Resume one of your own paused or cancelled watches (an expired one needs a later "
            "expiry first, through watch_update).",
            WatchReference,
            resume,
            replay_safe=True,
        ),
        Tool(
            "watch_update",
            "Move the expiry or level of one of your own watches; its condition and market "
            "stay. A later expiry revives an expired watch.",
            WatchUpdate,
            update,
            replay_safe=True,
        ),
    ]
