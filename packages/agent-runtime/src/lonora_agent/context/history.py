import json
from typing import Any, cast

from lonora_adapter_kit.types import ModelMessage
from lonora_db.schema import AgentRow, MessageRow, RunRow
from lonora_tools.runtime_control import WaitInput
from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession


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
            .limit(100)
        )
    ).all()
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
        content = (
            "[Peer " + names.get(row.agent_id or "", row.agent_id or "") + "]\n" + row.content
            if peer
            else row.content
        )
        content += options.get(row.id, "")
        messages.append(
            ModelMessage(
                role="user" if row.role == "user" or peer else "assistant", content=content
            )
        )
    return messages
