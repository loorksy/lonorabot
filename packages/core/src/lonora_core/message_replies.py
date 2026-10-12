from .user_error import LonoraError


def require_same_thread(message_thread: str, reply_thread: str) -> None:
    if message_thread != reply_thread:
        raise LonoraError("reply_thread_mismatch")
