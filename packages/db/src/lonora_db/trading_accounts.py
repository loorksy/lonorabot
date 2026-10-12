from .schema import TradingAccountRow
from .transactions import ResourceRepository


class TradingAccountRepository(ResourceRepository):
    """Transactional, owner-scoped persistence for trading accounts."""

    row_type = TradingAccountRow
    kind = "trading_accounts"
