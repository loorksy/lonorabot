"""The reply guards inside the real tool loop: no entry answers a stop request, exits
always run, and a claimed action needs a successful result of its kind in the request."""

from dataclasses import replace
from typing import Any

import pytest
from lonora_adapter_kit.types import ModelMessage, ModelReply, ToolCall
from lonora_agent.executor import execute_run
from lonora_agent.model_runtime import model_turn
from lonora_agent.reply_gates import CLAIM_NUDGE, record_owner_request
from lonora_agent.tool_block import goal_step_action
from lonora_agent.tool_exposure import ensure_exposure
from lonora_contracts.model_routing import Capability, ModelSelection
from lonora_db.schema import EventRow, MessageRow
from lonora_tools.base import Tool
from lonora_tools.context import ToolContext
from lonora_tools.loader import load_tools
from lonora_tools.registry import ToolRegistry
from pydantic import BaseModel
from sqlalchemy import select
from test_task_runtime import task_db as task_db
from test_tool_loop_execution import Fixture, Script, conversation_run, results, saved_run


class Anything(BaseModel):
    model_config = {"extra": "allow"}


def state_for(owner: str, pending: list[ToolCall] | None = None) -> dict[str, Any]:
    messages = [ModelMessage(role="user", content=owner)]
    if pending:
        messages.append(ModelMessage(role="assistant", content="", tool_calls=pending))
    return {
        "messages": [item.model_dump(mode="json") for item in messages],
        "pending": [item.model_dump(mode="json") for item in pending or []],
        "instruction_skill_ids": [],
        "rounds": 1 if pending else 0,
        "environment": {"version": 1},
    }


@pytest.mark.asyncio
async def test_a_stop_request_never_reaches_the_trade_handler(
    task_db: Fixture, monkeypatch: pytest.MonkeyPatch
) -> None:
    executed: list[dict[str, Any]] = []

    async def trade(_: ToolContext, arguments: dict[str, Any]) -> dict[str, Any]:
        executed.append(arguments)
        return {"status": "confirmed"}

    registry = ToolRegistry([Tool("trade_execute", "Trade", Anything, trade, financial=True)])
    buy = ToolCall(id="buy", name="trade_execute", arguments={"action": "buy", "symbol": "EURUSD"})
    context = await conversation_run(task_db, state_for("أوقف الصفقات الجديدة اليوم", [buy]))
    model = Script(ModelReply(text="لم أفتح أي صفقة، وسأسجّل الإيقاف لليوم."))
    monkeypatch.setattr("lonora_agent.tool_loop.model_turn", model)
    await execute_run(context, registry, 120, 8)
    run = await saved_run(context)
    assert executed == []
    refused = results(run)["buy"]
    assert refused["code"] == "owner_stop_request_no_entry" and refused["executed"] is False
    assert run.status == "completed"


@pytest.mark.asyncio
async def test_closing_still_runs_under_a_stop_request(
    task_db: Fixture, monkeypatch: pytest.MonkeyPatch
) -> None:
    executed: list[dict[str, Any]] = []

    async def trade(_: ToolContext, arguments: dict[str, Any]) -> dict[str, Any]:
        executed.append(arguments)
        return {"ok": False, "code": "fixture_not_sent"}

    registry = ToolRegistry([Tool("trade_execute", "Trade", Anything, trade, financial=True)])
    close = ToolCall(id="close", name="trade_execute", arguments={"action": "close_position"})
    context = await conversation_run(task_db, state_for("stop trading and close EURUSD", [close]))
    model = Script(ModelReply(text="The close was not sent."))
    monkeypatch.setattr("lonora_agent.tool_loop.model_turn", model)
    await execute_run(context, registry, 120, 8)
    assert executed == [{"action": "close_position"}]


LINE = "لم أتمكن من تأكيد ذلك بعد."


async def committed(context: ToolContext) -> MessageRow:
    async with context.db.sessions() as session:
        rows = (
            await session.scalars(
                select(MessageRow)
                .where(MessageRow.thread_id == context.thread_id, MessageRow.role == "assistant")
                .order_by(MessageRow.seq.desc())
            )
        ).all()
    return rows[0]


@pytest.mark.asyncio
async def test_an_unsupported_claim_is_repaired_once_then_keeps_its_reply_and_card(
    task_db: Fixture, monkeypatch: pytest.MonkeyPatch
) -> None:
    card = {"version": 1, "parts": [{"type": "text", "text": "تنبيه الذهب فوق 2400"}]}
    context = await conversation_run(task_db, state_for("ألغِ التنبيه"))
    model = Script(
        ModelReply(text="ألغيت التنبيه."),
        ModelReply(text="تم. وهذا تحليل الذهب اليوم.", rich_content=card),
    )
    monkeypatch.setattr("lonora_agent.tool_loop.model_turn", model)
    await execute_run(context, ToolRegistry([]), 120, 8)
    run = await saved_run(context)
    second, _ = model.requests[1]
    assert CLAIM_NUDGE.split(",")[0] in second[-1].content
    assert run.status == "completed"
    # Nothing is discarded: the reply, then one honest line; the card keeps its parts.
    assert run.result == "تم. وهذا تحليل الذهب اليوم.\n\n" + LINE
    message = await committed(context)
    assert message.rich_content is not None
    texts = [part.get("text") for part in message.rich_content["parts"]]
    assert texts == ["تنبيه الذهب فوق 2400", LINE]


@pytest.mark.asyncio
async def test_the_tool_less_final_report_after_a_repair_gets_the_line(
    task_db: Fixture, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Review C13: the nudge on the second-to-last round ends in finish_turn.
    context = await conversation_run(task_db, state_for("ألغِ التنبيه"))
    model = Script(ModelReply(text="ألغيت التنبيه."), ModelReply(text="تم."))
    monkeypatch.setattr("lonora_agent.tool_loop.model_turn", model)
    await execute_run(context, ToolRegistry([]), 120, 2)
    run = await saved_run(context)
    assert len(model.requests) == 2 and model.requests[1][1] == []
    assert run.result == "تم.\n\n" + LINE


@pytest.mark.asyncio
async def test_a_question_is_never_claim_checked(
    task_db: Fixture, monkeypatch: pytest.MonkeyPatch
) -> None:
    context = await conversation_run(task_db, state_for("كم الرصيد؟"))
    model = Script(ModelReply(text="تم. الرصيد 9841.69 USD."))
    monkeypatch.setattr("lonora_agent.tool_loop.model_turn", model)
    await execute_run(context, ToolRegistry([]), 120, 8)
    run = await saved_run(context)
    assert run.result == "تم. الرصيد 9841.69 USD." and len(model.requests) == 1


@pytest.mark.asyncio
async def test_the_repair_turn_can_still_close_but_not_open(
    task_db: Fixture, monkeypatch: pytest.MonkeyPatch
) -> None:
    executed: list[str] = []

    async def trade(_: ToolContext, arguments: dict[str, Any]) -> dict[str, Any]:
        executed.append(str(arguments["action"]))
        return {"ok": False, "code": "fixture_not_sent"}

    registry = ToolRegistry([Tool("trade_execute", "Trade", Anything, trade, financial=True)])
    close = ToolCall(id="close", name="trade_execute", arguments={"action": "close_position"})
    buy = ToolCall(id="buy", name="trade_execute", arguments={"action": "buy"})
    context = await conversation_run(task_db, state_for("سكّر صفقة اليورو"))
    model = Script(
        ModelReply(text="سكّرت الصفقة."),
        ModelReply(text="", tool_calls=[close]),
        ModelReply(text="", tool_calls=[buy]),
        ModelReply(text="لم أتمكن من إغلاقها بعد."),
    )
    monkeypatch.setattr("lonora_agent.tool_loop.model_turn", model)
    await execute_run(context, registry, 120, 8)
    run = await saved_run(context)
    assert executed == ["close_position"]
    assert results(run)["buy"]["code"] == "claim_repair_no_new_risk"


@pytest.mark.asyncio
async def test_a_missing_goal_step_is_left_to_its_handler(task_db: Fixture) -> None:
    context = await conversation_run(task_db, state_for("أوقف التداول"))
    step = ToolCall(id="step", name="goal_step_execute", arguments={"goal_id": "missing"})
    assert await goal_step_action(context, step) is None


@pytest.mark.asyncio
async def test_ensure_exposure_promotes_the_named_control_tool(task_db: Fixture) -> None:
    context = await conversation_run(task_db, state_for("أوقف الصفقات الجديدة اليوم"))
    registry = load_tools()
    state: dict[str, Any] = {}
    messages = [ModelMessage(role="user", content="أوقف الصفقات الجديدة اليوم")]
    record_owner_request(state, "user", messages)
    exposure = await ensure_exposure(
        context, registry, state, messages, [], scope="full", task_run=False
    )
    assert "trade_restriction_create" in exposure["native"]
    assert "trade_restriction_create" in exposure["promoted"]
    quiet: dict[str, Any] = {}
    record_owner_request(quiet, "user", [ModelMessage(role="user", content="حلل الذهب")])
    plain = await ensure_exposure(context, registry, quiet, [], [], scope="full", task_run=False)
    assert "trade_restriction_create" not in plain["native"]


@pytest.mark.asyncio
async def test_a_claim_backed_by_a_successful_effect_passes(
    task_db: Fixture, monkeypatch: pytest.MonkeyPatch
) -> None:
    async def cancel(_: ToolContext, __: dict[str, Any]) -> dict[str, Any]:
        return {"ok": True, "status": "cancelled"}

    registry = ToolRegistry([Tool("watch_cancel", "Cancel a watch", Anything, cancel)])
    pending = [ToolCall(id="cancel", name="watch_cancel", arguments={})]
    context = await conversation_run(task_db, state_for("ألغِ التنبيه", pending))
    model = Script(ModelReply(text="ألغيت التنبيه."))
    monkeypatch.setattr("lonora_agent.tool_loop.model_turn", model)
    await execute_run(context, registry, 120, 8)
    run = await saved_run(context)
    assert run.result == "ألغيت التنبيه." and len(model.requests) == 1


class ScriptedRouter:
    """Streams one reply in chunks, as a provider does."""

    def __init__(self, text: str) -> None:
        self.text = text

    async def complete(self, *_: Any, on_delta: Any = None, **__: Any) -> Any:
        for index in range(0, len(self.text), 40):
            if on_delta:
                await on_delta(self.text[index : index + 40])
        return ModelReply(text=self.text), ModelSelection(provider="openai", model="scripted")


@pytest.mark.asyncio
async def test_requested_code_is_declined_before_any_of_it_is_published(
    task_db: Fixture,
) -> None:
    code = "```mql5\n" + "\n".join(f"double buffer{i}[];" for i in range(20)) + "\n```"
    context = await conversation_run(task_db, state_for("اكتب لي كود مؤشر RSI بلغة MQL5"))
    context = replace(context, router=ScriptedRouter("هذا الكود:\n" + code))
    words = "اكتب لي كود مؤشر RSI بلغة MQL5"
    messages = [ModelMessage(role="user", content=words)]
    reply, _ = await model_turn(context, messages, [], Capability.CONVERSATION, owner_request=words)
    assert "```" not in reply.text and "لا أسلّم الكود" in reply.text
    assert reply.text.startswith("هذا الكود:")
    async with context.db.sessions() as session:
        events = (await session.scalars(select(EventRow))).all()
    published = "".join(
        str(event.payload.get("text", "")) for event in events if event.kind == "run.delta"
    )
    assert "buffer" not in published and published == reply.text
