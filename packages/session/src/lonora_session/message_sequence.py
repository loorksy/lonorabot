from lonora_core.user_error import LonoraError


def next_sequence(current: int) -> tuple[int, int]:
    if current < 1:
        raise LonoraError("invalid_message_sequence")
    return current, current + 1
