from lonora_core.user_error import LonoraError


def require_collaboration(
    source_owner: str, target_owner: str, depth: int, maximum: int = 3
) -> None:
    if source_owner != target_owner:
        raise LonoraError("peer_scope_forbidden", 403)
    if depth >= maximum:
        raise LonoraError("delegation_depth_exceeded", 409)
