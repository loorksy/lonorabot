from lonora_adapter_kit.broker import BrokerAdapter
from lonora_contracts.market import Candle, Instrument, Quote


class BrokerMarketAdapter:
    def __init__(self, broker: BrokerAdapter):
        self.broker = broker

    async def instruments(self) -> list[Instrument]:
        return await self.broker.instruments()

    async def quote(self, symbol: str) -> Quote:
        return await self.broker.quote(symbol)

    async def candles(self, symbol: str, timeframe: str, limit: int) -> list[Candle]:
        return await self.broker.candles(symbol, timeframe, limit)
