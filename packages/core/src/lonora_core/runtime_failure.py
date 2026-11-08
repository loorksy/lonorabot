"""Shared stable transient read codes for Run and logical Task recovery."""

# ``environment.retry.reason_code`` of a Run backing off after every model
# candidate failed (a read retry has its own reason, or none).
MODEL_RETRY_REASON = "model_provider_retry"

TRANSIENT_READ_CODES = frozenset(
    {
        "broker_connection_timeout",
        "broker_connection_unavailable",
        "broker_candles_unavailable",
        "market_quote_unavailable",
        "market_candles_unavailable",
        "tool_read_timeout",
        "tool_connection_failure",
        "provider_temporarily_unavailable",
    }
)
