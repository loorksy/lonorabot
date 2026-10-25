"""Validated replies publish atomically, independent of provider token framing."""

from importlib import import_module
from math import ceil
from types import SimpleNamespace
from typing import Any, cast
from unittest.mock import AsyncMock

import pytest
from lonora_adapter_kit.types import ModelMessage, ModelReply
from lonora_agent import model_runtime
from lonora_agent.progress import DELTA_CHUNK_CHARS, progress
from lonora_contracts.model_routing import Capability, ModelSelection
from lonora_contracts.runs import Lease
from lonora_contracts.tasks import TaskCreate
from lonora_core.user_error import LonoraError
from lonora_db.client import Database
from lonora_db.runs import claim_next
from lonora_db.schema import EventRow, RunRow
from lonora_db.streaming import MAX_STREAM_CHARS, start_stream, stream_data
from lonora_db.tasks import create_task
from lonora_security.secrets import redact
from lonora_tools.context import ToolContext
from sqlalchemy import event, select
from test_task_runtime import task_db as task_db


@pytest.mark.asyncio
async def test_many_provider_fragments_publish_one_accepted_reply(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    answer = "صباح النور. " * 150
    published = AsyncMock()

    async def complete(_capability: Any, _messages: Any, _tools: Any, **kwargs: Any):
        selection = ModelSelection(provider="openai", model="scripted")
        await kwargs["on_attempt"](selection)
        for character in answer:
            await kwargs["on_delta"](character)
            assert not any(item.args[1] == "run.delta" for item in published.await_args_list)
        return ModelReply(text=answer), selection

    async def images(
        _context: Any, messages: list[ModelMessage]
    ) -> tuple[list[ModelMessage], dict[str, Any]]:
        return messages, {}

    monkeypatch.setattr(model_runtime, "refresh_routing_context", AsyncMock())
    monkeypatch.setattr(model_runtime, "prepare_image_observations", images)
    monkeypatch.setattr(model_runtime, "save_usage", AsyncMock())
    monkeypatch.setattr(model_runtime, "progress", published)
    context = cast(
        ToolContext,
        SimpleNamespace(
            db=None,
            owner_id="owner",
            agent_id="agent",
            thread_id="thread",
            lease=SimpleNamespace(run_id="run"),
            router=SimpleNamespace(complete=complete),
        ),
    )
    reply, _ = await model_runtime.model_turn(
        context, [ModelMessage(role="user", content="صباح الخير")], [], Capability.CONVERSATION
    )
    deltas = [item for item in published.await_args_list if item.args[1] == "run.delta"]
    assert len(deltas) == 1 and deltas[0].args[2]["text"] == reply.text == answer


async def stream_context(fixture: tuple[Database, str, str, str]) -> ToolContext:
    db, owner, agent, origin = fixture
    async with db.sessions() as session, session.begin():
        task = await create_task(session, owner, agent, origin, TaskCreate(title="Reply delivery"))
        run = await claim_next(session, "batch-writer", 120, "work")
        assert run and run.id == task.payload["run_id"]
        run.status = "running"
        lease = Lease(run_id=run.id, owner="batch-writer", fence=run.lease_fence)
        start_stream(run, lease, "accepted-turn")
        return cast(
            ToolContext,
            SimpleNamespace(
                db=db, owner_id=owner, agent_id=agent, thread_id=run.thread_id, lease=lease
            ),
        )


@pytest.mark.asyncio
@pytest.mark.parametrize("length", [100, 3200, MAX_STREAM_CHARS + 50])
async def test_delta_chunks_and_snapshot_commit_in_one_fenced_transaction(
    task_db: tuple[Database, str, str, str], length: int
) -> None:
    context = await stream_context(task_db)
    commits = 0

    def committed(_connection: Any) -> None:
        nonlocal commits
        commits += 1

    event.listen(context.db.engine.sync_engine, "commit", committed)
    try:
        answer = "أ" * length
        await progress(context, "run.delta", {"turn_id": "accepted-turn", "text": answer})
        assert commits == 1
    finally:
        event.remove(context.db.engine.sync_engine, "commit", committed)
    async with context.db.sessions() as session:
        row = await session.get(RunRow, context.lease.run_id)
        assert row
        snapshot = stream_data(row)
        events = list(
            await session.scalars(
                select(EventRow)
                .where(EventRow.run_id == row.id, EventRow.kind == "run.delta")
                .order_by(EventRow.cursor)
            )
        )
        assert snapshot and snapshot["text"] == answer[:MAX_STREAM_CHARS]
        assert len(events) == snapshot["sequence"] == ceil(length / DELTA_CHUNK_CHARS)
        assert [item.payload["sequence"] for item in events] == list(range(1, len(events) + 1))
        assert all(item.payload["fence"] == context.lease.fence for item in events)
        assert all(item.payload["generation"] == snapshot["generation"] for item in events)
        assert all(len(item.payload["text"]) <= DELTA_CHUNK_CHARS for item in events)
        assert "".join(item.payload["text"] for item in events) == snapshot["text"]
        assert snapshot["truncated"] == (length > MAX_STREAM_CHARS)


@pytest.mark.asyncio
async def test_redaction_happens_before_splitting_a_bearer_secret(
    task_db: tuple[Database, str, str, str],
) -> None:
    context = await stream_context(task_db)
    answer = "x" * (DELTA_CHUNK_CHARS - 4) + "Bearer should-never-be-published end."
    await progress(context, "run.delta", {"turn_id": "accepted-turn", "text": answer})
    async with context.db.sessions() as session:
        row = await session.get(RunRow, context.lease.run_id)
        assert row
        snapshot = stream_data(row)
        assert snapshot and snapshot["text"] == redact(answer)
        assert "should-never-be-published" not in snapshot["text"]


@pytest.mark.asyncio
async def test_stale_turn_rolls_back_the_entire_delta_batch(
    task_db: tuple[Database, str, str, str],
) -> None:
    context = await stream_context(task_db)
    with pytest.raises(LonoraError, match="stale_stream_turn"):
        await progress(context, "run.delta", {"turn_id": "wrong-turn", "text": "x" * 3200})
    async with context.db.sessions() as session:
        row = await session.get(RunRow, context.lease.run_id)
        assert row
        snapshot = stream_data(row)
        assert snapshot and snapshot["sequence"] == 0 and snapshot["text"] == ""
        assert not list(
            await session.scalars(
                select(EventRow).where(EventRow.run_id == row.id, EventRow.kind == "run.delta")
            )
        )


@pytest.mark.asyncio
async def test_lost_worker_fence_cannot_publish_a_delta_batch(
    task_db: tuple[Database, str, str, str],
) -> None:
    context = await stream_context(task_db)
    async with context.db.sessions() as session, session.begin():
        row = await session.get(RunRow, context.lease.run_id)
        assert row
        row.lease_fence += 1
    with pytest.raises(LonoraError, match="stale_lease"):
        await progress(context, "run.delta", {"turn_id": "accepted-turn", "text": "x" * 3200})
    async with context.db.sessions() as session:
        row = await session.get(RunRow, context.lease.run_id)
        assert row
        snapshot = stream_data(row)
        assert snapshot and snapshot["sequence"] == 0 and snapshot["text"] == ""
        assert not list(
            await session.scalars(
                select(EventRow).where(EventRow.run_id == row.id, EventRow.kind == "run.delta")
            )
        )


@pytest.mark.asyncio
async def test_interruption_mid_batch_exposes_neither_partial_events_nor_partial_snapshot(
    task_db: tuple[Database, str, str, str], monkeypatch: pytest.MonkeyPatch
) -> None:
    context = await stream_context(task_db)
    writer = import_module("lonora_agent.progress")
    original = writer.append_stream

    def interrupted(row: RunRow, lease: Lease, turn: str, text: str):
        result = original(row, lease, turn, text)
        if result[0]["sequence"] == 2:
            raise RuntimeError("worker interrupted before commit")
        return result

    monkeypatch.setattr(writer, "append_stream", interrupted)
    with pytest.raises(RuntimeError, match="worker interrupted"):
        await progress(context, "run.delta", {"turn_id": "accepted-turn", "text": "x" * 3200})
    async with context.db.sessions() as session:
        row = await session.get(RunRow, context.lease.run_id)
        assert row
        snapshot = stream_data(row)
        assert snapshot and snapshot["sequence"] == 0 and snapshot["text"] == ""
        assert not list(
            await session.scalars(
                select(EventRow).where(EventRow.run_id == row.id, EventRow.kind == "run.delta")
            )
        )
