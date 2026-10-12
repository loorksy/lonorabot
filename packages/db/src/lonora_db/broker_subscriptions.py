from .schema import BrokerSubscriptionRow
from .transactions import ResourceRepository


class BrokerSubscriptionRepository(ResourceRepository):
    """Transactional, owner-scoped persistence for broker subscriptions."""

    row_type = BrokerSubscriptionRow
    kind = "broker_subscriptions"
