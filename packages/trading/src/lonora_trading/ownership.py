"""Who owns a ticket, the ticket a request names, and the broker snapshot it is read from.

Ownership is derived from the journal (mandate 3.3.4): a ticket belongs to the agent
whose journaled entry opened or placed it (``ticket_agent``), and to Lonora once that
agent is deleted (``current_holder``, 3.1.2); a ticket no entry matches is the owner's
own. The door, the trade tools, the agent picture (``picture.ticket_openers``) and the
delete's transfer all read this one rule.
"""

from lonora_adapter_kit.broker import BrokerStateReader
from lonora_contracts.account import Order, Position
from lonora_contracts.domain import utcnow
from lonora_contracts.execution_quality import ExecutionSnapshot
from lonora_contracts.trading import TradeRequest
from lonora_core.user_error import LonoraError
from lonora_db.lead import personal_agent_id
from lonora_db.schema import AgentRow, TradingJournalRow
from lonora_session.idempotency import broker_operation_tag
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from .exposure import ENTRY_ACTIONS
from .manual_activity import journal_agent


async def lonora_opened(
    session: AsyncSession, owner_id: str, request: TradeRequest, target: Position | Order
) -> bool:
    """Whether the journal attributes this ticket to an agent's entry (not the owner's own)."""
    return await ticket_agent(session, owner_id, request, target) is not None


async def ticket_agent(
    session: AsyncSession, owner_id: str, request: TradeRequest, target: Position | Order
) -> str | None:
    """The agent whose journaled entry opened or placed this ticket; None for the owner's own.
    A deleted agent's ticket is Lonora's (mandate 3.1.2).

    Attribute by the existing journal and broker identity, never ticket format, over every
    confirmed entry on the ticket's account and symbol. The entry whose operation id (or
    its ``broker_operation_tag``) the broker reports on the ticket opened or placed it; a
    filled pending order's position carries its order's tag. Only when none matches does
    the ticket id decide, and then the oldest entry whose order has that ticket: a position
    opened from flat, or filled from a pending order, carries that order's ticket, and a
    later order that netted into it has its own, so it never takes the position, not even
    from the owner (3.3.4). Only an entry an
    Agent's leased Run sent counts (``journal_agent``, the same rule the broker wakes use):
    the owner's own order from Lonora's Trading page is journaled too, with no agent, and
    stays the owner's own position. A ticket no entry matches is the owner's.
    """
    entry_filter = (
        TradingJournalRow.owner_id == owner_id,
        TradingJournalRow.account_id == request.account_id,
        TradingJournalRow.status == "confirmed",
        TradingJournalRow.request["symbol"].as_string() == request.symbol,
        TradingJournalRow.request["action"].as_string().in_(sorted(ENTRY_ACTIONS)),
    )
    if target.operation_id:
        # A raw operation id (our own, as the simulation reports it) is the primary key:
        # no scan. A broker tag cannot be inverted, so it is matched in the scan below.
        opener = await session.scalar(
            select(TradingJournalRow).where(
                TradingJournalRow.operation_id == target.operation_id, *entry_filter
            )
        )
        if opener is not None:
            return await current_holder(session, owner_id, journal_agent(opener))
    entries = list(
        await session.scalars(
            select(TradingJournalRow)
            .where(*entry_filter)
            .order_by(
                TradingJournalRow.submitted_at.asc().nulls_last(),
                TradingJournalRow.updated_at.asc(),
            )
        )
    )
    return await current_holder(session, owner_id, entry_holder(entries, target))


def entry_holder(entries: list[TradingJournalRow], target: Position | Order) -> str | None:
    """``ticket_agent``'s match over the entries it is given, oldest first (the caller picks
    their statuses: the door's and the picture's confirmed ones, the brief's SENT_STATUSES;
    this filters nothing): the entry whose operation id or tag the broker reports on the
    ticket, else the oldest entry whose order has the ticket id (never a position id in its
    result: on a netting account that is the position an order added to); None for the
    owner's own. It names the opener even when that agent was deleted: ``current_holder``
    hands such a ticket to Lonora for the door and the picture alike (3.1.2)."""
    for entry in entries:
        if target.operation_id in {entry.operation_id, broker_operation_tag(entry.operation_id)}:
            return journal_agent(entry)
    for entry in entries:
        details = entry.result.get("details", {})
        safe_id = entry.result.get("broker_id") if details.get("simulation") else None
        if target.id in {details.get("order_id"), safe_id}:
            return journal_agent(entry)
    return None


async def current_holder(session: AsyncSession, owner_id: str, opener: str | None) -> str | None:
    """The opener, or Lonora when the opener was deleted: its tickets transferred to
    Lonora (mandate 3.1.2, derived). None stays the owner's own."""
    if opener is None or await session.get(AgentRow, opener) is not None:
        return opener
    return await personal_agent_id(session, owner_id) or opener


async def authority_snapshot(broker: BrokerStateReader, account_id: str) -> ExecutionSnapshot:
    """The broker facts a grant's terms are checked against before anything is asked."""
    account = await broker.account()
    if account.id != account_id:
        raise LonoraError("broker_account_mismatch", 409)
    return ExecutionSnapshot(
        account=account,
        positions=await broker.positions(),
        orders=await broker.orders(),
        observed_at=utcnow(),
    )


def management_target(
    snapshot: ExecutionSnapshot, request: TradeRequest
) -> Position | Order | None:
    if request.position_id:
        return next((p for p in snapshot.positions if p.id == request.position_id), None)
    if request.order_id:
        return next((o for o in snapshot.orders if o.id == request.order_id), None)
    return None
