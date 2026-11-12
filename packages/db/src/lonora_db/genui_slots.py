"""The server records a lonora-ui trusted slot may reference (mandate 10.2, docs/genui.md).

A slot names a fixed card kind and a record id; the compiler places it only when that
record exists, belongs to this owner, sits in this conversation and is of that kind. The
clients draw everything inside the slot from the live record, never from the card.
"""

from collections.abc import Iterable

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from .schema import OwnerActionRow, RunRow, TradeApprovalRow


async def slot_records(
    session: AsyncSession, owner_id: str, run_id: str | None, thread_id: str, ids: Iterable[str]
) -> set[tuple[str, str]]:
    """``(card, record id)`` for every named record a slot of this reply may show. The reply's
    conversation is its Run's origin conversation when the Run works in its own thread (a
    broker event, a watch): its reply, approvals and cards land there (``outcome_return``)."""
    wanted = sorted(set(ids))
    run = await session.get(RunRow, run_id) if run_id else None
    origin = run.model_metadata.get("origin_thread_id") if run is not None else None
    thread_id = origin if isinstance(origin, str) and origin else thread_id
    if not wanted or not thread_id:
        return set()
    found: set[tuple[str, str]] = set()
    approvals = await session.scalars(
        select(TradeApprovalRow.id).where(
            TradeApprovalRow.id.in_(wanted),
            TradeApprovalRow.owner_id == owner_id,
            TradeApprovalRow.thread_id == thread_id,
        )
    )
    found |= {("trade_approval", identity) for identity in approvals}
    settles = await session.scalars(
        select(OwnerActionRow.id).where(
            OwnerActionRow.id.in_(wanted),
            OwnerActionRow.owner_id == owner_id,
            OwnerActionRow.thread_id == thread_id,
            OwnerActionRow.kind == "resolve_operation",
        )
    )
    found |= {("settle", identity) for identity in settles}
    secrets = await session.scalars(
        select(OwnerActionRow.id).where(
            OwnerActionRow.id.in_(wanted),
            OwnerActionRow.owner_id == owner_id,
            OwnerActionRow.thread_id == thread_id,
            OwnerActionRow.kind == "secret",
        )
    )
    found |= {("secret", identity) for identity in secrets}
    return found
