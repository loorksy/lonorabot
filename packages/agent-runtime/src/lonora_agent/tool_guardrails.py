"""Tool-call loop guardrails kept in the durable Run checkpoint.

Adapted from Hermes Agent ``agent/tool_guardrails.py``
(``ToolCallGuardrailController``: exact-args failure streaks, same-tool failure
counts, identical no-progress results and short identical call cycles).
Source: NousResearch/hermes-agent, MIT License, Copyright (c) 2025 Nous
Research. Lonora keeps the controller pure and JSON-serializable so a restart
or a new compute slice cannot buy a fresh loop budget, and classifies tools from
the server registry (``read_only``/``poller``), never from model declarations.

Decisions never raise: ``warn`` guidance is attached to the tool result,
``block`` replaces an execution with a synthetic observation and ``halt`` asks
the loop for its graceful finish. Effect boundaries stay with the executor;
exact failing financial or ambiguous routes are still refused by the existing
environment route record before this controller is consulted.
"""

import hashlib
import json
from dataclasses import dataclass
from typing import Any, Literal, cast

from lonora_adapter_kit.types import ToolCall
from lonora_tools.base import Tool

from .environment import route_key

STATE_KEY = "tool_guardrails"
VERSION = 1

EXACT_FAILURE_WARN_AFTER = 2
SAME_TOOL_FAILURE_WARN_AFTER = 3
SAME_TOOL_FAILURE_HALT_AFTER = 8
NO_PROGRESS_WARN_AFTER = 2
NO_PROGRESS_BLOCK_AFTER = 5
# Two refused repeats after a block mean the model is not changing strategy.
NO_PROGRESS_HALT_AFTER = NO_PROGRESS_BLOCK_AFTER + 2
IDENTICAL_CALL_NOTICE_AFTER = 3
IDENTICAL_CALL_HALT_AFTER = 5
MAXIMUM_CYCLE_PERIOD = 4
HISTORY_LIMIT = 32

Action = Literal["allow", "warn", "block", "halt"]

_MESSAGES = {
    "repeated_exact_failure_warning": (
        "{tool} has failed {count} times with identical arguments. Inspect the error and "
        "change strategy instead of retrying it unchanged."
    ),
    "same_tool_failure_warning": (
        "{tool} has failed {count} times in this run. Diagnose the latest error before "
        "another attempt: correct the arguments, use a narrower request or a genuinely "
        "different source, or report the blocker."
    ),
    "same_tool_failure_halt": (
        "{tool} failed {count} times in this run. Stop retrying this failing path."
    ),
    "idempotent_no_progress_warning": (
        "{tool} returned the same result {count} times. Use the result already provided "
        "or change the request instead of repeating it unchanged."
    ),
    "idempotent_no_progress_block": (
        "{tool} was not executed: the identical read already returned the same result "
        "{count} times. Use that result or change the request."
    ),
    "idempotent_no_progress_halt": (
        "{tool} kept being requested unchanged after it was refused for making no progress."
    ),
    "identical_call_warning": (
        "This is call {count} in a row to {tool} with identical arguments and an identical "
        "result. Do not repeat it; change the arguments, use a different tool or proceed "
        "with what you have."
    ),
    "identical_call_halt": (
        "{tool} was called {count} times in a row with identical arguments and an identical result."
    ),
    "identical_cycle_warning": (
        "The last {count} rounds repeated the same cycle of {period} calls (ending with "
        "{tool}) with identical arguments and results. Repeating it is not progress."
    ),
    "identical_cycle_halt": (
        "The same cycle of {period} calls (ending with {tool}) repeated {count} times with "
        "identical arguments and results."
    ),
}
_SEVERITY = {"allow": 0, "warn": 1, "block": 2, "halt": 3}


@dataclass(frozen=True)
class GuardrailDecision:
    action: Action = "allow"
    code: str = "allow"
    message: str = ""
    tool: str = ""
    count: int = 0

    def metadata(self) -> dict[str, Any]:
        return {"action": self.action, "code": self.code, "tool": self.tool, "count": self.count}


ALLOW = GuardrailDecision()


def _decision(action: Action, code: str, tool: str, count: int, **values: Any) -> GuardrailDecision:
    message = _MESSAGES[code].format(tool=tool, count=count, **values)
    return GuardrailDecision(action, code, message, tool, count)


def _stronger(left: GuardrailDecision, right: GuardrailDecision) -> GuardrailDecision:
    return right if _SEVERITY[right.action] > _SEVERITY[left.action] else left


def fresh_state() -> dict[str, Any]:
    return {
        "version": VERSION,
        "exact_failures": {},
        "tool_failures": {},
        "no_progress": {},
        "history": [],
        "halt": None,
    }


def guardrail_state(state: dict[str, Any]) -> dict[str, Any]:
    """Load the checkpointed controller; a malformed heuristic restarts empty.

    Unlike the stop gates, this controller grants no completion or authority:
    the round budget and route records still bound the Run if it restarts.
    """
    # The previous single-key repeat counter raised a Run failure; it is retired.
    state.pop("guard", None)
    saved = state.get(STATE_KEY)
    if not _valid(saved):
        saved = fresh_state()
        state[STATE_KEY] = saved
    return cast(dict[str, Any], saved)


def _valid(saved: Any) -> bool:
    if not isinstance(saved, dict):
        return False
    value = cast(dict[str, Any], saved)
    return (
        value.get("version") == VERSION
        and all(isinstance(value.get(key), dict) for key in ("exact_failures", "tool_failures"))
        and isinstance(value.get("no_progress"), dict)
        and isinstance(value.get("history"), list)
        and (value.get("halt") is None or isinstance(value.get("halt"), dict))
    )


def reset_guardrails(state: dict[str, Any]) -> None:
    """Real owner input or an external wake starts a new review epoch."""
    state.pop(STATE_KEY, None)
    state.pop("guard", None)


def result_digest(result: dict[str, Any]) -> str:
    stable = {key: value for key, value in result.items() if key != "runtime_notice"}
    encoded = json.dumps(stable, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(encoded.encode("utf-8", "surrogatepass")).hexdigest()[:16]


def _idempotent(tool: Tool | None) -> bool:
    return bool(tool and tool.read_only and not tool.poller)


def before_call(state: dict[str, Any], call: ToolCall, tool: Tool | None) -> GuardrailDecision:
    """Refuse an unchanged read that already proved to make no progress."""
    if not _idempotent(tool):
        return ALLOW
    guard = guardrail_state(state)
    signature = route_key(call)
    record = guard["no_progress"].get(signature)
    if not isinstance(record, list) or len(cast(list[Any], record)) != 2:
        return ALLOW
    count = cast(list[Any], record)[1]
    if type(count) is not int or count < NO_PROGRESS_BLOCK_AFTER:
        return ALLOW
    # Count the refused attempt so an ignored refusal escalates to a halt.
    guard["no_progress"][signature] = [cast(list[Any], record)[0], count + 1]
    if count + 1 >= NO_PROGRESS_HALT_AFTER:
        decision = _decision("halt", "idempotent_no_progress_halt", call.name, count + 1)
        guard["halt"] = decision.metadata() | {"message": decision.message}
        return decision
    return _decision("block", "idempotent_no_progress_block", call.name, count)


def blocked_result(decision: GuardrailDecision) -> dict[str, Any]:
    """Synthetic observation; the handler was not executed and nothing changed."""
    return {
        "ok": False,
        "code": "guardrail_blocked",
        "executed": False,
        "guardrail": decision.metadata(),
        "message": decision.message,
    }


def after_call(
    state: dict[str, Any],
    call: ToolCall,
    tool: Tool | None,
    result: dict[str, Any],
    *,
    failed: bool,
) -> GuardrailDecision:
    guard = guardrail_state(state)
    signature = route_key(call)
    digest = result_digest(result)
    exact: dict[str, int] = guard["exact_failures"]
    per_tool: dict[str, int] = guard["tool_failures"]
    no_progress: dict[str, list[Any]] = guard["no_progress"]
    decision = ALLOW
    if failed:
        exact_count = exact[signature] = int(exact.get(signature, 0)) + 1
        same_count = per_tool[call.name] = int(per_tool.get(call.name, 0)) + 1
        no_progress.pop(signature, None)
        if same_count >= SAME_TOOL_FAILURE_HALT_AFTER:
            decision = _decision("halt", "same_tool_failure_halt", call.name, same_count)
        elif exact_count >= EXACT_FAILURE_WARN_AFTER:
            decision = _decision("warn", "repeated_exact_failure_warning", call.name, exact_count)
        elif same_count >= SAME_TOOL_FAILURE_WARN_AFTER:
            decision = _decision("warn", "same_tool_failure_warning", call.name, same_count)
    else:
        exact.pop(signature, None)
        per_tool.pop(call.name, None)
        if tool is not None and not tool.read_only:
            # A completed mutation makes the next retry a new experiment and may
            # change what an identical read returns.
            exact.clear()
            per_tool.clear()
            no_progress.clear()
        elif _idempotent(tool):
            previous = no_progress.get(signature)
            repeat = (
                int(previous[1]) + 1
                if isinstance(previous, list) and len(previous) == 2 and previous[0] == digest
                else 1
            )
            no_progress[signature] = [digest, repeat]
            if repeat >= NO_PROGRESS_WARN_AFTER:
                decision = _decision("warn", "idempotent_no_progress_warning", call.name, repeat)
    history: list[Any] = guard["history"]
    history.append([signature, digest, bool(tool and tool.poller)])
    del history[:-HISTORY_LIMIT]
    if not (tool and tool.poller):
        streak = _streak(history)
        if streak >= IDENTICAL_CALL_HALT_AFTER:
            decision = _stronger(
                decision, _decision("halt", "identical_call_halt", call.name, streak)
            )
        elif streak >= IDENTICAL_CALL_NOTICE_AFTER:
            decision = _stronger(
                decision, _decision("warn", "identical_call_warning", call.name, streak)
            )
    cycle = _cycle(history)
    if cycle is not None:
        period, laps = cycle
        if laps >= IDENTICAL_CALL_HALT_AFTER:
            decision = _stronger(
                decision,
                _decision("halt", "identical_cycle_halt", call.name, laps, period=period),
            )
        elif decision.action == "allow":
            decision = _decision("warn", "identical_cycle_warning", call.name, laps, period=period)
    if decision.action == "halt" and guard.get("halt") is None:
        guard["halt"] = decision.metadata() | {"message": decision.message}
    return decision


def halt_reason(state: dict[str, Any]) -> dict[str, Any] | None:
    saved = state.get(STATE_KEY)
    if not isinstance(saved, dict):
        return None
    halt = cast(dict[str, Any], saved).get("halt")
    return cast(dict[str, Any], halt) if isinstance(halt, dict) else None


def _streak(history: list[Any]) -> int:
    if not history:
        return 0
    last = history[-1][:2]
    count = 0
    for entry in reversed(history):
        if entry[:2] != last:
            break
        count += 1
    return count


def _cycle(history: list[Any]) -> tuple[int, int] | None:
    """Smallest period 2..4 whose trailing identical laps reach the notice threshold.

    A cycle made only of poller calls is legitimate waiting and stays exempt.
    """
    for period in range(2, MAXIMUM_CYCLE_PERIOD + 1):
        if len(history) < period * IDENTICAL_CALL_NOTICE_AFTER:
            continue
        tail = history[-period:]
        if len({tuple(entry[:2]) for entry in tail}) < 2:
            continue
        laps = 1
        while True:
            base = len(history) - period * (laps + 1)
            if base < 0:
                break
            if any(
                history[base + index][:2] != history[len(history) - period + index][:2]
                for index in range(period)
            ):
                break
            laps += 1
        if laps >= IDENTICAL_CALL_NOTICE_AFTER:
            if all(entry[2] for entry in tail):
                continue
            return period, laps
    return None
