"""Runtime notices placed where the model reads them, never as mid-run system text.

Provider adapters hoist every system message into one prefix, so a nudge
appended as ``role=system`` would move above the conversation, lose recency and
change the cached prefix on every round. A notice is attached to the latest
tool result when the transcript ends with one, otherwise it is a trailing
``user`` message marked ``tool_observation``: it stays bound to its producing
exchange during context governance and is never mistaken for an owner request.
"""

import json
import re
from typing import Any, cast

from lonora_adapter_kit.types import ModelMessage

NOTICE_OPEN = "<runtime_notice>"
NOTICE_CLOSE = "</runtime_notice>"
NOTICE_FIELD = "runtime_notice"


def _payload(kind: str, text: str) -> dict[str, str]:
    return {"kind": kind, "source": "lonora_runtime", "message": text}


def notice_message(kind: str, text: str) -> ModelMessage:
    body = json.dumps(_payload(kind, text), ensure_ascii=False).replace("<", "\\u003c")
    return ModelMessage(
        role="user", context_origin="tool_observation", content=NOTICE_OPEN + body + NOTICE_CLOSE
    )


def is_runtime_notice(message: ModelMessage) -> bool:
    return (
        message.role == "user"
        and message.context_origin == "tool_observation"
        and message.content.startswith(NOTICE_OPEN)
    )


def is_owner_message(message: ModelMessage) -> bool:
    """User-role conversation input, excluding runtime notices and observations."""
    return message.role == "user" and message.context_origin == "conversation"


def attach_notice(result: dict[str, Any], kind: str, text: str) -> None:
    """Add guidance to a tool result before it is serialized for the model."""
    existing = result.get(NOTICE_FIELD)
    notices: list[dict[str, Any]] = (
        [cast(dict[str, Any], item) for item in cast(list[Any], existing) if isinstance(item, dict)]
        if isinstance(existing, list)
        else []
    )
    notices.append(_payload(kind, text))
    result[NOTICE_FIELD] = notices


def append_notice(messages: list[ModelMessage], kind: str, text: str) -> None:
    """Deliver at the tail: inside the latest tool result, else a trailing notice."""
    if messages and messages[-1].role == "tool":
        try:
            decoded: Any = json.loads(messages[-1].content)
        except ValueError:
            decoded = None
        if isinstance(decoded, dict):
            result = cast(dict[str, Any], decoded)
            attach_notice(result, kind, text)
            messages[-1] = messages[-1].model_copy(
                update={"content": json.dumps(result, ensure_ascii=False)}
            )
            return
    messages.append(notice_message(kind, text))


def prefers_arabic(messages: list[ModelMessage]) -> bool:
    """Same owner-language heuristic as the financial truth gate."""
    for owner in reversed(messages):
        if not is_owner_message(owner):
            continue
        if re.search(r"[ؠ-ي]", owner.content):
            return True
        if " " in owner.content and len(re.findall(r"[A-Za-z]", owner.content)) >= 8:
            return False
    return True


NO_ANSWER = (
    "No answer was provided for the selected request. Provide the substantive result or ask "
    "a necessary clarification with wait_for_input. Do not invent results."
)


def budget_warning(remaining: int) -> str:
    rounds = "1 model round" if remaining == 1 else f"{remaining} model rounds"
    return (
        f"{rounds} with tools remain in this run. Prioritize the steps that matter most; "
        "after that no further tool calls will execute and you will be asked for a final report."
    )


def finish_instruction(reason: str, detail: str = "") -> str:
    cause = {
        "tool_round_limit": "This run reached its tool-round limit.",
        "guardrail_halt": "This run stopped a repeating tool loop"
        + (": " + detail if detail else "")
        + ".",
    }.get(reason, "This run must stop now.")
    return (
        cause + " No tool call will execute any more. Write the final reply to the owner now, "
        "in the owner's language: report only results verified by tool observations in this run; "
        "name every operation whose outcome is unresolved or unverified without calling it "
        "successful; and give the concrete next steps. Do not invent progress."
    )


def limit_fallback(arabic: bool) -> str:
    return (
        "توقفت قبل إنهاء العمل لأن هذه الجولة بلغت حدّها، ولم يُنفَّذ أي إجراء بعد ذلك. "
        "اطلب مني المتابعة عندما تريد الاستئناف."
        if arabic
        else "I stopped before finishing because this run reached its limit, and nothing further "
        "was executed after that point. Ask me to continue when you want me to resume."
    )


def attention_fallback(arabic: bool) -> str:
    return (
        "لم أتمكن من إنهاء هذه المهمة بمفردي، وأحتاج توجيهك قبل المتابعة."
        if arabic
        else "I could not finish this task on my own and need your direction before continuing."
    )
