"""Recovery decisions and short provider cooldowns for the model router.

Each ``FailureReason`` maps to one recovery: how often to retry the same
provider (fewer when another candidate can answer), whether the next candidate
may be tried, whether the failure is transient for the Run (back off and retry
later rather than fail), and how long a provider that gave up is benched so the
next requests go straight to a healthy candidate.

The recovery hints adapt Hermes Agent ``agent/error_classifier.py``
(``ClassifiedError`` retryable/should_fallback/should_compress), the bench
adapts ``agent/fallback_cooldown.py`` (``_arm_rate_limit_cooldown``: wait out
the provider's declared reset, otherwise back off exponentially) and the delay
adapts the decorrelated jitter of ``agent/retry_utils.py``
(``jittered_backoff``), source https://github.com/NousResearch/hermes-agent at
revision a9ff9799e273f525b82718cdc69fdec71b1dca5a. Lonora's bench is
process-local and short, keyed by model or (for credential failures) by a
fingerprint of the credential so a replaced key is tried at once; nothing here
decides authority, and a request whose output was cut off is never accepted
because of a retry policy.

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

from collections.abc import Callable
from dataclasses import dataclass, field
from hashlib import sha256
from time import monotonic

from lonora_adapter_kit.model_errors import FailureReason, ModelProviderError
from lonora_contracts.model_routing import ModelSelection
from lonora_core.user_error import LonoraError


@dataclass(frozen=True)
class Recovery:
    # Same-provider retries while another candidate remains, and when alone.
    retries: int
    retries_alone: int
    # The next candidate in the chain may answer instead.
    fallback: bool
    # Run level: the situation may clear by itself; back off instead of failing.
    transient: bool
    # Base cooldown after the provider gives up; 0 means no bench.
    bench_seconds: float = 0.0
    # Bench the credential (all its models), not only the model.
    credential_scope: bool = False


_R = FailureReason
RECOVERY: dict[FailureReason, Recovery] = {
    _R.AUTH: Recovery(0, 0, True, False, 900.0, True),
    _R.BILLING: Recovery(0, 0, True, False, 900.0, True),
    _R.RATE_LIMIT: Recovery(0, 2, True, True, 30.0),
    _R.OVERLOADED: Recovery(1, 2, True, True, 20.0),
    _R.SERVER_ERROR: Recovery(1, 2, True, True, 20.0),
    _R.TIMEOUT: Recovery(0, 1, True, True, 30.0),
    _R.CONNECTION: Recovery(1, 2, True, True, 15.0),
    _R.UNKNOWN: Recovery(1, 1, True, True, 15.0),
    # Another model cannot shrink this request; the Run compacts and retries.
    _R.CONTEXT_OVERFLOW: Recovery(0, 0, False, False),
    _R.PAYLOAD_TOO_LARGE: Recovery(0, 0, False, False),
    _R.MODEL_NOT_FOUND: Recovery(0, 0, True, False, 900.0),
    _R.CONTENT_POLICY: Recovery(0, 0, True, False),
    _R.FORMAT_ERROR: Recovery(0, 0, True, False),
    # Corrected or boosted once by the router before these apply.
    _R.OUTPUT_LIMIT: Recovery(0, 0, True, False),
    _R.TRUNCATED: Recovery(0, 0, True, False),
    _R.INVALID_RESPONSE: Recovery(1, 1, True, False),
    _R.NOT_CONFIGURED: Recovery(0, 0, True, False),
}

# A provider-declared wait up to this long is waited out in the call itself;
# a longer one benches the provider and is left to the Run's own backoff.
MAXIMUM_INLINE_WAIT_SECONDS = 20.0
BACKOFF_BASE_SECONDS = 1.0
BACKOFF_CAP_SECONDS = 8.0
MAXIMUM_BENCH_SECONDS = 900.0
# Codes a router or fixture may raise without a classified reason.
_CODE_REASONS = {
    "model_provider_unavailable": FailureReason.CONNECTION,
    "model_rate_limited": FailureReason.RATE_LIMIT,
    "model_endpoint_unavailable": FailureReason.MODEL_NOT_FOUND,
    "model_credentials_rejected": FailureReason.AUTH,
    "model_billing_exhausted": FailureReason.BILLING,
    "model_request_rejected": FailureReason.FORMAT_ERROR,
    "model_response_invalid": FailureReason.INVALID_RESPONSE,
    "model_output_truncated": FailureReason.TRUNCATED,
    "model_content_blocked": FailureReason.CONTENT_POLICY,
}
# Stable codes the Run backs off on, whatever raised them.
TRANSIENT_CODES = frozenset({"model_provider_unavailable", "model_rate_limited"})


def classified(error: LonoraError) -> ModelProviderError | None:
    """The classified form of a provider failure; ``None`` for other errors."""
    if isinstance(error, ModelProviderError):
        return error
    reason = _CODE_REASONS.get(error.code)
    return ModelProviderError(reason) if reason is not None else None


def is_transient(error: LonoraError) -> bool:
    """Whether a Run should back off and retry later instead of failing."""
    if isinstance(error, ModelProviderError):
        return RECOVERY[error.reason].transient
    return error.code in TRANSIENT_CODES


def backoff_delay(
    attempt: int,
    jitter: Callable[[], float],
    *,
    base: float = BACKOFF_BASE_SECONDS,
    cap: float = BACKOFF_CAP_SECONDS,
) -> float:
    """``min(base * 2^(attempt-1), cap)`` plus up to half of it as jitter."""
    exponent = max(0, min(attempt - 1, 32))
    delay = min(base * (2**exponent), cap)
    return delay + max(0.0, min(1.0, jitter())) * 0.5 * delay


def credential_fingerprint(secret: str) -> str:
    return sha256(secret.encode()).hexdigest()[:16]


@dataclass
class Bench:
    until: float
    reason: FailureReason
    streak: int


@dataclass
class ProviderHealth:
    """Process-local cooldowns and learned output limits per provider/model."""

    clock: Callable[[], float] = monotonic
    benches: dict[str, Bench] = field(default_factory=dict[str, Bench])
    output_caps: dict[str, int] = field(default_factory=dict[str, int])

    @staticmethod
    def model_key(selection: ModelSelection) -> str:
        return selection.provider + ":" + selection.model

    @staticmethod
    def credential_key(selection: ModelSelection, fingerprint: str) -> str:
        return selection.provider + "#" + fingerprint

    def benched(self, selection: ModelSelection, fingerprint: str) -> tuple[Bench, float] | None:
        """The active bench and its remaining seconds, if this candidate is benched."""
        now = self.clock()
        for key in (self.credential_key(selection, fingerprint), self.model_key(selection)):
            bench = self.benches.get(key)
            if bench is not None and bench.until > now:
                return bench, bench.until - now
        return None

    def record_failure(
        self, selection: ModelSelection, fingerprint: str, error: ModelProviderError
    ) -> float:
        """Bench the candidate that gave up; returns the cooldown in seconds."""
        recovery = RECOVERY[error.reason]
        if recovery.bench_seconds <= 0:
            return 0.0
        key = (
            self.credential_key(selection, fingerprint)
            if recovery.credential_scope
            else self.model_key(selection)
        )
        previous = self.benches.get(key)
        streak = previous.streak + 1 if previous is not None else 1
        if error.retry_after is not None:
            seconds = error.retry_after
        else:
            seconds = recovery.bench_seconds * (2 ** min(streak - 1, 8))
        seconds = min(seconds, MAXIMUM_BENCH_SECONDS)
        self.benches[key] = Bench(self.clock() + seconds, error.reason, streak)
        return seconds

    def record_success(self, selection: ModelSelection, fingerprint: str) -> None:
        self.benches.pop(self.model_key(selection), None)
        self.benches.pop(self.credential_key(selection, fingerprint), None)

    def output_cap(self, selection: ModelSelection) -> int | None:
        return self.output_caps.get(self.model_key(selection))

    def learn_output_cap(self, selection: ModelSelection, limit: int) -> None:
        self.output_caps[self.model_key(selection)] = limit
