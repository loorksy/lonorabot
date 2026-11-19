"""Profile taint: whether Lonora may record an owner observation in this run (8.2, 6.10).

A run is profile-tainted when someone other than Lonora or the owner started it (its
trigger is not in OBSERVATION_TRIGGERS: a peer, subagent, follow-up, task or webhook
run), when it read content others wrote, or when a marked routine, watch or opportunity
woke it. Such a run may not write Lonora's observations of the owner to USER.md, and a
routine, watch or opportunity it creates, enables or changes carries the mark (an
effect receipt ``profile-taint:<kind>:<id>``), so the runs that row wakes are tainted
too, down any chain.

The mark is read ONLY by the owner-profile observation check in ``memory.py``. It never
taints the woken run otherwise: trading, tool exposure, other wakes and every other path
see it as untainted (6.10: taint does not spread to later watches, routines or wakes).
"""

from typing import Literal

from lonora_db.owner_words import owner_typed_message
from lonora_db.schema import EffectReceiptRow, RunRow
from sqlalchemy.ext.asyncio import AsyncSession

from .provenance import OWNER_TRIGGERS, external_content_seen

# Runs Lonora starts itself or the owner starts: what it observes there is its own (8.2).
# A peer, subagent, follow-up, task, webhook or other wake carries someone else's words.
OBSERVATION_TRIGGERS = OWNER_TRIGGERS | {"routine", "watch", "broker_event", "owner_card"}
Kind = Literal["routine", "watch", "opportunity"]
# The run metadata key that names the durable row a wake comes from.
SOURCES: tuple[tuple[str, Kind], ...] = (
    ("routine_id", "routine"),
    ("watch_id", "watch"),
    ("opportunity_id", "opportunity"),
)


def _key(kind: Kind, identifier: str) -> str:
    return f"profile-taint:{kind}:{identifier}"


async def run_read_others(session: AsyncSession, run: RunRow) -> bool:
    """Whether this run has read content others wrote, counted from the owner's typed
    message it answers, or from its input for any other run."""
    typed = await owner_typed_message(session, run) if run.trigger in OWNER_TRIGGERS else None
    return await external_content_seen(session, run, int(typed.seq) if typed else run.input_seq)


async def profile_tainted(session: AsyncSession, run: RunRow) -> bool:
    """Whether this run may not record Lonora's observations of the owner."""
    return (
        run.trigger not in OBSERVATION_TRIGGERS
        or await run_read_others(session, run)
        or await woken_by_marked_row(session, run)
    )


async def mark_from(session: AsyncSession, run: RunRow, kind: Kind, identifier: str) -> None:
    """A row a profile-tainted run creates or changes keeps the mark for good."""
    key = _key(kind, identifier)
    if await profile_tainted(session, run) and await session.get(EffectReceiptRow, key) is None:
        session.add(EffectReceiptRow(key=key, result={"run_id": run.id}))
        await session.flush()


async def woken_by_marked_row(session: AsyncSession, run: RunRow) -> bool:
    """Whether this run wakes from a routine, watch or opportunity carrying the mark."""
    metadata = run.model_metadata or {}
    for name, kind in SOURCES:
        identifier = metadata.get(name)
        if isinstance(identifier, str) and identifier:
            if await session.get(EffectReceiptRow, _key(kind, identifier)) is not None:
                return True
    return False
