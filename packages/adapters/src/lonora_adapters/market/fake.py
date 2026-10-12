from lonora_contracts.market import Candle, Instrument, Quote
from lonora_core.user_error import LonoraError


class RecordedMarketAdapter:
    def __init__(
        self, instruments: list[Instrument], quotes: dict[str, Quote], candles: list[Candle]
    ):
        self.recorded_instruments, self.recorded_quotes, self.recorded_candles = (
            instruments,
            quotes,
            candles,
        )

    async def instruments(self) -> list[Instrument]:
        return self.recorded_instruments

    async def quote(self, symbol: str) -> Quote:
        if symbol not in self.recorded_quotes:
            raise LonoraError("quote_unavailable", 404)
        return self.recorded_quotes[symbol]

    async def candles(self, symbol: str, timeframe: str, limit: int) -> list[Candle]:
        return [
            c for c in self.recorded_candles if c.symbol == symbol and c.timeframe == timeframe
        ][-limit:]
