from lonora_contracts.groups import GroupCreate

from .schema import GroupRow
from .transactions import ResourceRepository


class GroupRepository(ResourceRepository):
    """Transactional, owner-scoped persistence for groups."""

    row_type = GroupRow
    kind = "groups"
    payload_model = GroupCreate
