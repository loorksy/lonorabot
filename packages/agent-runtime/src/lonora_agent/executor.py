import asyncio
import logging
from collections.abc import Callable
from time import monotonic

from lonora_contracts.domain import utcnow
from lonora_core.user_error import LonoraError
from lonora_db.events import emit
from lonora_db.generated_artifacts import link_generated_artifacts, resolve_reply_artifacts
from lonora_db.rich_response import validated_rich_content
from lonora_db.runs import (
    complete_run,
    fail_run,
    locked_run_thread,
    renew_lease,
    require_lease,
    run_data,
)
from lonora_db.schema import MessageRow, SteeringRow, TradeApprovalRow
from lonora_db.steering import user_interrupt_pending
from lonora_db.streaming import settle_stream, stream_identity
from lonora_db.task_wait_settlement import settle_task_wait
from lonora_db.tasks import request_task_attention
from lonora_logging.context import run_id as diagnostic_run_id
from lonora_tools.context import ToolContext
from lonora_tools.registry import ToolRegistry
from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError

from .collaboration.outcome_return import return_outcome
from .environment import ToolRetryScheduled
from .model_recovery import RETRY_REASON
from .tasks import TaskSuspended
from .tool_loop import execute_tool_loop

log = logging.getLogger("lonora.executor")

# Database failures a lease renewal retries before it gives the lease up.
TRANSIENT_RENEWAL_ERRORS = (SQLAlchemyError, OSError, TimeoutError)


async def keep_lease(context: ToolContext, lease_seconds: int, lost: Callable[[], None]) -> None:
    """Renew the Run's lease every third of its length.

    A transient database error (a dropped connection, a failover, a timeout) is retried
    until shortly before the lease would expire; only a fenced ``stale_lease``, an
    unknown error or running out of lease time declares it lost and stops the Run.
    """
    renewed = monotonic()
    margin = lease_seconds / 6
    while True:
        await asyncio.sleep(lease_seconds / 3)
        while True:
            try:
                # A renewal that hangs is as transient as one that fails.
                async with asyncio.timeout(max(1.0, margin)):
                    async with context.db.sessions() as session, session.begin():
                        await renew_lease(session, context.lease, lease_seconds)
            except TRANSIENT_RENEWAL_ERRORS as error:
                if monotonic() - renewed >= lease_seconds - margin:
                    log.error("lease_lost reason=renewal_unavailable")
                    lost()
                    return
                log.warning("lease_renewal_retry type=%s", type(error).__name__)
                await asyncio.sleep(min(2.0, margin / 2))
                continue
            except Exception:
                lost()
                return
            renewed = monotonic()
            break


async def record_failure(context: ToolContext, registry: ToolRegistry, code: str) -> None:
    """Fail the Run with ``code``; once its lease is lost the failure is discarded."""
    try:
        async with context.db.sessions() as session, session.begin():
            await fail_run(
                session,
                context.lease,
                code,
                read_only_names={tool.name for tool in registry.tools.values() if tool.read_only},
            )
        await return_outcome(context.db, context.lease.run_id)
    except LonoraError:
        log.info("stale_failure_discarded")


async def execute_run(
    context: ToolContext, registry: ToolRegistry, lease_seconds: int, maximum_rounds: int
) -> None:
    correlation = diagnostic_run_id.set(context.lease.run_id)
    current = asyncio.current_task()
    lost_lease = asyncio.Event()

    def lose() -> None:
        lost_lease.set()
        if current:
            current.cancel()

    heartbeat_task = asyncio.create_task(keep_lease(context, lease_seconds, lose))
    try:
        async with context.db.sessions() as session, session.begin():
            row = await require_lease(session, context.lease, lock=True)
            row.status = "running"
            row.updated_at = utcnow()
            emit(
                session,
                context.owner_id,
                "run.running",
                thread_id=context.thread_id,
                agent_id=context.agent_id,
                run_id=row.id,
                payload={"run": run_data(row)},
            )
        while True:
            outcome = await execute_tool_loop(context, registry, maximum_rounds)
            async with context.db.sessions() as session, session.begin():
                if outcome.external_wait:
                    settled = await settle_task_wait(
                        session,
                        context.lease,
                        outcome.text,
                        outcome.metadata.get("external_wait_call_id"),
                        rich_content=validated_rich_content(outcome.metadata.get("rich_content")),
                    )
                    if settled == "continue":
                        continue
                    return
                if outcome.waiting:
                    row, thread = await locked_run_thread(session, context.lease)
                    outstanding = await session.scalar(
                        select(SteeringRow.id)
                        .where(SteeringRow.run_id == row.id, SteeringRow.consumed.is_(False))
                        .limit(1)
                    )
                    approval_id = outcome.metadata.get("trade_approval_id")
                    if approval_id:
                        approval = await session.get(TradeApprovalRow, approval_id)
                        if approval and approval.status != "pending":
                            continue
                    if outstanding:
                        continue
                    question = outcome.input_request
                    prior_question = next(
                        (
                            item
                            for item in row.execution_state.get("input_requests", [])
                            if question and item.get("id") == question["id"]
                        ),
                        None,
                    )
                    if (
                        prior_question
                        and question
                        and (
                            prior_question.get("question") != question["question"]
                            or prior_question.get("choices") != question.get("choices", [])
                            or prior_question.get("status") != "pending"
                        )
                    ):
                        raise LonoraError("input_question_identity_conflict", 409)
                    rich_content = validated_rich_content(outcome.metadata.get("rich_content"))
                    if thread and (outcome.text or rich_content) and prior_question is None:
                        answer, artifacts = await resolve_reply_artifacts(
                            session, context.owner_id, row, outcome.text
                        )
                        message = MessageRow(
                            thread_id=thread.id,
                            agent_id=context.agent_id,
                            seq=thread.next_seq,
                            role="assistant",
                            content=answer,
                            rich_content=rich_content,
                        )
                        thread.next_seq += 1
                        session.add(message)
                        await session.flush()
                        link_generated_artifacts(message, artifacts)
                        if question:
                            history = [
                                {**item, "status": "cancelled"}
                                if item.get("status") == "pending"
                                else item
                                for item in row.execution_state.get("input_requests", [])
                            ]
                            history.append(
                                {
                                    **question,
                                    "run_id": row.id,
                                    "message_id": message.id,
                                    "status": "pending",
                                    "selected_choice_id": None,
                                    "answer_message_id": None,
                                }
                            )
                            row.execution_state = {
                                **row.execution_state,
                                "input_requests": history[-20:],
                            }
                        snapshot = settle_stream(
                            row,
                            "committed",
                            message_id=message.id,
                            text=answer,
                            rich_content=rich_content,
                        )
                        if snapshot:
                            emit(
                                session,
                                context.owner_id,
                                "run.reply_committed",
                                thread_id=thread.id,
                                agent_id=context.agent_id,
                                run_id=row.id,
                                payload=stream_identity(snapshot),
                            )
                        from lonora_db.messages import message_data

                        emit(
                            session,
                            context.owner_id,
                            "message.created",
                            thread_id=thread.id,
                            run_id=row.id,
                            payload=message_data(message),
                        )
                    attention = outcome.metadata.get("owner_attention")
                    if isinstance(attention, str) and attention:
                        # Unfinished Task work waits for its owner, resumable
                        # from the same checkpoint, instead of failing the Run.
                        await request_task_attention(session, row, attention)
                    row.status = "waiting_input"
                    row.lease_expires_at = None
                    emit(
                        session,
                        context.owner_id,
                        "run.waiting_input",
                        thread_id=context.thread_id,
                        run_id=row.id,
                    )
                    return
                complete = await complete_run(
                    session, context.lease, outcome.text, outcome.metadata
                )
            if complete:
                await return_outcome(context.db, context.lease.run_id)
                return
    except ToolRetryScheduled:
        async with context.db.sessions() as session, session.begin():
            row, _ = await locked_run_thread(session, context.lease)
            row.status = "queued"
            row.lease_expires_at = None
            row.updated_at = utcnow()
            retry = row.execution_state["environment"]["retry"]
            if retry.get("reason_code") == RETRY_REASON:
                # The failed model turn left no reply: withdraw its preview so
                # clients do not show a partial answer during the backoff.
                snapshot = settle_stream(row, "discarded", text="")
                if snapshot:
                    emit(
                        session,
                        context.owner_id,
                        "run.reply_committed",
                        thread_id=context.thread_id,
                        agent_id=context.agent_id,
                        run_id=row.id,
                        payload=stream_identity(snapshot),
                    )
                if await user_interrupt_pending(session, row.id):
                    # The owner wrote while the failed turn was being retried.
                    # Admission only clears the deadline of an already queued
                    # Run, so clear it here: the new message is answered (or
                    # the provider state reported) now, not after the backoff.
                    # The failure streak is kept, so this cannot loop forever.
                    environment = dict(row.execution_state["environment"])
                    environment.pop("retry", None)
                    row.execution_state = {**row.execution_state, "environment": environment}
                    retry = {**retry, "not_before": row.updated_at.isoformat()}
            emit(
                session,
                context.owner_id,
                "run.retry_scheduled",
                thread_id=context.thread_id,
                agent_id=context.agent_id,
                run_id=row.id,
                payload={
                    "reason_code": retry.get("reason_code", "tool_read_recovery"),
                    "retry_at": retry["not_before"],
                    **({"code": retry["code"]} if isinstance(retry.get("code"), str) else {}),
                },
            )
    except TaskSuspended:
        return
    except asyncio.CancelledError:
        if not lost_lease.is_set():
            raise
    except LonoraError as error:
        if error.code != "stale_lease":
            await record_failure(context, registry, error.code)
    except Exception as error:
        log.error("run_failed type=%s", type(error).__name__)
        await record_failure(context, registry, "runtime_error")
    finally:
        heartbeat_task.cancel()
        await asyncio.gather(heartbeat_task, return_exceptions=True)
        diagnostic_run_id.reset(correlation)
