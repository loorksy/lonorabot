from lonora_adapter_kit.types import ModelMessage
from lonora_contracts.model_routing import Capability
from lonora_core.user_error import LonoraError
from lonora_db.runs import locked_run_thread, require_lease
from lonora_db.schema import MessageRow, RunRow, ThreadRow
from lonora_db.transactions import owned_thread
from lonora_llm_usage.models import UsageRecord
from lonora_llm_usage.store import save_usage
from lonora_tools.context import ToolContext
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..skills.loader import load_prompt
from .governance import MAXIMUM_CONTEXT_CHARS

SUMMARY_LIMIT = 24000
RECENT_HISTORY_LIMIT = 48000
COMPACTION_PROMPT = load_prompt("consolidator_archive")


async def compact_history(context: ToolContext, *, settled: bool = False) -> None:
    """Summarize canonical history; settled mode cannot mutate execution state.

    Gateway maintenance calls this only after the reply is independently committed.
    Begin early enough to leave headroom under the 100-message context window.
    A concurrent new turn may continue from the previous summary; the optimistic
    summary cursor can only advance through this completed turn's fixed input.
    """

    async def current_run(session: AsyncSession) -> RunRow | None:
        if not settled:
            return await require_lease(session, context.lease)
        row = await session.get(RunRow, context.lease.run_id)
        if (
            row is None
            or row.status != "completed"
            or row.thread_id != context.thread_id
            or row.agent_id != context.agent_id
            or row.lease_fence != context.lease.fence
            or row.lease_owner != context.lease.owner
        ):
            return None
        await owned_thread(session, context.owner_id, context.thread_id)
        return row

    async with context.db.sessions() as session:
        run = await current_run(session)
        if run is None:
            return
        thread = await session.get(ThreadRow, context.thread_id)
        if thread is None:
            return
        rows = list(
            (
                await session.scalars(
                    select(MessageRow)
                    .where(
                        MessageRow.thread_id == thread.id,
                        MessageRow.seq <= run.input_seq,
                        MessageRow.seq > thread.summary_seq,
                    )
                    .order_by(MessageRow.seq.desc())
                    .limit(121)
                )
            ).all()
        )
        threshold = 80 if settled else 120
        if (
            len(rows) < threshold
            and sum(len(row.content) + 80 for row in rows) <= RECENT_HISTORY_LIMIT
        ):
            return
        retained = 0
        size = 0
        for row in rows[:60]:
            if retained and size + len(row.content) + 80 > RECENT_HISTORY_LIMIT:
                break
            retained += 1
            size += len(row.content) + 80
        if not retained or retained == len(rows):
            return
        cutoff = rows[retained - 1].seq - 1

    while True:
        async with context.db.sessions() as session:
            if await current_run(session) is None:
                return
            thread = await session.get(ThreadRow, context.thread_id)
            if thread is None or thread.summary_seq >= cutoff:
                return
            prior_seq = thread.summary_seq
            prior_summary = thread.context_summary
            if len(prior_summary) > SUMMARY_LIMIT:
                raise LonoraError("history_summary_too_large", 413)
            rows = list(
                (
                    await session.scalars(
                        select(MessageRow)
                        .where(
                            MessageRow.thread_id == thread.id,
                            MessageRow.seq > prior_seq,
                            MessageRow.seq <= cutoff,
                        )
                        .order_by(MessageRow.seq)
                        .limit(60)
                    )
                ).all()
            )
            if not rows:
                return
            input_text = "Prior summary:\n" + prior_summary + "\n\nNew conversation messages:\n"
            # Never truncate a batch and then mark unseen messages as summarized.
            budget = MAXIMUM_CONTEXT_CHARS - len(COMPACTION_PROMPT) - 128
            through = prior_seq
            for row in rows:
                block = (
                    f"<message seq='{row.seq}' role='{row.role}' agent_id='{row.agent_id or ''}'>\n"
                    + row.content
                    + "\n</message>\n"
                )
                if len(input_text) + len(block) > budget:
                    break
                input_text += block
                through = row.seq
            if through == prior_seq:
                raise LonoraError("history_message_too_large", 413)
        reply, selection = await context.router.complete(
            Capability.BACKGROUND,
            [
                ModelMessage(role="system", content=COMPACTION_PROMPT),
                ModelMessage(role="user", content=input_text),
            ],
            [],
        )
        await save_usage(
            context.db,
            context.owner_id,
            context.agent_id,
            context.thread_id,
            UsageRecord(
                context.lease.run_id,
                selection.provider,
                selection.model,
                reply.usage,
                context_budget=reply.provider_metadata.get("context_budget", {}),
            ),
        )
        if not reply.text.strip():
            raise LonoraError("history_summary_empty", 502)
        if len(reply.text) > SUMMARY_LIMIT:
            raise LonoraError("history_summary_too_large", 502)
        async with context.db.sessions() as session, session.begin():
            if settled:
                # No model call holds a database lock. A deleted thread or an
                # overlapping summary is harmless; never resurrect owner data.
                if await current_run(session) is None:
                    return
                thread = await owned_thread(session, context.owner_id, context.thread_id, lock=True)
            else:
                _, thread = await locked_run_thread(session, context.lease)
            if thread.summary_seq == prior_seq:
                thread.context_summary = reply.text
                thread.summary_seq = through
