"""Actual Agent/runtime/DB question cards; scripted model only, no broker mutations."""

import asyncio
from typing import Any, cast
from unittest.mock import patch
from uuid import uuid4

from check_streaming import Fixture
from lonora_adapter_kit.types import ModelMessage, ModelReply, ToolCall, ToolDefinition
from lonora_agent.executor import execute_run
from lonora_agent.tool_loop import execute_tool_loop
from lonora_contracts.model_routing import ModelSelection
from lonora_db.schema import MessageRow, RunRow, TradingJournalRow
from lonora_tools.loader import load_tools
from lonora_tools.runtime_control import WaitInput
from pydantic import ValidationError
from sqlalchemy import func, select


async def main() -> None:
    fixture = await Fixture().open()
    registry = load_tools()
    choices = [{"id": "yes", "label": "نعم، حلل السوق"}, {"id": "no", "label": "لا"}]
    selection = ModelSelection(provider="openai", model="explicit-question-fixture")
    try:
        agent = await fixture.agent("Question cards")
        thread = await fixture.conversation(agent)
        async with fixture.runtime.db.sessions() as session:
            before_journal = await session.scalar(
                select(func.count()).select_from(TradingJournalRow)
            )

        async def ask(
            *,
            prepublication_crash: bool = False,
            background: bool = False,
        ) -> tuple[dict[str, Any], Any]:
            run = await fixture.run(agent, thread)
            if background:
                async with fixture.runtime.db.sessions() as session, session.begin():
                    row = await session.get(RunRow, run["id"])
                    assert row is not None
                    row.trigger = "routine"
            context = await fixture.lease(run)
            call_id = "question-" + uuid4().hex

            async def complete(
                messages: list[ModelMessage], tools: list[ToolDefinition], *args: Any, **kwargs: Any
            ) -> tuple[ModelReply, ModelSelection]:
                return ModelReply(
                    tool_calls=[
                        ToolCall(
                            id=call_id,
                            name="wait_for_input",
                            arguments={"question": "هل تريد تحليل السوق؟", "choices": choices},
                        )
                    ]
                ), selection

            with patch.object(context.router, "complete", complete):
                if prepublication_crash:
                    outcome = await execute_tool_loop(context, registry, 4)
                    assert outcome.waiting and outcome.input_request
                    async with fixture.runtime.db.sessions() as session:
                        row = await session.get(RunRow, run["id"])
                        assert row and row.execution_state["pending_input_request"]["id"] == call_id
                        assert not row.execution_state.get("input_requests")
                    # A replacement Worker resumes the durable question, not the model/tool.
                    context = await fixture.lease(run)
                    with patch.object(
                        context.router, "complete", side_effect=AssertionError("replayed model")
                    ):
                        await execute_run(context, registry, 120, 4)
                else:
                    await execute_run(context, registry, 120, 4)
            current = await fixture.request("GET", "/runs/" + run["id"])
            assert current["status"] == "waiting_input", current
            question = current["input_request"]
            assert question["choices"] == choices and question["status"] == "pending"
            assert question["id"] == call_id and question["run_id"] == run["id"]
            messages = cast(
                list[dict[str, Any]],
                await fixture.request("GET", f"/threads/{thread['id']}/messages"),
            )
            original = next(
                message for message in messages if message["id"] == question["message_id"]
            )
            assert original["role"] == "assistant" and original["content"] == question["question"]
            return current, context

        run, _ = await ask(prepublication_crash=True)
        question = run["input_request"]
        # Reclaiming an already published pending question must not duplicate its message.
        recovered = await fixture.lease(run)
        with patch.object(
            recovered.router, "complete", side_effect=AssertionError("duplicate model")
        ):
            await execute_run(recovered, registry, 120, 4)
        async with fixture.runtime.db.sessions() as session:
            count = await session.scalar(
                select(func.count())
                .select_from(MessageRow)
                .where(
                    MessageRow.thread_id == thread["id"],
                    MessageRow.content == question["question"],
                )
            )
            assert count == 1
        print("PASS actual tool checkpoint/Worker replacement publishes one stable question")

        body: dict[str, Any] = {
            "content": choices[0]["label"],
            "client_nonce": uuid4().hex,
            "reply_to": question["message_id"],
            "input_answer": {
                "run_id": run["id"],
                "question_id": question["id"],
                "choice_id": "yes",
            },
        }
        wrong = {**body, "input_answer": {**body["input_answer"], "choice_id": "fake"}}
        response = await fixture.client.post(f"/api/threads/{thread['id']}/messages", json=wrong)
        assert response.status_code == 422
        other = await fixture.conversation(await fixture.agent("Other question owner scope"))
        response = await fixture.client.post(f"/api/threads/{other['id']}/messages", json=body)
        assert response.status_code == 409
        concurrent = await asyncio.gather(
            *[fixture.request("POST", f"/threads/{thread['id']}/messages", body) for _ in range(3)]
        )
        assert sum(not result["deduplicated"] for result in concurrent) == 1
        answered = next(result for result in concurrent if not result["deduplicated"])
        assert answered["run_ids"] == [run["id"]] and not answered["deduplicated"]
        repeated = await fixture.request("POST", f"/threads/{thread['id']}/messages", body)
        assert repeated["deduplicated"] and repeated["run_ids"] == [run["id"]]
        response = await fixture.client.post(
            f"/api/threads/{thread['id']}/messages",
            json={
                **body,
                "content": choices[1]["label"],
                "input_answer": {**body["input_answer"], "choice_id": "no"},
            },
        )
        assert response.status_code == 409 and response.json()["code"] == "input_answer_conflict"
        response = await fixture.client.post(
            f"/api/threads/{thread['id']}/messages", json={**body, "client_nonce": uuid4().hex}
        )
        assert response.status_code == 409
        resumed = await fixture.request("GET", "/runs/" + run["id"])
        assert resumed["status"] == "queued"
        assert resumed["input_request"]["selected_choice_id"] == "yes"
        assert resumed["input_request"]["status"] == "answered"
        assert resumed["input_request"]["answer_message_id"] == answered["message"]["id"]
        resumed_context = await fixture.lease(run)

        async def finish(*args: Any, **kwargs: Any) -> tuple[ModelReply, ModelSelection]:
            return ModelReply(text="تم تسجيل الاختيار ومتابعة نفس المهمة."), selection

        with patch.object(resumed_context.router, "complete", finish):
            await execute_run(resumed_context, registry, 120, 4)
        done = await fixture.request("GET", "/runs/" + run["id"])
        assert done["status"] == "completed" and done["input_request"]["status"] == "answered"
        print(
            "PASS exact choice validation, nonce replay/conflict, stale clicks and same-Run continuation"
        )

        background, _ = await ask(background=True)
        free = await fixture.request(
            "POST",
            f"/threads/{thread['id']}/messages",
            {
                "content": "أريد تحليلاً مختلفًا بدل الخيارات",
                "client_nonce": uuid4().hex,
            },
        )
        assert free["run_ids"] == [background["id"]]
        state = await fixture.request("GET", "/runs/" + background["id"])
        assert state["status"] == "queued" and state["input_request"]["status"] == "answered"
        assert state["input_request"]["selected_choice_id"] is None
        await fixture.request("POST", "/runs/" + background["id"] + "/cancel", {})
        cancelled, _ = await ask()
        await fixture.request("POST", "/runs/" + cancelled["id"] + "/cancel", {})
        state = await fixture.request("GET", "/runs/" + cancelled["id"])
        assert state["input_request"]["status"] == "cancelled"
        async with fixture.runtime.db.sessions() as session:
            after_journal = await session.scalar(
                select(func.count()).select_from(TradingJournalRow)
            )
            assert before_journal == after_journal
        print(
            "PASS free text closes the informational card, background questions keep their Run, cancellation disables pending choices; zero trading effects"
        )
        for invalid in [
            [{"id": "a", "label": "One"}, {"id": "a", "label": "Duplicate"}],
            [{"id": str(i), "label": "Item"} for i in range(7)],
        ]:
            try:
                WaitInput.model_validate({"question": "Question", "choices": invalid})
            except ValidationError:
                pass
            else:
                raise AssertionError("Invalid option contract admitted")
        print("PASS bounded unique choice contracts")
    finally:
        await fixture.close()


if __name__ == "__main__":
    asyncio.run(main())
