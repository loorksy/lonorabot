from lonora_core.user_error import LonoraError


def validate_binding(agent_id: str, thread_agent_id: str | None) -> None:
    if agent_id != thread_agent_id:
        raise LonoraError("routine_binding_mismatch", 409)
