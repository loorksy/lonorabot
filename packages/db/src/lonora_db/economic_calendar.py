from .schema import EconomicCalendarRow
from .transactions import ResourceRepository


class EconomicCalendarRepository(ResourceRepository):
    """Transactional, owner-scoped persistence for economic calendar."""

    row_type = EconomicCalendarRow
    kind = "economic_calendar"
