"""The end-of-turn check of a conversation the owner started.

A Task has steps to finish; a conversation has none, so a reply could end a request with
one named step left untaken. This gate reads the request's own tool calls and results and
continues the turn, at most twice per owner message, in five cases:

- ``choice_not_carried_out``: the owner picked a choice of a question, the choice was
  bound to calls when it was offered (``offers``), and fewer calls of those tools have
  succeeded since. It is raised once; a reply that still leaves it undone gets one fixed
  line saying so;
- ``read_step_not_taken``: the last call did not find what it named, its result names one
  tool to read next, and that tool was never called;
- ``found_tool_unused``: ``tool_environment`` returned exactly one tool and it was never
  called;
- ``changes_all_failed``: every change failed and a result names how to repeat it;
- ``lead_action_unreported``: a lead action (``owner_line: required`` in its result)
  changed the team and the reply is empty: Lonora tells the owner in one line (3.1.2).

It reads structure only: call names, arguments and result fields. It never reads what the
owner or the model wrote, never issues a call, and never continues past a refusal for
permission, a financial call, an uncertain outcome or an exhausted retry. Each
continuation is recorded in the Run's state.
"""

import json
from collections.abc import Collection
from typing import Any, cast

from lonora_adapter_kit.types import ModelMessage, ToolCall
from lonora_core.user_error import LonoraError
from lonora_db.runs import OFFER_OBLIGATION
from lonora_tools.registry import BRIDGE_TOOLS, INSPECTOR, ToolRegistry

from .context.run_evidence import SKIPPED_TOOLS
from .offers import PICKED, bound_tools, open_obligation, outstanding
from .runtime_notices import is_owner_message, notice_kind
from .stop_gates import CONVERSATION_KEY, MAXIMUM_STOP_NUDGES, StopGateVerdict
from .uncertain_outcome import FINANCIAL_EFFECTS, uncertain_operations

WAKE_OPEN = "<runtime_wake>"
# A refusal for these is a rule, a decision of the owner's or an unknown outcome: the
# reply stands, whatever else the request holds.
HELD_CATEGORIES = frozenset(
    {
        "permission_denied",
        "authorization_required",
        "risk_limit_blocked",
        "health_blocked",
        "ambiguous_mutation",
    }
)
HELD_CODES = frozenset({"guardrail_blocked", "tool_route_exhausted", "broker_result_ambiguous"})
MAXIMUM_NAMED = 6
LEAD = (
    "Automated runtime check. This is not a message from the owner, and the owner has not "
    "been told anything. "
)
REPLACES = " Your next answer replaces the one you just wrote."

Exchange = tuple[ToolCall, dict[str, Any] | None]
Finding = tuple[str, str, str, str]
ACCEPT = StopGateVerdict(continue_turn=False)


def _record(state: dict[str, Any]) -> dict[str, Any]:
    raw = state.get(CONVERSATION_KEY)
    if raw is None:
        return {"version": 1, "attempts": 0, "fired": [], "exhausted": False}
    record = cast(dict[str, Any], raw) if isinstance(raw, dict) else {}
    attempts = record.get("attempts")
    if (
        record.get("version") != 1
        or type(attempts) is not int
        or not 0 <= attempts <= MAXIMUM_STOP_NUDGES
        or not isinstance(record.get("fired"), list)
        or type(record.get("exhausted")) is not bool
    ):
        raise LonoraError("conversation_gate_state_invalid", 409)
    return record


def _request(messages: list[ModelMessage]) -> list[ModelMessage] | None:
    """What followed the owner's last message; ``None`` when that is a wake, not a request."""
    last = next(
        (i for i in range(len(messages) - 1, -1, -1) if is_owner_message(messages[i])), None
    )
    if last is None or messages[last].content.startswith(WAKE_OPEN):
        return None
    return messages[last + 1 :]


def _since_pick(messages: list[ModelMessage]) -> list[Exchange] | None:
    """Every call made after the owner's pick, with its result; ``None`` without a pick.

    Read from the pick's own notice, not from the last owner-side message: another
    agent's outcome merged after the calls must not hide them, or a change that was made
    would be asked for again.
    """
    last = next(
        (i for i in range(len(messages) - 1, -1, -1) if notice_kind(messages[i]) == PICKED), None
    )
    if last is None:
        return None
    return [exchange for block in _blocks(messages[last + 1 :]) for exchange in block]


def _blocks(request: list[ModelMessage]) -> list[list[Exchange]]:
    """Each assistant message's calls with their results, in order."""
    results: dict[str, dict[str, Any]] = {}
    for message in request:
        if message.role != "tool" or not message.tool_call_id:
            continue
        try:
            parsed: Any = json.loads(message.content)
        except ValueError:
            continue
        if isinstance(parsed, dict):
            results[message.tool_call_id] = cast(dict[str, Any], parsed)
    return [
        [(call, results.get(call.id)) for call in message.tool_calls]
        for message in request
        if message.role == "assistant" and message.tool_calls
    ]


def _recovery(result: dict[str, Any]) -> dict[str, Any]:
    recovery = result.get("recovery")
    return cast(dict[str, Any], recovery) if isinstance(recovery, dict) else {}


def _steps(result: dict[str, Any]) -> list[dict[str, Any]]:
    steps = result.get("next_actions")
    return (
        [cast(dict[str, Any], step) for step in cast(list[Any], steps) if isinstance(step, dict)]
        if isinstance(steps, list)
        else []
    )


def _held(
    state: dict[str, Any],
    messages: list[ModelMessage],
    exchanges: list[Exchange],
    registry: ToolRegistry,
) -> bool:
    for call, result in exchanges:
        tool = registry.tools.get(call.name)
        if call.name in FINANCIAL_EFFECTS or (tool is not None and tool.financial):
            return True
        if result is None:
            continue
        recovery = _recovery(result)
        if (
            result.get("class") == "permission"
            or recovery.get("category") in HELD_CATEGORIES
            or recovery.get("retry_exhausted") is True
            or result.get("code") in HELD_CODES
        ):
            return True
    return bool(uncertain_operations(state, messages))


def _choice_not_carried_out(
    obligation: dict[str, Any] | None, exchanges: list[Exchange]
) -> Finding | None:
    if obligation is None:
        return None
    missing = outstanding(obligation, exchanges)
    if not missing:
        return None
    bound = bound_tools(obligation)
    done = sum(bound.values()) - sum(missing.values())
    listed = ", ".join(
        name if count == 1 else f"{name} ({count} calls)" for name, count in missing.items()
    )
    return (
        "choice_not_carried_out",
        next(iter(missing)),
        str(obligation.get("question_id")),
        f"The owner picked choice {obligation.get('choice_id')} of your question, and you "
        f"bound that choice to {sum(bound.values())} call(s). Since the pick, {done} of them "
        f"succeeded; still to make: {listed}. Make them now, as you bound them. If they no "
        "longer apply, your reply must say plainly that what the owner chose was not "
        "carried out, and why; do not describe it as done.",
    )


def _reads(registry: ToolRegistry, name: Any, permitted: Collection[str]) -> bool:
    tool = registry.tools.get(name) if isinstance(name, str) else None
    return tool is not None and tool.read_only and not tool.financial and name in permitted


def _read_step_not_taken(
    blocks: list[list[Exchange]],
    called: set[str],
    registry: ToolRegistry,
    permitted: Collection[str],
) -> Finding | None:
    for call, result in blocks[-1]:
        if (
            result is None
            or result.get("ok") is not False
            or result.get("class") != "resolution"
            # A result that already lists what exists was answered from: nothing to read.
            or result.get("candidates")
            or result.get("existing")
        ):
            continue
        steps = _steps(result)
        step = steps[0].get("tool") if len(steps) == 1 else None
        if not _reads(registry, step, permitted) or step in called:
            continue
        return (
            "read_step_not_taken",
            call.name,
            call.id,
            f"Your call to {call.name} did not find what it named, and its result gives one "
            f"next step: call {step}. That step was not taken. Take it now and answer from "
            "what it returns. If you decide not to, say plainly in your reply what was not "
            "done and why.",
        )
    return None


def _found_tool_unused(
    exchanges: list[Exchange], called: set[str], registry: ToolRegistry
) -> Finding | None:
    if any(
        result is not None and result.get("ok") is not False
        for call, result in exchanges
        if (tool := registry.tools.get(call.name)) is not None
        and not tool.read_only
        and call.name not in SKIPPED_TOOLS
    ):
        # A change went through: the request was acted on another way.
        return None
    for call, result in exchanges:
        if call.name != INSPECTOR or result is None or result.get("ok") is False:
            continue
        listed = cast(list[Any], result["tools"]) if isinstance(result.get("tools"), list) else []
        # One row of a longer listing is a page, not the one tool a lookup found.
        only = listed[0] if len(listed) == 1 and result.get("total") == 1 else None
        entry: Any = result.get("tool") or only
        if not isinstance(entry, dict):
            continue
        name = cast(dict[str, Any], entry).get("name")
        tool = registry.tools.get(name) if isinstance(name, str) else None
        if (
            tool is None
            or cast(dict[str, Any], entry).get("available") is False
            or tool.financial
            or tool.name in FINANCIAL_EFFECTS
            or tool.name in BRIDGE_TOOLS
            or tool.name in called
        ):
            continue
        lead = f"tool_environment returned exactly one tool, {tool.name}, and it has not been called for this request. "
        if tool.read_only:
            body = (
                "If it gives what the request needs, call it now, directly if it is in your "
                "tool list and otherwise through tool_call, and answer from its result. If it "
                "does not fit, say so plainly."
            )
        else:
            # A change is the owner's to ask for: a question about it is answered, not acted on.
            body = (
                f"If the owner asked for what {tool.name} does, call it. If the owner only "
                "asked about it, your answer stands."
            )
        return (
            "found_tool_unused",
            tool.name,
            call.id,
            lead + body + " Do not say an ability is missing when a listed tool provides it.",
        )
    return None


def _changes_all_failed(
    exchanges: list[Exchange], registry: ToolRegistry, permitted: Collection[str]
) -> Finding | None:
    changes = [
        (call, result)
        for call, result in exchanges
        if (tool := registry.tools.get(call.name)) is not None
        and not tool.read_only
        and call.name not in SKIPPED_TOOLS
    ]
    if not changes or any(result is None or result.get("ok") is not False for _, result in changes):
        return None
    for call, result in changes:
        # Only a step that repeats the same change or reads: never another change.
        if any(
            isinstance(step.get("repeat_with"), dict)
            or _reads(registry, step.get("tool"), permitted)
            for step in _steps(cast(dict[str, Any], result))
        ):
            names = list(dict.fromkeys(change.name for change, _ in changes))[:MAXIMUM_NAMED]
            return (
                "changes_all_failed",
                call.name,
                call.id,
                f"Every change you tried for this request failed ({', '.join(names)}), so "
                f"nothing was changed. The result of {call.name} names a next step: take it. "
                "Otherwise your reply must say that the change was not made; do not describe "
                "it as done.",
            )
    return None


# A lead tool's result field that names the owner's one-line report as an open step
# (mandate 3.1.2: Lonora "tells the owner in one line what it did and why").
OWNER_LINE = "owner_line"


def _lead_action_unreported(
    exchanges: list[Exchange], request: list[ModelMessage] | None
) -> Finding | None:
    """A lead action changed something, and the reply that ends the turn is empty."""
    if not request or request[-1].role != "assistant" or request[-1].content.strip():
        return None
    for call, result in exchanges:
        if result is not None and result.get(OWNER_LINE) == "required":
            return (
                "lead_action_unreported",
                call.name,
                call.id,
                f"{call.name} changed the team, and your reply is empty. Tell the owner in "
                "one line what you did and why.",
            )
    return None


def conversation_stop_gate(
    state: dict[str, Any],
    messages: list[ModelMessage],
    registry: ToolRegistry,
    permitted: Collection[str],
) -> StopGateVerdict:
    """Whether the reply ends this request; ``permitted`` names the tools of this Run."""
    if state.get("owner_started") is not True:
        return _wake_gate(state, messages)
    record = _record(state)
    request = _request(messages)
    blocks = _blocks(request) if request else []
    # A picked choice is checked even when the reply made no call at all.
    picked = _since_pick(messages) if request is not None else None
    obligation = open_obligation(state) if picked is not None else None
    if not blocks and obligation is None:
        return ACCEPT
    exchanges = [exchange for block in blocks for exchange in block]
    # The pick starts at or before the request, so its calls include the request's.
    if _held(state, messages, picked if obligation and picked else exchanges, registry):
        return ACCEPT
    called = {call.name for call, _ in exchanges}
    fired = {
        (cast(dict[str, Any], entry).get("condition"), cast(dict[str, Any], entry).get("call_id"))
        for entry in cast(list[Any], record["fired"])
        if isinstance(entry, dict)
    }
    finding = next(
        (
            found
            for found in (
                _choice_not_carried_out(obligation, picked or []),
                _read_step_not_taken(blocks, called, registry, permitted) if blocks else None,
                _found_tool_unused(exchanges, called, registry),
                _changes_all_failed(exchanges, registry, permitted),
                _lead_action_unreported(exchanges, request),
            )
            # One fact is raised once: a reply that keeps its answer after it stands.
            if found is not None and (found[0], found[2]) not in fired
        ),
        None,
    )
    return _nudge(state, record, finding)


def _wake_gate(state: dict[str, Any], messages: list[ModelMessage]) -> StopGateVerdict:
    """A run the owner did not start (a wake): only a lead action left unreported holds
    it, read from the calls since the last conversation input or finished reply (an
    earlier turn's action was reported, or not, in that turn)."""
    last = next(
        (
            i
            for i in range(len(messages) - 2, -1, -1)
            if is_owner_message(messages[i])
            or (
                messages[i].role == "assistant"
                and not messages[i].tool_calls
                and bool(messages[i].content.strip())
            )
        ),
        -1,
    )
    tail = messages[last + 1 :]
    exchanges = [exchange for block in _blocks(tail) for exchange in block]
    finding = _lead_action_unreported(exchanges, tail)
    if finding is None:
        return ACCEPT
    record = _record(state)
    fired = {
        (cast(dict[str, Any], entry).get("condition"), cast(dict[str, Any], entry).get("call_id"))
        for entry in cast(list[Any], record["fired"])
        if isinstance(entry, dict)
    }
    return ACCEPT if (finding[0], finding[2]) in fired else _nudge(state, record, finding)


def _nudge(
    state: dict[str, Any], record: dict[str, Any], finding: Finding | None
) -> StopGateVerdict:
    if finding is None:
        return ACCEPT
    if record["attempts"] >= MAXIMUM_STOP_NUDGES:
        state[CONVERSATION_KEY] = {**record, "exhausted": True}
        return ACCEPT
    condition, tool, call_id, text = finding
    state[CONVERSATION_KEY] = {
        **record,
        "attempts": record["attempts"] + 1,
        "fired": [*record["fired"], {"condition": condition, "tool": tool, "call_id": call_id}],
    }
    return StopGateVerdict(continue_turn=True, nudge=LEAD + text + REPLACES)


def choice_left_undone(
    state: dict[str, Any], messages: list[ModelMessage], registry: ToolRegistry
) -> bool:
    """At a reply that ends the turn: record how the picked choice ended and say whether
    it was left undone with nothing holding it, so the reply gets the fixed line.

    The obligation stays open: a reply drafted again (another agent's outcome arrived, or
    a restart) is judged afresh from the same transcript.
    """
    obligation = open_obligation(state)
    picked = _since_pick(messages)
    if (
        obligation is None
        or picked is None
        or _request(messages) is None
        or state.get("owner_started") is not True
    ):
        return False
    missing = outstanding(obligation, picked)
    # A rule, a decision of the owner's or an unknown outcome stopped it: the reply stands.
    held = bool(missing) and _held(state, messages, picked, registry)
    state[OFFER_OBLIGATION] = {
        **obligation,
        "outcome": "held" if held else "unmet" if missing else "met",
    }
    return bool(missing) and not held
