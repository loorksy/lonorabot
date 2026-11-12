"""Settle an uncertain operation the way the owner does: through its Settle card (6.8).

The card is raised by the gateway's own projection of the operation's
``trading.operation_updated`` event (``lonora_gateway.owner_cards``), and the owner's
answer is the authenticated ``POST /owner-actions/{id}/decision``. A journal row seeded
without its event gets that event first, as the door would have emitted it.
"""

from typing import Any

from lonora_db.schema import OwnerActionRow, TradingJournalRow
from lonora_gateway.attention import attention_tick
from lonora_trading.operation_events import operation_event
from sqlalchemy import select


async def pending_card(db: Any, operation_id: str) -> str | None:
    async with db.sessions() as session:
        return await session.scalar(
            select(OwnerActionRow.id).where(
                OwnerActionRow.kind == "settle_operation",
                OwnerActionRow.subject == "operation:" + operation_id,
                OwnerActionRow.status == "pending",
            )
        )


async def settle_card(fixture: Any, operation_id: str) -> str:
    """The pending Settle card of ``operation_id``, raised by the gateway if needed."""
    db = fixture.runtime.db
    brokers = fixture.runtime.services(fixture.owner).brokers
    for attempt in range(2):
        for _ in range(4):
            await attention_tick(db, brokers, fixture.owner)
        card = await pending_card(db, operation_id)
        if card is not None:
            return card
        if attempt == 0:
            async with db.sessions() as session, session.begin():
                row = await session.get(TradingJournalRow, operation_id)
                assert row is not None and row.status == "ambiguous", operation_id
                await operation_event(session, row)
    raise AssertionError("no Settle card was raised for " + operation_id)


async def settle_by_card(fixture: Any, operation_id: str, outcome: str) -> dict[str, Any]:
    """The owner's answer on the operation's Settle card; returns the card."""
    card = await settle_card(fixture, operation_id)
    return await fixture.request(
        "POST", f"/owner-actions/{card}/decision", {"decision": "confirm", "outcome": outcome}
    )
