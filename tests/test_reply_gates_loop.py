"""The reply guards inside the real tool loop: no entry answers a stop request, and a
claimed action needs a successful effect in the same request."""

from dataclasses import replace
from typing import Any

import pytest
from lonora_adapter_kit.types import ModelMessage, ModelReply, ToolCall
from lonora_agent.executor import execute_run
from lonora_agent.model_runtime import model_turn
from lonora_agent.reply_gates import CLAIM_NUDGE
from lonora_contracts.model_routing import Capability, ModelSelection
from lonora_db.schema import EventRow
from lonora_tools.base import Tool
from lonora_tools.context import ToolContext
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


@pytest.mark.asyncio
async def test_an_unsupported_claim_is_repaired_once_then_replaced(
    task_db: Fixture, monkeypatch: pytest.MonkeyPatch
) -> None:
    context = await conversation_run(task_db, state_for("ألغِ التنبيه"))
    model = Script(ModelReply(text="ألغيت التنبيه."), ModelReply(text="تم."))
    monkeypatch.setattr("lonora_agent.tool_loop.model_turn", model)
    await execute_run(context, ToolRegistry([]), 120, 8)
    run = await saved_run(context)
    second, _ = model.requests[1]
    assert CLAIM_NUDGE.split(",")[0] in second[-1].content
    assert run.status == "completed"
    assert run.result is not None and run.result.startswith("لم يُنفَّذ أي تغيير")


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
    messages = [ModelMessage(role="user", content="اكتب لي كود مؤشر RSI بلغة MQL5")]
    reply, _ = await model_turn(context, messages, [], Capability.CONVERSATION)
    assert "```" not in reply.text and reply.text.startswith("لا أسلّم الكود")
    async with context.db.sessions() as session:
        events = (await session.scalars(select(EventRow))).all()
    published = "".join(
        str(event.payload.get("text", "")) for event in events if event.kind == "run.delta"
    )
    assert "buffer" not in published and published == reply.text
