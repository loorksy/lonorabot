from lonora_db.skills import SkillRepository

from . import resource_router

router = resource_router("/skills", SkillRepository())
