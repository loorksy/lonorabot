"""Bounds and path rules of a skill package's files (relative POSIX paths, no `.`/`..`)."""

import base64
import hashlib
import json
from pathlib import PurePosixPath

from lonora_core.user_error import LonoraError

MAX_FILES = 128
MAX_FILE_BYTES = 2 * 1024 * 1024
MAX_TOTAL_BYTES = 8 * 1024 * 1024


def package_path(name: str) -> str:
    path = PurePosixPath(name)
    if (
        not name
        or len(name) > 256
        or len(path.parts) > 8
        or path.is_absolute()
        or any(part in {".", ".."} for part in name.split("/"))
        or "\\" in name
        or "\x00" in name
        or str(path) != name
    ):
        raise LonoraError("workspace_path_unsafe", 422)
    return name


def check_files(files: dict[str, bytes]) -> None:
    """Every path safe, and the count and sizes bounded."""
    if len(files) > MAX_FILES or sum(map(len, files.values())) > MAX_TOTAL_BYTES:
        raise LonoraError("workspace_snapshot_too_large", 422)
    for name, body in files.items():
        package_path(name)
        if len(body) > MAX_FILE_BYTES:
            raise LonoraError("workspace_file_too_large", 422)


def files_digest(files: dict[str, bytes]) -> str:
    """The SHA-256 of the files' canonical JSON encoding (sorted paths, base64 bodies): the
    digest recorded as a workspace package's source since packages were first made."""
    canonical = json.dumps(
        {name: base64.b64encode(body).decode("ascii") for name, body in sorted(files.items())}
    ).encode()
    return hashlib.sha256(canonical).hexdigest()
