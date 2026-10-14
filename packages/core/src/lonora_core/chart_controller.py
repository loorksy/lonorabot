from .user_error import LonoraError

# Canonical MetaTrader/MetaApi timeframes; preserve the SDK's monthly `1mn` spelling.
TIMEFRAMES = {
    "1m",
    "2m",
    "3m",
    "4m",
    "5m",
    "6m",
    "10m",
    "12m",
    "15m",
    "20m",
    "30m",
    "1h",
    "2h",
    "3h",
    "4h",
    "6h",
    "8h",
    "12h",
    "1d",
    "1w",
    "1mn",
}


def validate_timeframe(timeframe: str) -> str:
    if timeframe not in TIMEFRAMES:
        raise LonoraError("unsupported_timeframe")
    return timeframe
