"""Shared stable transient read codes for Run and logical Task recovery."""

from math import ceil
from typing import Literal

# ``environment.retry.reason_code`` of a Run backing off after every model
# candidate failed (a read retry has its own reason, or none).
MODEL_RETRY_REASON = "model_provider_retry"
# ``environment.retry.reason_code`` of a Run a stopping Gateway handed back at a step
# boundary: it is not waiting out any failure, the next Gateway continues it at once.
DRAIN_REASON = "gateway_drained"

TRANSIENT_READ_CODES = frozenset(
    {
        "broker_connection_timeout",
        "broker_connection_unavailable",
        # The broker refuses the terminal's login: often its server is down for a while,
        # so recovery keeps trying; a lasting refusal reaches the owner after the grace.
        "broker_login_rejected",
        # MetaApi's terminal is deployed but not logged in to the broker, for a reason
        # MetaApi does not give (DISCONNECTED): recovery keeps trying, as above.
        "broker_login_not_established",
        # The broker asked to slow down: the same read succeeds after a short wait.
        "broker_rate_limited",
        "broker_candles_unavailable",
        "market_quote_unavailable",
        "market_candles_unavailable",
        "tool_read_timeout",
        "tool_connection_failure",
        "provider_temporarily_unavailable",
    }
)


RunFailureFamily = Literal["quota", "rate", "timeout", "model", "other"]

# The provider's own failure family (Q22): the error card says which, and offers its fix.
QUOTA_CODES = frozenset({"model_billing_exhausted"})
RATE_CODES = frozenset({"model_rate_limited"})
# The provider's classified reason (``FailureReason`` values) when the failing error had
# one: a timeout shares ``model_provider_unavailable`` with outages, the reason tells.
REASON_FAMILIES: dict[str, RunFailureFamily] = {
    "billing": "quota",
    "rate_limit": "rate",
    "timeout": "timeout",
}
MODEL_CODES = frozenset({"context_limit_exceeded"})


def failure_family(code: str | None, reason: str | None = None) -> RunFailureFamily:
    """quota · rate · timeout · model · other, from the provider reason, else the code."""
    if reason in REASON_FAMILIES:
        return REASON_FAMILIES[reason]
    value = code or ""
    if value in QUOTA_CODES:
        return "quota"
    if value in RATE_CODES:
        return "rate"
    if value.endswith("_timeout"):
        return "timeout"
    if value.startswith("model_") or value in MODEL_CODES:
        return "model"
    return "other"


def retry_after_seconds(value: float | None) -> int | None:
    """A provider ``Retry-After`` hint in whole seconds (rounded up); None without one."""
    if value is None or value <= 0:
        return None
    return ceil(value)
