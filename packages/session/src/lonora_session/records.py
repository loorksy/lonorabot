from dataclasses import dataclass


@dataclass(frozen=True)
class SessionHandle:
    owner_id: str
    agent_id: str
    thread_id: str
    run_id: str | None = None
