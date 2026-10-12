from pathlib import PurePath

from .user_error import LonoraError

MAX_ATTACHMENT_BYTES = 20 * 1024 * 1024


def safe_filename(name: str) -> str:
    clean = PurePath(name.replace("\\", "/")).name
    if not clean or clean in {".", ".."} or "\x00" in clean:
        raise LonoraError("invalid_filename")
    return clean[:160]


def check_size(size: int) -> None:
    if size > MAX_ATTACHMENT_BYTES:
        raise LonoraError("attachment_too_large", 413)
