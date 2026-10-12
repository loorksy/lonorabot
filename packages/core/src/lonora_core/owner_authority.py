from .user_error import LonoraError


def require_owner(actual: str | None, expected: str) -> None:
    if actual != expected:
        raise LonoraError("unauthorized", 401)
