from lonora_core.user_error import LonoraError


def error_code(error: BaseException) -> str:
    return error.code if isinstance(error, LonoraError) else "internal_error"
