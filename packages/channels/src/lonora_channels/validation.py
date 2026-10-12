from lonora_core.user_error import LonoraError


def require_destination(destination: str, allowed: set[str]) -> None:
    if destination not in allowed:
        raise LonoraError("channel_sender_forbidden", 403)
