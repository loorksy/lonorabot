"""Native visual documents use the existing fenced message and event transaction."""

from copy import deepcopy
from pathlib import Path
from typing import Any, cast

import pytest
from lonora_adapter_kit.types import ModelMessage, ModelReply, ToolCall
from lonora_adapters.models.anthropic import anthropic_messages
from lonora_adapters.models.openai_compatible import wire_message
from lonora_agent.collaboration.outcome_return import return_outcome
from lonora_agent.executor import execute_run
from lonora_agent.recovery import restore_execution
from lonora_agent.tool_loop import external_wait_outcome, wait_update
from lonora_contracts.domain import MessageCreate
from lonora_contracts.model_routing import ModelSelection
from lonora_contracts.runs import Lease, RunRequest
from lonora_contracts.tasks import TaskControl, TaskCreate
from lonora_core.user_error import LonoraError
from lonora_db.client import Database
from lonora_db.messages import history, message_data, send_message
from lonora_db.rich_response import validated_rich_content
from lonora_db.runs import claim_next, complete_run, create_run
from lonora_db.schema import AgentRow, EventRow, MessageRow, RunRow, ThreadRow
from lonora_db.streaming import settle_stream, start_stream, stream_data, stream_identity
from lonora_db.task_wait_settlement import settle_task_wait
from lonora_db.tasks import control_task, create_task, get_task
from lonora_tools.context import ToolContext
from lonora_tools.registry import ToolRegistry
from sqlalchemy import select
from test_task_runtime import task_db as task_db
from test_task_wait_settlement import admitted

RICH: dict[str, Any] = {
    "version": 1,
    "parts": [
        {"type": "text", "text": "Here is an illustrative calculation."},
        {
            "type": "ui",
            "document": {
                "version": 1,
                "mode": "example",
                "root": {
                    "id": "summary",
                    "type": "card",
                    "children": [
                        {"id": "heading", "type": "heading", "text": "Illustration"},
                        {"id": "result", "type": "metric", "label": "Value", "value": 42},
                    ],
                },
            },
        },
        {"type": "text", "text": "This does not execute a trade."},
    ],
}


async def leased(fixture: tuple[Database, str, str, str]) -> Lease:
    db, owner, _, thread = fixture
    async with db.sessions() as session, session.begin():
        sent = await send_message(session, owner, thread, MessageCreate(content="Explain visually"))
        run = await claim_next(session, "visual-writer", 120, "conversation")
        assert run and run.id in sent["run_ids"]
        run.status = "running"
        lease = Lease(run_id=run.id, owner="visual-writer", fence=run.lease_fence)
        start_stream(run, lease, "visual-turn")
        return lease


@pytest.mark.parametrize("unsupported", ["javascript", "html", "trade_execute"])
def test_publication_rejects_unsupported_actions_and_component_types(unsupported: str):
    raw = deepcopy(RICH)
    raw["parts"][1]["document"]["root"]["type"] = unsupported
    assert validated_rich_content(raw) is None


def test_compiled_document_preserves_order_without_materializing_unsupported_defaults():
    assert validated_rich_content(RICH) == RICH
    assert validated_rich_content({"version": 99, "parts": []}) is None
    raw = deepcopy(RICH)
    raw["parts"][1]["document"]["root"]["children"][1]["value"] = {
        "fact": {"call_id": "unresolved", "path": "balance"}
    }
    assert validated_rich_content(raw) is None


@pytest.mark.parametrize("action", ["trade_execute", "grant", "api", "javascript"])
def test_visual_actions_cannot_become_an_alternate_financial_authority(action: str):
    raw = deepcopy(RICH)
    raw["parts"][1]["document"]["root"] = {
        "id": "action",
        "type": "button",
        "label": "Execute",
        "action": {"kind": action},
    }
    assert validated_rich_content(raw) is None


def test_runtime_display_checkpoint_never_becomes_an_extra_provider_wire_field():
    message = ModelMessage(role="assistant", content="Readable fallback.", rich_content=RICH)
    saved = message.model_dump(mode="json")
    assert saved["rich_content"] == RICH
    assert wire_message(message) == {"role": "assistant", "content": "Readable fallback."}
    assert anthropic_messages([message]) == (
        "",
        [{"role": "assistant", "content": [{"type": "text", "text": "Readable fallback."}]}],
    )


@pytest.mark.asyncio
@pytest.mark.parametrize("visual", [True, False])
async def test_same_agent_loop_checkpoints_and_publishes_only_current_reply(
    task_db: tuple[Database, str, str, str], monkeypatch: pytest.MonkeyPatch, visual: bool
):
    """A resumed prior visual turn must not decorate a newer plain answer."""
    db, owner, agent, thread = task_db
    lease = await leased(task_db)
    async with db.sessions() as session, session.begin():
        run = await session.get(RunRow, lease.run_id)
        assert run
        run.execution_state = {
            "messages": [ModelMessage(role="user", content="Explain.").model_dump(mode="json")],
            "instruction_skill_ids": [],
            "rich_content": RICH,
        }
    calls = 0

    async def complete(*args: Any, **kwargs: Any) -> tuple[ModelReply, ModelSelection]:
        nonlocal calls
        calls += 1
        return ModelReply(
            text="Current answer.", rich_content=deepcopy(RICH) if visual else None
        ), ModelSelection(provider="openai", model="scripted-visual-reply")

    monkeypatch.setattr("lonora_agent.tool_loop.model_turn", complete)
    context = ToolContext(
        db,
        owner,
        agent,
        thread,
        lease,
        cast(Any, None),
        cast(Any, None),
        cast(Any, None),
        cast(Any, None),
        Path("/tmp/visual-persistence-fixture"),
    )
    await execute_run(context, ToolRegistry([]), 120, 4)
    async with db.sessions() as session:
        run = await session.get(RunRow, lease.run_id)
        assert run and run.status == "completed"
        rows = await history(session, owner, thread)
        assert calls == 1 and len(rows) == 2
        assert rows[-1].content == "Current answer."
        assert rows[-1].rich_content == (RICH if visual else None)
        assert run.execution_state["messages"][-1]["rich_content"] == (RICH if visual else None)
        assert run.execution_state.get("rich_content") == (RICH if visual else None)
        assert run.model_metadata["rich_content"] == (RICH if visual else None)


@pytest.mark.asyncio
async def test_canonical_reply_event_and_fenced_snapshot_commit_the_same_document(
    task_db: tuple[Database, str, str, str],
):
    db, owner, _, thread = task_db
    lease = await leased(task_db)
    async with db.sessions() as session, session.begin():
        assert await complete_run(session, lease, "Ordinary fallback.", {"rich_content": RICH})
    async with db.sessions() as session:
        rows = await history(session, owner, thread)
        answer = rows[-1]
        assert answer.role == "assistant" and answer.content == "Ordinary fallback."
        assert answer.rich_content == RICH
        assert message_data(answer)["rich_content"] == RICH
        run = await session.get(RunRow, lease.run_id)
        assert run and run.status == "completed" and run.model_metadata["rich_content"] == RICH
        snapshot = stream_data(run)
        assert snapshot and snapshot["phase"] == "committed"
        assert snapshot["rich_content"] == RICH and snapshot["message_id"] == answer.id
        events = list(
            await session.scalars(
                select(EventRow).where(
                    EventRow.run_id == run.id,
                    EventRow.kind.in_(["message.created", "run.reply_committed"]),
                )
            )
        )
        assert len(events) == 2
        assert all(item.payload["rich_content"] == RICH for item in events)
    with pytest.raises(LonoraError, match="stale_lease"):
        async with db.sessions() as session, session.begin():
            await complete_run(session, lease, "Duplicate", {"rich_content": RICH})
    async with db.sessions() as session:
        assert len(await history(session, owner, thread)) == 2


@pytest.mark.asyncio
async def test_rollback_and_stale_worker_cannot_publish_visual_content(
    task_db: tuple[Database, str, str, str],
):
    db, owner, _, thread = task_db
    lease = await leased(task_db)
    async with db.sessions() as session:
        await session.begin()
        await complete_run(session, lease, "Not committed", {"rich_content": RICH})
        await session.rollback()
    async with db.sessions() as session, session.begin():
        assert len(await history(session, owner, thread)) == 1
        run = await session.get(RunRow, lease.run_id)
        assert run and run.status == "running"
        assert "rich_content" not in (stream_data(run) or {})
        run.lease_fence += 1
    with pytest.raises(LonoraError, match="stale_lease"):
        async with db.sessions() as session, session.begin():
            await complete_run(session, lease, "Lost worker", {"rich_content": RICH})
    async with db.sessions() as session:
        assert len(await history(session, owner, thread)) == 1


@pytest.mark.asyncio
async def test_invalid_ui_falls_back_to_text_and_owner_metadata_cannot_forge_ui(
    task_db: tuple[Database, str, str, str],
):
    db, owner, agent, thread = task_db
    async with db.sessions() as session, session.begin():
        created = await create_run(
            session,
            owner,
            RunRequest(thread_id=thread, agent_id=agent, metadata={"rich_content": RICH}),
        )
        assert "rich_content" not in created.model_metadata
        run = await claim_next(session, "visual-writer", 120, "conversation")
        assert run
        run.status = "running"
        lease = Lease(run_id=run.id, owner="visual-writer", fence=run.lease_fence)
        start_stream(run, lease, "invalid-visual")
        invalid = {"version": 1, "parts": [{"type": "html", "text": "<script>evil</script>"}]}
        assert await complete_run(session, lease, "Readable fallback", {"rich_content": invalid})
    async with db.sessions() as session:
        rows = await history(session, owner, thread)
        assert len(rows) == 1 and rows[0].content == "Readable fallback"
        assert rows[0].rich_content is None


def test_cancelled_stream_drops_previous_visual_data_and_checkpoint_preserves_wait_identity():
    run = RunRow(input_seq=1, model_metadata={})
    lease = Lease(run_id="run", owner="worker", fence=1)
    start_stream(run, lease, "first")
    snapshot = settle_stream(run, "committed", message_id="message", rich_content=RICH)
    assert snapshot and snapshot["rich_content"] == RICH
    assert stream_identity(snapshot)["rich_content"] == RICH
    snapshot = start_stream(run, lease, "replacement")
    assert "rich_content" not in snapshot
    snapshot = settle_stream(run, "cancelled", rich_content=RICH)
    assert snapshot and "rich_content" not in snapshot
    call = ToolCall(id="wait", name="task_wait", arguments={"kind": "timer"})
    message = ModelMessage(
        role="assistant", content="Review later.", rich_content=RICH, tool_calls=[call]
    )
    restored, _ = restore_execution({"messages": [message.model_dump(mode="json")]})
    update = wait_update(restored, call.id)
    assert update["rich_content"] == RICH
    outcome = external_wait_outcome(
        {"environment": {"wait": {"call_id": call.id}, "wait_update": update}}
    )
    assert outcome.metadata["rich_content"] == RICH


@pytest.mark.asyncio
async def test_admitted_task_wait_publishes_visual_owner_update_atomically(
    task_db: tuple[Database, str, str, str],
):
    db, _, _, origin = task_db
    text = "Review after the next close."
    lease, _, state = await admitted(task_db, update=text)
    state["environment"]["wait_update"]["rich_content"] = RICH
    async with db.sessions() as session, session.begin():
        run = await session.get(RunRow, lease.run_id)
        assert run
        run.execution_state = state
        assert (
            await settle_task_wait(session, lease, text, "actual-wait", rich_content=RICH)
            == "settled"
        )
    async with db.sessions() as session:
        rows = list(await session.scalars(select(MessageRow).where(MessageRow.thread_id == origin)))
        assert len(rows) == 1 and rows[0].rich_content == RICH
        run = await session.get(RunRow, lease.run_id)
        assert run and (stream_data(run) or {})["rich_content"] == RICH


@pytest.mark.asyncio
async def test_wait_visual_update_must_belong_to_the_exact_admitted_content(
    task_db: tuple[Database, str, str, str],
):
    db, _, _, origin = task_db
    text = "Review after the next close."
    lease, _, state = await admitted(task_db, update=text)
    state["environment"]["wait_update"]["rich_content"] = RICH
    async with db.sessions() as session, session.begin():
        run = await session.get(RunRow, lease.run_id)
        assert run
        run.execution_state = state
    forged = deepcopy(RICH)
    forged["parts"][1]["document"]["root"]["children"][1]["value"] = 999
    with pytest.raises(LonoraError, match="task_wait_update_invalid"):
        async with db.sessions() as session, session.begin():
            await settle_task_wait(session, lease, text, "actual-wait", rich_content=forged)
    async with db.sessions() as session:
        assert not await history(session, task_db[1], origin)


@pytest.mark.asyncio
@pytest.mark.parametrize("action", ["pause", "cancel"])
async def test_owner_control_withdraws_unpublished_visual_update(
    task_db: tuple[Database, str, str, str], action: Any
):
    db, owner, _, origin = task_db
    text = "Review later."
    lease, task_id, state = await admitted(task_db, update=text)
    state["environment"]["wait_update"]["rich_content"] = RICH
    async with db.sessions() as session, session.begin():
        run = await session.get(RunRow, lease.run_id)
        assert run
        run.execution_state = state
        task = await get_task(session, owner, task_id)
        await control_task(
            session,
            owner,
            TaskControl(task_id=task_id, expected_version=task.version, action=action),
        )
    async with db.sessions() as session, session.begin():
        assert (
            await settle_task_wait(session, lease, text, "actual-wait", rich_content=RICH)
            == "suspended"
        )
    async with db.sessions() as session:
        assert not await history(session, owner, origin)


@pytest.mark.asyncio
async def test_rich_only_task_result_returns_to_origin_once(
    task_db: tuple[Database, str, str, str],
):
    db, owner, agent, origin = task_db
    async with db.sessions() as session, session.begin():
        task = await create_task(session, owner, agent, origin, TaskCreate(title="Explain"))
        run = await claim_next(session, "visual-task", 120, "work")
        assert run and run.id == task.payload["run_id"]
        run.status = "running"
        lease = Lease(run_id=run.id, owner="visual-task", fence=run.lease_fence)
        assert await complete_run(session, lease, "", {"rich_content": RICH})
    await return_outcome(db, lease.run_id)
    await return_outcome(db, lease.run_id)
    async with db.sessions() as session:
        rows = await history(session, owner, origin)
        assert len(rows) == 1 and rows[0].rich_content == RICH


@pytest.mark.asyncio
async def test_peer_return_preserves_validated_visual_content_once(
    task_db: tuple[Database, str, str, str],
):
    db, owner, _, thread = task_db
    parent = await leased(task_db)
    async with db.sessions() as session, session.begin():
        peer = AgentRow(owner_id=owner, name="Visual colleague")
        session.add(peer)
        await session.flush()
        peer_thread = ThreadRow(owner_id=owner, agent_id=peer.id)
        session.add(peer_thread)
        await session.flush()
        child = RunRow(
            thread_id=peer_thread.id,
            agent_id=peer.id,
            parent_run_id=parent.run_id,
            trigger="peer",
            status="completed",
            result="Sourced peer answer.",
            model_metadata={"rich_content": RICH},
            lease_fence=1,
        )
        session.add(child)
        await session.flush()
        child_id = child.id
    await return_outcome(db, child_id)
    await return_outcome(db, child_id)
    async with db.sessions() as session:
        rows = await history(session, owner, thread)
        assert len(rows) == 2 and rows[-1].rich_content == RICH
        assert rows[-1].agent_id == peer.id
