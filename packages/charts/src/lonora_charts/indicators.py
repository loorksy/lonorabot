from statistics import pstdev

from lonora_contracts.market import Candle
from lonora_core.chart_indicator import validate_indicator


def sma(values: list[float], period: int) -> list[float | None]:
    return [
        None if index + 1 < period else sum(values[index - period + 1 : index + 1]) / period
        for index in range(len(values))
    ]


def ema(values: list[float], period: int) -> list[float | None]:
    result: list[float | None] = [None] * len(values)
    if len(values) < period:
        return result
    previous = sum(values[:period]) / period
    result[period - 1] = previous
    alpha = 2 / (period + 1)
    for index in range(period, len(values)):
        previous = values[index] * alpha + previous * (1 - alpha)
        result[index] = previous
    return result


def rsi(values: list[float], period: int) -> list[float | None]:
    result: list[float | None] = [None] * len(values)
    if len(values) <= period:
        return result
    changes = [values[i] - values[i - 1] for i in range(1, len(values))]
    gain = sum(max(change, 0) for change in changes[:period]) / period
    loss = sum(max(-change, 0) for change in changes[:period]) / period
    for index in range(period, len(values)):
        if index > period:
            change = changes[index - 1]
            gain = (gain * (period - 1) + max(change, 0)) / period
            loss = (loss * (period - 1) + max(-change, 0)) / period
        result[index] = (
            50.0 if gain == loss == 0 else 100.0 if loss == 0 else 100 - 100 / (1 + gain / loss)
        )
    return result


def indicator_series(
    name: str, candles: list[Candle], period: int = 14
) -> dict[str, list[float | None]]:
    name = name.casefold()
    validate_indicator(name, period)
    values = [float(c.close) for c in candles]
    if name == "sma":
        return {"value": sma(values, period)}
    if name == "ema":
        return {"value": ema(values, period)}
    if name == "rsi":
        return {"value": rsi(values, period)}
    if name == "bollinger":
        middle = sma(values, period)
        widths = [
            None if i + 1 < period else 2 * pstdev(values[i - period + 1 : i + 1])
            for i in range(len(values))
        ]
        return {
            "middle": middle,
            "upper": [
                m + w if m is not None and w is not None else None
                for m, w in zip(middle, widths, strict=True)
            ],
            "lower": [
                m - w if m is not None and w is not None else None
                for m, w in zip(middle, widths, strict=True)
            ],
        }
    if name == "atr":
        ranges = [
            float(c.high - c.low)
            if i == 0
            else max(
                float(c.high - c.low),
                abs(float(c.high - candles[i - 1].close)),
                abs(float(c.low - candles[i - 1].close)),
            )
            for i, c in enumerate(candles)
        ]
        return {"value": sma(ranges, period)}
    fast, slow = ema(values, 12), ema(values, 26)
    macd = [
        f - s if f is not None and s is not None else None for f, s in zip(fast, slow, strict=True)
    ]
    available = [value for value in macd if value is not None]
    signal_available = ema(available, 9)
    signal: list[float | None] = [None] * (len(macd) - len(available)) + signal_available
    return {
        "macd": macd,
        "signal": signal,
        "histogram": [
            m - s if m is not None and s is not None else None
            for m, s in zip(macd, signal, strict=True)
        ],
    }
