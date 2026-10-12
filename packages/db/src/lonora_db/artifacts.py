from .schema import ArtifactRow
from .transactions import ResourceRepository


class ArtifactRepository(ResourceRepository):
    """Transactional, owner-scoped persistence for artifacts."""

    row_type = ArtifactRow
    kind = "artifacts"
