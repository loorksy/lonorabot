"""Structural end-of-turn checks adapted from Hermes Agent's turn_stop_gates.py.

Source: NousResearch/hermes-agent, revision
c78ca093aa4b6759c055c3ed2bfbe7f741cf0292. The typed continue/stop verdict
and bounded terminal-protocol nudge are adapted for Lonora's durable work.
Prose is an update, never proof of a saved monitoring or scheduling action.

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

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any, cast

from lonora_core.user_error import LonoraError
from lonora_db.runs import require_lease
from lonora_db.schema import TicketRow
from lonora_db.tasks import is_continuous_task, task_state
from lonora_tools.context import ToolContext

MAXIMUM_STOP_NUDGES = 2
_STATE_KEY = "continuous_stop_gate"
_COMPLETION_KEY = "task_completion_gate"

CONTINUOUS_NUDGE = (
    "This responsibility is continuous. A text answer does not complete it or save "
    "monitoring. Continue useful authorized work, or use task_wait with a real owned "
    "watch, verified broker-recovery source, or a deliberate review timer. Discover "
    "the capability through tool_environment if needed. Put any concise owner update "
    "in the same assistant message as task_wait; only a successful saved wait can "
    "support a promise to follow up. Use wait_for_input only for genuinely missing "
    "owner information or authority. Do not invent activity, ask routine trading "
    "questions, or poll the model continuously. The owner can pause or stop this work."
)


@dataclass(frozen=True)
class StopGateVerdict:
    continue_turn: bool
    nudge: str | None = None
    # Set once the bounded nudges are spent: the held answer then goes to the
    # owner as a resumable attention request instead of failing the Run.
    exhausted: str | None = None


def reset_stop_gate(state: dict[str, Any]) -> None:
    """Only real external wake/owner input starts another bounded review epoch."""
    state.pop(_STATE_KEY, None)
    state.pop(_COMPLETION_KEY, None)
    state.pop("effect_claim_gate", None)


def _steps_nudge(steps: Sequence[tuple[str, str]]) -> str:
    listed = "; ".join(f"{identifier}: {title}" for identifier, title in steps[:12])
    more = f" (+{len(steps) - 12} more)" if len(steps) > 12 else ""
    return (
        "This task is not complete: these declared steps are not completed yet: "
        + listed
        + more
        + ". A final answer cannot complete the task. Continue the remaining authorized "
        "work and record each finished step with task_step_update citing the successful "
        "tool call that proves it. If a step is genuinely blocked, explain the blocker or "
        "ask the owner with wait_for_input. Never mark or describe unfinished work as done."
    )


def apply_stop_gates(
    state: dict[str, Any],
    *,
    continuous: bool,
    incomplete_steps: Sequence[tuple[str, str]] = (),
) -> StopGateVerdict:
    """A model's finish reason cannot terminate an ongoing or unfinished responsibility.

    The counter lives in the existing checkpoint, so process restarts and new
    compute slices cannot buy unlimited final-answer retries. No text classifier
    decides whether monitoring exists: the successful wait path settles it.
    Finite work with declared unfinished steps gets the same bounded review.
    """
    if continuous:
        key, code, nudge = _STATE_KEY, "task_wait_required", CONTINUOUS_NUDGE
    elif incomplete_steps:
        key, code, nudge = _COMPLETION_KEY, "task_steps_incomplete", _steps_nudge(incomplete_steps)
    else:
        return StopGateVerdict(continue_turn=False)
    revision = state.get("task_plan_revision", 0)
    if type(revision) is not int or revision < 0:
        raise LonoraError("task_stop_gate_state_invalid", 409)
    saved = state.setdefault(key, {"version": 1, "attempts": 0, "plan_revision": revision})
    if not isinstance(saved, dict):
        raise LonoraError("task_stop_gate_state_invalid", 409)
    value = cast(dict[str, Any], saved)
    attempts = value.get("attempts")
    prior_revision = value.get("plan_revision")
    if (
        value.get("version") != 1
        or type(attempts) is not int
        or not 0 <= attempts <= MAXIMUM_STOP_NUDGES
        or type(prior_revision) is not int
        or not 0 <= prior_revision <= revision
    ):
        raise LonoraError("task_stop_gate_state_invalid", 409)
    if prior_revision != revision:
        # task_checkpoint reads the server-owned plan revision before invoking
        # the model. Resuming unchanged work cannot manufacture this boundary.
        value["plan_revision"], attempts = revision, 0
    if attempts >= MAXIMUM_STOP_NUDGES:
        return StopGateVerdict(continue_turn=False, exhausted=code)
    value["attempts"] = attempts + 1
    return StopGateVerdict(continue_turn=True, nudge=nudge)


@dataclass(frozen=True)
class TaskProgress:
    """Server-owned completion facts of the Task bound to this Run."""

    continuous: bool
    declared_steps: int
    incomplete: tuple[tuple[str, str], ...]

    def contract_satisfied(self) -> bool:
        """Finite work whose declared steps were all recorded complete with evidence.

        Work without declared steps has nothing that proves completion at a
        limit, so it is never treated as finished there.
        """
        return not self.continuous and self.declared_steps > 0 and not self.incomplete


async def task_progress(context: ToolContext) -> TaskProgress | None:
    """Resolve the existing Task identity; metadata alone grants no authority."""
    async with context.db.sessions() as session:
        run = await require_lease(session, context.lease)
        identifier = run.model_metadata.get("task_id")
        if not identifier:
            return None
        row = await session.get(TicketRow, identifier)
        if (
            row is None
            or row.owner_id != context.owner_id
            or row.agent_id != run.agent_id
            or row.thread_id != run.thread_id
            or row.payload.get("run_id") != run.id
            or not row.state.get("task")
        ):
            raise LonoraError("task_run_mismatch", 409)
        task = task_state(row)
        return TaskProgress(
            continuous=is_continuous_task(task, run),
            declared_steps=len(task.steps),
            incomplete=tuple(
                (step.id, step.title)
                for step in task.steps
                if step.state not in {"completed", "skipped"}
            ),
        )


async def task_stop_gate(context: ToolContext, state: dict[str, Any]) -> StopGateVerdict:
    progress = await task_progress(context)
    if progress is None:
        return StopGateVerdict(continue_turn=False)
    return apply_stop_gates(
        state, continuous=progress.continuous, incomplete_steps=progress.incomplete
    )
