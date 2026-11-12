"""The card-send taint (docs/genui.md #12, §8.5).

Two different facts, never one key:

* ``ui_submit_origin`` marks the one queued Run a card's send started. Only the queue
  rules (Q, W, L, V, N) and that Run's own data block read it.
* ``ui_tainted`` is the taint. A tainted Run can never spend the signed grant: its
  trades become approval cards. A Run is tainted when it is a submission, or when it
  descends from a tainted Run (``parent_run_id``), or when a tainted Run started it
  (Tasks, tickets), or when it wakes from a durable row a tainted Run created or changed
  (a watch, routine, ticket or Task).

Durable rows keep their taint in the effect-receipt ledger under ``ui_tainted:<kind>:<id>``,
written by the server from the acting Run, never from a model argument, so no later state
rewrite of the row can drop it. ``create_run`` reads every source, so every wake and start
from tainted work is tainted.
"""

from typing import Any, Literal, cast

from lonora_core.user_error import LonoraError
from sqlalchemy.ext.asyncio import AsyncSession

from .schema import EffectReceiptRow, RunRow

TAINT = "ui_tainted"
SUBMIT = "ui_submit_origin"
Kind = Literal["watch", "routine", "ticket", "opportunity"]
# The run metadata keys that name a durable wake source, and its kind.
SOURCES: tuple[tuple[str, Kind], ...] = (
    ("watch_id", "watch"),
    ("routine_id", "routine"),
    ("ticket_id", "ticket"),
    ("task_id", "ticket"),
    ("opportunity_id", "opportunity"),
)


def _mapping(value: Any) -> dict[str, Any] | None:
    return cast(dict[str, Any], value) if isinstance(value, dict) and value else None


def own_taint(run: RunRow) -> dict[str, Any] | None:
    """The taint stored on this Run itself: its own, or the submission's origin."""
    metadata = run.model_metadata or {}
    return _mapping(metadata.get(TAINT)) or _mapping(metadata.get(SUBMIT))


async def _source_taint(
    session: AsyncSession, metadata: dict[str, Any], depth: int = 0
) -> dict[str, Any] | None:
    for key, kind in SOURCES:
        identifier = metadata.get(key)
        if isinstance(identifier, str) and identifier:
            taint = await row_taint(session, kind, identifier)
            if taint is not None:
                return taint
    # A Run that continues an owner's card (``continue_after_card``, an agent's first
    # task) carries the taint of the Run that proposed the card (review round 4).
    card_id = metadata.get("owner_action_id")
    if isinstance(card_id, str) and card_id and depth < 4:
        from .schema import OwnerActionRow

        card = await session.get(OwnerActionRow, card_id)
        proposer = await session.get(RunRow, card.run_id) if card and card.run_id else None
        if proposer is not None:
            return await run_taint(session, proposer, depth + 1)
    return None


async def run_taint(session: AsyncSession, run: RunRow, depth: int = 0) -> dict[str, Any] | None:
    """The taint of ``run`` or of any Run in its ``parent_run_id`` ancestry: stored on the
    Run, or on the durable row it wakes from or works on (a Task Run resumed in place
    follows its Task's taint)."""
    seen: set[str] = set()
    for _ in range(16):
        if run.id in seen:
            raise LonoraError("goal_run_ancestry_invalid", 409)
        seen.add(run.id)
        taint = own_taint(run) or await _source_taint(session, run.model_metadata or {}, depth)
        if taint is not None:
            return taint
        if not run.parent_run_id:
            return None
        parent = await session.get(RunRow, run.parent_run_id)
        if parent is None:
            raise LonoraError("goal_run_ancestry_invalid", 409)
        run = parent
    raise LonoraError("goal_run_ancestry_invalid", 409)


async def is_tainted(session: AsyncSession, run: RunRow) -> bool:
    return await run_taint(session, run) is not None


def _key(kind: Kind, identifier: str) -> str:
    return f"{TAINT}:{kind}:{identifier}"


async def row_taint(session: AsyncSession, kind: Kind, identifier: str) -> dict[str, Any] | None:
    receipt = await session.get(EffectReceiptRow, _key(kind, identifier))
    return _mapping(receipt.result) if receipt is not None else None


async def mark_row(
    session: AsyncSession, kind: Kind, identifier: str, taint: dict[str, Any]
) -> None:
    """Taint a durable row for good; the first taint is kept."""
    if await session.get(EffectReceiptRow, _key(kind, identifier)) is None:
        session.add(EffectReceiptRow(key=_key(kind, identifier), result=dict(taint)))
        await session.flush()


async def taint_row_from(
    session: AsyncSession, run: RunRow | None, kind: Kind, identifier: str
) -> None:
    """Every durable row a tainted Run creates or changes carries the taint."""
    if run is None:
        return
    taint = await run_taint(session, run)
    if taint is not None:
        await mark_row(session, kind, identifier, taint)


async def inherited_taint(
    session: AsyncSession, metadata: dict[str, Any], parent_run_id: str | None
) -> dict[str, Any] | None:
    """The taint a new Run inherits: given by the server, from its parent Run, or from
    the durable row it wakes from or works on."""
    explicit = _mapping(metadata.get(TAINT))
    if explicit is not None:
        return explicit
    if parent_run_id:
        parent = await session.get(RunRow, parent_run_id)
        if parent is not None:
            taint = await run_taint(session, parent)
            if taint is not None:
                return taint
    return await _source_taint(session, metadata)
