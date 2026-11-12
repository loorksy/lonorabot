from datetime import UTC, datetime, timedelta
from typing import Any, cast

from lonora_contracts.domain import utcnow
from lonora_contracts.runs import WORK_TRIGGERS, Lease, RunFailure, RunRequest
from lonora_core.run_state import assert_transition
from lonora_core.runtime_failure import failure_family, retry_after_seconds
from lonora_core.user_error import LonoraError
from sqlalchemy import and_, exists, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased

from .events import emit
from .generated_artifacts import link_generated_artifacts, resolve_reply_artifacts
from .rich_response import validated_rich_content
from .schema import AgentRow, GroupRow, MessageRow, RunRow, SteeringRow, ThreadRow
from .streaming import STREAM_KEY, settle_stream, stream_data, stream_identity
from .transactions import owned_agent, owned_thread

# Crash recoveries a Run gets before the watchdog quarantines it instead of re-leasing it.
MAX_RUN_RECOVERIES = 5


def aware(value: datetime) -> datetime:
    return value if value.tzinfo else value.replace(tzinfo=UTC)


def outcome_status(row: RunRow) -> str:
    """The Run's outcome as projected to tickets, parents, peers and collaborations.

    A Run that stopped at its work limit (tool rounds, identical-effect halt) completes
    with an honest report so the owner sees it, but its work is unfinished: consumers
    read it as ``limited``, never as ``completed``.
    """
    if row.status == "completed" and row.model_metadata.get("reply_outcome") == "limited":
        return "limited"
    return row.status


def failure_data(row: RunRow) -> dict[str, Any] | None:
    """The failed Run's error family and the provider's retry hint, else None."""
    if row.status != "failed":
        return None
    stored = row.model_metadata.get("failure")
    if isinstance(stored, dict):
        return RunFailure.model_validate(stored).model_dump()
    return RunFailure(family=failure_family(row.error_code)).model_dump()


# The key, in a Run's execution state, of the picked choice the Run answers for: the
# calls the choice was bound to when it was offered (``lonora_agent.offers``).
OFFER_OBLIGATION = "offer_obligation"


def question_choices(item: dict[str, Any]) -> list[dict[str, Any]]:
    """A question's choices as clients get them: what a pick does, never the bound calls."""
    raw = item.get("effects")
    effects = cast(dict[str, Any], raw) if isinstance(raw, dict) else {}
    shown: list[dict[str, Any]] = []
    for stored in cast(list[Any], item.get("choices", [])):
        if not isinstance(stored, dict):
            continue
        choice = {
            key: value for key, value in cast(dict[str, Any], stored).items() if key != "actions"
        }
        if choice.get("id") in effects:
            choice["effects"] = effects[choice["id"]]
        shown.append(choice)
    return shown


def run_data(row: RunRow) -> dict[str, Any]:
    questions: list[dict[str, Any]] = []
    for raw in cast(list[Any], row.execution_state.get("input_requests", []))[-20:]:
        if not isinstance(raw, dict):
            continue
        item = cast(dict[str, Any], raw)
        if not all(key in item for key in ("id", "message_id", "question")):
            continue
        questions.append(
            {
                "id": item["id"],
                "run_id": row.id,
                "message_id": item["message_id"],
                "question": item["question"],
                "choices": question_choices(item),
                "status": "cancelled"
                if item.get("status") == "pending"
                and row.status in {"cancelled", "failed", "completed"}
                else item.get("status", "pending"),
                "selected_choice_id": item.get("selected_choice_id"),
                "answer_message_id": item.get("answer_message_id"),
            }
        )
    return {
        "input_requests": questions,
        "input_request": questions[-1] if questions else None,
        "id": row.id,
        "thread_id": row.thread_id,
        "agent_id": row.agent_id,
        "parent_run_id": row.parent_run_id,
        "status": row.status,
        "trigger": row.trigger,
        "input_seq": row.input_seq,
        "error_code": row.error_code,
        "failure": failure_data(row),
        "result": row.result,
        "model_metadata": row.model_metadata,
        "stream": stream_data(row),
        "created_at": row.created_at.isoformat(),
        "updated_at": row.updated_at.isoformat(),
    }


def inherited_authority(starter: RunRow | None) -> dict[str, Any]:
    """Run metadata that carries an observe-only Run's narrowing into work it starts.

    A Task or ticket started from an observe-only wake runs observe-only too, so
    neither it nor anything it delegates can send a broker mutation. Watches,
    routines are the Agent's own later work and are not narrowed.
    """
    if starter is None:
        return {}
    inherited: dict[str, Any] = {}
    if starter.model_metadata.get("authority") == "observe_only":
        inherited["authority"] = "observe_only"
        inherited["authority_run_id"] = str(
            starter.model_metadata.get("authority_run_id") or starter.id
        )
    return inherited


async def create_run(
    session: AsyncSession, owner_id: str, request: RunRequest, run_id: str | None = None
) -> RunRow:
    thread = await owned_thread(session, owner_id, request.thread_id, lock=True)
    agent = await owned_agent(session, owner_id, request.agent_id)
    if thread.agent_id and thread.agent_id != agent.id:
        raise LonoraError("agent_thread_mismatch", 409)
    if thread.group_id:
        group = await session.get(GroupRow, thread.group_id)
        if group is None or agent.id not in group.payload.get("member_ids", []):
            raise LonoraError("agent_not_group_member", 409)
    if request.parent_run_id:
        parent = await session.get(RunRow, request.parent_run_id)
        if parent is None:
            raise LonoraError("parent_run_not_found", 404)
        await owned_thread(session, owner_id, parent.thread_id)
    if agent.paused:
        raise LonoraError("agent_paused", 409)
    row = RunRow(
        thread_id=thread.id,
        agent_id=agent.id,
        trigger=request.trigger,
        prompt=request.prompt,
        parent_run_id=request.parent_run_id,
        input_seq=thread.next_seq - 1,
        model_metadata={
            key: value
            for key, value in request.metadata.items()
            # Skill snapshots and diagnostics are created under the Run fence.
            # Owner-supplied metadata must never impersonate bundled instructions.
            if key
            not in {
                STREAM_KEY,
                "result_message_id",
                "rich_content",
                "skill_snapshot",
                "skill_selection",
                "skill_authority",
                "skill_execution_image",
                # Only ``submit_card`` marks a card submission's own Run.
                "ui_submit_origin",
            }
        },
    )
    if run_id:
        row.id = run_id
    session.add(row)
    await session.flush()
    emit(
        session,
        owner_id,
        "run.queued",
        thread_id=thread.id,
        agent_id=agent.id,
        run_id=row.id,
        payload={"run": run_data(row)},
    )
    return row


async def claim_next(
    session: AsyncSession, worker_id: str, lease_seconds: int, lane: str | None = None
) -> RunRow | None:
    now = utcnow()
    from .genui_submit import expire_submits

    # Rule L: a card submission not started 30 minutes after it was sent is cancelled.
    await expire_submits(session)
    eligible = or_(
        RunRow.status == "queued",
        and_(
            RunRow.status.in_(["leased", "running"]),
            RunRow.lease_expires_at <= now,
            # Past the cap the watchdog decides: quarantine, or hold for reconciliation.
            RunRow.recovery_count < MAX_RUN_RECOVERIES,
        ),
    )
    # Server-owned checkpoint deadline reuses this claimant, not another timer
    # service. ISO UTC values are written only by the runtime under its fence.
    retry_at = RunRow.execution_state["environment"]["retry"]["not_before"].as_string()
    eligible = and_(eligible, or_(retry_at.is_(None), retry_at <= now.isoformat()))
    # Rule Q: a card submission's Run starts only after every earlier Run of its agent in
    # the thread has ended, so it never overtakes work in retry backoff, an open question
    # or an approved trade waiting for its execution (docs/genui.md).
    earlier = aliased(RunRow)
    behind = exists(
        select(earlier.id).where(
            earlier.thread_id == RunRow.thread_id,
            earlier.agent_id == RunRow.agent_id,
            earlier.id != RunRow.id,
            earlier.created_at < RunRow.created_at,
            earlier.status.not_in(["completed", "failed", "cancelled"]),
        )
    )
    eligible = and_(
        eligible,
        or_(RunRow.model_metadata["ui_submit_origin"].as_string().is_(None), ~behind),
    )
    if lane == "conversation":
        eligible = and_(
            eligible,
            RunRow.trigger.not_in(WORK_TRIGGERS),
        )
    elif lane == "work":
        eligible = and_(
            eligible,
            RunRow.trigger.in_(WORK_TRIGGERS),
        )
    active = exists(
        select(RunRow.id).where(
            RunRow.thread_id == ThreadRow.id,
            RunRow.status.in_(["leased", "running"]),
            RunRow.lease_expires_at > now,
        )
    )
    pending = exists(
        select(RunRow.id)
        .join(AgentRow, AgentRow.id == RunRow.agent_id)
        .where(RunRow.thread_id == ThreadRow.id, eligible, AgentRow.paused.is_(False))
    )
    # Claim the thread lock first so two queued turns cannot be claimed simultaneously.
    thread = await session.scalar(
        select(ThreadRow)
        .where(pending, ~active)
        .order_by(ThreadRow.created_at)
        .limit(1)
        .with_for_update(skip_locked=True)
    )
    if thread is None:
        return None
    row = await session.scalar(
        select(RunRow)
        .join(AgentRow, AgentRow.id == RunRow.agent_id)
        .where(RunRow.thread_id == thread.id, eligible, AgentRow.paused.is_(False))
        .order_by(RunRow.created_at)
        .limit(1)
        .with_for_update(skip_locked=True)
    )
    if row is None:
        return None
    recovered = row.status != "queued"
    # Consecutive crash recoveries; a claim from the queue means the last attempt ended
    # cleanly (completed a step, waited, or was released on drain).
    row.recovery_count = row.recovery_count + 1 if recovered else 0
    # A retry answers its failed Run's message, not the newest one. A submission's Run
    # reads the reply of the work it waited behind; its own message is read by id.
    if (
        (thread.group_id or row.model_metadata.get("ui_submit_origin"))
        and not row.execution_state
        and not row.model_metadata.get("retry_of")
    ):
        row.input_seq = max(row.input_seq, thread.next_seq - 1)
    row.status = "leased"
    row.lease_owner = worker_id
    row.lease_fence += 1
    row.lease_expires_at = now + timedelta(seconds=lease_seconds)
    row.updated_at = now
    row.error_code = None
    emit(
        session,
        thread.owner_id,
        "run.recovered" if recovered else "run.leased",
        thread_id=row.thread_id,
        agent_id=row.agent_id,
        run_id=row.id,
        payload={"fence": row.lease_fence, "run": run_data(row)},
    )
    await session.flush()
    return row


async def require_lease(session: AsyncSession, lease: Lease, lock: bool = False) -> RunRow:
    query = select(RunRow).where(RunRow.id == lease.run_id)
    if lock:
        query = query.with_for_update()
    row = await session.scalar(query.execution_options(populate_existing=True))
    if (
        row is None
        or row.status not in {"leased", "running"}
        or row.lease_owner != lease.owner
        or row.lease_fence != lease.fence
        or row.lease_expires_at is None
        or aware(row.lease_expires_at) <= utcnow()
    ):
        raise LonoraError("stale_lease", 409)
    return row


async def locked_run_thread(session: AsyncSession, lease: Lease) -> tuple[RunRow, ThreadRow]:
    """Use the same thread-before-run lock order as message admission and claiming."""
    row = await require_lease(session, lease)
    thread = await session.get(
        ThreadRow, row.thread_id, with_for_update=True, populate_existing=True
    )
    if thread is None:
        raise LonoraError("thread_not_found", 404)
    return await require_lease(session, lease, lock=True), thread


async def renew_lease(session: AsyncSession, lease: Lease, lease_seconds: int) -> None:
    row = await require_lease(session, lease, lock=True)
    row.lease_expires_at = utcnow() + timedelta(seconds=lease_seconds)


async def checkpoint(session: AsyncSession, lease: Lease, state: dict[str, Any]) -> None:
    row = await require_lease(session, lease, lock=True)
    row.execution_state = state
    row.updated_at = utcnow()


async def suggested_reply(
    session: AsyncSession,
    row: RunRow,
    metadata: dict[str, Any],
    rich_content: dict[str, Any] | None,
) -> str | None:
    """The agent's suggestion for the owner's next reply (Q23), kept only on a
    conversational answer to the owner: never with a generated interface, and never when
    this Run raised a card (owner action, trade approval or question)."""
    from .schema import OwnerActionRow, TradeApprovalRow

    value = metadata.get("suggested_reply")
    if not isinstance(value, str) or not value.strip() or len(value.strip()) > 60:
        return None
    if row.trigger not in {"user", "group"} or row.execution_state.get("input_requests"):
        return None
    if rich_content and any(part.get("type") == "ui" for part in rich_content.get("parts", [])):
        return None
    for card in (OwnerActionRow, TradeApprovalRow):
        if await session.scalar(select(card.id).where(card.run_id == row.id).limit(1)):
            return None
    return value.strip()


async def complete_run(
    session: AsyncSession, lease: Lease, answer: str, metadata: dict[str, Any]
) -> bool:
    row, thread = await locked_run_thread(session, lease)
    outstanding = await session.scalar(
        select(SteeringRow.id)
        .where(SteeringRow.run_id == row.id, SteeringRow.consumed.is_(False))
        .limit(1)
    )
    if outstanding:
        return False
    from .tasks import require_completed_task_steps

    await require_completed_task_steps(session, row)
    assert_transition(row.status, "completed")
    final_message_id: str | None = None
    final_message: MessageRow | None = None
    answer, artifacts = await resolve_reply_artifacts(session, thread.owner_id, row, answer)
    rich_content = validated_rich_content(metadata.get("rich_content"))
    if (answer or artifacts or rich_content) and row.trigger != "tickets":
        message = MessageRow(
            thread_id=thread.id,
            agent_id=row.agent_id,
            role="assistant",
            seq=thread.next_seq,
            content=answer,
            rich_content=rich_content,
            suggested_reply=await suggested_reply(session, row, metadata, rich_content),
        )
        thread.next_seq += 1
        session.add(message)
        await session.flush()
        link_generated_artifacts(message, artifacts)
        final_message_id = message.id
        final_message = message
    snapshot = settle_stream(
        row,
        "committed" if final_message_id else "discarded",
        message_id=final_message_id,
        text=answer if final_message_id else "",
        rich_content=rich_content if final_message_id else None,
    )
    if snapshot:
        emit(
            session,
            thread.owner_id,
            "run.reply_committed",
            thread_id=thread.id,
            agent_id=row.agent_id,
            run_id=row.id,
            payload=stream_identity(snapshot),
        )
    if final_message:
        from .messages import message_data

        emit(
            session,
            thread.owner_id,
            "message.created",
            thread_id=thread.id,
            agent_id=row.agent_id,
            run_id=row.id,
            payload=message_data(final_message),
        )
    row.status = "completed"
    row.result = answer
    row.model_metadata = {
        **row.model_metadata,
        **{
            key: value
            for key, value in metadata.items()
            if key not in {STREAM_KEY, "result_message_id"}
        },
    }
    row.model_metadata = {
        **row.model_metadata,
        "result_message_id": final_message_id,
        "rich_content": rich_content,
    }
    row.updated_at = utcnow()
    row.lease_expires_at = None
    emit(
        session,
        thread.owner_id,
        "run.completed",
        thread_id=thread.id,
        agent_id=row.agent_id,
        run_id=row.id,
    )
    return True


async def fail_run(
    session: AsyncSession,
    lease: Lease,
    code: str,
    *,
    read_only_names: set[str] | None = None,
    reason: str | None = None,
    retry_after: float | None = None,
) -> None:
    """``reason`` and ``retry_after`` are the provider's classified reason and its
    ``Retry-After`` hint, when the failure came from a model provider."""
    row = await require_lease(session, lease, lock=True)
    row.status = "failed"
    settle_stream(row, "failed")
    row.error_code = code
    failure = RunFailure(
        family=failure_family(code, reason), retry_after_seconds=retry_after_seconds(retry_after)
    ).model_dump()
    row.model_metadata = {**row.model_metadata, "failure": failure}
    row.updated_at = utcnow()
    row.lease_expires_at = None
    if row.model_metadata.get("task_id"):
        from .task_recovery import record_failure

        await record_failure(session, row, read_only_names or set())
    thread = await session.get(ThreadRow, row.thread_id)
    if thread:
        emit(
            session,
            thread.owner_id,
            "run.failed",
            thread_id=row.thread_id,
            agent_id=row.agent_id,
            run_id=row.id,
            payload={"code": code, "failure": failure},
        )


async def release_leases(session: AsyncSession, owner: str) -> list[str]:
    """Graceful drain: this process's leased Runs go back to the queue at once.

    The fence is kept (the next claim increments it), so a late write from the old
    lease is still rejected; the checkpoint and its in-flight markers stay untouched.
    """
    identifiers = list(
        await session.scalars(
            select(RunRow.id).where(
                RunRow.lease_owner == owner, RunRow.status.in_(["leased", "running"])
            )
        )
    )
    released: list[str] = []
    for identifier in identifiers:
        candidate = await session.get(RunRow, identifier)
        if candidate is None:
            continue
        thread = await session.get(
            ThreadRow, candidate.thread_id, with_for_update=True, populate_existing=True
        )
        row = await session.get(RunRow, identifier, with_for_update=True, populate_existing=True)
        if row is None or row.lease_owner != owner or row.status not in {"leased", "running"}:
            continue
        row.status, row.lease_expires_at, row.updated_at = "queued", None, utcnow()
        released.append(row.id)
        if thread:
            emit(
                session,
                thread.owner_id,
                "run.queued",
                thread_id=row.thread_id,
                agent_id=row.agent_id,
                run_id=row.id,
                payload={"reason_code": "gateway_drained", "run": run_data(row)},
            )
    return released


async def quarantine_run(
    session: AsyncSession, run_id: str, read_only_names: set[str]
) -> str | None:
    """A Run that crashed its worker too often is failed instead of re-leased forever.

    Returns ``"failed"``, ``"held"`` when an unresolved financial operation of the Run
    must be reconciled first (it is never failed silently over an uncertain trade), or
    None when the Run is no longer over the cap.
    """
    from .task_recovery import record_failure, unresolved_financial

    candidate = await session.get(RunRow, run_id)
    if candidate is None:
        return None
    thread = await session.get(
        ThreadRow, candidate.thread_id, with_for_update=True, populate_existing=True
    )
    row = await session.get(RunRow, run_id, with_for_update=True, populate_existing=True)
    if (
        row is None
        or row.status not in {"leased", "running"}
        or row.recovery_count < MAX_RUN_RECOVERIES
        or (row.lease_expires_at is not None and aware(row.lease_expires_at) > utcnow())
    ):
        return None
    if await unresolved_financial(session, row.id):
        return "held"
    row.status = "failed"
    settle_stream(row, "failed")
    row.error_code = "run_recovery_limit"
    row.model_metadata = {
        **row.model_metadata,
        "failure": RunFailure(family=failure_family(row.error_code)).model_dump(),
    }
    row.updated_at = utcnow()
    row.lease_expires_at = None
    if row.model_metadata.get("task_id"):
        await record_failure(session, row, read_only_names)
    if thread:
        emit(
            session,
            thread.owner_id,
            "run.failed",
            thread_id=row.thread_id,
            agent_id=row.agent_id,
            run_id=row.id,
            payload={"code": "run_recovery_limit", "failure": failure_data(row)},
        )
    return "failed"
