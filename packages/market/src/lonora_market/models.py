from dataclasses import dataclass

from lonora_contracts.market import Candle, Instrument, Quote


@dataclass(frozen=True)
class MarketSnapshot:
    instrument: Instrument
    quote: Quote
    candles: list[Candle]
