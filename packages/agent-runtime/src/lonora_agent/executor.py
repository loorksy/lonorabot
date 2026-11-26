import asyncio
import logging
from collections.abc import Awaitable, Callable
from functools import partial
from time import monotonic

from lonora_adapter_kit.model_errors import ModelProviderError
from lonora_contracts.domain import utcnow
from lonora_core.user_error import LonoraError
from lonora_db.events import emit
from lonora_db.generated_artifacts import link_generated_artifacts, resolve_reply_artifacts
from lonora_db.genui_submit import mark_submit_started
from lonora_db.rich_response import validated_rich_content
from lonora_db.runs import (
    complete_run,
    fail_run,
    locked_run_thread,
    renew_lease,
    require_lease,
    run_data,
)
from lonora_db.schema import MessageRow, RunRow, SteeringRow, ThreadRow, TradeApprovalRow
from lonora_db.steering import user_interrupt_pending
from lonora_db.streaming import settle_stream, stream_identity
from lonora_db.task_wait_settlement import settle_task_wait
from lonora_db.tasks import request_task_attention
from lonora_db.threads import report_thread
from lonora_logging.context import run_id as diagnostic_run_id
from lonora_tools.context import ToolContext
from lonora_tools.registry import ToolRegistry
from sqlalchemy import select
from sqlalchemy.exc import DBAPIError, InterfaceError, OperationalError, SQLAlchemyError
from sqlalchemy.exc import TimeoutError as PoolTimeoutError
from sqlalchemy.ext.asyncio import AsyncSession

from .collaboration.outcome_return import return_outcome
from .environment import ToolRetryScheduled
from .loop_outcomes import LoopOutcome
from .model_recovery import RETRY_REASON
from .tasks import TaskSuspended
from .tool_loop import execute_tool_loop

log = logging.getLogger("lonora.executor")

# Database failures a lease renewal retries before it gives the lease up.
TRANSIENT_RENEWAL_ERRORS = (SQLAlchemyError, OSError, TimeoutError)
# How often a running Run looks whether it was cancelled (VISION 4.6, 4.7, 7.1.5).
WATCH_SECONDS = 2.0
# SQLSTATE classes of a failure of the database rather than of the statement (PostgreSQL,
# appendix A): a Run's final commit is retried after one of them (database_failed).
TRANSIENT_SQLSTATES = ("08", "40", "53", "57", "58")
# How often a lost lease noticed inside an effect looks again whether the effect ended.
EFFECT_POLL_SECONDS = 0.2


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


async def watch_fence(context: ToolContext, lost: Callable[[], None]) -> None:
    """Stop the Run within about two seconds once its fence moved (a cancel).

    A cancel only moves the fence. Between fenced writes (a model thinking before its
    first token, a long read, a backoff sleep) the Run would otherwise go on, spending
    the owner's key, until its next lease renewal. ``lost`` never cuts a worker inside
    an effect (``execute_run``): the cancel takes effect once that call has returned, and
    the checkpoint of its result is already refused by the moved fence.
    """
    while True:
        await asyncio.sleep(WATCH_SECONDS)
        try:
            async with context.db.sessions() as session:
                fence = await session.scalar(
                    select(RunRow.lease_fence).where(RunRow.id == context.lease.run_id)
                )
        except TRANSIENT_RENEWAL_ERRORS:
            # An outage is keep_lease's to judge.
            continue
        # Only a cancel (or a newer claim) moves the fence; the Run's own completion or
        # release keeps it, so the writing of its outcome is never cut.
        if fence != context.lease.fence:
            lost()
            return


def database_failed(error: Exception) -> bool:
    """A failure of the database, not of the statement: worth another attempt of the same
    transaction.

    asyncpg reaches SQLAlchemy as a plain ``DBAPIError`` for most of these, so its SQLSTATE
    decides: a connection exception (08), a rollback such as a deadlock or a serialization
    failure (40), insufficient resources such as too many connections (53), an operator's
    intervention such as a restart or a failover (57) or a system error (58). A full pool
    is SQLAlchemy's ``TimeoutError``, not the builtin one. A constraint, a bad value or any
    other error of the statement would fail every attempt and is never retried.
    """
    if isinstance(error, DBAPIError):
        sqlstate = getattr(error.orig, "sqlstate", None)
        return (
            error.connection_invalidated
            or isinstance(error, OperationalError | InterfaceError)
            or (isinstance(sqlstate, str) and sqlstate.startswith(TRANSIENT_SQLSTATES))
        )
    return isinstance(error, OSError | TimeoutError | PoolTimeoutError)


async def final_commit[Committed](
    context: ToolContext,
    lease_seconds: int,
    lost: asyncio.Event,
    write: Callable[[AsyncSession], Awaitable[Committed]],
) -> Committed:
    """A Run's final transaction (its completion, its wait for the owner, its release),
    retried like a lease renewal after a failure of the database (``database_failed``)
    while the lease holds.

    ``keep_lease`` goes on renewing meanwhile and sets ``lost`` once it gives the lease
    up; a fenced ``stale_lease`` or an error of the statement is never retried. The fence
    makes a second commit impossible: a retry after a commit whose answer was lost finds
    the Run no longer leased.
    """
    margin = lease_seconds / 6
    failed_at: float | None = None
    while True:
        try:
            async with context.db.sessions() as session, session.begin():
                return await write(session)
        except Exception as error:
            failed_at = monotonic() if failed_at is None else failed_at
            if (
                not database_failed(error)
                or lost.is_set()
                or monotonic() - failed_at >= lease_seconds - margin
            ):
                raise
            log.warning("final_commit_retry type=%s", type(error).__name__)
        await asyncio.sleep(min(2.0, margin / 2))


async def record_failure(
    context: ToolContext, registry: ToolRegistry, code: str, error: LonoraError | None = None
) -> None:
    """Fail the Run with ``code``; once its lease is lost the failure is discarded.

    A provider error adds its classified reason and ``Retry-After`` hint (Q22).
    """
    provider = error if isinstance(error, ModelProviderError) else None
    try:
        async with context.db.sessions() as session, session.begin():
            await fail_run(
                session,
                context.lease,
                code,
                read_only_names={tool.name for tool in registry.tools.values() if tool.read_only},
                reason=provider.reason.value if provider else None,
                retry_after=provider.retry_after if provider else None,
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
    # Only the Run's own work is cancelled: once it ended, its outcome is being written
    # (or discarded) and a cancel there would escape into the worker loop.
    working = True
    cutting: asyncio.Task[None] | None = None

    async def cut_after_effect() -> None:
        while True:
            if context.drain is None or current not in context.drain.effects:
                if current and working:
                    current.cancel()
                return
            await asyncio.sleep(EFFECT_POLL_SECONDS)

    def lose() -> None:
        """The lease is lost (a cancel, a newer claim, renewal out of time): stop the Run.

        Whoever noticed it (the fence watcher or a lease renewal), a worker inside an
        effect, from ``before_effect`` of a call that is not read-only until its result is
        checkpointed, is never cut: it stops once that call has returned (VISION 6.3).
        """
        nonlocal cutting
        lost_lease.set()
        if not (current and working) or cutting is not None:
            return
        if context.drain is not None and current in context.drain.effects:
            cutting = asyncio.create_task(cut_after_effect())
        else:
            current.cancel()

    heartbeat_task = asyncio.create_task(keep_lease(context, lease_seconds, lose))
    watch_task = asyncio.create_task(watch_fence(context, lose))
    try:
        async with context.db.sessions() as session, session.begin():
            row = await require_lease(session, context.lease, lock=True)
            row.status = "running"
            row.updated_at = utcnow()
            # Rules N and T: a card submission records that its Run started.
            await mark_submit_started(session, row)
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

            # The pass's final transaction: "again" runs the loop once more, "ended" leaves
            # the Run waiting and "completed" completes it.
            async def finish(session: AsyncSession, outcome: LoopOutcome) -> str:
                if outcome.external_wait:
                    settled = await settle_task_wait(
                        session,
                        context.lease,
                        outcome.text,
                        outcome.metadata.get("external_wait_call_id"),
                        rich_content=validated_rich_content(outcome.metadata.get("rich_content")),
                    )
                    if settled == "continue":
                        return "again"
                    return "ended"
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
                            return "again"
                    if outstanding:
                        return "again"
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
                        # A run working in a hidden work thread asks where it reports
                        # (VISION 11.6): its question stays in the work thread, its memory,
                        # and is copied into that conversation, where the owner answers it.
                        asked = message
                        report_id = await report_thread(session, row)
                        if report_id != row.thread_id:
                            origin = await session.get(
                                ThreadRow, report_id, with_for_update=True, populate_existing=True
                            )
                            if origin is not None:
                                asked = MessageRow(
                                    thread_id=origin.id,
                                    agent_id=context.agent_id,
                                    seq=origin.next_seq,
                                    role="assistant",
                                    content=answer,
                                    rich_content=rich_content,
                                )
                                origin.next_seq += 1
                                session.add(asked)
                                await session.flush()
                                # The owner sees the question there, with what it shows.
                                link_generated_artifacts(asked, artifacts)
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
                                    "message_id": asked.id,
                                    "thread_id": asked.thread_id,
                                    # The question in the run's own thread, its memory.
                                    "source_message_id": message.id,
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
                        if asked is not message:
                            emit(
                                session,
                                context.owner_id,
                                "message.created",
                                thread_id=asked.thread_id,
                                agent_id=context.agent_id,
                                run_id=row.id,
                                payload=message_data(asked),
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
                    return "ended"
                complete = await complete_run(
                    session, context.lease, outcome.text, outcome.metadata
                )
                return "completed" if complete else "again"

            ending = await final_commit(
                context, lease_seconds, lost_lease, partial(finish, outcome=outcome)
            )
            if ending == "again":
                continue
            working = False
            if ending == "completed":
                await return_outcome(context.db, context.lease.run_id)
            return
    except ToolRetryScheduled:
        working = False

        async def release(session: AsyncSession) -> None:
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

        try:
            await final_commit(context, lease_seconds, lost_lease, release)
        except LonoraError as error:
            # A cancel that raced the hand-back moved the fence first: as in the other
            # branches, a stale lease ends the Run here and is no failure of the worker.
            if error.code != "stale_lease":
                raise
    except TaskSuspended:
        return
    except asyncio.CancelledError:
        if not lost_lease.is_set():
            raise
    except LonoraError as error:
        working = False
        if error.code != "stale_lease":
            await record_failure(context, registry, error.code, error)
    except Exception as error:
        working = False
        log.error("run_failed type=%s", type(error).__name__)
        await record_failure(context, registry, "runtime_error")
    finally:
        working = False
        helpers = [heartbeat_task, watch_task, *([cutting] if cutting else [])]
        for helper in helpers:
            helper.cancel()
        await asyncio.gather(*helpers, return_exceptions=True)
        diagnostic_run_id.reset(correlation)
