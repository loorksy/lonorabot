from lonora_adapters.brokers.base import BrokerManager

from .provider import MarketProvider


async def broker_market(
    manager: BrokerManager, owner_id: str, connection_id: str
) -> MarketProvider:
    if manager.market and manager.market.owner_id == owner_id:
        from .runtime import RuntimeMarketAdapter

        return MarketProvider(RuntimeMarketAdapter(manager.market, connection_id))
    return MarketProvider(await manager.get(owner_id, connection_id))
