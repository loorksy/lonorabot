from .user_error import LonoraError


def require_exact_symbol(requested: str, supplied: str) -> str:
    if requested != supplied:
        raise LonoraError("broker_symbol_mismatch", 409)
    return supplied
