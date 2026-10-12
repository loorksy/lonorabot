from lonora_contracts.market_watch import Watch

from .schema import MarketWatchRow
from .transactions import ResourceRepository


class MarketWatchRepository(ResourceRepository):
    """Transactional, owner-scoped persistence for market watches."""

    row_type = MarketWatchRow
    kind = "market_watches"
    payload_model = Watch
