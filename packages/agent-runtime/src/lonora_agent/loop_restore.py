"""Restore a Run's checkpoint before the loop's first round, including checkpoints written
by earlier releases, and apply the owner resume or external wake it carries.

A checkpoint keeps the context it was built with. A continuous Task can sleep across
releases, edits of the agent's instructions and memory, and account changes, so every
wake rebuilds the context head (system blocks and labelled context data) from the
current server state and keeps the Run's own transcript after it."""

import json
import logging
from typing import Any, cast

from lonora_adapter_kit.context_sections import is_context_message
from lonora_adapter_kit.types import ModelMessage, ToolCall
from lonora_core.user_error import LonoraError
from lonora_db.schema import RunRow
from lonora_db.tasks import ATTENTION_RESUMED
from lonora_tools.base import ToolScope
from lonora_tools.context import ToolContext
from lonora_tools.registry import ToolRegistry

from .context.builder import build_context
from .context.skills import refresh_skill_context, selected_skill_ids
from .context_engine import DELEGATED_KEY, DELEGATED_TRIGGERS
from .continuation import slice_limit
from .environment import environment_state
from .model_recovery import reset_streak
from .recovery import restore_execution
from .runtime_notices import append_notice, resumed_notice
from .skills.snapshot import read_snapshot
from .stop_gates import reset_stop_gate
from .tool_block import supersede_wait_siblings
from .tool_exposure import ensure_exposure
from .tool_guardrails import reset_guardrails
from .tool_intent import start_budget_epoch
from .uncertain_outcome import record_request_start

log = logging.getLogger(__name__)


async def restore_checkpoint(
    context: ToolContext,
    registry: ToolRegistry,
    run: RunRow,
    state: dict[str, Any],
    *,
    scope: ToolScope,
    task_run: bool,
) -> tuple[list[ModelMessage], list[ToolCall], dict[str, Any]]:
    """Return the transcript, the pending calls and the Run's frozen tool exposure."""
    # Compaction must not label another Agent's request as the owner's.
    state[DELEGATED_KEY] = run.trigger in DELEGATED_TRIGGERS
    messages, pending = restore_execution(state)
    if messages and "instruction_skill_ids" not in state:
        # Legacy checkpoints have no binding between saved instructions and the
        # latest metadata selection. Conservatively check all retained versions.
        state["instruction_skill_ids"] = list(
            read_snapshot(run.model_metadata.get("skill_snapshot"))
        ) or await selected_skill_ids(context)
    if "environment" not in state and pending:
        # Older checkpoints did not distinguish proposed from in-flight calls.
        # Unknown legacy mutations must not acquire a new replay permission.
        environment_state(state)["legacy_pending"] = [call.id for call in pending]
    if not messages:
        messages = await build_context(context, registry)
        state["instruction_skill_ids"] = await selected_skill_ids(context)
    # Whether the owner started this Run, for the uncertain-outcome line.
    record_request_start(state, run.trigger, messages)
    # Chosen once per Run and frozen in the checkpoint: the native tools array
    # is identical on every model turn, so discovery never invalidates the
    # reusable prompt prefix. Exposure is presentation, never authority.
    exposure = await ensure_exposure(
        context, registry, state, messages, pending, scope=scope, task_run=task_run
    )
    return messages, pending, exposure


async def refresh_context_head(
    context: ToolContext,
    registry: ToolRegistry,
    state: dict[str, Any],
    messages: list[ModelMessage],
) -> None:
    """Replace the checkpoint's context head with one built now; keep the transcript.

    The head is every system message (only ``build_context`` writes them into a
    checkpoint) and the labelled context data that leads the transcript. Compaction
    records index the transcript without either, so they stay valid. Skills the Run
    viewed stay in its procedures and its authority checks, as after owner steering.

    A head that cannot be built now (a resource, the skill catalog or the window
    changed) leaves the frozen one in place: the wake is delivered, never failed for
    it. A lost lease still ends the pass.
    """
    viewed = list(state.get("viewed_skill_ids", []))
    try:
        fresh = await build_context(context, registry)
        body = [message for message in messages if message.role != "system"]
        while body and is_context_message(body[0]):
            body.pop(0)
        data = [message for message in fresh if message.role != "system"]
        rebuilt = (
            [message for message in fresh if message.role == "system"]
            + [message for message in data[:1] if is_context_message(message)]
            + body
        )
        selected = await refresh_skill_context(context, registry, rebuilt, retained_ids=viewed)
        if selected is None:
            selected = await selected_skill_ids(context)
    except LonoraError as error:
        if error.code == "stale_lease":
            raise
        log.warning("context_head_refresh_failed code=%s", error.code)
        return
    messages[:] = rebuilt
    state["instruction_skill_ids"] = sorted(set(selected) | set(viewed))


def resume_after_attention(
    state: dict[str, Any], messages: list[ModelMessage], maximum_rounds: int
) -> bool:
    """Apply a Task control that resumed work held for owner attention, if one did."""
    resumed = state.pop(ATTENTION_RESUMED, None)
    if not isinstance(resumed, dict):
        return False
    # A Task control resumed work held for owner attention: that is owner
    # input, so it starts a new review epoch, and at a limit a new budget.
    reset_stop_gate(state)
    reset_guardrails(state)
    reset_streak(state)
    if state.get("limit_exit") or int(state.get("rounds", 0)) >= slice_limit(state, maximum_rounds):
        start_budget_epoch(state)
    state.pop("exit_reason", None)
    append_notice(
        messages,
        "owner_resumed",
        resumed_notice(str(cast(dict[str, Any], resumed).get("action") or "")),
    )
    return True


def consume_wake(
    state: dict[str, Any], messages: list[ModelMessage], pending: list[ToolCall]
) -> list[ToolCall] | None:
    """Deliver a new external wake once; return the proposals it superseded, or None
    when there was no new wake."""
    environment = environment_state(state)
    wake = environment.get("last_wake")
    if not wake or environment.get("consumed_wake") == wake:
        return None
    # A previous release may have committed the wake before upgrading its
    # worker. Close its pre-wait proposals before adding the new observation.
    superseded = list(pending)
    supersede_wait_siblings(messages, pending)
    reset_stop_gate(state)
    reset_guardrails(state)
    messages.append(
        ModelMessage(
            role="user",
            content="<runtime_wake>"
            + json.dumps(wake, ensure_ascii=False).replace("<", "\\u003c")
            + "</runtime_wake>",
        )
    )
    environment["consumed_wake"] = wake
    return superseded
