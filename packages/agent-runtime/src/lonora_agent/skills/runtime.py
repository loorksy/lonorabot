from typing import Any

from .registry import built_in_skills
from .resolver import enabled_skills


def skill_context(installed: list[dict[str, Any]]) -> str:
    return "\n\n".join(
        f"<skill name='{name}'>\n{content}\n</skill>"
        for name, content in enabled_skills(built_in_skills(), installed).items()
    )
