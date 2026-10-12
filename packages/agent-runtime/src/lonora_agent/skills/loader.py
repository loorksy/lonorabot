import sys
from pathlib import Path

from lonora_core.agent_skill import validate_skill_name
from lonora_core.user_error import LonoraError


def resources_root() -> Path:
    source = Path(__file__).resolve().parents[3] / "resources"
    return source if source.is_dir() else Path(sys.prefix) / "share/lonora"


def load_skill(name: str) -> str:
    path = resources_root() / "skills" / validate_skill_name(name) / "SKILL.md"
    if not path.is_file():
        raise LonoraError("skill_not_found", 404)
    return path.read_text()


def load_prompt(name: str) -> str:
    path = resources_root() / "prompts" / (validate_skill_name(name) + ".md")
    if not path.is_file():
        raise LonoraError("prompt_resource_missing", 500)
    return path.read_text()
