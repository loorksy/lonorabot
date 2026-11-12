from lonora_adapters.brokers.base import BrokerManager
from lonora_db.client import Database
from lonora_market.watchers import SecretReader, check_watches


async def dispatch_market_wakes(
    db: Database, brokers: BrokerManager, read_secret: SecretReader
) -> int:
    # The owner's store reads a calendar address a Secret card saved (7.2.3: never the
    # broker layer's).
    return await check_watches(db, brokers, read_secret=read_secret)
