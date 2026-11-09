"""The outcomes that end one pass of the loop: a final reply, a wait or a limit report.

A wait is checkpointed before the pass returns, so the next pass re-enters the
same wait instead of calling the model again: a question for the owner, owner
attention for unfinished Task work, a trade approval or an external event. A
final answer first passes the bounded Task stop gates.
"""

from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any, cast

from lonora_adapter_kit.types import ModelMessage, ToolCall
from lonora_core.user_error import LonoraError
from lonora_db.tasks import OWNER_ATTENTION
from lonora_tools.context import ToolContext

from .environment import environment_state
from .progress import progress
from .runtime_notices import (
    append_notice,
    attention_message,
    attention_notice,
    is_owner_message,
    prefers_arabic,
)
from .stop_gates import task_progress, task_stop_gate
from .tool_intent import close_unexecuted


@dataclass
class LoopOutcome:
    text: str
    metadata: dict[str, Any]
    waiting: bool = False
    external_wait: bool = False
    input_request: dict[str, Any] | None = None


def rich_metadata(state: dict[str, Any]) -> dict[str, Any]:
    value = state.get("rich_content")
    return {"rich_content": value} if isinstance(value, dict) else {}


def wait_update(messages: list[ModelMessage], call_id: str) -> dict[str, Any]:
    """Only display content attached to this exact accepted wait describes it."""
    message = next(
        (
            message
            for message in reversed(messages)
            if message.role == "assistant"
            and any(call.id == call_id for call in message.tool_calls)
        ),
        None,
    )
    result: dict[str, Any] = {
        "call_id": call_id,
        "text": message.content.strip() if message else "",
    }
    if message and message.rich_content is not None:
        result["rich_content"] = message.rich_content
    return result


def external_wait_outcome(state: dict[str, Any]) -> LoopOutcome:
    environment = environment_state(state)
    identifier = environment["wait"].get("call_id")
    if not isinstance(identifier, str) or not identifier:
        raise LonoraError("task_wait_identity_invalid", 409)
    update = environment.get("wait_update")
    # Legacy checkpoints never published this narration. Keep them silent rather
    # than promoting old private prose through a newer disclosure boundary.
    rich_content: dict[str, Any] | None = None
    if update is None:
        text = ""
    elif not isinstance(update, dict):
        raise LonoraError("task_wait_identity_invalid", 409)
    else:
        saved = cast(dict[str, Any], update)
        if saved.get("call_id") != identifier or not isinstance(saved.get("text"), str):
            raise LonoraError("task_wait_identity_invalid", 409)
        text = cast(str, saved["text"])
        raw_rich = saved.get("rich_content")
        if isinstance(raw_rich, dict):
            rich_content = cast(dict[str, Any], raw_rich)
    return LoopOutcome(
        text,
        {
            **state.get("selection", {}),
            "external_wait_call_id": identifier,
            **({"rich_content": rich_content} if rich_content is not None else {}),
        },
        external_wait=True,
    )


def supersede_wait_siblings(messages: list[ModelMessage], pending: list[ToolCall]) -> None:
    """Close the current tool block without carrying stale actions across a wait.

    Their identities remain durable observations, just as for owner steering.
    After waking, the model must decide again from current external evidence.
    """
    close_unexecuted(messages, pending, "task_wait_requires_fresh_analysis_after_wake")


async def report_wait_superseded(context: ToolContext, superseded: list[ToolCall]) -> None:
    for sibling in superseded:
        await progress(
            context,
            "tool.cancelled",
            {"name": sibling.name, "call_id": sibling.id, "code": "tool_call_superseded"},
        )


def question_outcome(state: dict[str, Any], question: dict[str, Any]) -> LoopOutcome:
    """Wait for the owner's answer to the Run's pending question."""
    if question.get("kind") == OWNER_ATTENTION:
        return attention_outcome(state, question)
    return LoopOutcome(
        str(question["question"]),
        {**state.get("selection", {}), **rich_metadata(state)},
        True,
        input_request=question,
    )


def attention_outcome(state: dict[str, Any], question: dict[str, Any]) -> LoopOutcome:
    reason = str(question.get("reason") or "task_attention")
    return LoopOutcome(
        str(question["question"]),
        {
            **state.get("selection", {}),
            **rich_metadata(state),
            "exit_reason": reason,
            OWNER_ATTENTION: reason,
            "reply_outcome": "needs_owner_attention",
        },
        True,
        input_request=question,
    )


def latest_answer(messages: list[ModelMessage]) -> str:
    """The best held answer: the newest assistant prose since the owner's request."""
    for message in reversed(messages):
        if is_owner_message(message):
            break
        if message.role == "assistant" and message.content.strip():
            return message.content.strip()
    return ""


async def request_owner_attention(
    context: ToolContext,
    state: dict[str, Any],
    messages: list[ModelMessage],
    reason: str,
    text: str,
    save: Callable[[], Awaitable[None]],
) -> LoopOutcome:
    """Hand unfinished Task work to its owner as a resumable question.

    The Run is not failed and the Task is not completed: the checkpoint stays
    intact and the owner's reply continues it. Prose already passed the model
    runtime's financial-truth gate, so no unverified effect becomes success,
    and the runtime's own account of what is unfinished leads the message so a
    held answer claiming completion is never the owner's only report.
    """
    arabic = prefers_arabic(messages)
    completion = await task_progress(context)
    notice = attention_notice(
        reason, arabic, [title for _, title in completion.incomplete] if completion else ()
    )
    # Every escalation gets its own question id. A Task-control resume cancels the
    # previous question without adding a message (its notice joins the last tool
    # result), so the transcript length alone would repeat the cancelled id.
    taken = {
        str(cast(dict[str, Any], item).get("id"))
        for item in cast(list[Any], state.get("input_requests", []))
        if isinstance(item, dict)
    }
    sequence = int(state.get("attention_sequence", 0)) + 1
    while f"attention-{len(messages)}-{sequence}" in taken:
        sequence += 1
    state["attention_sequence"] = sequence
    question: dict[str, Any] = {
        "id": f"attention-{len(messages)}-{sequence}",
        "question": attention_message(notice, text, arabic),
        "choices": [],
        "kind": OWNER_ATTENTION,
        "reason": reason,
    }
    state["pending_input_request"] = question
    state["exit_reason"] = reason
    await save()
    return attention_outcome(state, question)


async def final_answer(
    context: ToolContext,
    state: dict[str, Any],
    messages: list[ModelMessage],
    text: str,
    metadata: dict[str, Any],
    save: Callable[[], Awaitable[None]],
) -> LoopOutcome | None:
    """Apply the bounded task stop gates; ``None`` means the turn continues."""
    verdict = await task_stop_gate(context, state)
    if verdict.continue_turn:
        append_notice(messages, "completion_check", verdict.nudge or "")
        await save()
        return None
    if verdict.exhausted:
        return await request_owner_attention(
            context, state, messages, verdict.exhausted, text or latest_answer(messages), save
        )
    return LoopOutcome(text, metadata)


async def limit_outcome(
    context: ToolContext,
    state: dict[str, Any],
    messages: list[ModelMessage],
    text: str,
    save: Callable[[], Awaitable[None]],
    *,
    reason: str,
    task_run: bool,
) -> LoopOutcome:
    """Deliver the final report written at a limit."""
    if task_run:
        question = state.get("pending_input_request")
        if isinstance(question, dict) and cast(dict[str, Any], question).get("kind") == (
            OWNER_ATTENTION
        ):
            return attention_outcome(state, cast(dict[str, Any], question))
        completion = await task_progress(context)
        if completion is None or not completion.contract_satisfied():
            # Never mark unfinished Task work completed; the owner decides next.
            return await request_owner_attention(context, state, messages, reason, text, save)
    # A Task here has every declared step recorded complete with evidence, so
    # the report completes it; complete_run still enforces that contract.
    return LoopOutcome(
        text,
        {
            **state.get("selection", {}),
            **rich_metadata(state),
            "exit_reason": reason,
            "reply_outcome": "answered" if task_run else "limited",
        },
    )
