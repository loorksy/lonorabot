from lonora_contracts.skills import AgentSkill

from .schema import SkillRow
from .transactions import ResourceRepository


class SkillRepository(ResourceRepository):
    """Transactional, owner-scoped persistence for skills."""

    row_type = SkillRow
    kind = "skills"
    payload_model = AgentSkill
