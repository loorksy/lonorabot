from .user_error import LonoraError

TIMEFRAMES = {"1m", "5m", "15m", "30m", "1h", "4h", "1d", "1w"}


def validate_timeframe(timeframe: str) -> str:
    if timeframe not in TIMEFRAMES:
        raise LonoraError("unsupported_timeframe")
    return timeframe
