import json
from dataclasses import dataclass
from datetime import datetime
from typing import Any, cast

from lonora_adapter_kit.types import ModelMessage
from lonora_core.message_preview import model_content
from lonora_db.schema import AgentRow, MessageRow, RunRow
from lonora_tools.runtime_control import WaitInput
from pydantic import ValidationError
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

HISTORY_WINDOW = 100


@dataclass(frozen=True)
class HistoryGap:
    """Unsummarized messages older than the loaded window (the summary lags behind)."""

    first_seq: int
    last_seq: int
    count: int
    first_at: datetime | None
    last_at: datetime | None

    def notice(self) -> str:
        span = (
            f" from {self.first_at.isoformat()} to {self.last_at.isoformat()}"
            if self.first_at and self.last_at
            else ""
        )
        return (
            f"{self.count} earlier messages of this conversation (sequence {self.first_seq} to "
            f"{self.last_seq}{span}) are not shown and not yet covered by the conversation "
            "summary, because background summarization has not reached them. Recalled evidence "
            "below may quote relevant ones; do not assume they contain nothing, and ask or search "
            "before relying on what they might have said."
        )


async def history_gap(
    session: AsyncSession, thread_id: str, input_seq: int, summary_seq: int = 0
) -> HistoryGap | None:
    """Messages after the summary cursor that the newest-window load cannot include."""
    window = (
        select(MessageRow.seq)
        .where(
            MessageRow.thread_id == thread_id,
            MessageRow.seq <= input_seq,
            MessageRow.seq > summary_seq,
            MessageRow.role.in_(["user", "assistant"]),
        )
        .order_by(MessageRow.seq.desc())
        .offset(HISTORY_WINDOW - 1)
        .limit(1)
    )
    oldest_loaded = await session.scalar(window)
    if oldest_loaded is None:
        return None
    row = (
        await session.execute(
            select(
                func.count(),
                func.min(MessageRow.seq),
                func.max(MessageRow.seq),
                func.min(MessageRow.created_at),
                func.max(MessageRow.created_at),
            ).where(
                MessageRow.thread_id == thread_id,
                MessageRow.seq > summary_seq,
                MessageRow.seq < oldest_loaded,
                MessageRow.role.in_(["user", "assistant"]),
            )
        )
    ).one()
    count, first, last, first_at, last_at = row
    if not count:
        return None
    return HistoryGap(int(first), int(last), int(count), first_at, last_at)


async def history_context(
    session: AsyncSession,
    thread_id: str,
    input_seq: int,
    summary_seq: int = 0,
    agent_id: str | None = None,
) -> list[ModelMessage]:
    rows = (
        await session.scalars(
            select(MessageRow)
            .where(
                MessageRow.thread_id == thread_id,
                MessageRow.seq <= input_seq,
                MessageRow.seq > summary_seq,
                MessageRow.role.in_(["user", "assistant"]),
            )
            .order_by(MessageRow.seq.desc())
            .limit(HISTORY_WINDOW)
        )
    ).all()
    # Edit-and-resend (Q21): an owner message replaced by a newer one is no longer the
    # owner's instruction. Every later run reads only the replacement, never the original.
    replaced = set(
        await session.scalars(
            select(MessageRow.edited_from).where(
                MessageRow.thread_id == thread_id,
                MessageRow.seq <= input_seq,
                MessageRow.edited_from.in_([row.id for row in rows if row.role == "user"]),
            )
        )
    )
    rows = [row for row in rows if row.id not in replaced]
    # Published messages store question text; the existing Run stores its exact
    # choices. Recover a bounded projection so a new turn can understand the
    # original alternatives without manufacturing them or reading future replies.
    question_ids = {row.id for row in rows if row.role == "assistant"}
    options: dict[str, str] = {}
    if question_ids:
        histories = await session.scalars(
            select(RunRow.execution_state["input_requests"])
            .where(RunRow.thread_id == thread_id, RunRow.input_seq <= input_seq)
            .order_by(RunRow.created_at.desc())
            .limit(100)
        )
        for history in histories:
            if not isinstance(history, list):
                continue
            for raw in reversed(cast(list[Any], history)[-20:]):
                if not isinstance(raw, dict):
                    continue
                item = cast(dict[str, Any], raw)
                message_id = item.get("message_id")
                if (
                    not isinstance(message_id, str)
                    or message_id not in question_ids
                    or message_id in options
                ):
                    continue
                if len(options) >= 8:
                    break
                try:
                    question = WaitInput.model_validate(
                        {"question": item.get("question"), "choices": item.get("choices", [])}
                    )
                except ValidationError:
                    continue
                if question.choices:
                    payload = json.dumps(
                        [choice.model_dump() for choice in question.choices], ensure_ascii=False
                    ).replace("<", "\\u003c")
                    options[message_id] = "\n<question_choices>" + payload + "</question_choices>"
    names = {
        agent.id: agent.name
        for agent in (
            await session.scalars(
                select(AgentRow).where(
                    AgentRow.id.in_([row.agent_id for row in rows if row.agent_id])
                )
            )
        ).all()
    }
    messages: list[ModelMessage] = []
    for row in reversed(rows):
        peer = bool(agent_id and row.agent_id and row.agent_id != agent_id)
        text = model_content(row.content, row.rich_content)
        content = (
            "[Peer " + names.get(row.agent_id or "", row.agent_id or "") + "]\n" + text
            if peer
            else text
        )
        content += options.get(row.id, "")
        messages.append(
            ModelMessage(
                role="user" if row.role == "user" or peer else "assistant", content=content
            )
        )
    return messages
