from .user_error import LonoraError

SUPPORTED = {"sma", "ema", "rsi", "macd", "atr", "bollinger"}


def validate_indicator(name: str, period: int) -> None:
    if name.casefold() not in SUPPORTED or not 2 <= period <= 500:
        raise LonoraError("unsupported_indicator")
