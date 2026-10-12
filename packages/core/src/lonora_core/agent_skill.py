import re

from .user_error import LonoraError


def validate_skill_name(name: str) -> str:
    if not re.fullmatch(r"[a-z0-9][a-z0-9_-]{0,79}", name):
        raise LonoraError("invalid_skill_name")
    return name
