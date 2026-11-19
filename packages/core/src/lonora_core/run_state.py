# Modified Python port; source attribution in THIRD_PARTY_NOTICES.md.
from collections.abc import Mapping
from typing import Any

from lonora_contracts.runs import RunStatus

from .user_error import LonoraError

ACTIVE = {"queued", "leased", "running", "waiting_input", "waiting_takeover"}
TERMINAL = {"completed", "failed", "cancelled"}
ALLOWED: dict[str, set[str]] = {
    "queued": {"leased", "cancelled"},
    "leased": {"running", "queued", "cancelled"},
    "running": {
        "queued",
        "waiting_input",
        "waiting_takeover",
        "completed",
        "failed",
        "cancelled",
        "leased",
    },
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
    return trigger not in {"routine", "webhook", "created", "tickets", "watch", "workspace_wake"}


# VISION 11.5: a scheduled or background run with nothing new posts nothing. These wakes
# have no one waiting on their reply: the agent's own scheduled and event work.
BACKGROUND_TRIGGERS = frozenset(
    {"routine", "watch", "broker_event", "activation", "tickets", "webhook", "workspace_wake"}
)
# Set by ``create_run`` alone, on a follow-up of background work; a caller never can.
BACKGROUND_KEY = "background"
# Set when the owner's words reach a Run: by admission in its metadata (server-only),
# and in its execution state when they are merged into its transcript.
OWNER_SPOKE = "owner_spoke"


def is_background(trigger: str, metadata: Mapping[str, Any] | None) -> bool:
    """A background run: its reply may be empty, and an empty one posts nothing. A run the
    owner's words were given to answers them: it is not background."""
    data = metadata or {}
    if data.get(OWNER_SPOKE) is True:
        return False
    return trigger in BACKGROUND_TRIGGERS or (
        trigger == "follow_up" and data.get(BACKGROUND_KEY) is True
    )


def may_end_silent(background: bool, state: Mapping[str, Any]) -> bool:
    """Once the owner writes to a background run, the rest of it answers them."""
    return background and state.get(OWNER_SPOKE) is not True


def next_fence(fence: int) -> int:
    return fence + 1
