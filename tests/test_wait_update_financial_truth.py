"""Suspension prose uses the same disclosure and execution-truth boundary."""

import json
from types import SimpleNamespace
from typing import Any, cast
from unittest.mock import AsyncMock

import pytest
from lonora_adapter_kit.types import ModelMessage, ModelReply, ToolCall
from lonora_agent import model_runtime
from lonora_contracts.model_routing import Capability, ModelSelection
from lonora_tools.context import ToolContext


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "scenario",
    [
        "proposed",
        "unverified",
        "verified",
        "private",
        "failed",
        "ambiguous",
        "rejected",
        "pending",
        "submitted",
        "failed_final",
    ],
)
async def test_wait_prose_cannot_publish_premature_or_private_financial_claims(
    monkeypatch: pytest.MonkeyPatch, scenario: str
):
    wait = ToolCall(id="wait", name="task_wait", arguments={"kind": "timer"})
    trade = ToolCall(id="mutation", name="trade_execute", arguments={})
    calls = (
        [trade, wait] if scenario == "proposed" else [] if scenario == "failed_final" else [wait]
    )
    proposed = "The position was opened. I will review after the next close."
    answer = (
        "Review aaaaaaaa-bbbb-4ccc-8ddd-eeeeeeeeeeee at /mnt/data/private.json before the next check."
        if scenario == "private"
        else proposed
    )
    if scenario == "failed_final":
        answer = "The broker rejected the request because the volume is invalid."
    messages = [ModelMessage(role="user", content="نفذ ثم تابع الصفقة")]
    if scenario in {
        "unverified",
        "verified",
        "failed",
        "ambiguous",
        "rejected",
        "pending",
        "submitted",
        "failed_final",
    }:
        messages.extend(
            [
                ModelMessage(role="assistant", content="", tool_calls=[trade]),
                ModelMessage(
                    role="tool",
                    tool_call_id=trade.id,
                    content=json.dumps(
                        {
                            "status": "confirmed"
                            if scenario in {"unverified", "verified"}
                            else scenario,
                            "code": "TRADE_RETCODE_INVALID_VOLUME",
                            "details": {
                                "verification": {
                                    "status": "verified" if scenario == "verified" else "pending"
                                }
                            },
                        }
                    ),
                ),
            ]
        )
    reply = ModelReply(text=answer, tool_calls=calls)
    complete = AsyncMock(return_value=(reply, ModelSelection(provider="openai", model="scripted")))
    context = cast(
        ToolContext,
        SimpleNamespace(
            db=None,
            owner_id="owner",
            agent_id="agent",
            thread_id="thread",
            lease=SimpleNamespace(run_id="run"),
            router=SimpleNamespace(complete=complete),
        ),
    )
    monkeypatch.setattr(model_runtime, "refresh_routing_context", AsyncMock())

    async def images(
        _context: Any, data: list[ModelMessage]
    ) -> tuple[list[ModelMessage], dict[str, Any]]:
        return data, {}

    monkeypatch.setattr(model_runtime, "prepare_image_observations", images)
    monkeypatch.setattr(model_runtime, "save_usage", AsyncMock())
    published = AsyncMock()
    monkeypatch.setattr(model_runtime, "progress", published)
    actual, _ = await model_runtime.model_turn(context, messages, [], Capability.BACKGROUND)
    assert actual.tool_calls == calls and complete.await_count == 1
    text = "".join(
        str(call.args[2]["text"])
        for call in published.await_args_list
        if call.args[1] == "run.delta"
    )
    assert text == actual.text
    if scenario == "proposed":
        assert not actual.text
    elif scenario == "private":
        assert "[REDACTED]" in actual.text
        assert "aaaaaaaa-bbbb-4ccc-8ddd-eeeeeeeeeeee" not in actual.text
        assert "/mnt/data/private.json" not in actual.text
        assert "position was opened" not in actual.text
    elif scenario in {"failed", "rejected"}:
        assert "لم يُنفّذ الطلب" in actual.text and "حجم التداول" in actual.text
        assert "position was opened" not in actual.text
    elif scenario in {"ambiguous", "pending", "submitted"}:
        assert "قبل أي إعادة إرسال" in actual.text and "position was opened" not in actual.text
    elif scenario == "failed_final":
        assert actual.text == answer
    elif scenario == "unverified":
        assert "لم يكتمل بعد" in actual.text and actual.text != proposed
    else:
        assert actual.text == proposed


@pytest.mark.parametrize(
    "payload",
    [
        {"ok": False, "status": "ambiguous", "code": "broker_result_ambiguous"},
        {"ok": False, "code": "tool_execution_uncertain"},
        {"ok": False, "status": "submitted"},
        {"ok": False, "status": "pending"},
        {
            "ok": False,
            "results": [
                {"status": "confirmed", "details": {"verification": {"status": "verified"}}},
                {"status": "ambiguous"},
            ],
        },
    ],
)
def test_ambiguous_failure_wrapper_is_not_evidence_of_nonexecution(payload: dict[str, Any]):
    from lonora_agent.context.financial_result import unsettled_wait_result

    result = unsettled_wait_result(
        [
            ModelMessage(role="user", content="نفذ ثم تابع الحساب"),
            ModelMessage(
                role="assistant",
                content="",
                tool_calls=[ToolCall(id="effect", name="trade_execute", arguments={})],
            ),
            ModelMessage(role="tool", tool_call_id="effect", content=json.dumps(payload)),
        ]
    )
    assert result and "قبل أي إعادة إرسال" in result
    assert "لم يُنفّذ" not in result
    assert any(word in result for word in ("غير محسومة", "تعذر تأكيد", "لم تتأكد جميع"))


@pytest.mark.parametrize("locale", ["ar", "en"])
@pytest.mark.parametrize(
    "code",
    ["TRADE_RETCODE_MARKET_CLOSED", "err_invalid_stops", "invalid_volume", "token=private-secret"],
)
def test_wait_rejection_summary_uses_known_causes_and_never_arbitrary_diagnostics(
    locale: str, code: str
):
    from lonora_agent.context.financial_result import unsettled_wait_result

    result = unsettled_wait_result(
        [
            ModelMessage(
                role="user",
                content="نفذ ثم تابع الحساب"
                if locale == "ar"
                else "Execute then review the account",
            ),
            ModelMessage(
                role="assistant",
                content="",
                tool_calls=[ToolCall(id="effect", name="trade_execute", arguments={})],
            ),
            ModelMessage(
                role="tool",
                tool_call_id="effect",
                content=json.dumps(
                    {
                        "status": "failed",
                        "code": code,
                        "details": {"description": "token=private-secret"},
                    }
                ),
            ),
        ]
    )
    assert result and "private-secret" not in result and "token=" not in result
    if code.upper().endswith("MARKET_CLOSED"):
        assert ("السوق مغلق" if locale == "ar" else "market is closed") in result
    if code.upper().endswith("INVALID_STOPS"):
        assert ("وقف الخسارة" if locale == "ar" else "stop-loss") in result
