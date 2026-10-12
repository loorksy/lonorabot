from lonora_core.user_error import LonoraError


def continuation_state(status: str) -> str:
    if status not in {"waiting_input", "waiting_takeover", "failed"}:
        raise LonoraError("run_cannot_resume", 409)
    return "queued"
