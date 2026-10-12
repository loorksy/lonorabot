from lonora_contracts.market import Candle


def trim_candle_history(candles: list[Candle], maximum: int = 1000) -> list[Candle]:
    unique = {c.time: c for c in candles}
    return [unique[time] for time in sorted(unique)[-maximum:]]
