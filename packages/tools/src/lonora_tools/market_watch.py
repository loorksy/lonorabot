import hashlib
import json
from decimal import Decimal
from typing import Any

from lonora_contracts.domain import Contract, utcnow
from lonora_contracts.market_watch import Watch
from lonora_db.genui_taint import taint_row_from
from lonora_db.market_watches import (
    MarketWatchRepository,
    WatchAction,
    control_watch,
    steered_watch,
    stop_watch,
    update_watch,
    watch_active,
)
from lonora_db.notice_cards import raise_watch_changed
from lonora_db.owner_actions import lock_owner_actions
from lonora_db.runs import require_lease
from lonora_db.schema import EventRow, MarketWatchRow, RunRow
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
    row = await session.scalar(
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
    # An expired watch is enabled and will never fire: the request gets a new one.
    return row if row is not None and watch_active(row) else None


async def identical_watch(
    session: AsyncSession, context: ToolContext, run: RunRow, thread_id: str, args: dict[str, Any]
) -> MarketWatchRow | None:
    """This Agent's live watch with exactly this condition, in the same conversation or
    Task: a repeated identical request (a model that asks again after a worker restart or
    a later wake re-arming what is already armed) keeps the one watch, never adds one."""
    stored = await MarketWatchRepository().stored_payload(
        session, context.owner_id, context.agent_id, args
    )
    if session.get_bind().dialect.name == "postgresql":
        digest = hashlib.sha256(
            json.dumps(stored, sort_keys=True, default=str).encode()
        ).hexdigest()
        await session.execute(
            text("SELECT pg_advisory_xact_lock(hashtextextended(:key, 0))"),
            {"key": "watch-identical:" + context.agent_id + ":" + digest},
        )
    task_id = run.model_metadata.get("task_id")
    for row in await session.scalars(
        select(MarketWatchRow)
        .where(
            MarketWatchRow.owner_id == context.owner_id,
            MarketWatchRow.agent_id == context.agent_id,
            MarketWatchRow.thread_id == thread_id,
            MarketWatchRow.payload["enabled"].as_boolean().is_(True),
        )
        .order_by(MarketWatchRow.created_at.desc())
        .limit(50)
        .with_for_update()
    ):
        if row.payload == stored and row.state.get("task_id") == task_id and watch_active(row):
            return row
    return None


async def create(context: ToolContext, args: dict[str, Any]) -> dict[str, Any]:
    async with context.db.sessions() as session, session.begin():
        run = await require_lease(session, context.lease, lock=True)
        row = await session.get(MarketWatchRepository.row_type, context.resource_id)
        if row is not None:
            return resource_data(row)
        # A wake's watch belongs to the Agent's conversation, like one set up in chat;
        # a Task's watch stays with the Task's own work.
        thread_id = (
            context.thread_id
            if run.model_metadata.get("task_id")
            else await report_thread(session, run)
        )
        key = args.get("dedupe_key")
        if not isinstance(key, str):
            same = await identical_watch(session, context, run, thread_id, args)
            if same is not None:
                return {**resource_data(same), "deduplicated": True}
        existing = await keyed_watch(session, context, key) if isinstance(key, str) else None
        if existing is not None:
            # Compare what would be stored, server-filled fields included.
            if existing.payload == await MarketWatchRepository().stored_payload(
                session, context.owner_id, context.agent_id, args
            ):
                return {**resource_data(existing), "deduplicated": True}
            # A changed condition replaces the live watch for this key, never adds one.
            stop_watch(existing, "watch_replaced")
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
        row = await MarketWatchRepository().create(
            session,
            context.owner_id,
            args,
            agent_id=context.agent_id,
            thread_id=thread_id,
            resource_id=context.resource_id,
        )
        if run.model_metadata.get("task_id"):
            row.state = {
                **row.state,
                "task_id": run.model_metadata["task_id"],
                "task_run_id": run.id,
            }
        # A watch tainted work created wakes tainted (GENUI_PLAN §8.5).
        await taint_row_from(session, run, "watch", row.id)
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
        # Tainted work that resumes or steers a watch taints it (GENUI_PLAN §8.5).
        await taint_row_from(session, run, "watch", row.id)
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
        run = await require_lease(session, context.lease, lock=True)
        # The owner's cards before the watch: the order the notice's Undo takes them in.
        await lock_owner_actions(session, context.owner_id)
        before = await steered_watch(session, context.owner_id, params.watch_id, context.agent_id)
        previous, version = before.payload.get("expires_at"), before.version
        row = await update_watch(
            session,
            context.owner_id,
            params.watch_id,
            agent_id=context.agent_id,
            expires_at=params.expires_at,
            clear_expiry=params.clear_expiry,
            level=params.level,
        )
        await taint_row_from(session, run, "watch", row.id)
        if row.version != version:
            # An extension the owner did not ask for shows as a notice with Undo (Q31).
            await raise_watch_changed(
                session,
                context.owner_id,
                row,
                previous,
                agent_id=context.agent_id,
                thread_id=await report_thread(session, run),
                run_id=run.id,
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
            eager=eager_for("market"),
        ),
        Tool(
            "watch_cancel",
            "Stop one of your own watches; its record stays, and watch_resume undoes it.",
            WatchReference,
            cancel,
            replay_safe=True,
            eager=eager_for("market"),
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
