from lonora_adapters.brokers.base import BrokerManager
from lonora_db.client import Database
from lonora_market.watchers import check_watches


async def dispatch_market_wakes(db: Database, brokers: BrokerManager) -> int:
    return await check_watches(db, brokers)
