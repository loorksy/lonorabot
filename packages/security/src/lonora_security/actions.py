from lonora_core.user_error import LonoraError


def require_action_scope(tool: str, allowed: set[str]) -> None:
    if tool not in allowed:
        raise LonoraError("tool_not_allowed", 403)
