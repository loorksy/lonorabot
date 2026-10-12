from .schema import ModelBackupRow
from .transactions import ResourceRepository


class ModelBackupRepository(ResourceRepository):
    """Transactional, owner-scoped persistence for model backups."""

    row_type = ModelBackupRow
    kind = "model_backups"
