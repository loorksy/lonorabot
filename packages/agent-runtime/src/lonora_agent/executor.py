import asyncio
import logging
from time import perf_counter

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
from lonora_db.streaming import settle_stream, stream_identity
from lonora_db.task_wait_settlement import settle_task_wait
from lonora_logging.context import run_id as diagnostic_run_id
from lonora_tools.context import ToolContext
from lonora_tools.registry import ToolRegistry
from sqlalchemy import select

from .collaboration.outcome_return import return_outcome
from .context.compaction import compact_history
from .environment import ToolRetryScheduled
from .tasks import TaskSuspended
from .tool_loop import execute_tool_loop

log = logging.getLogger("lonora.executor")


async def execute_run(
    context: ToolContext, registry: ToolRegistry, lease_seconds: int, maximum_rounds: int
) -> None:
    correlation = diagnostic_run_id.set(context.lease.run_id)
    current = asyncio.current_task()
    lost_lease = asyncio.Event()

    async def heartbeat() -> None:
        while True:
            await asyncio.sleep(lease_seconds / 3)
            try:
                async with context.db.sessions() as session, session.begin():
                    await renew_lease(session, context.lease, lease_seconds)
            except Exception:
                lost_lease.set()
                if current:
                    current.cancel()
                return

    heartbeat_task = asyncio.create_task(heartbeat())
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
        async with context.db.sessions() as session:
            row = await require_lease(session, context.lease)
            restored = bool(row.execution_state)
        if not restored:
            preparing = perf_counter()
            await compact_history(context)
            log.info(
                "agent_history_prepared duration_ms=%.2f",
                (perf_counter() - preparing) * 1000,
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
            emit(
                session,
                context.owner_id,
                "run.retry_scheduled",
                thread_id=context.thread_id,
                agent_id=context.agent_id,
                run_id=row.id,
                payload={
                    "reason_code": row.execution_state["environment"]["retry"].get(
                        "reason_code", "tool_read_recovery"
                    ),
                    "retry_at": row.execution_state["environment"]["retry"]["not_before"],
                },
            )
    except TaskSuspended:
        return
    except asyncio.CancelledError:
        if not lost_lease.is_set():
            raise
    except LonoraError as error:
        if error.code != "stale_lease":
            try:
                async with context.db.sessions() as session, session.begin():
                    await fail_run(
                        session,
                        context.lease,
                        error.code,
                        read_only_names={
                            tool.name for tool in registry.tools.values() if tool.read_only
                        },
                    )
                await return_outcome(context.db, context.lease.run_id)
            except LonoraError:
                log.info("stale_failure_discarded")
    except Exception as error:
        log.error("run_failed type=%s", type(error).__name__)
        try:
            async with context.db.sessions() as session, session.begin():
                await fail_run(
                    session,
                    context.lease,
                    "runtime_error",
                    read_only_names={
                        tool.name for tool in registry.tools.values() if tool.read_only
                    },
                )
            await return_outcome(context.db, context.lease.run_id)
        except LonoraError:
            log.info("stale_failure_discarded")
    finally:
        heartbeat_task.cancel()
        await asyncio.gather(heartbeat_task, return_exceptions=True)
        diagnostic_run_id.reset(correlation)
