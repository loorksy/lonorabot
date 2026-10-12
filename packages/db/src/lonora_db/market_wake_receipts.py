from .schema import MarketWakeReceiptRow
from .transactions import ResourceRepository


class MarketWakeReceiptRepository(ResourceRepository):
    """Transactional, owner-scoped persistence for market wake receipts."""

    row_type = MarketWakeReceiptRow
    kind = "market_wake_receipts"
