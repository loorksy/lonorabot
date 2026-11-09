"""Resume a Run where its checkpoint left it, before the loop's first round.

Checkpoints written by earlier releases resume unchanged: one without
``instruction_skill_ids`` checks every retained skill version, one without
``environment`` gives its pending calls no new replay permission, a wait saved
halfway through a tool block closes the unexecuted siblings, and a wake
committed by an older worker closes the proposals made before the wait.
"""

import json
from collections.abc import Awaitable, Callable
from typing import Any, cast

from lonora_adapter_kit.types import ModelMessage, ToolCall
from lonora_db.schema import RunRow
from lonora_db.tasks import ATTENTION_RESUMED
from lonora_tools.base import ToolScope
from lonora_tools.context import ToolContext
from lonora_tools.registry import ToolRegistry

from .context.builder import build_context
from .context.skills import selected_skill_ids
from .context_engine import DELEGATED_KEY, DELEGATED_TRIGGERS
from .continuation import slice_limit
from .environment import environment_state
from .loop_outcomes import LoopOutcome, external_wait_outcome, supersede_wait_siblings
from .model_recovery import reset_streak
from .recovery import restore_execution
from .runtime_notices import append_notice, resumed_notice
from .skills.snapshot import read_snapshot
from .stop_gates import reset_stop_gate
from .tool_block import report_closed
from .tool_exposure import ensure_exposure
from .tool_guardrails import reset_guardrails
from .tool_intent import start_budget_epoch


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
    # Chosen once per Run and frozen in the checkpoint: the native tools array
    # is identical on every model turn, so discovery never invalidates the
    # reusable prompt prefix. Exposure is presentation, never authority.
    exposure = await ensure_exposure(
        context, registry, state, messages, pending, scope=scope, task_run=task_run
    )
    return messages, pending, exposure


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


async def reenter_external_wait(
    context: ToolContext,
    state: dict[str, Any],
    messages: list[ModelMessage],
    pending: list[ToolCall],
    save: Callable[[], Awaitable[None]],
) -> LoopOutcome:
    if pending:
        # Older checkpoints could suspend halfway through a tool block.
        # Repair their unexecuted siblings before any future wake can run
        # stale financial intent or insert a user message into that block.
        superseded = list(pending)
        supersede_wait_siblings(messages, pending)
        await save()
        await report_closed(context, superseded, [], "tool_call_superseded")
    return external_wait_outcome(state)


def consume_wake(
    state: dict[str, Any], messages: list[ModelMessage], pending: list[ToolCall]
) -> list[ToolCall]:
    """Deliver a new external wake once; return the proposals it superseded."""
    environment = environment_state(state)
    wake = environment.get("last_wake")
    if not wake or environment.get("consumed_wake") == wake:
        return []
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
