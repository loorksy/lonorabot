"""Compute-budget state is finite and survives configuration changes/restarts."""

from typing import Any

import pytest
from lonora_agent.continuation import MAXIMUM_SLICES, slice_limit
from lonora_core.user_error import LonoraError


def test_restart_and_config_change_cannot_reset_original_budget() -> None:
    state: dict[str, Any] = {"rounds": 24, "pending": [{"id": "original-operation"}]}
    assert slice_limit(state, 24) == 24
    restored = {**state, "task_continuation": {**state["task_continuation"], "slice": 2}}
    assert slice_limit(restored, 1000) == 48
    assert restored["rounds"] == 24
    assert restored["pending"] == [{"id": "original-operation"}]
    assert slice_limit(restored, 1) == 48


def test_maximum_slice_has_a_finite_total_model_budget() -> None:
    state: dict[str, Any] = {}
    assert slice_limit(state, 8) == 8
    state["task_continuation"]["slice"] = MAXIMUM_SLICES
    assert slice_limit(state, 8) == 32


@pytest.mark.parametrize(
    "saved",
    [
        None,
        [],
        {"version": 2, "slice": 1, "rounds_per_slice": 8},
        {"version": 1, "slice": 0, "rounds_per_slice": 8},
        {"version": 1, "slice": MAXIMUM_SLICES + 1, "rounds_per_slice": 8},
        {"version": 1, "slice": True, "rounds_per_slice": 8},
        {"version": 1, "slice": 1, "rounds_per_slice": 0},
        {"version": 1, "slice": 1, "rounds_per_slice": True},
    ],
)
def test_corrupt_or_exhausted_state_is_not_silently_reinitialized(saved: Any) -> None:
    with pytest.raises(LonoraError, match="task_continuation_state_invalid"):
        slice_limit({"task_continuation": saved}, 24)


@pytest.mark.parametrize("budget", [0, -1, True])
def test_invalid_initial_budget_is_rejected(budget: int) -> None:
    with pytest.raises(LonoraError, match="task_continuation_budget_invalid"):
        slice_limit({}, budget)
