from .schema import PeerMessageRow
from .transactions import ResourceRepository


class PeerMessageRepository(ResourceRepository):
    """Transactional, owner-scoped persistence for peer messages."""

    row_type = PeerMessageRow
    kind = "peer_messages"
