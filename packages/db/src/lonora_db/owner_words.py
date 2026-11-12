"""The owner's own words, and nothing a card composed (docs/genui.md).

Every owner-words check (supervision, agent creation and control, the owner profile and
reach-me, model switches, full delegation, a rejected trade card) reads the owner's typed
message through these helpers. A message stored with ``origin`` ``ui_submit`` (a card's
send, its text written by the server) or ``ui_follow_up`` (a v1 follow-up tap) is card
words: it never stands for the owner, and a Run started by a card submission has no owner
words at all, so those checks fall back to their own card or refusal.
"""

from typing import Any, cast

from sqlalchemy import ColumnElement, and_, exists, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from .schema import MessageRow, RunRow

OWNER = "owner"


def ui_submit_origin(run: RunRow) -> dict[str, Any] | None:
    origin: Any = (run.model_metadata or {}).get("ui_submit_origin")
    return cast(dict[str, Any], origin) if isinstance(origin, dict) else None


# A card send's retry names the send's own Run here (``run_retry.retry_run``). Provenance
# only (mandate 6.10): no queue rule (Q, W, L, V, N, T) reads it.
RETRY_OF_SUBMIT = "ui_submit_retry_of"


def ui_submit_provenance(run: RunRow) -> bool:
    """Whether this Run answers a card's send, for authority and owner words (6.10): the Run
    the send started (``ui_submit_origin``, also the queue rules' key) or a retry of it."""
    retry_of: Any = (run.model_metadata or {}).get(RETRY_OF_SUBMIT)
    return ui_submit_origin(run) is not None or retry_of is not None


TERMINAL = frozenset({"completed", "failed", "cancelled"})


def visible_to_recall() -> ColumnElement[bool]:
    """SQL: not a card submission hidden by rules V and N (its Run started and ended).
    Recall, session_search and history views share it; a hidden one never reaches them."""
    return or_(
        MessageRow.origin != "ui_submit",
        and_(
            MessageRow.ui_submit["started_at"].as_string().is_not(None),
            exists(
                select(RunRow.id).where(
                    RunRow.id == MessageRow.ui_submit["run_id"].as_string(),
                    RunRow.status.in_(list(TERMINAL)),
                )
            ),
        ),
    )


async def submit_hidden(session: AsyncSession, message: MessageRow, run: RunRow | None) -> bool:
    """Whether a card submission is invisible to ``run`` (docs/genui.md §7, rules V and N):
    until its own Run has ended it is visible only to that Run, and a submission whose Run
    ended without ever starting stays invisible to every Run for good."""
    if message.origin != "ui_submit":
        return False
    submit = message.ui_submit or {}
    own = submit.get("run_id")
    if run is not None and own == run.id:
        return False
    if not submit.get("started_at"):
        return True
    status = await session.scalar(select(RunRow.status).where(RunRow.id == own)) if own else None
    return status not in TERMINAL


async def owner_typed_message(session: AsyncSession, run: RunRow) -> MessageRow | None:
    """The latest message the owner typed that this Run answers, or None.

    None for any Run a card submission started and for its retry (its window may include
    later messages, rule W, but lends it no owner words), and when the latest visible
    message in the window is card words rather than the owner's (the fail-safe direction).
    A submission hidden from this Run (rules V and N) is skipped, never read.
    """
    if ui_submit_provenance(run):
        return None
    rows = await session.scalars(
        select(MessageRow)
        .where(
            MessageRow.thread_id == run.thread_id,
            MessageRow.role == "user",
            MessageRow.seq <= run.input_seq,
        )
        .order_by(MessageRow.seq.desc())
        .limit(12)
    )
    for row in rows:
        if await submit_hidden(session, row, run):
            continue
        return row if row.origin == OWNER else None
    return None
