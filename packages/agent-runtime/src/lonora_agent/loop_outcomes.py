"""The outcomes that end one pass: a final reply after the Task stop gates, or a checkpointed
wait (a question, owner attention or an external event) that the next pass re-enters."""

from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any, cast

from lonora_adapter_kit.types import ModelMessage
from lonora_core.user_error import LonoraError
from lonora_db.tasks import OWNER_ATTENTION
from lonora_tools.context import ToolContext

from .environment import environment_state
from .runtime_notices import (
    append_notice,
    attention_message,
    attention_notice,
    is_owner_message,
    prefers_arabic,
)
from .stop_gates import StopGateVerdict, task_progress, task_stop_gate
from .uncertain_outcome import append_uncertain_line


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
    *,
    outcome_line: bool = False,
    conversation_gate: Callable[[], StopGateVerdict] | None = None,
) -> LoopOutcome | None:
    """Apply the bounded stop gates; ``None`` means the turn continues.

    With ``outcome_line``, a reply that ends an owner-started request with an uncertain
    financial outcome gets one appended line; its text and card are kept.
    ``conversation_gate`` is the check of a text reply in a conversation: once its two
    continuations are spent the reply stands, since ending a turn is always allowed.
    """
    verdict = await task_stop_gate(context, state)
    if verdict.continue_turn:
        append_notice(messages, "completion_check", verdict.nudge or "")
        await save()
        return None
    if verdict.exhausted:
        return await request_owner_attention(
            context, state, messages, verdict.exhausted, text or latest_answer(messages), save
        )
    if conversation_gate is not None:
        held = conversation_gate()
        if held.continue_turn:
            append_notice(messages, "conversation_check", held.nudge or "")
            await save()
            return None
    if outcome_line:
        updated = append_uncertain_line(state, messages, text)
        if updated != text:
            text, metadata = updated, {**metadata, **rich_metadata(state)}
            await save()
    return LoopOutcome(text, metadata)
