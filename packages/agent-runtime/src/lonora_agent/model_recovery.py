"""Run-level recovery once every model candidate of one request has failed.

The router already retried, corrected and fell back inside the request. What is
left is decided here, on the fenced Run checkpoint, and never repeats an effect:
the failed step is a model request, every executed call keeps its recorded
result, and an interrupted call keeps its in-flight marker for the existing
replay and reconciliation rules.

- A provider-proven context overflow tightens this Run's admission scale; the
  turn is compacted and retried (bounded).
- A transient failure (outage, overload, rate limit) schedules a retry of the
  same checkpoint after a growing, jittered backoff and releases the worker
  through the existing ``ToolRetryScheduled`` path, as safe reads already do.
- After a streak of transient failures the owner is told: Task work waits for
  owner attention, resumable from the same checkpoint; any other Run fails with
  the provider's stable code. The streak threshold follows the failure-streak
  escalation idea of Hermes Agent's scheduler; no code is ported from it.
"""

import random
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any, Literal, cast

from lonora_adapter_kit.model_errors import FailureReason, ModelProviderError
from lonora_contracts.domain import utcnow
from lonora_core.user_error import LonoraError
from lonora_providers.context import MINIMUM_INPUT_SCALE
from lonora_providers.resilience import is_transient

STATE_KEY = "model_recovery"
RETRY_REASON = "model_provider_retry"
ATTENTION_REASON = "model_unavailable"
# Each provider-proven overflow multiplies this Run's admission by this factor.
OVERFLOW_SCALE = 0.7
MAXIMUM_OVERFLOW_RETRIES = 3


@dataclass(frozen=True)
class BackoffProfile:
    base_seconds: float
    cap_seconds: float
    # Consecutive transient failures before the owner is told.
    escalate_after: int


# The owner is waiting on a conversation: short waits, early honest failure.
CONVERSATION = BackoffProfile(10.0, 60.0, 3)
# Background and Task work outlasts ordinary outages before asking the owner.
WORK = BackoffProfile(30.0, 900.0, 6)


@dataclass(frozen=True)
class Decision:
    kind: Literal["compact", "retry", "escalate", "raise"]
    not_before: datetime | None = None
    failures: int = 0


def recovery_state(state: dict[str, Any]) -> dict[str, Any]:
    value = state.get(STATE_KEY)
    record = cast(dict[str, Any], value) if isinstance(value, dict) else {}
    state[STATE_KEY] = record
    return record


def input_scale(state: dict[str, Any]) -> float:
    value = state.get(STATE_KEY)
    if not isinstance(value, dict):
        return 1.0
    scale = cast(dict[str, Any], value).get("input_scale", 1.0)
    if not isinstance(scale, int | float) or isinstance(scale, bool):
        return 1.0
    return min(1.0, max(MINIMUM_INPUT_SCALE, float(scale)))


def record_success(state: dict[str, Any]) -> bool:
    """A successful model turn ends the failure streak; ``True`` if it changed.

    The spent model-retry deadline is removed too, so status projections stop
    reporting a retry that already happened.
    """
    environment = state.get("environment")
    if isinstance(environment, dict):
        retry = cast(dict[str, Any], environment).get("retry")
        if isinstance(retry, dict) and cast(dict[str, Any], retry).get("reason_code") == (
            RETRY_REASON
        ):
            cast(dict[str, Any], environment).pop("retry", None)
    value = state.get(STATE_KEY)
    if not isinstance(value, dict):
        return False
    record = cast(dict[str, Any], value)
    changed = bool(record.get("failures") or record.get("overflow_retries"))
    record["failures"] = 0
    record["overflow_retries"] = 0
    record.pop("code", None)
    return changed


def reset_streak(state: dict[str, Any]) -> None:
    """Owner input after an escalation starts a fresh streak."""
    value = state.get(STATE_KEY)
    if isinstance(value, dict):
        cast(dict[str, Any], value)["failures"] = 0


def backoff_seconds(
    failures: int,
    profile: BackoffProfile,
    hint: float | None,
    jitter: Callable[[], float] = random.random,
) -> float:
    """Exponential from the profile base, never shorter than the provider's hint."""
    exponent = max(0, min(failures - 1, 16))
    delay = min(profile.base_seconds * (2**exponent), profile.cap_seconds)
    delay += max(0.0, min(1.0, jitter())) * 0.25 * delay
    if hint is not None and hint > delay:
        delay = min(hint, profile.cap_seconds * 2)
    return delay


def plan_failure(
    state: dict[str, Any],
    error: LonoraError,
    profile: BackoffProfile,
    *,
    now: datetime | None = None,
    jitter: Callable[[], float] = random.random,
) -> Decision:
    """Record the failure in ``state`` and decide what the Run does next."""
    record = recovery_state(state)
    reason = error.reason if isinstance(error, ModelProviderError) else None
    if reason in {FailureReason.CONTEXT_OVERFLOW, FailureReason.PAYLOAD_TOO_LARGE}:
        retries = int(record.get("overflow_retries") or 0)
        scale = input_scale(state)
        if retries >= MAXIMUM_OVERFLOW_RETRIES or scale <= MINIMUM_INPUT_SCALE:
            return Decision("raise")
        record["overflow_retries"] = retries + 1
        record["input_scale"] = round(max(MINIMUM_INPUT_SCALE, scale * OVERFLOW_SCALE), 4)
        return Decision("compact")
    if not is_transient(error):
        return Decision("raise")
    failures = int(record.get("failures") or 0) + 1
    moment = now or utcnow()
    record.update(
        failures=failures,
        code=error.code,
        reason=reason.value if reason else None,
        last_failed_at=moment.isoformat(),
    )
    if failures == 1:
        record["first_failed_at"] = moment.isoformat()
    if failures >= profile.escalate_after:
        # The streak restarts from zero if the owner resumes the work.
        record["failures"] = 0
        record["escalations"] = int(record.get("escalations") or 0) + 1
        return Decision("escalate", failures=failures)
    hint = error.retry_after if isinstance(error, ModelProviderError) else None
    delay = backoff_seconds(failures, profile, hint, jitter)
    return Decision("retry", not_before=moment + timedelta(seconds=delay), failures=failures)
