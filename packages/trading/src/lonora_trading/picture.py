"""The account picture an agent receives on every wake (mandate 5.4).

Built from the stored reconciliation snapshot of each enabled connection
(``broker_recovery``), never from a broker read, and attributed with the
ownership rule of 3.3.4 (``ticket_agent``'s match). It is presentation for the
model only: nothing in preflight, the stale-target check or the expected-target
capture reads it, so a snapshot seconds old can never decide an order.
"""

import asyncio
import re
from dataclasses import dataclass
from decimal import Decimal
from typing import Any, cast

from lonora_adapters.brokers.base import BrokerManager
from lonora_contracts.account import Order, Position
from lonora_contracts.broker_activity import BrokerRecoverySnapshot
from lonora_db.broker_sessions import BrokerSessionRepository
from lonora_db.client import Database
from lonora_db.schema import BrokerSessionRow, TradingJournalRow
from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from .account_authority import entry_opened
from .exposure import ENTRY_ACTIONS, direction
from .manual_activity import journal_agent

# The same bound as ticket_agent: the newest confirmed entries per symbol.
JOURNAL_ENTRIES_PER_SYMBOL = 1000
# Instrument currencies the broker reported, per symbol, kept on the connection row.
CURRENCIES_KEY = "instrument_currencies"
CURRENCY_CODE = re.compile(r"^[A-Z]{3}$")
MAX_LEARNED_PER_PASS = 20


@dataclass(frozen=True)
class AccountBook:
    """One enabled connection's last reconciled state with every ticket's owner.

    ``owners`` maps ``("position" | "order", ticket id)`` to the owning agent, or
    None for a ticket that belongs to the owner (3.3.4).
    """

    account_id: str
    snapshot: BrokerRecoverySnapshot | None
    owners: dict[tuple[str, str], str | None]
    # The currencies of each held symbol: both legs of a pair, else the quote
    # currency; absent while the broker has not reported the instrument yet.
    currencies: dict[str, list[str]]


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
        books.append(AccountBook(row.id, snapshot, owners, symbol_currencies(row)))
    return books


def instrument_legs(base: str | None, profit: str | None) -> list[str]:
    """Each leg of a pair (two different currency codes), else the quote currency."""
    legs = [code.strip().upper() for code in (base, profit) if code and code.strip()]
    if len(legs) == 2 and legs[0] != legs[1] and all(CURRENCY_CODE.match(c) for c in legs):
        return legs
    return [profit.strip().upper()] if profit and profit.strip() else []


def symbol_currencies(row: BrokerSessionRow) -> dict[str, list[str]]:
    stored: Any = row.state.get(CURRENCIES_KEY)
    if not isinstance(stored, dict):
        return {}
    return {
        str(symbol): [str(code) for code in cast(list[Any], legs)]
        for symbol, legs in cast(dict[str, Any], stored).items()
        if isinstance(legs, list)
    }


async def learn_currencies(db: Database, brokers: BrokerManager, owner_id: str) -> int:
    """Keep the currencies of every held symbol the connection row does not know yet.

    Instrument metadata is static, so each symbol is read from the broker once; a read
    that fails is tried again on the next pass. Returns how many symbols were learned.
    """
    async with db.sessions() as session:
        rows = await BrokerSessionRepository().all_connections(session, owner_id)
        wanted: dict[str, list[str]] = {}
        for row in rows:
            raw = row.state.get("broker_recovery")
            if not row.payload.get("enabled") or not raw:
                continue
            try:
                snapshot = BrokerRecoverySnapshot.model_validate(raw)
            except ValidationError:
                continue
            known = symbol_currencies(row)
            held = {item.symbol for item in [*snapshot.positions, *snapshot.orders]}
            missing = sorted(held - set(known))[:MAX_LEARNED_PER_PASS]
            if missing:
                wanted[row.id] = missing
    learned = 0
    for account_id, symbols in wanted.items():
        found: dict[str, list[str]] = {}
        try:
            broker = await brokers.get(owner_id, account_id)
            for symbol in symbols:
                async with asyncio.timeout(20):
                    instrument = await broker.instrument(symbol)
                found[symbol] = instrument_legs(
                    instrument.base_currency, instrument.profit_currency
                )
        except Exception:
            pass  # Kept what was read; the rest is read again on the next pass.
        if not found:
            continue
        async with db.sessions() as session, session.begin():
            row = await session.get(
                BrokerSessionRow, account_id, with_for_update=True, populate_existing=True
            )
            if row is None or row.owner_id != owner_id:
                continue
            row.state = {**row.state, CURRENCIES_KEY: {**symbol_currencies(row), **found}}
        learned += len(found)
    return learned


def net_volume(positions: list[Position]) -> Decimal:
    """Buy volume minus sell volume, in lots."""
    return sum(
        (item.volume if direction(item.side) == "buy" else -item.volume for item in positions),
        Decimal(0),
    )
