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
