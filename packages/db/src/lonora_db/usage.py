from .schema import UsageRow
from .transactions import ResourceRepository


class UsageRepository(ResourceRepository):
    """Transactional, owner-scoped persistence for usage."""

    row_type = UsageRow
    kind = "usage"
