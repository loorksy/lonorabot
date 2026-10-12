from lonora_contracts.broker import BrokerConnection

from .schema import BrokerSessionRow
from .transactions import ResourceRepository


class BrokerSessionRepository(ResourceRepository):
    """Transactional, owner-scoped persistence for broker sessions."""

    row_type = BrokerSessionRow
    kind = "broker_sessions"
    payload_model = BrokerConnection
