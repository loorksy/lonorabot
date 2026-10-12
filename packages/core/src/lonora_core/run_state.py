# Modified Python port; source attribution in THIRD_PARTY_NOTICES.md.
from lonora_contracts.runs import RunStatus

from .user_error import LonoraError

ACTIVE = {"queued", "leased", "running", "waiting_input", "waiting_takeover"}
TERMINAL = {"completed", "failed", "cancelled"}
ALLOWED: dict[str, set[str]] = {
    "queued": {"leased", "cancelled"},
    "leased": {"running", "queued", "cancelled"},
    "running": {"waiting_input", "waiting_takeover", "completed", "failed", "cancelled", "leased"},
    "waiting_input": {"queued", "leased", "cancelled"},
    "waiting_takeover": {"queued", "leased", "cancelled"},
    "completed": set(),
    "failed": {"queued"},
    "cancelled": set(),
}


def assert_transition(current: str, target: RunStatus) -> None:
    if target not in ALLOWED.get(current, set()):
        raise LonoraError("illegal_run_transition", 409)


def is_conversational(trigger: str) -> bool:
    return trigger not in {"routine", "webhook", "created", "tickets", "watch"}


def next_fence(fence: int) -> int:
    return fence + 1
