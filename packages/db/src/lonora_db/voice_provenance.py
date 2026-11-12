"""Voice provenance travels with the run that re-asks a voice request (mandate 6.10).

A spoken request is provisional (``model_metadata.voice_handoff.finalized is False``) on
the run that answers it, and on no other: it never spreads to the agent's later watches,
routines, wakes, peers or follow-ups. On a signed grant's old path its trades ask
(``lonora_trading.account_authority.provisional_voice``). A run that re-asks that same
request (the error card's retry, «طلب جديد» on an expired approval) carries its
``voice_handoff``, so it stays provisional, and a later spoken correction withdraws its
approvals too: the correction path also selects every run carrying the delegation's id
(:func:`delegation_runs`).
"""

from typing import Any, cast

from sqlalchemy import Select, select
from sqlalchemy.ext.asyncio import AsyncSession

from .schema import RunRow


async def carry_voice_handoff(session: AsyncSession, source: RunRow, target: RunRow) -> None:
    """Copy the source run's own provisional voice provenance onto a run that re-asks it."""
    handoff = source.model_metadata.get("voice_handoff")
    if not isinstance(handoff, dict):
        return
    target.model_metadata = {
        **target.model_metadata,
        "voice_handoff": dict(cast(dict[str, Any], handoff)),
    }


def delegation_runs(delegation_id: str) -> Select[Any]:
    """Every run carrying one voice delegation's provenance (originals, retries, renewals)."""
    return select(RunRow.id).where(
        RunRow.model_metadata["voice_handoff"]["delegation_id"].as_string() == delegation_id
    )
