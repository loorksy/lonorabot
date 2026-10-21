from typing import Any

from .registry import installed_registry
from .resolver import SkillSelection, SkillSignals, resolve_skills


def select_skill_context(
    installed: list[dict[str, Any]],
    signals: SkillSignals,
    known_tools: set[str],
    budget: int = 16000,
) -> SkillSelection:
    registry, rejected = installed_registry(installed, known_tools)
    return resolve_skills(registry, signals, budget, rejected)
