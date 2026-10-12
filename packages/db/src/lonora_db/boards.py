from lonora_contracts.domain import Board

from .schema import BoardRow
from .transactions import ResourceRepository


class BoardRepository(ResourceRepository):
    """Transactional, owner-scoped persistence for boards."""

    row_type = BoardRow
    kind = "boards"
    payload_model = Board
