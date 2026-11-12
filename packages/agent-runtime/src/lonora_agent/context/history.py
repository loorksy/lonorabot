import json
from dataclasses import dataclass
from datetime import datetime
from typing import Any, cast

from lonora_adapter_kit.context_sections import ContextSection, context_data
from lonora_adapter_kit.types import ModelMessage
from lonora_core.message_preview import model_content
from lonora_db.genui_submit import NEVER_RAN_NOTE, never_ran, submit_status
from lonora_db.owner_words import submit_hidden
from lonora_db.schema import AgentRow, MessageRow, RunRow
from lonora_db.threads import asks_in
from lonora_tools.runtime_control import WaitInput
from pydantic import ValidationError
from sqlalchemy import and_, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

# Read by a later turn of the conversation: the owner's answer to a background run's
# question already went to that work, which acts on it and reports here.
ROUTED_ANSWER_NOTE = (
    "\n[This answered a question from your background work; that work received it, acts"
    " on it and reports here.]"
)

HISTORY_WINDOW = 100


def peer_content(name: str, text: str) -> str:
    """Another agent's message in the transcript: information, never an order (3.2.3).

    The body travels in the same data frame as other third-party content (6.10), so
    it can neither close its frame nor pass as the owner's words or system policy.
    """
    label = " ".join(name.replace("]", ")").split())
    return (
        "[Peer "
        + label
        + "]\n"
        + context_data(
            [ContextSection("peer_message", "peer_agent", "peer_untrusted", text or "(empty)")]
        )
    )


def card_words(row: MessageRow, run: RunRow | None) -> str:
    """Card words are labelled as such, never as the owner's own (docs/genui.md §7); the submission a
    Run answers carries its validated data as ``<ui_submit>``, marked as data (docs/genui.md §7)."""
    if row.origin == "ui_follow_up":
        return "[owner_via_card]\n" + row.content
    if row.origin != "ui_submit":
        return row.content
    submit = row.ui_submit or {}
    title = str(submit.get("card_title", ""))[:40].replace('"', "'").replace("<", "‹")
    text = f"[owner_via_card «{title}»]\n" + row.content
    if run is not None and submit.get("run_id") == run.id:
        data = json.dumps(submit.get("data", {}), ensure_ascii=False).replace("<", "\\u003c")
        intent = str(submit.get("intent", ""))
        text += f'\n<ui_submit card="{title}" intent="{intent}">{data}</ui_submit>'
    return text


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
    run: RunRow | None = None,
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
    answer_ids = {row.id for row in rows if row.role == "user"}
    options: dict[str, str] = {}
    remote_answers: dict[str, str] = {}
    if question_ids:
        # A background run's question copied here is read like this thread's own; the
        # answer the owner gave it is marked as already sent to that work.
        histories = await session.execute(
            select(RunRow.thread_id, RunRow.execution_state["input_requests"])
            .where(
                or_(
                    and_(RunRow.thread_id == thread_id, RunRow.input_seq <= input_seq),
                    asks_in(thread_id),
                )
            )
            .order_by(RunRow.created_at.desc())
            .limit(100)
        )
        for asker_thread, history in histories:
            if not isinstance(history, list):
                continue
            for raw in reversed(cast(list[Any], history)[-20:]):
                if not isinstance(raw, dict):
                    continue
                item = cast(dict[str, Any], raw)
                answered = item.get("answer_message_id")
                if asker_thread != thread_id and answered in answer_ids:
                    options.setdefault(str(answered), ROUTED_ANSWER_NOTE)
                # A background run's own question is in its thread (``source_message_id``);
                # the request names the copy in the conversation it reports to.
                message_id = (
                    item.get("source_message_id") or item.get("message_id")
                    if asker_thread == thread_id
                    else item.get("message_id")
                )
                if (
                    asker_thread == thread_id
                    and item.get("source_message_id") in question_ids
                    and isinstance(answered, str)
                ):
                    remote_answers[str(item["source_message_id"])] = answered
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
                        [choice.model_dump(include={"id", "label"}) for choice in question.choices],
                        ensure_ascii=False,
                    ).replace("<", "\\u003c")
                    options[message_id] = "\n<question_choices>" + payload + "</question_choices>"
    if remote_answers:
        # The owner answered this run's question in the conversation it reports to: the
        # work thread, its memory, keeps what the owner said.
        answers = {
            row.id: row
            for row in await session.scalars(
                select(MessageRow).where(MessageRow.id.in_(list(remote_answers.values())))
            )
        }
        for question_id, answer_id in remote_answers.items():
            answer = answers.get(answer_id)
            if answer is not None and answer.role == "user":
                options[question_id] = (
                    options.get(question_id, "")
                    + "\n[The owner answered in the conversation: "
                    + model_content(answer.content, answer.rich_content)[:2000]
                    + "]"
                )
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
        if row.origin == "ui_submit" and await submit_hidden(session, row, run):
            # Rules V and N (docs/genui.md): a submission another Run has not finished is
            # not shown at all; one whose Run never started leaves only a note, never its
            # bubble, intent, data or values.
            if never_ran(row.ui_submit, await submit_status(session, row)):
                messages.append(ModelMessage(role="user", content="[" + NEVER_RAN_NOTE + "]"))
            continue
        text = (
            card_words(row, run)
            if row.origin in {"ui_submit", "ui_follow_up"}
            else model_content(row.content, row.rich_content)
        )
        content = (
            peer_content(names.get(row.agent_id or "", row.agent_id or ""), text) if peer else text
        )
        content += options.get(row.id, "")
        messages.append(
            ModelMessage(
                role="user" if row.role == "user" or peer else "assistant", content=content
            )
        )
    return messages
