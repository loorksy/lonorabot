from lonora_adapter_kit.market import MarketAdapter
from lonora_contracts.market import Candle, Instrument, Quote
from lonora_core.chart_controller import validate_timeframe
from lonora_core.trading_run_market import require_exact_symbol


class MarketProvider:
    def __init__(self, adapter: MarketAdapter):
        self.adapter = adapter

    async def instruments(self) -> list[Instrument]:
        return await self.adapter.instruments()

    async def quote(self, symbol: str) -> Quote:
        quote = await self.adapter.quote(symbol)
        require_exact_symbol(symbol, quote.symbol)
        return quote

    async def candles(self, symbol: str, timeframe: str, limit: int = 300) -> list[Candle]:
        validate_timeframe(timeframe)
        candles = await self.adapter.candles(symbol, timeframe, max(1, min(limit, 1000)))
        for candle in candles:
            require_exact_symbol(symbol, candle.symbol)
        return sorted(candles, key=lambda candle: candle.time)
