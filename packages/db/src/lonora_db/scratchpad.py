from lonora_contracts.domain import ScratchpadItem

from .schema import ScratchpadRow
from .transactions import ResourceRepository


class ScratchpadRepository(ResourceRepository):
    """Transactional, owner-scoped persistence for scratchpad."""

    row_type = ScratchpadRow
    kind = "scratchpad"
    payload_model = ScratchpadItem
