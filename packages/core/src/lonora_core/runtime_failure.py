"""Shared stable transient read codes for Run and logical Task recovery."""

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
