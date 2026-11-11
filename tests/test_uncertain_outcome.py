"""One appended line when an owner-started request leaves a financial outcome uncertain.

Real result shapes only: trade_execute and trade_close_positions TradeResults, a goal
step's nested and deduplicated result, and the dispatcher's reconciliation of the same
operation. No wording is read.
"""

import json
from typing import Any, cast

import pytest
from lonora_adapter_kit.types import ModelMessage, ModelReply, ToolCall
from lonora_agent.executor import execute_run
from lonora_agent.uncertain_outcome import (
    LINE_AR,
    LINE_EN,
    MAXIMUM_PARTS,
    append_uncertain_line,
    appended_parts,
    record_request_start,
    uncertain_operations,
)
from lonora_contracts.model_routing import ModelSelection
from lonora_tools.base import Tool
from lonora_tools.context import ToolContext
from lonora_tools.registry import ToolRegistry
from pydantic import BaseModel
from test_task_runtime import task_db as task_db
from test_tool_loop_execution import Fixture, Script, conversation_run, saved_run

AR, EN = "اشترِ ذهب 0.1 لوت", "Buy 0.2 lots of EURUSD now"


def exchange(
    name: str, call_id: str, payload: dict[str, Any], **arguments: Any
) -> list[ModelMessage]:
    made = ToolCall(id=call_id, name=name, arguments=arguments)
    return [
        ModelMessage(role="assistant", content="", tool_calls=[made]),
        ModelMessage(role="tool", tool_call_id=call_id, content=json.dumps(payload)),
    ]


def request(
    words: str, *blocks: list[ModelMessage], trigger: str = "user"
) -> tuple[dict[str, Any], list[ModelMessage]]:
    messages = [ModelMessage(role="user", content=words)]
    state: dict[str, Any] = {}
    record_request_start(state, trigger, messages)
    for block in blocks:
        messages += block
    return state, messages


AMBIGUOUS = {"operation_id": "op-1", "status": "ambiguous", "code": "TIMEOUT"}
CONFIRMED = {
    "operation_id": "op-1",
    "status": "confirmed",
    "details": {"verification": {"status": "verified"}},
}


def lined(state: dict[str, Any], messages: list[ModelMessage]) -> bool:
    return bool(uncertain_operations(state, messages))


def test_an_ambiguous_trade_gets_the_line() -> None:
    state, messages = request(AR, exchange("trade_execute", "c1", AMBIGUOUS, action="buy"))
    assert lined(state, messages)
    for payload in (
        {"operation_id": "op-1", "status": "submitted"},
        {"operation_id": "op-1", "status": "reserved"},
        {"ok": False, "code": "tool_execution_uncertain"},
        {"ok": False, "code": "operation_ambiguous"},
        {"results": [{"operation_id": "op-2", "status": "confirmed"}, AMBIGUOUS]},
    ):
        state, messages = request(AR, exchange("trade_close_positions", "c1", payload))
        assert lined(state, messages), payload


def test_a_reconciled_operation_gets_no_line() -> None:
    # The dispatcher replays the same operation and marks it reconciled.
    reconciled = {**CONFIRMED, "_runtime_reconciled": "c1"}
    state, messages = request(
        AR,
        exchange("trade_execute", "c1", AMBIGUOUS, action="buy"),
        exchange("trade_execute", "c2", reconciled, action="buy"),
    )
    assert not lined(state, messages)
    # An uncertain call reconciled under the broker's own operation id settles too.
    uncertain = {"ok": False, "code": "tool_execution_uncertain"}
    state, messages = request(
        AR,
        exchange("trade_execute", "c1", uncertain, action="buy"),
        exchange("trade_execute", "c2", {**CONFIRMED, "_runtime_reconciled": "c1"}),
    )
    assert not lined(state, messages)
    # A later final result of the same operation settles it as well.
    state, messages = request(
        AR,
        exchange("trade_execute", "c1", AMBIGUOUS, action="buy"),
        exchange("trade_execute", "c2", CONFIRMED, action="buy"),
    )
    assert not lined(state, messages)


def test_a_goal_steps_nested_and_deduplicated_results_count() -> None:
    nested = {"decision_id": "d1", "operation_id": "op-9", "result": {"status": "ambiguous"}}
    state, messages = request(AR, exchange("goal_step_execute", "g1", nested, goal_id="g"))
    assert lined(state, messages)
    replay = {**nested, "deduplicated": True}
    state, messages = request(AR, exchange("goal_step_execute", "g1", replay, goal_id="g"))
    assert lined(state, messages)
    settled = {"decision_id": "d1", "operation_id": "op-9", "result": {"status": "confirmed"}}
    state, messages = request(
        AR,
        exchange("goal_step_execute", "g1", nested, goal_id="g"),
        exchange("goal_step_execute", "g2", settled, goal_id="g"),
    )
    assert not lined(state, messages)


@pytest.mark.parametrize(
    "payload",
    [
        {"operation_id": "op-1", "status": "failed", "code": "MARKET_CLOSED"},
        {"operation_id": "op-1", "status": "rejected"},
        {"operation_id": "op-1", "status": "resolved"},
        CONFIRMED,
        {"ok": False, "code": "trade_approval_required"},
    ],
)
def test_a_final_state_gets_no_line(payload: dict[str, Any]) -> None:
    state, messages = request(AR, exchange("trade_execute", "c1", payload, action="buy"))
    assert not lined(state, messages)


def test_other_tools_and_earlier_requests_are_not_read() -> None:
    state, messages = request(AR, exchange("watch_create", "w1", {"status": "ambiguous"}))
    assert not lined(state, messages)
    earlier = exchange("trade_execute", "old", AMBIGUOUS, action="buy")
    messages = [
        *earlier,
        ModelMessage(role="assistant", content="..."),
        ModelMessage(role="user", content=AR),
    ]
    fresh: dict[str, Any] = {}
    record_request_start(fresh, "user", messages)
    assert not lined(fresh, messages)


@pytest.mark.parametrize(
    "trigger", ["broker_event", "goal", "owner_card", "follow_up", "activation", "agent_created"]
)
def test_a_wake_run_gets_no_line_even_with_owner_steering(trigger: str) -> None:
    state, messages = request(
        "wake", exchange("trade_execute", "c1", AMBIGUOUS, action="buy"), trigger=trigger
    )
    messages.append(ModelMessage(role="user", content="وش صار؟"))
    assert not lined(state, messages)
    assert append_uncertain_line(state, messages, "تقرير") == "تقرير"


def test_the_line_follows_the_conversation_language_and_is_appended_once() -> None:
    state, messages = request(AR, exchange("trade_execute", "c1", AMBIGUOUS, action="buy"))
    messages.append(ModelMessage(role="assistant", content="حللت الذهب وأرسلت الطلب."))
    text = append_uncertain_line(state, messages, "حللت الذهب وأرسلت الطلب.")
    assert text == "حللت الذهب وأرسلت الطلب.\n\n" + LINE_AR
    assert messages[-1].content == text
    assert append_uncertain_line(state, messages, text) == text
    state, messages = request(EN, exchange("trade_execute", "c1", AMBIGUOUS, action="buy"))
    assert append_uncertain_line(state, messages, "Sent.").endswith(LINE_EN)


def test_a_full_card_keeps_every_part() -> None:
    card: dict[str, Any] = {"type": "ui", "document": {}}
    texts: list[Any] = [{"type": "text", "text": str(i)} for i in range(MAXIMUM_PARTS)]
    parts: list[Any] = [card, *texts]
    assert len(parts) == MAXIMUM_PARTS + 1
    kept = appended_parts(parts, LINE_AR)
    assert len(kept) == len(parts) and kept[0] == card
    assert kept[-1]["text"].endswith(LINE_AR)
    state, messages = request(AR, exchange("trade_execute", "c1", AMBIGUOUS, action="buy"))
    rich: dict[str, Any] = {"version": 1, "parts": parts}
    state["rich_content"] = rich
    append_uncertain_line(state, messages, "تحليل")
    stored = cast(list[Any], state["rich_content"]["parts"])
    assert stored[0] == card and len(stored) == len(parts)


# --- In the real loop ------------------------------------------------------------------


class Anything(BaseModel):
    model_config = {"extra": "allow"}


async def ambiguous_trade(context: ToolContext, _: dict[str, Any]) -> dict[str, Any]:
    return {"operation_id": "op-" + context.call_id, "status": "ambiguous", "code": "TIMEOUT"}


def trade_registry(*extra: Tool) -> ToolRegistry:
    return ToolRegistry(
        [Tool("trade_execute", "Trade", Anything, ambiguous_trade, financial=True), *extra]
    )


def seeded(words: str, pending: list[ToolCall]) -> dict[str, Any]:
    messages = [
        ModelMessage(role="user", content=words),
        ModelMessage(role="assistant", content="", tool_calls=pending),
    ]
    return {
        "messages": [item.model_dump(mode="json") for item in messages],
        "pending": [item.model_dump(mode="json") for item in pending],
        "instruction_skill_ids": [],
        "rounds": 1,
        "environment": {"version": 1},
    }


BUY = ToolCall(id="buy", name="trade_execute", arguments={"action": "buy", "symbol": "XAUUSD"})


@pytest.mark.asyncio
async def test_the_final_reply_keeps_its_analysis_and_gets_the_line(
    task_db: Fixture, monkeypatch: pytest.MonkeyPatch
) -> None:
    context = await conversation_run(task_db, seeded(AR, [BUY]))
    model = Script(ModelReply(text="الذهب في اتجاه صاعد؛ أرسلت طلب الشراء."))
    monkeypatch.setattr("lonora_agent.tool_loop.model_turn", model)
    await execute_run(context, trade_registry(), 120, 8)
    run = await saved_run(context)
    assert run.result == "الذهب في اتجاه صاعد؛ أرسلت طلب الشراء.\n\n" + LINE_AR


@pytest.mark.asyncio
async def test_the_round_limit_report_gets_the_line(
    task_db: Fixture, monkeypatch: pytest.MonkeyPatch
) -> None:
    context = await conversation_run(task_db, seeded(AR, [BUY]))
    model = Script(ModelReply(text="توقفت عند حد الجولات."))
    monkeypatch.setattr("lonora_agent.tool_loop.model_turn", model)
    await execute_run(context, trade_registry(), 120, 2)
    run = await saved_run(context)
    assert run.model_metadata["exit_reason"] == "tool_round_limit"
    assert run.result == "توقفت عند حد الجولات.\n\n" + LINE_AR


@pytest.mark.asyncio
async def test_the_guardrail_report_gets_the_line(
    task_db: Fixture, monkeypatch: pytest.MonkeyPatch
) -> None:
    async def write(_: ToolContext, __: dict[str, Any]) -> dict[str, Any]:
        return {"version": 1}

    registry = trade_registry(Tool("fixture_write", "Write", Anything, write))
    context = await conversation_run(task_db, seeded(AR, [BUY]))
    repeats = [
        ModelReply(tool_calls=[ToolCall(id=f"same-{i}", name="fixture_write", arguments={"n": 7})])
        for i in range(9)
    ]
    model = Script(*repeats)

    async def turn(context: Any, messages: list[ModelMessage], tools: list[Any], *a: Any, **k: Any):
        if not tools:
            return ModelReply(text="توقفت لأن التكرار لا يغيّر شيئًا."), ModelSelection(
                provider="openai", model="scripted"
            )
        return await model(context, messages, tools, *a, **k)

    monkeypatch.setattr("lonora_agent.tool_loop.model_turn", turn)
    await execute_run(context, registry, 120, 24)
    run = await saved_run(context)
    assert run.model_metadata["exit_reason"] == "guardrail_halt"
    assert run.result == "توقفت لأن التكرار لا يغيّر شيئًا.\n\n" + LINE_AR


@pytest.mark.asyncio
async def test_a_question_reply_without_financial_calls_is_untouched(
    task_db: Fixture, monkeypatch: pytest.MonkeyPatch
) -> None:
    context = await conversation_run(task_db, seeded(AR, []) | {"pending": [], "rounds": 0})
    model = Script(ModelReply(text="تم."))
    monkeypatch.setattr("lonora_agent.tool_loop.model_turn", model)
    await execute_run(context, trade_registry(), 120, 8)
    run = await saved_run(context)
    assert run.result == "تم."
