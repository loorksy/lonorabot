"""Real ledger suspension, admission/control races and owner-update delivery."""

from typing import Any

import pytest
from lonora_adapter_kit.types import ModelMessage, ToolCall
from lonora_contracts.runs import Lease
from lonora_contracts.tasks import TaskControl, TaskCreate, TaskWait
from lonora_core.user_error import LonoraError
from lonora_db.client import Database
from lonora_db.runs import checkpoint, claim_next
from lonora_db.schema import (
    ArtifactRow,
    EffectReceiptRow,
    EventRow,
    MessageRow,
    RunRow,
    SteeringRow,
)
from lonora_db.streaming import start_stream
from lonora_db.task_wait import prepare_wait
from lonora_db.task_wait_settlement import settle_task_wait
from lonora_db.tasks import control_task, create_task, get_task, task_state
from lonora_session.idempotency import stable_id
from sqlalchemy import func, select
from test_task_runtime import task_db as task_db


async def admitted(
    fixture: tuple[Database, str, str, str], *, update: str = "I will review after the next close."
) -> tuple[Lease, str, dict[str, Any]]:
    db, owner, agent, thread = fixture
    async with db.sessions() as session, session.begin():
        task = await create_task(session, owner, agent, thread, TaskCreate(title="Follow market"))
        run = await claim_next(session, "wait-test", 120, "work")
        assert run is not None and run.id == task.payload["run_id"]
        run.status = "running"
        lease = Lease(run_id=run.id, owner="wait-test", fence=run.lease_fence)
        start_stream(run, lease, "wait-update")
        wait = await prepare_wait(session, lease, TaskWait(kind="timer", seconds=60), "actual-wait")
        state: dict[str, Any] = {
            "environment": {
                "wait": wait,
                "wait_update": {"call_id": "actual-wait", "text": update},
            },
            "messages": [
                ModelMessage(
                    role="assistant",
                    content=update,
                    tool_calls=[
                        ToolCall(id="actual-wait", name="task_wait", arguments={"kind": "timer"})
                    ],
                ).model_dump(mode="json")
            ],
        }
        await checkpoint(session, lease, state)
        return lease, task.id, state


async def delivered(db: Database, origin: str) -> list[MessageRow]:
    async with db.sessions() as session:
        return list(
            await session.scalars(
                select(MessageRow).where(MessageRow.thread_id == origin).order_by(MessageRow.seq)
            )
        )


@pytest.mark.asyncio
async def test_settlement_commits_real_wait_and_update_together(
    task_db: tuple[Database, str, str, str],
):
    db, _, _, origin = task_db
    lease, task_id, _ = await admitted(task_db)
    async with db.sessions() as session, session.begin():
        assert (
            await settle_task_wait(
                session, lease, "I will review after the next close.", "actual-wait"
            )
            == "settled"
        )
    messages = await delivered(db, origin)
    assert len(messages) == 1 and messages[0].content == "I will review after the next close."
    async with db.sessions() as session:
        run = await session.get(RunRow, lease.run_id)
        task = await get_task(session, task_db[1], task_id)
        receipt = await session.get(
            EffectReceiptRow, "task-wait-update:" + stable_id(lease.run_id, "actual-wait")
        )
        assert run and run.status == "waiting_takeover" and run.lease_expires_at is None
        assert task_state(task).status == "waiting" and receipt
        assert receipt.result["message_id"] == messages[0].id
        assert run.model_metadata["reply_stream"]["message_id"] == messages[0].id
        assert run.model_metadata["reply_stream"]["phase"] == "committed"
        assert (
            await session.scalar(
                select(func.count()).select_from(EventRow).where(EventRow.kind == "message.created")
            )
            == 1
        )


@pytest.mark.asyncio
async def test_rollback_and_resume_redeliver_once(task_db: tuple[Database, str, str, str]):
    db, owner, _, origin = task_db
    lease, task_id, _ = await admitted(task_db)
    with pytest.raises(RuntimeError, match="crash"):
        async with db.sessions() as session, session.begin():
            await settle_task_wait(
                session, lease, "I will review after the next close.", "actual-wait"
            )
            raise RuntimeError("crash")
    assert not await delivered(db, origin)
    async with db.sessions() as session, session.begin():
        await settle_task_wait(session, lease, "I will review after the next close.", "actual-wait")
    async with db.sessions() as session, session.begin():
        task = await get_task(session, owner, task_id)
        await control_task(
            session,
            owner,
            TaskControl(task_id=task.id, expected_version=task.version, action="pause"),
        )
    async with db.sessions() as session, session.begin():
        task = await get_task(session, owner, task_id)
        await control_task(
            session,
            owner,
            TaskControl(task_id=task.id, expected_version=task.version, action="resume"),
        )
        run = await claim_next(session, "replacement", 120, "work")
        assert run and run.id == lease.run_id
        run.status = "running"
        replacement = Lease(run_id=run.id, owner="replacement", fence=run.lease_fence)
    async with db.sessions() as session, session.begin():
        await settle_task_wait(
            session, replacement, "I will review after the next close.", "actual-wait"
        )
    messages = await delivered(db, origin)
    assert len(messages) == 1
    async with db.sessions() as session:
        run = await session.get(RunRow, lease.run_id)
        assert run and run.model_metadata["reply_stream"]["message_id"] == messages[0].id
        assert (
            await session.scalar(
                select(func.count()).select_from(EventRow).where(EventRow.kind == "message.created")
            )
            == 1
        )


@pytest.mark.asyncio
@pytest.mark.parametrize("action", ["pause", "cancel"])
async def test_owner_control_between_admission_and_settlement_wins(
    task_db: tuple[Database, str, str, str], action: Any
):
    db, owner, _, origin = task_db
    lease, task_id, _ = await admitted(task_db)
    async with db.sessions() as session, session.begin():
        task = await get_task(session, owner, task_id)
        await control_task(
            session,
            owner,
            TaskControl(task_id=task.id, expected_version=task.version, action=action),
        )
    async with db.sessions() as session, session.begin():
        assert (
            await settle_task_wait(
                session, lease, "I will review after the next close.", "actual-wait"
            )
            == "suspended"
        )
    assert not await delivered(db, origin)
    async with db.sessions() as session:
        run = await session.get(RunRow, lease.run_id)
        task = await get_task(session, owner, task_id)
        assert run and run.status == ("waiting_takeover" if action == "pause" else "cancelled")
        assert task_state(task).status == ("paused" if action == "pause" else "cancelled")
        assert not task_state(task).control_requested


@pytest.mark.asyncio
async def test_pending_steering_withdraws_stale_wait_and_update(
    task_db: tuple[Database, str, str, str],
):
    db, owner, agent, origin = task_db
    lease, task_id, _ = await admitted(task_db)
    async with db.sessions() as session, session.begin():
        run = await session.get(RunRow, lease.run_id)
        assert run
        message = MessageRow(
            thread_id=run.thread_id, agent_id=agent, role="user", seq=1, content="Revise"
        )
        session.add(message)
        await session.flush()
        session.add(SteeringRow(run_id=run.id, message_id=message.id))
    async with db.sessions() as session, session.begin():
        assert (
            await settle_task_wait(
                session, lease, "I will review after the next close.", "actual-wait"
            )
            == "continue"
        )
    assert not await delivered(db, origin)
    async with db.sessions() as session:
        task = await get_task(session, owner, task_id)
        run = await session.get(RunRow, lease.run_id)
        assert task_state(task).status == "running" and run and run.status == "running"
        assert "wait" not in run.execution_state["environment"]
        assert "wait_update" not in run.execution_state["environment"]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("text", "call_id", "error"),
    [
        ("Forged update", "actual-wait", "task_wait_update_invalid"),
        ("I will review after the next close.", "invented-call", "task_wait_identity_invalid"),
        ("I will review after the next close.", None, "task_wait_identity_invalid"),
    ],
)
async def test_update_identity_cannot_be_invented(
    task_db: tuple[Database, str, str, str], text: str, call_id: str | None, error: str
):
    db, _, _, origin = task_db
    lease, _, _ = await admitted(task_db)
    with pytest.raises(LonoraError, match=error):
        async with db.sessions() as session, session.begin():
            await settle_task_wait(session, lease, text, call_id)
    assert not await delivered(db, origin)


@pytest.mark.asyncio
async def test_missing_admission_receipt_cannot_claim_monitoring(
    task_db: tuple[Database, str, str, str],
):
    db, _, _, origin = task_db
    lease, _, _ = await admitted(task_db)
    async with db.sessions() as session, session.begin():
        receipt = await session.get(
            EffectReceiptRow, "task-wait:" + stable_id(lease.run_id, "actual-wait")
        )
        assert receipt
        await session.delete(receipt)
    with pytest.raises(LonoraError, match="task_wait_receipt_invalid"):
        async with db.sessions() as session, session.begin():
            await settle_task_wait(
                session, lease, "I will review after the next close.", "actual-wait"
            )
    assert not await delivered(db, origin)


@pytest.mark.asyncio
async def test_wait_delivers_generated_artifact_with_actual_message_receipt(
    task_db: tuple[Database, str, str, str],
):
    db, owner, agent, origin = task_db
    lease, _, _ = await admitted(task_db, update="The analysis is ready.")
    async with db.sessions() as session, session.begin():
        run = await session.get(RunRow, lease.run_id)
        assert run
        artifact = ArtifactRow(
            owner_id=owner,
            agent_id=agent,
            thread_id=run.thread_id,
            payload={"name": "review.png", "media_type": "image/png", "key": "fixture/review.png"},
            state={"producer_run_id": run.id},
        )
        session.add(artifact)
        await session.flush()
        artifact_id = artifact.id
    async with db.sessions() as session, session.begin():
        assert (
            await settle_task_wait(session, lease, "The analysis is ready.", "actual-wait")
            == "settled"
        )
    messages = await delivered(db, origin)
    assert len(messages) == 1 and messages[0].attachment_ids == [artifact_id]
    async with db.sessions() as session:
        artifact = await session.get(ArtifactRow, artifact_id)
        assert artifact and artifact.state["delivered_message_id"] == messages[0].id


@pytest.mark.asyncio
async def test_legacy_wait_has_no_newly_published_private_prose(
    task_db: tuple[Database, str, str, str],
):
    db, _, _, origin = task_db
    lease, _, state = await admitted(task_db, update="Old private tool API narration")
    state["environment"].pop("wait_update")
    async with db.sessions() as session, session.begin():
        await checkpoint(session, lease, state)
    async with db.sessions() as session, session.begin():
        assert await settle_task_wait(session, lease, "", "actual-wait") == "settled"
    assert not await delivered(db, origin)
