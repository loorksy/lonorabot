"""Nanobot-compatible name/description frontmatter; server manifests own authority."""

import re
from typing import Any, cast

import yaml
from lonora_core.user_error import LonoraError

FRONTMATTER = re.compile(r"\A---[ \t]*\r?\n(.*?)\r?\n---[ \t]*(?:\r?\n|$)", re.S)


def skill_document(content: str, identity: str, *, required: bool = False) -> tuple[str, str]:
    match = FRONTMATTER.match(content)
    if match is None:
        if required or content.startswith("---"):
            raise LonoraError("skill_frontmatter_invalid", 422)
        return "", content
    if len(match[1]) > 8000:
        raise LonoraError("skill_frontmatter_invalid", 422)
    try:
        metadata = yaml.safe_load(match[1])
    except (yaml.YAMLError, RecursionError):
        raise LonoraError("skill_frontmatter_invalid", 422) from None
    if not isinstance(metadata, dict):
        raise LonoraError("skill_frontmatter_invalid", 422)
    data = cast(dict[str, Any], metadata)
    description = data.get("description")
    body = content[match.end() :].strip()
    if (
        data.get("name") != identity
        or not isinstance(description, str)
        or not 1 <= len(description.strip()) <= 1000
        or not body
    ):
        raise LonoraError("skill_frontmatter_invalid", 422)
    # Metadata such as commands, dependencies or source cannot extend authority.
    return description.strip(), body
