"""Pure contracts of the tool execution core: planning, overlap, deadlines, loops, notices."""

import asyncio
import json
from types import SimpleNamespace
from typing import Any

import pytest
from lonora_adapter_kit.context import context_blocks, govern_context
from lonora_adapter_kit.types import ModelMessage, ToolCall
from lonora_agent import tool_guardrails as guardrails
from lonora_agent.context.financial_result import unverified_financial_result
from lonora_agent.runtime_notices import (
    NOTICE_OPEN,
    append_notice,
    attach_notice,
    is_runtime_notice,
    notice_message,
)
from lonora_agent.tool_batch import gather_bounded, next_segment, plan_segments
from lonora_core.user_error import LonoraError
from lonora_tools.base import (
    DEFAULT_MUTATION_TIMEOUT_SECONDS,
    DEFAULT_READ_TIMEOUT_SECONDS,
    Tool,
)
from lonora_tools.loader import load_tools
from lonora_tools.registry import ToolRegistry
from pydantic import BaseModel


class Empty(BaseModel):
    pass


async def handler(_: Any, __: dict[str, Any]) -> dict[str, Any]:
    return {}


def tool(name: str, **flags: Any) -> Tool:
    return Tool(name, name, Empty, handler, **flags)


TOOLS = {
    item.name: item
    for item in [
        tool("read_a", read_only=True),
        tool("read_b", read_only=True),
        tool("mutate", replay_safe=True),
        tool("trade", financial=True, replay_safe=True),
        tool("silence", read_only=True, parallel_safe=False),
        tool("status", read_only=True, poller=True),
    ]
}


def call(name: str, identifier: str | None = None, **arguments: Any) -> ToolCall:
    return ToolCall(id=identifier or name, name=name, arguments=arguments)


def shape(calls: list[ToolCall]) -> list[tuple[str, list[str]]]:
    return [
        (segment.kind, [item.id for item in segment.calls])
        for segment in plan_segments(calls, TOOLS)
    ]


def test_planner_keeps_order_and_isolates_every_barrier() -> None:
    calls = [
        call("read_a", "1"),
        call("read_b", "2"),
        call("mutate", "3"),
        call("read_a", "4"),
        call("status", "5"),
        call("read_b", "6"),
        call("silence", "7"),
        call("read_a", "8"),
        call("trade", "9"),
        call("unknown", "10"),
        call("read_a", "11"),
        call("read_b", "12"),
    ]
    assert shape(calls) == [
        ("parallel", ["1", "2"]),
        ("serial", ["3"]),
        ("parallel", ["4", "5", "6"]),
        ("serial", ["7"]),
        # A lone read between barriers keeps the richer serial path.
        ("serial", ["8"]),
        ("serial", ["9"]),
        ("serial", ["10"]),
        ("parallel", ["11", "12"]),
    ]
    flattened = [item.id for segment in plan_segments(calls, TOOLS) for item in segment.calls]
    assert flattened == [item.id for item in calls]
    assert next_segment(calls[2:], TOOLS).calls == (calls[2],)


def test_actual_catalog_never_parallelizes_effects_waits_or_instruction_authority() -> None:
    catalog = load_tools()
    parallel = {name for name, item in catalog.tools.items() if item.runs_in_parallel()}
    assert {"market_quote", "market_candles", "account_read", "web_search"} <= parallel
    for name in (
        "trade_execute",
        "trade_close_positions",
        "goal_step_execute",
        "wait_for_input",
        "task_wait",
        "group_silence",
        "skill_view",
        "skills_list",
        "subagent_spawn",
        "memory_write",
        # The shared browser service fails fast above two pages at once.
        "web_browse",
    ):
        assert name not in parallel, name
    assert all(
        not item.financial and item.read_only
        for name, item in catalog.tools.items()
        if name in parallel
    )


def test_dispatch_deadlines_follow_effect_class_and_financial_tools_are_never_wrapped() -> None:
    assert tool("r", read_only=True).dispatch_timeout() == DEFAULT_READ_TIMEOUT_SECONDS
    assert tool("m").dispatch_timeout() == DEFAULT_MUTATION_TIMEOUT_SECONDS
    assert tool("f", financial=True).dispatch_timeout() is None
    assert tool("slow", read_only=True, timeout_seconds=120).dispatch_timeout() == 120
    catalog = load_tools()
    for name in ("trade_execute", "trade_close_positions", "goal_step_execute"):
        assert catalog.tools[name].dispatch_timeout() is None
    assert catalog.tools["web_browse"].dispatch_timeout() == 60
    for invalid in (
        tool("f", financial=True, timeout_seconds=5),
        tool("m", poller=True),
        tool("r", read_only=True, timeout_seconds=0),
    ):
        with pytest.raises(LonoraError, match="tool_effect_contract_invalid"):
            ToolRegistry([invalid])


@pytest.mark.asyncio
async def test_registry_deadline_raises_the_existing_timeout_classification(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    started = asyncio.Event()

    async def stuck(_: Any, __: dict[str, Any]) -> dict[str, Any]:
        started.set()
        await asyncio.sleep(30)
        return {}

    async def lease(*_: Any, **__: Any) -> Any:
        return SimpleNamespace(trigger="user", model_metadata={})

    class Sessions:
        async def __aenter__(self) -> object:
            return object()

        async def __aexit__(self, *_: Any) -> None:
            return None

    monkeypatch.setattr("lonora_tools.registry.require_lease", lease)

    def for_call(identifier: str) -> Any:
        return SimpleNamespace(call_id=identifier)

    context: Any = SimpleNamespace(
        db=SimpleNamespace(sessions=Sessions),
        lease=None,
        for_call=for_call,
    )
    registry = ToolRegistry(
        [Tool("fixture_stuck", "Stuck", Empty, stuck, True, timeout_seconds=0.05)]
    )
    with pytest.raises(TimeoutError):
        await registry.execute(call("fixture_stuck"), context)
    assert started.is_set()


@pytest.mark.asyncio
async def test_bounded_gather_overlaps_up_to_its_limit_and_keeps_call_order() -> None:
    active = 0
    peak = 0
    release = asyncio.Event()

    def make(index: int) -> Any:
        async def run() -> int:
            nonlocal active, peak
            active += 1
            peak = max(peak, active)
            if peak >= 3:
                release.set()
            await asyncio.wait_for(release.wait(), 2)
            # Later calls finish first; results must still follow call order.
            await asyncio.sleep(0.01 * (6 - index))
            active -= 1
            return index

        return run

    assert await gather_bounded([make(index) for index in range(6)], limit=3) == list(range(6))
    assert peak == 3


@pytest.mark.asyncio
async def test_fatal_error_cancels_sibling_handlers_before_propagating() -> None:
    cancelled = asyncio.Event()

    async def stale() -> int:
        await asyncio.sleep(0.01)
        raise LonoraError("stale_lease", 409)

    async def sibling() -> int:
        try:
            await asyncio.sleep(30)
        except asyncio.CancelledError:
            cancelled.set()
            raise
        return 1

    with pytest.raises(LonoraError, match="stale_lease"):
        await gather_bounded([stale, sibling])
    assert cancelled.is_set()


def failing(state: dict[str, Any], name: str, **arguments: Any) -> guardrails.GuardrailDecision:
    target = TOOLS.get(name) or tool(name, read_only=True)
    return guardrails.after_call(
        state, call(name, **arguments), target, {"ok": False, "code": "x"}, failed=True
    )


def succeeding(
    state: dict[str, Any], name: str, result: dict[str, Any] | None = None, **arguments: Any
) -> guardrails.GuardrailDecision:
    target = TOOLS.get(name) or tool(name, read_only=True)
    return guardrails.after_call(
        state, call(name, **arguments), target, result or {"ok": True}, failed=False
    )


def test_failure_streaks_warn_then_halt_and_a_completed_mutation_resets_them() -> None:
    state: dict[str, Any] = {}
    assert failing(state, "read_a", q=1).action == "allow"
    warned = failing(state, "read_a", q=1)
    assert warned.action == "warn" and warned.code == "repeated_exact_failure_warning"
    assert failing(state, "read_a", q=2).code == "same_tool_failure_warning"
    for value in range(3, 7):
        assert failing(state, "read_a", q=value).action == "warn"
    halted = failing(state, "read_a", q=99)
    assert halted.action == "halt" and halted.code == "same_tool_failure_halt"
    assert guardrails.halt_reason(state) == halted.metadata() | {"message": halted.message}
    # Checkpoint round trip keeps the budget; owner input starts a new epoch.
    restored = json.loads(json.dumps(state))
    assert guardrails.halt_reason(restored)
    guardrails.reset_guardrails(restored)
    assert guardrails.halt_reason(restored) is None

    fresh: dict[str, Any] = {}
    failing(fresh, "read_a", q=1)
    succeeding(fresh, "mutate", {"ok": True, "version": 2})
    assert failing(fresh, "read_a", q=1).action == "allow"


def test_identical_reads_warn_block_then_halt_while_pollers_are_exempt() -> None:
    state: dict[str, Any] = {}
    read = call("read_a", q=1)
    decisions = [succeeding(state, "read_a", {"ok": True, "price": 1}, q=1) for _ in range(2)]
    assert [item.code for item in decisions] == ["allow", "idempotent_no_progress_warning"]
    # Different results are progress, not a loop.
    assert succeeding(state, "read_a", {"ok": True, "price": 2}, q=1).action == "allow"

    blocked: dict[str, Any] = {}
    # Interleave another read so the consecutive-call halt does not fire first.
    for index in range(guardrails.NO_PROGRESS_BLOCK_AFTER):
        succeeding(blocked, "read_a", {"ok": True, "price": 1}, q=1)
        succeeding(blocked, "read_b", {"ok": True, "n": index}, q=index)
    assert guardrails.halt_reason(blocked) is None
    refusal = guardrails.before_call(blocked, read, TOOLS["read_a"])
    assert refusal.action == "block" and refusal.code == "idempotent_no_progress_block"
    synthetic = guardrails.blocked_result(refusal)
    assert synthetic["ok"] is False and synthetic["executed"] is False
    assert synthetic["code"] == "guardrail_blocked"
    assert guardrails.before_call(blocked, read, TOOLS["read_a"]).action == "halt"
    assert guardrails.halt_reason(blocked)

    poller: dict[str, Any] = {}
    for _ in range(12):
        assert succeeding(poller, "status", {"ok": True, "state": "pending"}).action == "allow"
    assert guardrails.before_call(poller, call("status"), TOOLS["status"]).action == "allow"


def test_identical_effects_are_bounded_whatever_they_return() -> None:
    state: dict[str, Any] = {}
    trade, buy = TOOLS["trade"], call("trade", side="buy", symbol="XAUUSD", volume=0.01)
    codes: list[str] = []
    for index in range(guardrails.IDENTICAL_EFFECT_BLOCK_AFTER):
        assert guardrails.before_call(state, buy, trade).action == "allow"
        # Every financial result carries a new operation identity.
        result = {"ok": True, "status": "confirmed", "operation_id": f"op-{index}"}
        codes.append(guardrails.after_call(state, buy, trade, result, failed=False).code)
        if index == 2:
            # An observation between repeats does not make them different effects.
            succeeding(state, "read_a", {"ok": True, "price": index}, q=index)
    assert codes == ["allow"] + ["identical_effect_warning"] * 4
    assert guardrails.halt_reason(state) is None
    # The 6th identical effect is refused before its handler can run.
    restored = json.loads(json.dumps(state))
    refusal = guardrails.before_call(restored, buy, trade)
    assert (refusal.action, refusal.code, refusal.count) == ("block", "identical_effect_block", 5)
    synthetic = guardrails.blocked_result(refusal)
    assert synthetic["executed"] is False and synthetic["code"] == "guardrail_blocked"
    halted = guardrails.before_call(restored, buy, trade)
    assert (halted.action, halted.code) == ("halt", "identical_effect_halt")
    assert guardrails.halt_reason(restored)

    # A different effect starts a new streak; real owner input resets it all.
    other: dict[str, Any] = {}
    sell = call("trade", side="sell", symbol="XAUUSD", volume=0.01)
    for index in range(guardrails.IDENTICAL_EFFECT_BLOCK_AFTER):
        guardrails.after_call(other, buy, trade, {"ok": True, "n": index}, failed=False)
    assert guardrails.after_call(other, sell, trade, {"ok": True}, failed=False).action == "allow"
    assert guardrails.before_call(other, buy, trade).action == "allow"
    for _ in range(guardrails.IDENTICAL_EFFECT_BLOCK_AFTER):
        guardrails.after_call(other, buy, trade, {"ok": True}, failed=False)
    guardrails.reset_guardrails(other)
    assert guardrails.before_call(other, buy, trade).action == "allow"

    # Identical non-financial mutations with identical results use the same bound.
    same: dict[str, Any] = {}
    codes = [succeeding(same, "mutate", {"ok": True, "same": True}).code for _ in range(5)]
    assert codes == ["allow"] + ["identical_effect_warning"] * 4
    assert guardrails.before_call(same, call("mutate"), TOOLS["mutate"]).action == "block"

    # Checkpoints written before the effect streak existed keep loading.
    legacy = {"tool_guardrails": guardrails.fresh_state()}
    del legacy["tool_guardrails"]["effect_streak"]
    assert guardrails.before_call(legacy, buy, trade).action == "allow"
    assert legacy["tool_guardrails"]["effect_streak"] is None


def test_reconciling_an_ambiguous_trade_is_never_counted_as_a_repeated_effect() -> None:
    from lonora_agent.environment import blocked_route, observe

    state: dict[str, Any] = {}
    trade = TOOLS["trade"]
    first = call("trade", "t1", side="buy", symbol="XAUUSD", volume=0.01)
    sent = {"ok": True, "status": "ambiguous", "operation_id": "op-1"}
    record = observe(state, first, trade, sent)
    assert guardrails.after_call(state, first, trade, sent, failed=record["failures"] > 0)
    for index in range(2, 8):
        repeat = call("trade", f"t{index}", side="buy", symbol="XAUUSD", volume=0.01)
        assert guardrails.reconciles(state, repeat, trade)
        route = blocked_route(state, repeat)
        assert route is not None and route["origin_call_id"] == "t1"
        assert guardrails.before_call(state, repeat, trade).action == "allow", index
        # Dispatch reconciled the SAME operation through the blocked route.
        reconciled = {**sent, "_runtime_reconciled": "t1"}
        record = observe(state, repeat, trade, reconciled)
        decision = guardrails.after_call(
            state, repeat, trade, reconciled, failed=record["failures"] > 0
        )
        assert decision.code not in {"identical_effect_block", "identical_effect_halt"}
    assert guardrails.halt_reason(state) is None
    assert guardrails.guardrail_state(state)["effect_streak"][1] == 1
    # The same-tool failure bound still ends an endless reconciliation loop.
    decision = guardrails.ALLOW
    for index in range(8, 12):
        repeat = call("trade", f"t{index}", side="buy", symbol="XAUUSD", volume=0.01)
        reconciled = {**sent, "_runtime_reconciled": "t1"}
        record = observe(state, repeat, trade, reconciled)
        decision = guardrails.after_call(
            state, repeat, trade, reconciled, failed=record["failures"] > 0
        )
    assert decision.code == "same_tool_failure_halt"


def test_short_identical_cycles_end_gracefully() -> None:
    cycle: dict[str, Any] = {}
    decisions: list[guardrails.GuardrailDecision] = []
    for _ in range(guardrails.IDENTICAL_CALL_HALT_AFTER):
        decisions.append(succeeding(cycle, "mutate", {"ok": True, "a": 1}, side="a"))
        decisions.append(succeeding(cycle, "mutate", {"ok": True, "b": 1}, side="b"))
    assert decisions[5].code == "identical_cycle_warning"
    assert decisions[-1].action == "halt" and decisions[-1].code == "identical_cycle_halt"

    pollers: dict[str, Any] = {}
    for _ in range(6):
        assert succeeding(pollers, "status", {"ok": True}, side="a").action == "allow"
        assert succeeding(pollers, "status", {"ok": True}, side="b").action == "allow"


def test_malformed_or_legacy_guard_state_restarts_without_failing_the_run() -> None:
    state: dict[str, Any] = {"guard": {"key": "old", "count": 5}, "tool_guardrails": []}
    assert succeeding(state, "read_a").action == "allow"
    assert "guard" not in state and state["tool_guardrails"]["version"] == 1


def exchange() -> list[ModelMessage]:
    trade = ToolCall(id="trade", name="trade_execute", arguments={})
    return [
        ModelMessage(role="user", content="Buy one lot of gold for me please"),
        ModelMessage(role="assistant", content="", tool_calls=[trade]),
        ModelMessage(
            role="tool",
            tool_call_id="trade",
            content=json.dumps({"ok": True, "status": "confirmed", "details": {}}),
        ),
    ]


def test_notice_joins_latest_tool_result_otherwise_trails_as_runtime_observation() -> None:
    messages = exchange()
    append_notice(messages, "budget", "One round remains.")
    assert len(messages) == 3
    payload = json.loads(messages[-1].content)
    assert payload["runtime_notice"] == [
        {"kind": "budget", "source": "lonora_runtime", "message": "One round remains."}
    ]
    messages.append(ModelMessage(role="assistant", content="Done"))
    append_notice(messages, "completion_check", "Steps remain <script>.")
    notice = messages[-1]
    assert is_runtime_notice(notice) and notice.role == "user"
    assert notice.context_origin == "tool_observation" and NOTICE_OPEN in notice.content
    assert "<script>" not in notice.content
    result: dict[str, Any] = {"ok": False}
    attach_notice(result, "tool_guardrail", "first")
    attach_notice(result, "tool_guardrail", "second")
    assert [item["message"] for item in result["runtime_notice"]] == ["first", "second"]


def test_trailing_notice_stays_with_its_block_and_never_becomes_the_owner_anchor() -> None:
    messages = [
        ModelMessage(role="system", content="policy"),
        ModelMessage(role="user", content="Analyze gold"),
        ModelMessage(role="assistant", content="Partial answer"),
        notice_message("completion_check", "Steps remain."),
    ]
    blocks = context_blocks([item for item in messages if item.role != "system"])
    assert [len(block) for block in blocks] == [1, 2]
    governed = govern_context(messages, 10_000)
    assert governed[-1].context_origin == "tool_observation"
    # A notice can never open a conversation on its own.
    with pytest.raises(LonoraError, match="invalid_tool_exchange"):
        context_blocks([notice_message("budget", "x")])


def test_runtime_notice_cannot_hide_an_unverified_financial_result() -> None:
    messages = exchange()
    expected = unverified_financial_result(messages)
    assert expected and "not yet independently verified" in expected
    messages.append(notice_message("budget", "One round remains."))
    assert unverified_financial_result(messages) == expected
    messages.append(ModelMessage(role="user", content="And what about silver today?"))
    assert unverified_financial_result(messages) is None


def test_owner_attention_notice_states_the_known_truth_in_the_owner_language() -> None:
    from lonora_agent.runtime_notices import attention_message, attention_notice

    english = attention_notice("task_steps_incomplete", False, ["Verify quote", "Report"])
    assert english.startswith("This task is not finished. Steps not completed yet: Verify quote;")
    message = attention_message(english, "Everything is done.", False)
    assert message.startswith(english) and message.endswith("Latest report: Everything is done.")
    assert attention_message(english, "  ", False) == english
    arabic = attention_notice("task_wait_required", True)
    assert arabic.startswith("هذه المهمة المستمرة غير مراقَبة")
    assert "آخر تقرير: تم" in attention_message(arabic, "تم", True)
    limited = attention_notice("tool_round_limit", False, [f"step {n}" for n in range(14)])
    assert "work limit" in limited and "(+2)" in limited
    assert attention_notice("guardrail_halt", False).startswith("This task stopped before")


def test_an_exhausted_read_route_expires_with_a_new_review_epoch() -> None:
    from lonora_agent.environment import blocked_route, observe

    state: dict[str, Any] = {}
    quote = call("read_a", symbol="XAUUSD")
    for _ in range(3):
        observe(state, quote, TOOLS["read_a"], {"ok": False, "code": "market_quote_unavailable"})
    trade = call("trade", side="buy", symbol="XAUUSD", volume=0.01)
    observe(state, trade, TOOLS["trade"], {"ok": True, "status": "ambiguous"})
    assert blocked_route(state, quote) and blocked_route(state, trade)
    # Real owner input or an external wake: the market may have reopened.
    guardrails.reset_guardrails(state)
    assert blocked_route(state, quote) is None
    # An uncertain effect keeps blocking until it is reconciled.
    assert blocked_route(state, trade)
    # Records written before the read-only flag existed are kept.
    observe(state, quote, TOOLS["read_a"], {"ok": False, "code": "market_quote_unavailable"})
    for record in state["environment"]["routes"].values():
        record.pop("read_only", None)
        record["failures"] = 3
    guardrails.reset_guardrails(state)
    assert blocked_route(state, quote)
