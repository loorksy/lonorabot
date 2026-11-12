"""The account picture an agent receives on every wake (mandate 5.4).

Built from the stored reconciliation snapshot of each enabled connection
(``broker_recovery``) and the instrument currencies kept on the connection row,
never from a broker read at build time, and attributed with the ownership rule of
3.3.4 (``ticket_agent``'s match). Only the gateway step ``learn_currencies`` reads
the broker, for instrument metadata. The picture is presentation for the model
only: nothing in preflight, the stale-target check or the expected-target capture
reads it, so a snapshot seconds old can never decide an order.
"""

import asyncio
import re
from dataclasses import dataclass
from decimal import Decimal
from time import monotonic
from typing import Any, cast

from lonora_adapters.brokers.base import BrokerManager
from lonora_contracts.account import Order, Position
from lonora_contracts.broker_activity import BrokerRecoverySnapshot
from lonora_core.user_error import LonoraError
from lonora_db.broker_sessions import (
    BrokerSessionRepository,
    broker_identity_key,
    current_broker_identity,
)
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
# ISO codes (EUR, XAU) and the longer codes of crypto pairs (BTC, USDT); not "US500".
CURRENCY_CODE = re.compile(r"^[A-Z]{3,5}$")
MAX_LEARNED_PER_PASS = 20
# The broker says it lists no such instrument: kept with no currencies, not read again.
INSTRUMENT_ABSENT = frozenset({"broker_instrument_unavailable", "symbol_not_found"})
# Any other failure (rate limit, timeout, a lost connection) is read again after this.
RETRY_SECONDS = 600
PASS_SECONDS = 90
_retry_after: dict[tuple[str, str], float] = {}


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


async def account_books(
    session: AsyncSession, owner_id: str, limit: int
) -> tuple[list[AccountBook], int]:
    """The first ``limit`` enabled connections of the owner in a stable order, and how
    many are enabled; tickets are attributed only on the connections returned."""
    books: list[AccountBook] = []
    rows = await BrokerSessionRepository().all_connections(session, owner_id)
    enabled = sorted((row for row in rows if row.payload.get("enabled")), key=lambda r: r.id)
    for row in enabled[:limit]:
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
    return books, len(enabled)


def instrument_legs(base: str | None, profit: str | None) -> list[str]:
    """Each leg of a pair (two different currency codes), else the quote currency."""
    legs = [code.strip().upper() for code in (base, profit) if code and code.strip()]
    if len(legs) == 2 and legs[0] != legs[1] and all(CURRENCY_CODE.match(c) for c in legs):
        return legs
    return [profit.strip().upper()] if profit and profit.strip() else []


def account_identity(row: BrokerSessionRow) -> list[str]:
    """The broker-observed account behind the connection, else its configuration version."""
    identity = current_broker_identity(row)
    key = broker_identity_key(identity) if identity else None
    return list(key) if key else ["connection_version", str(row.version)]


def symbol_currencies(row: BrokerSessionRow) -> dict[str, list[str]]:
    """What the broker reported for each symbol, while the connection's account is the
    one that reported it (another login or server lists other instruments)."""
    stored: Any = row.state.get(CURRENCIES_KEY)
    if not isinstance(stored, dict):
        return {}
    kept = cast(dict[str, Any], stored)
    symbols: Any = kept.get("symbols")
    if kept.get("identity") != account_identity(row) or not isinstance(symbols, dict):
        return {}
    return {
        str(symbol): [str(code) for code in cast(list[Any], legs)]
        for symbol, legs in cast(dict[str, Any], symbols).items()
        if isinstance(legs, list)
    }


async def learn_currencies(db: Database, brokers: BrokerManager, owner_id: str) -> int:
    """Keep the currencies of every held symbol the connection row does not know yet.

    Instrument metadata is static, so each symbol is read from the broker once and kept
    as soon as it is read. A symbol the broker says it does not list is kept with no
    currencies; any other failure is read again after ``RETRY_SECONDS``. One pass stops
    after ``PASS_SECONDS``. Returns how many symbols were learned with currencies.
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
            missing = [
                symbol
                for symbol in sorted(held - set(known))
                if _retry_after.get((row.id, symbol), 0.0) <= monotonic()
            ][:MAX_LEARNED_PER_PASS]
            if missing:
                wanted[row.id] = missing
    learned = 0
    deadline = monotonic() + PASS_SECONDS
    for account_id, symbols in wanted.items():
        try:
            broker = await brokers.get(owner_id, account_id)
        except Exception:
            continue  # The connection is read again on the next pass.
        for symbol in symbols:
            if monotonic() >= deadline:
                return learned
            try:
                async with asyncio.timeout(20):
                    instrument = await broker.instrument(symbol)
                legs = instrument_legs(instrument.base_currency, instrument.profit_currency)
            except LonoraError as error:
                if error.code not in INSTRUMENT_ABSENT:
                    _retry_after[(account_id, symbol)] = monotonic() + RETRY_SECONDS
                    continue
                legs = []
            except Exception:
                _retry_after[(account_id, symbol)] = monotonic() + RETRY_SECONDS
                continue
            _retry_after.pop((account_id, symbol), None)
            if await _keep(db, owner_id, account_id, symbol, legs):
                learned += bool(legs)
    return learned


async def _keep(db: Database, owner_id: str, account_id: str, symbol: str, legs: list[str]) -> bool:
    async with db.sessions() as session, session.begin():
        row = await session.get(
            BrokerSessionRow, account_id, with_for_update=True, populate_existing=True
        )
        if row is None or row.owner_id != owner_id:
            return False
        row.state = {
            **row.state,
            CURRENCIES_KEY: {
                "identity": account_identity(row),
                "symbols": {**symbol_currencies(row), symbol: legs},
            },
        }
        return True


def net_volume(positions: list[Position]) -> Decimal:
    """Buy volume minus sell volume, in lots; a side that is neither counts in neither."""
    sign = {"buy": 1, "sell": -1}
    return sum((item.volume * sign.get(direction(item.side), 0) for item in positions), Decimal(0))
