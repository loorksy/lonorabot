from .schema import VoiceSessionRow
from .transactions import ResourceRepository


class VoiceSessionRepository(ResourceRepository):
    """Transactional, owner-scoped persistence for voice."""

    row_type = VoiceSessionRow
    kind = "voice"
