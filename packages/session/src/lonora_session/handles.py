from lonora_contracts.ids import validate_id

from .records import SessionHandle


def make_handle(
    owner_id: str, agent_id: str, thread_id: str, run_id: str | None = None
) -> SessionHandle:
    return SessionHandle(
        validate_id(owner_id),
        validate_id(agent_id),
        validate_id(thread_id),
        validate_id(run_id) if run_id else None,
    )
