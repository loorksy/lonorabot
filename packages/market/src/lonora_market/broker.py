from lonora_adapters.brokers.base import BrokerManager

from .provider import MarketProvider


async def broker_market(
    manager: BrokerManager, owner_id: str, connection_id: str
) -> MarketProvider:
    return MarketProvider(await manager.get(owner_id, connection_id))
