from .schema import FinancialReceiptRow
from .transactions import ResourceRepository


class FinancialReceiptRepository(ResourceRepository):
    """Transactional, owner-scoped persistence for financial receipts."""

    row_type = FinancialReceiptRow
    kind = "financial_receipts"
