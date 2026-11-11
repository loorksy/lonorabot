"""One appended line when an owner-started request leaves a financial outcome uncertain.

Structured results only: no wording of the owner or the model is read. At the end of a
Run the owner started by typing, every financial effect call of the request is checked
(``trade_execute``, ``trade_close_positions``, ``goal_step_execute``, including a goal
step's nested and deduplicated result and the reconciliation of the same operation).
If an operation's latest result is still uncertain, one line in the conversation
language says the outcome is not confirmed, is being checked and will not be resent.
The reply and its card are never replaced.
"""

import json
from typing import Any, cast

from lonora_adapter_kit.types import ModelMessage

from .runtime_notices import is_owner_message, prefers_arabic

_STARTED_KEY = "owner_started"
_START_KEY = "owner_request_start"
# Runs the owner started by typing. Steering inside a wake run does not make it one.
OWNER_TRIGGERS = frozenset({"user", "group"})
FINANCIAL_EFFECTS = frozenset({"trade_execute", "trade_close_positions", "goal_step_execute"})
UNCERTAIN = frozenset(
    {
        "ambiguous",
        "operation_ambiguous",
        "tool_execution_uncertain",
        "submitted",
        "reserved",
        "broker_result_ambiguous",
    }
)
# RichContent holds at most this many parts.
MAXIMUM_PARTS = 24
LINE_AR = "نتيجة العملية غير مؤكدة بعد؛ أتحقق منها ولن أعيد إرسالها."
LINE_EN = "The outcome is not confirmed yet; I am checking it and will not resend it."


def record_request_start(state: dict[str, Any], trigger: str, messages: list[ModelMessage]) -> None:
    """On a Run's first entry: whether the owner started it and where its request begins."""
    if _STARTED_KEY in state:
        return
    last = next(
        (i for i in range(len(messages) - 1, -1, -1) if is_owner_message(messages[i])), None
    )
    state[_STARTED_KEY] = trigger in OWNER_TRIGGERS and last is not None
    state[_START_KEY] = last if last is not None else len(messages)


def _rows(result: dict[str, Any]) -> list[dict[str, Any]]:
    """The operation rows of one result: itself, a goal step's nested result, a batch."""
    rows = [result]
    nested = result.get("result")
    if isinstance(nested, dict):
        rows.append(cast(dict[str, Any], nested))
    listed = result.get("results")
    if isinstance(listed, list):
        rows += [
            cast(dict[str, Any], row) for row in cast(list[Any], listed) if isinstance(row, dict)
        ]
    return rows


def _states(call_id: str, arguments: dict[str, Any], result: dict[str, Any]) -> dict[str, bool]:
    """``{operation key: uncertain}`` for each operation this result reports."""
    fallback = str(result.get("operation_id") or arguments.get("operation_id") or call_id)
    found: dict[str, bool] = {}
    for row in _rows(result):
        status, code = row.get("status"), row.get("code")
        if status is None and code is None:
            continue
        key = str(row.get("operation_id") or fallback)
        found[key] = found.get(key, False) or status in UNCERTAIN or code in UNCERTAIN
    return found


def uncertain_operations(state: dict[str, Any], messages: list[ModelMessage]) -> set[str]:
    """Operations of this request whose latest result is still uncertain."""
    if state.get(_STARTED_KEY) is not True:
        return set()
    start = state.get(_START_KEY)
    if type(start) is not int or not 0 <= start <= len(messages):
        return set()
    calls = {
        call.id: call
        for message in messages
        for call in message.tool_calls
        if call.name in FINANCIAL_EFFECTS
    }
    reported: dict[str, set[str]] = {}
    latest: dict[str, bool] = {}
    for message in messages[start:]:
        call = calls.get(message.tool_call_id or "") if message.role == "tool" else None
        if call is None:
            continue
        try:
            raw: Any = json.loads(message.content)
        except ValueError:
            continue
        if not isinstance(raw, dict):
            continue
        result = cast(dict[str, Any], raw)
        states = _states(call.id, call.arguments, result)
        origin = result.get("_runtime_reconciled")
        if isinstance(origin, str) and states:
            # A reconciliation of the same operation settles what the original reported.
            for key in reported.get(origin, set()):
                states.setdefault(key, any(states.values()))
        latest.update(states)
        reported.setdefault(call.id, set()).update(states)
    return {key for key, uncertain in latest.items() if uncertain}


def uncertain_line(state: dict[str, Any], messages: list[ModelMessage]) -> str | None:
    if not uncertain_operations(state, messages):
        return None
    return LINE_AR if prefers_arabic(messages) else LINE_EN


def appended_parts(parts: list[Any], line: str) -> list[Any]:
    """The card's parts with the line: a new text part, or the last text part at the cap."""
    if len(parts) < MAXIMUM_PARTS:
        return [*parts, {"type": "text", "text": line}]
    for index in range(len(parts) - 1, -1, -1):
        part = parts[index]
        if isinstance(part, dict) and cast(dict[str, Any], part).get("type") == "text":
            updated = dict(cast(dict[str, Any], part))
            updated["text"] = str(updated.get("text", "")).rstrip() + "\n\n" + line
            return [*parts[:index], updated, *parts[index + 1 :]]
    return parts


def append_uncertain_line(state: dict[str, Any], messages: list[ModelMessage], text: str) -> str:
    """The reply with the line appended once (text, stored message and card text)."""
    line = uncertain_line(state, messages)
    if line is None or line in text:
        return text
    text = (text.rstrip() + "\n\n" + line) if text.strip() else line
    rich = state.get("rich_content")
    if isinstance(rich, dict):
        parts = cast(dict[str, Any], rich).get("parts")
        if isinstance(parts, list):
            state["rich_content"] = {
                **cast(dict[str, Any], rich),
                "parts": appended_parts(cast(list[Any], parts), line),
            }
    if messages and messages[-1].role == "assistant":
        messages[-1] = messages[-1].model_copy(
            update={"content": text, "rich_content": state.get("rich_content")}
        )
    return text
