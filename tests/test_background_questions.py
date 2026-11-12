"""A background run's question is asked and answered in its agent's own conversation (11.6).

A routine, watch or broker-event run works in a hidden work thread. When it asks the owner
(``wait_for_input``), the question stays in the work thread (its memory) and is copied
into the conversation it reports to; the owner answers there, by a choice, a reply, or the
next message, and the same run resumes from its checkpoint.
"""

import os
from typing import Any, cast
from unittest.mock import patch
from uuid import uuid4

import pytest

CHOICES = [{"id": "hold", "label": "أبقِها"}, {"id": "close", "label": "أغلقها"}]
QUESTION = "الذهب عند 2,412 والصفقة رابحة 40 نقطة: هل أبقيها مفتوحة؟"


def database() -> None:
    if not os.environ.get("LONORA_DATABASE_URL"):
        pytest.skip("The background question cases use the real migrated PostgreSQL schema.")


async def background_run(fixture: Any, agent: dict[str, Any], conversation: dict[str, Any]) -> Any:
    from lonora_contracts.domain import ThreadCreate
    from lonora_contracts.runs import RunRequest
    from lonora_db.runs import create_run, run_data
    from lonora_db.threads import create_thread

    async with fixture.runtime.db.sessions() as session, session.begin():
        work = await create_thread(
            session, fixture.owner, ThreadCreate(agent_id=agent["id"]), purpose="work"
        )
        run = await create_run(
            session,
            fixture.owner,
            RunRequest(
                thread_id=work.id,
                agent_id=agent["id"],
                trigger="routine",
                prompt="Review the gold position",
                metadata={"origin_thread_id": conversation["id"]},
            ),
        )
        return run_data(run)


async def ask(fixture: Any, run: dict[str, Any], question: str = QUESTION) -> dict[str, Any]:
    from lonora_adapter_kit.types import ModelReply, ToolCall
    from lonora_agent.executor import execute_run
    from lonora_contracts.model_routing import ModelSelection
    from lonora_tools.loader import load_tools

    context = await fixture.lease(run)
    call_id = "question-" + uuid4().hex

    async def complete(*_: Any, **__: Any) -> Any:
        return ModelReply(
            tool_calls=[
                ToolCall(
                    id=call_id,
                    name="wait_for_input",
                    arguments={"question": question, "choices": CHOICES},
                )
            ]
        ), ModelSelection(provider="openai", model="background-question-fixture")

    with patch.object(context.router, "complete", complete):
        await execute_run(context, load_tools(), 120, 4)
    current = await fixture.request("GET", "/runs/" + run["id"])
    assert current["status"] == "waiting_input", current
    return current


async def resume(fixture: Any, run: dict[str, Any], reply: str) -> list[str]:
    """Run the answered run to completion; returns the user texts the model received."""
    from lonora_adapter_kit.types import ModelReply
    from lonora_agent.executor import execute_run
    from lonora_contracts.model_routing import ModelSelection
    from lonora_tools.loader import load_tools

    context = await fixture.lease(run)
    seen: list[str] = []

    async def complete(*args: Any, **kwargs: Any) -> Any:
        messages = kwargs.get("messages") or next(
            arg for arg in args if isinstance(arg, list) and arg and hasattr(arg[0], "role")
        )
        seen.extend(str(message.content) for message in messages if message.role == "user")
        return ModelReply(text=reply), ModelSelection(
            provider="openai", model="background-question-fixture"
        )

    with patch.object(context.router, "complete", complete):
        await execute_run(context, load_tools(), 120, 4)
    return seen


async def thread_messages(fixture: Any, thread_id: str) -> list[dict[str, Any]]:
    return cast(
        list[dict[str, Any]], await fixture.request("GET", f"/threads/{thread_id}/messages")
    )


async def send(
    fixture: Any, thread_id: str, content: str, **extra: Any
) -> tuple[int, dict[str, Any]]:
    response = await fixture.client.post(
        f"/api/threads/{thread_id}/messages",
        json={"content": content, "client_nonce": uuid4().hex, **extra},
    )
    return response.status_code, response.json()


@pytest.mark.asyncio
async def test_a_background_question_is_asked_and_answered_in_the_conversation():
    database()
    from check_streaming import Fixture
    from lonora_db.schema import RunRow, SteeringRow
    from sqlalchemy import select

    fixture = await Fixture().open()
    try:
        agent = await fixture.agent("Background asker")
        conversation = await fixture.conversation(agent)
        run = await background_run(fixture, agent, conversation)
        current = await ask(fixture, run)
        question = current["input_request"]
        # The question stays in the work thread (its memory) and is copied into the
        # conversation, which is where the owner sees and answers it.
        work_messages = await thread_messages(fixture, run["thread_id"])
        assert [m["content"] for m in work_messages] == [QUESTION]
        chat = await thread_messages(fixture, conversation["id"])
        assert [m["content"] for m in chat] == [QUESTION]
        assert question["message_id"] == chat[0]["id"]
        assert question["thread_id"] == conversation["id"]
        # The conversation's run list carries the asking run, so its card renders there.
        listed = await fixture.request("GET", f"/runs?thread_id={conversation['id']}")
        asking = [row for row in cast(list[dict[str, Any]], listed) if row["id"] == run["id"]]
        assert asking and asking[0]["thread_id"] == run["thread_id"]
        # The same tap posted to the hidden thread is refused: the question is not there.
        answer = {
            "input_answer": {
                "run_id": run["id"],
                "question_id": question["id"],
                "choice_id": "hold",
            },
            "reply_to": question["message_id"],
        }
        status, _ = await send(fixture, run["thread_id"], "أبقِها", **answer)
        assert status == 409
        # The owner's tap in the conversation answers the waiting run and starts nothing else.
        status, body = await send(fixture, conversation["id"], "أبقِها", **answer)
        assert status < 300, body
        assert body["run_ids"] == [run["id"]]
        async with fixture.runtime.db.sessions() as session:
            row = await session.get(RunRow, run["id"])
            assert row is not None and row.status == "queued"
            steering = await session.scalar(
                select(SteeringRow).where(SteeringRow.run_id == run["id"])
            )
            assert steering is not None and steering.message_id == body["message"]["id"]
            in_chat = list(
                await session.scalars(
                    select(RunRow.id).where(RunRow.thread_id == conversation["id"])
                )
            )
            assert in_chat == []
        # A second tap finds no pending question.
        status, _ = await send(
            fixture,
            conversation["id"],
            "أغلقها",
            **{
                **answer,
                "input_answer": {**answer["input_answer"], "choice_id": "close"},
            },
        )
        assert status == 409
        # The run resumes in its work thread, reads the owner's answer and reports back.
        seen = await resume(fixture, run, "أبقيت الصفقة؛ الوقف عند 2,398.")
        assert "أبقِها" in seen
        chat = await thread_messages(fixture, conversation["id"])
        assert [m["content"] for m in chat] == [QUESTION, "أبقِها", "أبقيت الصفقة؛ الوقف عند 2,398."]
    finally:
        await fixture.close()


@pytest.mark.asyncio
async def test_the_owners_next_message_answers_a_background_question_only_when_nothing_else_takes_it():
    database()
    from check_streaming import Fixture
    from lonora_db.schema import RunRow
    from sqlalchemy import select

    async def runs_in(fixture: Any, thread_id: str) -> list[str]:
        async with fixture.runtime.db.sessions() as session:
            return list(
                await session.scalars(select(RunRow.id).where(RunRow.thread_id == thread_id))
            )

    async def status_of(fixture: Any, run_id: str) -> str:
        async with fixture.runtime.db.sessions() as session:
            row = await session.get(RunRow, run_id)
            assert row is not None
            return row.status

    fixture = await Fixture().open()
    try:
        agent = await fixture.agent("Background typed answer")
        conversation = await fixture.conversation(agent)
        # 1. Nothing in the conversation is taking messages: the next message is the answer.
        first = await background_run(fixture, agent, conversation)
        await ask(fixture, first)
        status, body = await send(fixture, conversation["id"], "أغلق نصفها")
        assert status < 300, body
        assert body["run_ids"] == [first["id"]]
        assert await status_of(fixture, first["id"]) == "queued"
        assert await runs_in(fixture, conversation["id"]) == []

        # 2. The owner's own turn that is still active takes a plain message; a reply to
        # the background question still reaches the run that asked it.
        second = await background_run(fixture, agent, conversation)
        second_question = (await ask(fixture, second, "هل أضيف إلى الصفقة؟"))["input_request"]
        busy = await fixture.run(agent, conversation)
        status, body = await send(fixture, conversation["id"], "تابع")
        assert status < 300 and body["run_ids"] == [busy["id"]]
        assert await status_of(fixture, second["id"]) == "waiting_input"
        status, body = await send(
            fixture, conversation["id"], "لا", reply_to=second_question["message_id"]
        )
        assert status < 300 and body["run_ids"] == [second["id"]]

        # 3. Once the owner has written after a question, a later message is a new turn.
        third = await background_run(fixture, agent, conversation)
        await ask(fixture, third, "هل أنقل الوقف؟")
        status, body = await send(fixture, conversation["id"], "سؤال آخر أولاً")
        assert body["run_ids"] == [busy["id"]]
        await fixture.request("POST", "/runs/" + busy["id"] + "/cancel", {})
        status, body = await send(fixture, conversation["id"], "ما وضع الحساب؟")
        assert status < 300 and body["run_ids"] and body["run_ids"] != [third["id"]]
        assert await status_of(fixture, third["id"]) == "waiting_input"
    finally:
        await fixture.close()


@pytest.mark.asyncio
async def test_a_routed_answer_cannot_be_edited_and_later_turns_see_where_it_went():
    database()
    from check_streaming import Fixture
    from lonora_agent.context.history import ROUTED_ANSWER_NOTE

    fixture = await Fixture().open()
    try:
        agent = await fixture.agent("Background edit")
        conversation = await fixture.conversation(agent)
        run = await background_run(fixture, agent, conversation)
        await ask(fixture, run)
        status, body = await send(fixture, conversation["id"], "أبقِها مفتوحة")
        assert body["run_ids"] == [run["id"]]
        status, edited = await send(
            fixture, conversation["id"], "أغلقها", edited_from=body["message"]["id"]
        )
        assert status == 409 and edited["code"] == "message_not_editable"
        # A later owner turn in the conversation reads the question with its choices and
        # learns that the answer already went to the background work.
        from lonora_agent.context.history import history_context

        async with fixture.runtime.db.sessions() as session:
            history = await history_context(
                session, conversation["id"], 10_000, agent_id=agent["id"]
            )
        text = "\n".join(str(message.content) for message in history)
        assert "question_choices" in text
        assert ROUTED_ANSWER_NOTE.strip() in text
    finally:
        await fixture.close()


@pytest.mark.asyncio
async def test_a_question_from_a_run_that_reports_nowhere_else_stays_in_its_own_thread():
    database()
    from check_streaming import Fixture
    from lonora_db.schema import RunRow

    fixture = await Fixture().open()
    try:
        agent = await fixture.agent("Chat watch asker")
        conversation = await fixture.conversation(agent)
        # A watch set in a chat runs in that chat: its question is the chat's own.
        run = await fixture.run(agent, conversation)
        async with fixture.runtime.db.sessions() as session, session.begin():
            row = await session.get(RunRow, run["id"])
            assert row is not None
            row.trigger = "watch"
        question = (await ask(fixture, run))["input_request"]
        assert question["thread_id"] == conversation["id"]
        chat = await thread_messages(fixture, conversation["id"])
        assert [m["content"] for m in chat] == [QUESTION]
    finally:
        await fixture.close()
