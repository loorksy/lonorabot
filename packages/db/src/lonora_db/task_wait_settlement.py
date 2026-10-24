"""Commit a real Task suspension and its optional owner update atomically."""

from typing import Any, Literal, cast

from lonora_contracts.domain import utcnow
from lonora_contracts.runs import Lease
from lonora_core.user_error import LonoraError
from lonora_session.idempotency import stable_id
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from .events import emit
from .generated_artifacts import link_generated_artifacts, resolve_reply_artifacts
from .messages import message_data
from .runs import locked_run_thread
from .schema import EffectReceiptRow, MessageRow, SteeringRow, ThreadRow, TicketRow
from .streaming import settle_stream, stream_identity
from .tasks import checkpoint_task, save_task, task_state


async def settle_task_wait(
    session: AsyncSession, lease: Lease, text: str, call_id: str | None
) -> Literal["settled", "continue", "suspended"]:
    """Publish only after admission, lease and owner control still agree.

    The source tool has already committed its wait receipt. This second boundary
    closes the crash window without mistaking a prose promise for monitoring.
    Its update identity is the actual wait call, independent of worker fences.
    """
    run, work = await locked_run_thread(session, lease)
    task = await session.get(
        TicketRow,
        run.model_metadata.get("task_id", ""),
        with_for_update=True,
        populate_existing=True,
    )
    if (
        task is None
        or task.owner_id != work.owner_id
        or task.agent_id != run.agent_id
        or task.thread_id != run.thread_id
        or task.payload.get("run_id") != run.id
    ):
        raise LonoraError("task_run_mismatch", 409)
    state = task_state(task)
    if state.control_requested or state.status in {"paused", "completed", "failed", "cancelled"}:
        # A normal checkpoint would turn an admitted wait back into "running".
        # Only invoke it here when an owner/terminal transition must be applied.
        await checkpoint_task(session, lease)
        return "suspended"
    environment = dict(run.execution_state.get("environment", {}))
    wait = environment.get("wait")
    outstanding = await session.scalar(
        select(SteeringRow.id)
        .where(SteeringRow.run_id == run.id, SteeringRow.consumed.is_(False))
        .limit(1)
    )
    if outstanding or not wait:
        # A revision can withdraw the wait between admission and settlement.
        # Resume the same execution so it can consume the latest owner input.
        environment.pop("wait", None)
        environment.pop("wait_update", None)
        environment["phase"] = "revalidating"
        run.execution_state = {**run.execution_state, "environment": environment}
        state.status, state.phase, state.waiting_reason = "running", "revalidating", None
        save_task(session, task, state)
        return "continue"
    if not isinstance(wait, dict):
        raise LonoraError("task_wait_identity_invalid", 409)
    wait = cast(dict[str, Any], wait)
    if (
        not call_id
        or wait.get("call_id") != call_id
        or wait.get("run_id") != run.id
        or wait.get("task_id") != task.id
    ):
        raise LonoraError("task_wait_identity_invalid", 409)
    admission = await session.get(EffectReceiptRow, "task-wait:" + stable_id(run.id, call_id))
    if admission is None or admission.result != wait:
        raise LonoraError("task_wait_receipt_invalid", 409)
    raw_update = environment.get("wait_update")
    update = cast(dict[str, Any], raw_update) if isinstance(raw_update, dict) else None
    if text and (update is None or update.get("call_id") != call_id or update.get("text") != text):
        raise LonoraError("task_wait_update_invalid", 409)
    key = "task-wait-update:" + stable_id(run.id, call_id)
    previous = await session.get(EffectReceiptRow, key)
    message: MessageRow | None = None
    if previous is None:
        origin = await session.get(
            ThreadRow, state.origin_thread_id, with_for_update=True, populate_existing=True
        )
        if origin is None or origin.owner_id != work.owner_id or origin.agent_id != run.agent_id:
            raise LonoraError("task_origin_thread_invalid", 409)
        answer, artifacts = await resolve_reply_artifacts(session, work.owner_id, run, text)
        if answer or artifacts:
            message = MessageRow(
                thread_id=origin.id,
                agent_id=run.agent_id,
                role="assistant",
                seq=origin.next_seq,
                content=answer,
            )
            origin.next_seq += 1
            session.add(message)
            await session.flush()
            link_generated_artifacts(message, artifacts)
            emit(
                session,
                work.owner_id,
                "message.created",
                thread_id=origin.id,
                agent_id=run.agent_id,
                run_id=run.id,
                payload=message_data(message),
            )
        session.add(
            EffectReceiptRow(
                key=key,
                result={
                    "run_id": run.id,
                    "task_id": task.id,
                    "message_id": message.id if message else None,
                },
            )
        )
    elif previous.result.get("message_id"):
        # A pause/resume or worker replacement may settle the same admission
        # again. Preserve its committed stream identity without redelivery.
        message = await session.get(MessageRow, previous.result["message_id"])
        if (
            message is None
            or message.thread_id != state.origin_thread_id
            or message.agent_id != run.agent_id
        ):
            raise LonoraError("task_wait_update_invalid", 409)
    snapshot = settle_stream(
        run,
        "committed" if message else "discarded",
        message_id=message.id if message else None,
        text=message.content if message else "",
    )
    if snapshot:
        emit(
            session,
            work.owner_id,
            "run.reply_committed",
            thread_id=state.origin_thread_id,
            agent_id=run.agent_id,
            run_id=run.id,
            payload=stream_identity(snapshot),
        )
    run.status, run.lease_expires_at, run.updated_at = "waiting_takeover", None, utcnow()
    state.status, state.phase, state.waiting_reason = (
        "waiting",
        "waiting",
        "external_" + str(wait["kind"]),
    )
    save_task(session, task, state)
    emit(
        session,
        work.owner_id,
        "task.waiting",
        thread_id=state.origin_thread_id,
        agent_id=run.agent_id,
        run_id=run.id,
        payload={"id": task.id, "source_kind": wait["kind"]},
    )
    return "settled"
