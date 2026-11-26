import re
import sys
from pathlib import Path

from lonora_core.agent_skill import validate_skill_name
from lonora_core.user_error import LonoraError

_EXAMPLE = re.compile(r"\bExample:")
_SAYING = re.compile(r"^#+ *(?:Output|Saying it)\b.*?(?=^#|\Z)", re.M | re.S)
_QUOTED_FIRST_PERSON = re.compile(r"\"[^\"\n]*\b(?:I|me|my|we|our)\b[^\"\n]*\"")


def bundled(text: str) -> str:
    """Bundled guidance states what a good reply carries; it never hands the model a reply
    to copy: no ``Example:`` line, no quoted first-person sentence where it says what to say."""
    if _EXAMPLE.search(text) or any(_QUOTED_FIRST_PERSON.search(s) for s in _SAYING.findall(text)):
        raise LonoraError("bundled_resource_quotes_a_reply", 500)
    return text


def resources_root() -> Path:
    source = Path(__file__).resolve().parents[3] / "resources"
    return source if source.is_dir() else Path(sys.prefix) / "share/lonora"


def load_skill(name: str) -> str:
    path = resources_root() / "skills" / validate_skill_name(name) / "SKILL.md"
    if not path.is_file():
        raise LonoraError("skill_not_found", 404)
    return bundled(path.read_text())


def load_prompt(name: str) -> str:
    path = resources_root() / "prompts" / (validate_skill_name(name) + ".md")
    if not path.is_file():
        raise LonoraError("prompt_resource_missing", 500)
    return bundled(path.read_text())


def load_constitution() -> list[str]:
    """Mandatory runtime laws stay outside selectable skill context budgets."""
    names = (
        "identity",
        "tool-policy",
        "memory-policy",
        "security-policy",
        "collaboration-policy",
        "trading-policy",
    )
    from .system_policy import mandatory_policy
    from .visual_policy import native_visual_policy

    result: list[str] = [mandatory_policy() + "\n\n" + native_visual_policy()]
    for name in names:
        path = resources_root() / "constitution" / (name + ".md")
        if not path.is_file() or not path.read_text().strip():
            raise LonoraError("policy_resource_missing", 500)
        result.append(bundled(path.read_text()))
    return result
