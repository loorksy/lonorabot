import asyncio
from collections.abc import AsyncIterator

from lonora_contracts.market import Quote

from .provider import MarketProvider


async def quote_stream(
    provider: MarketProvider, symbol: str, interval: float = 2
) -> AsyncIterator[Quote]:
    last: Quote | None = None
    while True:
        quote = await provider.quote(symbol)
        if quote != last:
            last = quote
            yield quote
        await asyncio.sleep(interval)
