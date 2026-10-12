from .user_error import LonoraError


def require_capability(capabilities: list[str], requested: str, verified: bool) -> None:
    if not verified:
        raise LonoraError("model_capabilities_unverified", 409)
    if requested not in capabilities:
        raise LonoraError("model_capability_unsupported", 409)
