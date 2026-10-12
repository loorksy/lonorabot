from .user_error import LonoraError


def reaction_key(message_id: str, owner_id: str, emoji: str) -> str:
    if not 1 <= len(emoji) <= 16:
        raise LonoraError("invalid_reaction")
    return f"{message_id}:{owner_id}:{emoji}"
