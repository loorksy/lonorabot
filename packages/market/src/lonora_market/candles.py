from lonora_contracts.market import Candle
from lonora_core.user_error import LonoraError


def validate_candle_series(candles: list[Candle]) -> list[Candle]:
    if len({c.time for c in candles}) != len(candles):
        raise LonoraError("duplicate_candle_timestamp")
    if candles and any(
        c.symbol != candles[0].symbol or c.timeframe != candles[0].timeframe for c in candles
    ):
        raise LonoraError("mixed_candle_series")
    return sorted(candles, key=lambda candle: candle.time)


CSV_COLUMNS = ("time", "close_time", "open", "high", "low", "close", "volume", "closed")


def candles_csv(candles: list[Candle], closed_flags: list[bool], close_times: list[str]) -> bytes:
    """Exact broker values as CSV for analysis files; no rounding or resampling."""
    lines = [",".join(CSV_COLUMNS)]
    for candle, closed, close_time in zip(candles, closed_flags, close_times, strict=True):
        lines.append(
            ",".join(
                (
                    candle.time.isoformat(),
                    close_time,
                    str(candle.open),
                    str(candle.high),
                    str(candle.low),
                    str(candle.close),
                    str(candle.volume),
                    "1" if closed else "0",
                )
            )
        )
    return ("\n".join(lines) + "\n").encode()
