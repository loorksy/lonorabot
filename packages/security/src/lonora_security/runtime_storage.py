from pathlib import Path

from lonora_core.user_error import LonoraError


def confined_path(root: Path, key: str) -> Path:
    base = root.resolve()
    candidate = (base / key).resolve()
    if not candidate.is_relative_to(base) or candidate == base:
        raise LonoraError("storage_path_forbidden", 403)
    return candidate
