"""Voice provenance travels with every run that re-asks a voice request.

A spoken request is provisional (``model_metadata.voice_handoff.finalized is False``): it and
its descendants cannot spend standing authority, so a trade needs its own approval card
(``lonora_trading.account_authority.provisional_voice``). A run that re-asks such a request
outside its ancestry (the error card's retry, «طلب جديد» on an expired approval) carries the
same ``voice_handoff``, so it stays provisional, and a later spoken correction withdraws its
approvals too: the correction path also selects every run carrying the delegation's id
(:func:`delegation_runs`).
"""

from typing import Any, cast

from lonora_core.user_error import LonoraError
from sqlalchemy import Select, select
from sqlalchemy.ext.asyncio import AsyncSession

from .schema import RunRow


async def voice_handoff(session: AsyncSession, run: RunRow) -> dict[str, Any] | None:
    """The nearest ``voice_handoff`` of the run or its ancestors (the provisional source)."""
    seen: set[str] = set()
    current: RunRow | None = run
    for _ in range(16):
        if current is None:
            raise LonoraError("goal_run_ancestry_invalid", 409)
        if current.id in seen:
            raise LonoraError("goal_run_ancestry_invalid", 409)
        seen.add(current.id)
        handoff = current.model_metadata.get("voice_handoff")
        if isinstance(handoff, dict):
            return dict(cast(dict[str, Any], handoff))
        if not current.parent_run_id:
            return None
        current = await session.get(RunRow, current.parent_run_id)
    raise LonoraError("goal_run_ancestry_invalid", 409)


async def carry_voice_handoff(session: AsyncSession, source: RunRow, target: RunRow) -> None:
    """Copy the source's provisional voice provenance onto a run that re-asks it."""
    handoff = await voice_handoff(session, source)
    if handoff is None:
        return
    target.model_metadata = {**target.model_metadata, "voice_handoff": handoff}


def delegation_runs(delegation_id: str) -> Select[Any]:
    """Every run carrying one voice delegation's provenance (originals, retries, renewals)."""
    return select(RunRow.id).where(
        RunRow.model_metadata["voice_handoff"]["delegation_id"].as_string() == delegation_id
    )
