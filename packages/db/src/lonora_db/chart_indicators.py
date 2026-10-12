from .schema import ChartIndicatorRow
from .transactions import ResourceRepository


class ChartIndicatorRepository(ResourceRepository):
    """Transactional, owner-scoped persistence for chart indicators."""

    row_type = ChartIndicatorRow
    kind = "chart_indicators"
