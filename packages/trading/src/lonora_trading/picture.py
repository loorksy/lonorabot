"""The account picture an agent receives on every wake (mandate 5.4).

Built from the stored reconciliation snapshot of each enabled connection
(``broker_recovery``), never from a broker read, and attributed with the
ownership rule of 3.3.4 (``ticket_agent``'s match). It is presentation for the
model only: nothing in preflight, the stale-target check or the expected-target
capture reads it, so a snapshot seconds old can never decide an order.
"""

from dataclasses import dataclass
from decimal import Decimal

from lonora_contracts.account import Order, Position
from lonora_contracts.broker_activity import BrokerRecoverySnapshot
from lonora_db.broker_sessions import BrokerSessionRepository
from lonora_db.schema import TradingJournalRow
from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from .account_authority import entry_opened
from .exposure import ENTRY_ACTIONS, direction
from .manual_activity import journal_agent

# The same bound as ticket_agent: the newest confirmed entries per symbol.
JOURNAL_ENTRIES_PER_SYMBOL = 1000


@dataclass(frozen=True)
class AccountBook:
    """One enabled connection's last reconciled state with every ticket's owner.

    ``owners`` maps ``("position" | "order", ticket id)`` to the owning agent, or
    None for a ticket that belongs to the owner (3.3.4).
    """

    account_id: str
    snapshot: BrokerRecoverySnapshot | None
    owners: dict[tuple[str, str], str | None]


async def ticket_owners(
    session: AsyncSession,
    owner_id: str,
    account_id: str,
    positions: list[Position],
    orders: list[Order],
) -> dict[tuple[str, str], str | None]:
    """The owner of every ticket, by the journal match ``ticket_agent`` uses."""
    owners: dict[tuple[str, str], str | None] = {}
    tickets = [("position", item) for item in positions] + [("order", item) for item in orders]
    for symbol in sorted({item.symbol for _, item in tickets}):
        entries = list(
            await session.scalars(
                select(TradingJournalRow)
                .where(
                    TradingJournalRow.owner_id == owner_id,
                    TradingJournalRow.account_id == account_id,
                    TradingJournalRow.status == "confirmed",
                    TradingJournalRow.request["symbol"].as_string() == symbol,
                    TradingJournalRow.request["action"].as_string().in_(sorted(ENTRY_ACTIONS)),
                )
                .order_by(TradingJournalRow.updated_at.desc())
                .limit(JOURNAL_ENTRIES_PER_SYMBOL)
            )
        )
        for kind, item in tickets:
            if item.symbol != symbol:
                continue
            field = "position_id" if kind == "position" else "order_id"
            owners[(kind, item.id)] = next(
                (journal_agent(entry) for entry in entries if entry_opened(entry, item, field)),
                None,
            )
    return owners


async def account_books(session: AsyncSession, owner_id: str) -> list[AccountBook]:
    """Every enabled connection of the owner, in a stable order."""
    books: list[AccountBook] = []
    rows = await BrokerSessionRepository().all_connections(session, owner_id)
    for row in sorted(rows, key=lambda item: item.id):
        if not row.payload.get("enabled"):
            continue
        try:
            raw = row.state.get("broker_recovery")
            snapshot = BrokerRecoverySnapshot.model_validate(raw) if raw else None
        except ValidationError:
            snapshot = None
        owners = (
            await ticket_owners(session, owner_id, row.id, snapshot.positions, snapshot.orders)
            if snapshot
            else {}
        )
        books.append(AccountBook(row.id, snapshot, owners))
    return books


def net_volume(positions: list[Position]) -> Decimal:
    """Buy volume minus sell volume, in lots."""
    return sum(
        (item.volume if direction(item.side) == "buy" else -item.volume for item in positions),
        Decimal(0),
    )
