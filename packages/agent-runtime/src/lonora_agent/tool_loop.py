"""The durable agent tool loop: the one loop that drives every Run's model.

Every trigger reaches ``execute_tool_loop`` through ``executor.execute_run``, ``model_turn``
is called only here, and every checkpoint is written by ``persist`` (through ``save``).

The final tool-less report at a limit (``finish_turn``) adapts the
iteration-budget grace call of Hermes Agent
``agent/chat_completion_helpers.py::handle_max_iterations``, source
https://github.com/NousResearch/hermes-agent at revision
a9ff9799e273f525b82718cdc69fdec71b1dca5a. Lonora checkpoints the report before
returning it, so a restart commits the same text instead of calling again.

MIT License

Copyright (c) 2025 Nous Research

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
"""

import json
import logging
from collections.abc import Awaitable, Callable, Collection
from typing import Any, cast

from lonora_adapter_kit.types import ModelMessage, ModelReply, ToolCall, ToolDefinition
from lonora_contracts.model_routing import Capability, ModelSelection
from lonora_contracts.runs import WORK_TRIGGERS
from lonora_core.run_state import is_conversational
from lonora_core.user_error import LonoraError
from lonora_db.runs import checkpoint, require_lease
from lonora_db.schema import RunRow
from lonora_db.tasks import OWNER_ATTENTION, report_task_degraded
from lonora_tools.base import run_scope
from lonora_tools.context import ToolContext
from lonora_tools.registry import ToolRegistry

from .cancellation import cancellation_checkpoint
from .context.skills import assert_skill_authority, refresh_skill_context
from .context_engine import (
    FENCE_CODES,
    compact_context,
    compacted_view,
    request_overhead,
    resolve_limits,
)
from .continuation import MAXIMUM_SLICES, schedule_task_continuation, slice_limit
from .environment import ToolRetryScheduled, environment_state, retry_pending
from .loop_outcomes import (
    LoopOutcome,
    append_line,
    attention_outcome,
    external_wait_outcome,
    final_answer,
    question_outcome,
    request_owner_attention,
    rich_metadata,
)
from .loop_restore import consume_wake, restore_checkpoint, resume_after_attention
from .model_recovery import (
    ATTENTION_REASON,
    CONTINUOUS,
    CONVERSATION,
    RETRY_REASON,
    STATE_KEY,
    WORK,
    BackoffProfile,
    input_scale,
    plan_failure,
    record_success,
)
from .model_runtime import model_turn
from .reply_gates import owner_words, unconfirmed_line
from .runtime_notices import (
    NO_ANSWER,
    append_notice,
    budget_warning,
    finish_instruction,
    is_runtime_notice,
    limit_fallback,
    notice_message,
    prefers_arabic,
)
from .steering import merge_steering, owner_steering_pending
from .stop_gates import task_progress
from .tasks import task_checkpoint
from .tool_block import (
    close_pending,
    report_closed,
    run_and_record_segment,
    supersede_wait_siblings,
)
from .tool_exposure import inventory, native_definitions
from .tool_guardrails import halt_reason
from .tool_intent import start_budget_epoch

log = logging.getLogger("lonora.tool_loop")

# Executable model rounds left before the final limit at which the model is told.
BUDGET_WARNING_ROUNDS = 2


async def persist(
    context: ToolContext,
    state: dict[str, Any],
    messages: list[ModelMessage],
    pending: list[ToolCall],
) -> None:
    state["messages"] = [message.model_dump(mode="json") for message in messages]
    state["pending"] = [call.model_dump(mode="json") for call in pending]
    async with context.db.sessions() as session, session.begin():
        await checkpoint(session, context.lease, state)


async def compact_for_turn(
    context: ToolContext,
    state: dict[str, Any],
    messages: list[ModelMessage],
    pending: list[ToolCall],
    capability: Capability,
    tools: list[ToolDefinition],
    *,
    inventory_text: str = "",
    policy_tools: Collection[str] | None = None,
) -> Callable[[list[ModelMessage]], list[ModelMessage]]:
    """Keep the next request under its model's window; return the request view.

    Compaction is persisted in the checkpoint before the request, so it is not
    recomputed after a restart and canonical messages are never rewritten. It
    never fails the turn: fencing errors propagate, anything else keeps the
    current view and admission degrades the request instead.
    """

    async def save() -> None:
        await persist(context, state, messages, pending)

    try:
        limits = await resolve_limits(
            context, capability, for_agent=True, input_scale=input_scale(state)
        )
        await compact_context(
            context,
            state,
            messages,
            limits,
            extra_tokens=request_overhead(
                messages, tools, limits, inventory=inventory_text, available=policy_tools
            ),
            save=save,
        )
    except LonoraError as error:
        if error.code in FENCE_CODES:
            raise
        log.warning("context_compaction_failed code=%s", error.code)
    except Exception as error:
        log.warning("context_compaction_failed type=%s", type(error).__name__)
    return lambda request: compacted_view(request, state)


def capability_for(messages: list[ModelMessage], capability: Capability) -> Capability:
    return Capability.VISION if any(message.images for message in messages) else capability


def selection_metadata(
    selection: ModelSelection, reply: ModelReply, capability: Capability
) -> dict[str, Any]:
    """The checkpointed facts of the model that answered a turn."""
    return {
        "provider": selection.provider,
        "model": selection.model,
        "capability": reply.provider_metadata.get("runtime_capability", capability.value),
        "stream_timings": reply.provider_metadata.get("stream_timings", {}),
        "visual_errors": reply.provider_metadata.get("visual_errors", []),
        "visual_diagnostics": reply.provider_metadata.get("visual_diagnostics", []),
    }


# Subagents delegate at most two levels deep; a few extra hops guard bad data.
_MAXIMUM_DELEGATION_HOPS = 4


async def recovery_profile(context: ToolContext, task_run: bool) -> BackoffProfile:
    """How long this Run may back off: whoever waits on it decides.

    Continuous Task work keeps monitoring through an outage; finite Task and
    background work outlast ordinary outages; a conversation (and a subagent
    it delegated, which the conversation waits on) fails honestly within
    about a minute.
    """
    if task_run:
        progress = await task_progress(context)
        return CONTINUOUS if progress is not None and progress.continuous else WORK
    async with context.db.sessions() as session:
        run = await require_lease(session, context.lease)
        trigger, parent_id = run.trigger, run.parent_run_id
        for _ in range(_MAXIMUM_DELEGATION_HOPS):
            if trigger != "subagent" or parent_id is None:
                break
            parent = await session.get(RunRow, parent_id)
            if parent is None:
                break
            if parent.model_metadata.get("task_id"):
                return WORK
            trigger, parent_id = parent.trigger, parent.parent_run_id
    return WORK if trigger in WORK_TRIGGERS else CONVERSATION


def effect_names(registry: ToolRegistry) -> frozenset[str]:
    """Tools whose successful result can support a reply saying something was done."""
    return frozenset(name for name, tool in registry.tools.items() if not tool.read_only)


async def finish_turn(
    context: ToolContext,
    registry: ToolRegistry,
    state: dict[str, Any],
    messages: list[ModelMessage],
    pending: list[ToolCall],
    capability: Capability,
    save: Callable[[], Awaitable[None]],
    *,
    reason: str,
    task_run: bool,
) -> LoopOutcome:
    """One final tool-less model call instead of failing the Run at a limit.

    Adapted from Hermes Agent's iteration-budget grace call (see the module
    notice). The reply is checkpointed before it is returned, so a restart
    commits the same text instead of making another model call.
    """
    saved = state.get("limit_exit")
    if isinstance(saved, dict) and isinstance(cast(dict[str, Any], saved).get("text"), str):
        text = cast(str, cast(dict[str, Any], saved)["text"])
    else:
        halt = halt_reason(state) or {}
        closed, uncertain = await close_pending(
            context, registry, state, messages, pending, reason, "tool_call_not_executed"
        )
        # The final request is its own trailing notice, the last thing read. A
        # restart after this checkpoint finds it already there: never add it twice.
        notice = notice_message(
            "work_limit", finish_instruction(reason, str(halt.get("message") or ""))
        )
        if not (messages and is_runtime_notice(messages[-1]) and messages[-1] == notice):
            messages.append(notice)
        state["exit_reason"] = reason
        await save()
        await report_closed(context, closed, uncertain, "tool_call_not_executed")
        turn_capability = capability_for(messages, capability)
        selection: ModelSelection | None
        try:
            view = await compact_for_turn(context, state, messages, pending, turn_capability, [])
            # No tools are offered, but a provider may still propose calls; the
            # resolver lets the truth gates read a bridged financial proposal.
            reply, selection = await model_turn(
                context,
                messages,
                [],
                turn_capability,
                resolve_calls=registry.resolve_calls,
                context_view=view,
                owner_request=owner_words(state),
            )
        except LonoraError as error:
            if error.code in FENCE_CODES:
                raise
            # The report is a courtesy at a limit: an unavailable model must not
            # turn the bounded stop into a Run failure. Nothing more executes.
            log.warning("finish_turn_model_unavailable code=%s", error.code)
            reply, selection = ModelReply(), None
        if reply.tool_calls:
            # No tools were offered. A provider that still proposes calls gets
            # none executed; financial prose was already withheld upstream.
            log.info("finish_turn_ignored_tool_calls count=%s", len(reply.tool_calls))
        text = reply.text.strip() or limit_fallback(prefers_arabic(messages))
        if reply.rich_content is None or not reply.text.strip():
            state.pop("rich_content", None)
        else:
            state["rich_content"] = reply.rich_content
        if selection is not None:
            state["selection"] = selection_metadata(selection, reply, turn_capability)
        messages.append(
            ModelMessage(
                role="assistant",
                content=text,
                rich_content=state.get("rich_content"),
            )
        )
        # No repair turn can follow this tool-less report: an unsupported claim of
        # the owner's requested action gets its honest line here.
        line = unconfirmed_line(state, messages, text, effect_names(registry))
        if line:
            text = append_line(state, messages, text, line)
        state["limit_exit"] = {"reason": reason, "text": text}
        await save()
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


async def execute_tool_loop(
    context: ToolContext, registry: ToolRegistry, maximum_rounds: int
) -> LoopOutcome:
    """Drive one pass of a Run: restore it, then alternate tool blocks and model turns."""
    async with context.db.sessions() as session:
        run = await require_lease(session, context.lease)
        state: dict[str, Any] = dict(run.execution_state)
        scope = run_scope(run.trigger, run.model_metadata)
        capability = (
            Capability.BACKGROUND if run.trigger in WORK_TRIGGERS else Capability.CONVERSATION
        )
        task_run = bool(run.model_metadata.get("task_id"))
    messages, pending, exposure = await restore_checkpoint(
        context, registry, run, state, scope=scope, task_run=task_run
    )

    async def save() -> None:
        await persist(context, state, messages, pending)

    effect_tools = effect_names(registry)

    async def refresh_after_steering() -> None:
        updated_skills = await refresh_skill_context(
            context, registry, messages, retained_ids=state.get("viewed_skill_ids", [])
        )
        if updated_skills is not None:
            state["instruction_skill_ids"] = sorted(
                set(updated_skills) | set(state.get("viewed_skill_ids", []))
            )

    async def supersede_for_steering() -> None:
        # Owner input supersedes only calls that never started; one interrupted
        # after its in-flight marker may have executed and is reported uncertain.
        closed, uncertain = await close_pending(
            context, registry, state, messages, pending, None, "tool_call_superseded"
        )
        state.pop("waiting_call_id", None)
        await save()
        await report_closed(context, closed, uncertain, "tool_call_superseded")

    # Resume where the checkpoint left off: owner attention, a pending question,
    # an external wait or a new wake.
    if resume_after_attention(state, messages, maximum_rounds):
        await save()
    question = state.get("pending_input_request")
    if isinstance(question, dict):
        question = cast(dict[str, Any], question)
        if not await owner_steering_pending(context):
            if not pending and await merge_steering(context, state, messages):
                # A peer outcome woke a Run that waits for its owner. Keep it as
                # evidence for the answer; otherwise the outstanding steering row
                # would make the executor re-enter this wait indefinitely.
                await save()
            return question_outcome(state, question)
        # A new owner message supersedes an unpublished question before it reaches chat.
        state.pop("pending_input_request", None)
        await save()
    if environment_state(state).get("wait"):
        if pending:
            # Older checkpoints could suspend halfway through a tool block.
            # Repair their unexecuted siblings before any future wake can run
            # stale financial intent or insert a user message into that block.
            superseded = list(pending)
            supersede_wait_siblings(messages, pending)
            await save()
            await report_closed(context, superseded, [], "tool_call_superseded")
        return external_wait_outcome(state)
    woken = consume_wake(state, messages, pending)
    await save()
    await report_closed(context, woken, [], "tool_call_superseded")

    while True:
        await cancellation_checkpoint(context)
        await task_checkpoint(context)
        # At a limit: owner input buys a new budget, a Task takes another slice,
        # otherwise the final report ends the pass.
        limit = slice_limit(state, maximum_rounds)
        if int(state.get("rounds", 0)) >= limit or halt_reason(state) or state.get("limit_exit"):
            reason = "guardrail_halt" if halt_reason(state) else "tool_round_limit"
            if await owner_steering_pending(context):
                # Owner input at a boundary is a new request: it supersedes the
                # unexecuted proposals and authorizes one new bounded budget.
                await supersede_for_steering()
                if await merge_steering(context, state, messages):
                    await refresh_after_steering()
                start_budget_epoch(state)
                await save()
                continue
            if (
                reason == "tool_round_limit"
                and not state.get("limit_exit")
                and await schedule_task_continuation(context, state, maximum_rounds)
            ):
                raise ToolRetryScheduled()
            if pending:
                closed, uncertain = await close_pending(
                    context, registry, state, messages, pending, reason, "tool_call_not_executed"
                )
                await save()
                await report_closed(context, closed, uncertain, "tool_call_not_executed")
            if await merge_steering(context, state, messages):
                # A peer outcome arrived after the final reply was drafted; the
                # reply must account for it, so draft it again (bounded by input).
                await refresh_after_steering()
                state.pop("limit_exit", None)
            return await finish_turn(
                context,
                registry,
                state,
                messages,
                pending,
                capability,
                save,
                reason=reason,
                task_run=task_run,
            )
        # The pending tool block, one segment at a time. New user input follows
        # the complete tool-result block, never splits it.
        while pending:
            await task_checkpoint(context)
            if await owner_steering_pending(context):
                await supersede_for_steering()
                break
            if retry_pending(state, pending[0]):
                raise ToolRetryScheduled()
            outcome = await run_and_record_segment(
                context, registry, state, messages, pending, exposure, scope, save
            )
            if outcome is not None:
                return outcome
            if halt_reason(state):
                break
        if halt_reason(state):
            # The boundary handler finishes gracefully with the halt reason.
            continue
        # Between the block and the next model turn: steering, Task controls,
        # skill authority and the round budget.
        if await merge_steering(context, state, messages):
            await refresh_after_steering()
        await task_checkpoint(context, state, messages)
        await assert_skill_authority(
            context, registry, active_ids=cast(list[str], state["instruction_skill_ids"])
        )
        # Only the last slice ends the Run; earlier Task slices continue later.
        per_slice = int(cast(dict[str, Any], state["task_continuation"])["rounds_per_slice"])
        final_limit = per_slice * MAXIMUM_SLICES if task_run else limit
        # Calls proposed in a turn execute only when another round follows it,
        # so count the turns, this one included, whose calls can still run.
        executable = final_limit - int(state.get("rounds", 0)) - 1
        if executable <= 0:
            # Offering tools now would waste the turn on calls that never run:
            # the last budgeted turn is the final tool-less report instead.
            return await finish_turn(
                context,
                registry,
                state,
                messages,
                pending,
                capability,
                save,
                reason="tool_round_limit",
                task_run=task_run,
            )
        if executable <= BUDGET_WARNING_ROUNDS and state.get("budget_warned") != executable:
            append_notice(messages, "budget", budget_warning(executable))
            state["budget_warned"] = executable
        # The model turn.
        turn_capability = capability_for(messages, capability)
        native = native_definitions(registry, exposure, scope)
        inventory_text = inventory(registry, exposure, scope)
        policy_tools = registry.names(scope)
        view = await compact_for_turn(
            context,
            state,
            messages,
            pending,
            turn_capability,
            native,
            inventory_text=inventory_text,
            policy_tools=policy_tools,
        )
        try:
            reply, selection = await model_turn(
                context,
                messages,
                native,
                turn_capability,
                capability_inventory=inventory_text,
                # Bridge calls become the real calls before any boundary sees them.
                resolve_calls=registry.resolve_calls,
                policy_tools=policy_tools,
                context_view=view,
                input_scale=input_scale(state),
                owner_request=owner_words(state),
            )
        except LonoraError as error:
            if error.code in FENCE_CODES:
                raise
            # Every candidate failed. Nothing ran for this turn and nothing is
            # repeated: retry the same checkpoint later or tell the owner.
            profile = await recovery_profile(context, task_run)
            decision = plan_failure(state, error, profile)
            if decision.kind == "compact":
                log.warning("model_context_overflow input_scale=%s", input_scale(state))
                await save()
                continue
            if decision.kind == "retry" and decision.not_before is not None:
                environment_state(state)["retry"] = {
                    "not_before": decision.not_before.isoformat(),
                    "reason_code": RETRY_REASON,
                    "code": error.code,
                    "attempt": decision.failures,
                }
                await save()
                if decision.notify:
                    # Monitoring continues; the owner hears of the outage once.
                    async with context.db.sessions() as session, session.begin():
                        await report_task_degraded(
                            session,
                            await require_lease(session, context.lease),
                            ATTENTION_REASON,
                            error.code,
                            cast(dict[str, Any], state[STATE_KEY]).get("first_failed_at"),
                        )
                log.warning(
                    "model_turn_retry_scheduled code=%s attempt=%s notify=%s",
                    error.code,
                    decision.failures,
                    decision.notify,
                )
                raise ToolRetryScheduled() from None
            if decision.kind == "escalate":
                await save()
                if task_run:
                    # The Task waits for its owner, resumable from this checkpoint.
                    return await request_owner_attention(
                        context, state, messages, ATTENTION_REASON, "", save
                    )
            raise
        record_success(state)
        if reply.rich_content is None:
            state.pop("rich_content", None)
        else:
            state["rich_content"] = reply.rich_content
        state["rounds"] = int(state.get("rounds", 0)) + 1
        state["selection"] = selection_metadata(selection, reply, turn_capability)
        log.info(
            "model_turn_completed timings=%s visual_errors=%s",
            json.dumps(state["selection"]["stream_timings"], sort_keys=True),
            len(state["selection"]["visual_errors"]),
        )
        empty = not reply.text.strip() and reply.rich_content is None and not reply.tool_calls
        if empty and is_conversational(run.trigger):
            # An empty provider turn carries nothing to keep; the notice follows
            # the existing tail instead of an empty assistant message.
            append_notice(messages, "no_answer", NO_ANSWER)
            await save()
            continue
        messages.append(
            ModelMessage(
                role="assistant",
                content=reply.text,
                tool_calls=reply.tool_calls,
                rich_content=reply.rich_content,
            )
        )
        pending = list(reply.tool_calls)
        await save()
        if pending:
            continue
        if await merge_steering(context, state, messages):
            await refresh_after_steering()
            continue
        outcome = await final_answer(
            context,
            state,
            messages,
            reply.text,
            {
                **state["selection"],
                **rich_metadata(state),
                "reply_outcome": "answered"
                if reply.text.strip() or reply.rich_content
                else "silent",
            },
            save,
            effect_tools=effect_tools,
        )
        if outcome is not None:
            return outcome
