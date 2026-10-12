from lonora_db.market_watches import MarketWatchRepository

from . import resource_router

router = resource_router("/watches", MarketWatchRepository())
