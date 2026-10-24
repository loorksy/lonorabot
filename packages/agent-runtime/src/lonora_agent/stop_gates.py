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

from dataclasses import dataclass
from typing import Any, cast

from lonora_core.user_error import LonoraError
from lonora_db.runs import require_lease
from lonora_db.schema import TicketRow
from lonora_db.tasks import is_continuous_task, task_state
from lonora_tools.context import ToolContext

MAXIMUM_STOP_NUDGES = 2
_STATE_KEY = "continuous_stop_gate"


@dataclass(frozen=True)
class StopGateVerdict:
    continue_turn: bool
    nudge: str | None = None


def reset_stop_gate(state: dict[str, Any]) -> None:
    """Only real external wake/owner input starts another bounded review epoch."""
    state.pop(_STATE_KEY, None)


def apply_stop_gates(state: dict[str, Any], *, continuous: bool) -> StopGateVerdict:
    """A model's finish reason cannot terminate an ongoing responsibility.

    The counter lives in the existing checkpoint, so process restarts and new
    compute slices cannot buy unlimited final-answer retries. No text classifier
    decides whether monitoring exists: the successful wait path settles it.
    """
    if not continuous:
        return StopGateVerdict(continue_turn=False)
    revision = state.get("task_plan_revision", 0)
    if type(revision) is not int or revision < 0:
        raise LonoraError("task_stop_gate_state_invalid", 409)
    saved = state.setdefault(_STATE_KEY, {"version": 1, "attempts": 0, "plan_revision": revision})
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
        raise LonoraError("task_wait_required", 409)
    value["attempts"] = attempts + 1
    return StopGateVerdict(
        continue_turn=True,
        nudge=(
            "This responsibility is continuous. A text answer does not complete it or save "
            "monitoring. Continue useful authorized work, or use task_wait with a real owned "
            "watch, verified broker-recovery source, or a deliberate review timer. Discover "
            "the capability through tool_environment if needed. Put any concise owner update "
            "in the same assistant message as task_wait; only a successful saved wait can "
            "support a promise to follow up. Use wait_for_input only for genuinely missing "
            "owner information or authority. Do not invent activity, ask routine trading "
            "questions, or poll the model continuously. The owner can pause or stop this work."
        ),
    )


async def task_stop_gate(context: ToolContext, state: dict[str, Any]) -> StopGateVerdict:
    """Resolve the existing Task identity; metadata alone grants no authority."""
    async with context.db.sessions() as session:
        run = await require_lease(session, context.lease)
        identifier = run.model_metadata.get("task_id")
        if not identifier:
            return StopGateVerdict(continue_turn=False)
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
        continuous = is_continuous_task(task_state(row), run)
    return apply_stop_gates(state, continuous=continuous)
