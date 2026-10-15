import asyncio
import logging

from lonora_contracts.domain import utcnow
from lonora_core.user_error import LonoraError
from lonora_db.events import emit
from lonora_db.generated_artifacts import link_generated_artifacts, pending_generated_artifacts
from lonora_db.runs import complete_run, fail_run, locked_run_thread, renew_lease, require_lease
from lonora_db.schema import MessageRow, SteeringRow, TradeApprovalRow
from lonora_db.streaming import settle_stream, stream_identity
from lonora_tools.context import ToolContext
from lonora_tools.registry import ToolRegistry
from sqlalchemy import select

from .collaboration.outcome_return import return_outcome
from .context.compaction import compact_history
from .tasks import TaskSuspended
from .tool_loop import execute_tool_loop

log = logging.getLogger("lonora.executor")


async def execute_run(
    context: ToolContext, registry: ToolRegistry, lease_seconds: int, maximum_rounds: int
) -> None:
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
            )
        async with context.db.sessions() as session:
            row = await require_lease(session, context.lease)
            restored = bool(row.execution_state)
        if not restored:
            await compact_history(context)
        while True:
            outcome = await execute_tool_loop(context, registry, maximum_rounds)
            async with context.db.sessions() as session, session.begin():
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
                    if thread and outcome.text:
                        message = MessageRow(
                            thread_id=thread.id,
                            agent_id=context.agent_id,
                            seq=thread.next_seq,
                            role="assistant",
                            content=outcome.text,
                        )
                        thread.next_seq += 1
                        session.add(message)
                        await session.flush()
                        artifacts = await pending_generated_artifacts(
                            session, context.owner_id, row
                        )
                        link_generated_artifacts(message, artifacts)
                        snapshot = settle_stream(
                            row, "committed", message_id=message.id, text=outcome.text
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
    except TaskSuspended:
        return
    except asyncio.CancelledError:
        if not lost_lease.is_set():
            raise
    except LonoraError as error:
        if error.code != "stale_lease":
            try:
                async with context.db.sessions() as session, session.begin():
                    await fail_run(session, context.lease, error.code)
                await return_outcome(context.db, context.lease.run_id)
            except LonoraError:
                log.info("stale_failure_discarded")
    except Exception as error:
        log.error("run_failed type=%s", type(error).__name__)
        try:
            async with context.db.sessions() as session, session.begin():
                await fail_run(session, context.lease, "runtime_error")
            await return_outcome(context.db, context.lease.run_id)
        except LonoraError:
            log.info("stale_failure_discarded")
    finally:
        heartbeat_task.cancel()
        await asyncio.gather(heartbeat_task, return_exceptions=True)
