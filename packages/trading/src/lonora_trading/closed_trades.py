"""The closed-trade ledger: one row per position whose volume reached zero at the broker.

Mandate 5.5.1: "A trade is closed when its position's volume reaches zero at the
broker, whatever the cause." The ledger reads broker deal history from a stored cursor,
not the reconciliation snapshot diff (which stays for activity events), so a close is
recorded after a restart and for a trade opened and closed between two reads.

A position is closed when its deals include an exit (``DEAL_ENTRY_OUT`` or
``DEAL_ENTRY_OUT_BY``) and a fresh broker position read, taken after the history read,
no longer lists it. Its realized P&L is the profit, commission and swap of its broker
deals (``realized.deal_pnl``), in the account currency. Its owner follows 3.3.4: the
agent whose journaled order opened it, else the owner. A ticket with no agent-attributed
journaled opening order, such as one opened in the broker terminal or by code deployed
outside the door, is the owner's and is never attributed to an agent.
"""

import asyncio
import logging
from datetime import datetime, timedelta
from decimal import Decimal
from typing import Any
from uuid import NAMESPACE_URL, uuid5

from lonora_adapters.brokers.base import BrokerManager
from lonora_contracts.domain import utcnow
from lonora_core.user_error import LonoraError
from lonora_db.client import Database
from lonora_db.schema import (
    BrokerDealRow,
    BrokerSessionRow,
    ClosedTradeCursorRow,
    ClosedTradeRow,
    TradingJournalRow,
)
from lonora_session.idempotency import broker_operation_tag
from sqlalchemy import delete, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from .exposure import ENTRY_ACTIONS
from .manual_activity import journal_agent
from .realized import TRADE_DEALS, deal_pnl

log = logging.getLogger("lonora.trading.closed_trades")

PAGE = 1000
PAGES = 20
# A connection's first read starts this far before the connection was made, so the
# opening deals of positions already open are in the ledger's copy of history.
FIRST_LOOKBACK = timedelta(days=30)
# Every complete read re-reads this much before the cursor: broker history can list a
# deal after a later one has been read.
OVERLAP = timedelta(minutes=15)
EXITS = frozenset({"OUT", "OUT_BY"})


def _kind(deal: dict[str, Any]) -> str:
    return str(deal.get("type") or "").strip().upper().removeprefix("DEAL_TYPE_")


def _entry(deal: dict[str, Any]) -> str:
    return str(deal.get("entryType") or "").strip().upper().removeprefix("DEAL_ENTRY_")


def _time(deal: dict[str, Any]) -> datetime:
    return datetime.fromisoformat(str(deal["time"]).replace("Z", "+00:00"))


def trade_deal(deal: dict[str, Any]) -> bool:
    """A buy or sell deal of a position: the deals a closed trade is made of."""
    return (
        _kind(deal) in TRADE_DEALS
        and bool(_entry(deal))
        and bool(deal.get("positionId"))
        and bool(deal.get("id"))
        and deal.get("time") is not None
    )


def realized(deals: list[dict[str, Any]]) -> Decimal | None:
    """Profit + commission + swap of the deals; None when an exit has no broker profit."""
    if any(_entry(deal) in EXITS and deal.get("profit") in (None, "") for deal in deals):
        return None
    try:
        return sum((deal_pnl(deal) for deal in deals), Decimal(0))
    except LonoraError:
        return None


async def opening_entry(
    session: AsyncSession,
    owner_id: str,
    account_id: str,
    symbol: str,
    position_id: str,
    opening: dict[str, Any] | None,
) -> TradingJournalRow | None:
    """The confirmed journaled order that opened or placed this position, if Lonora sent it.

    A broker position id is the ticket of the order that opened it, so the opening
    order is matched by its broker order id, by the operation tag the door sends as the
    client id, or (simulation) by the broker id. A later order that added to a netting
    position has another order id and never matches.
    """
    orders = {position_id}
    tags: set[str] = set()
    if opening is not None:
        if opening.get("orderId"):
            orders.add(str(opening["orderId"]))
        if opening.get("clientId"):
            tags.add(str(opening["clientId"]))
    entries = await session.scalars(
        select(TradingJournalRow)
        .where(
            TradingJournalRow.owner_id == owner_id,
            TradingJournalRow.account_id == account_id,
            TradingJournalRow.status == "confirmed",
            TradingJournalRow.request["symbol"].as_string() == symbol,
            TradingJournalRow.request["action"].as_string().in_(sorted(ENTRY_ACTIONS)),
        )
        .order_by(TradingJournalRow.updated_at.desc())
        .limit(PAGE)
    )
    for entry in entries:
        details = entry.result.get("details", {})
        if (
            str(details.get("order_id") or "") in orders
            or broker_operation_tag(entry.operation_id) in tags
            or (details.get("simulation") and str(entry.result.get("broker_id")) == position_id)
        ):
            return entry
    return None


async def close_position(
    session: AsyncSession,
    owner_id: str,
    account_id: str,
    position_id: str,
    deals: list[dict[str, Any]],
    currency: str,
) -> bool:
    """Write the ledger row of a closed position once; True when this call wrote it."""
    deals = sorted(deals, key=lambda deal: (_time(deal), str(deal["id"])))
    exits = [deal for deal in deals if _entry(deal) in EXITS]
    entries = [deal for deal in deals if _entry(deal) == "IN"]
    opening = entries[0] if entries else None
    symbol = str((opening or exits[0]).get("symbol") or "")
    journal = await opening_entry(session, owner_id, account_id, symbol, position_id, opening)
    if opening is not None:
        side = "buy" if _kind(opening) == "BUY" else "sell"
    else:
        side = "sell" if _kind(exits[0]) == "BUY" else "buy"
    written = await session.execute(
        insert(ClosedTradeRow)
        .values(
            id=str(
                uuid5(NAMESPACE_URL, f"lonora:closed-trade:{owner_id}:{account_id}:{position_id}")
            ),
            owner_id=owner_id,
            account_id=account_id,
            position_id=position_id,
            symbol=symbol,
            side=side,
            volume=sum((Decimal(str(deal.get("volume") or 0)) for deal in exits), Decimal(0)),
            agent_id=journal_agent(journal) if journal is not None else None,
            opening_operation_id=journal.operation_id if journal is not None else None,
            currency=currency,
            realized_pnl=realized(deals),
            opened_at=_time(opening) if opening is not None else None,
            closed_at=max(_time(deal) for deal in exits),
            deals=deals,
            created_at=utcnow(),
        )
        .on_conflict_do_nothing(constraint="ln_closed_trade_position")
        .returning(ClosedTradeRow.id)
    )
    return written.scalar() is not None


async def record_closed_trades(
    db: Database, brokers: BrokerManager, owner_id: str, account_id: str
) -> int:
    """Read this account's deals since the cursor and record every trade that closed."""
    async with db.sessions() as session:
        cursor = await session.get(ClosedTradeCursorRow, (owner_id, account_id))
        if cursor is not None:
            start = cursor.read_to - OVERLAP if cursor.complete else cursor.read_to
        else:
            connection = await session.get(BrokerSessionRow, account_id)
            if connection is None or connection.owner_id != owner_id:
                return 0
            start = connection.created_at - FIRST_LOOKBACK
    end = utcnow()
    async with asyncio.timeout(30):
        broker = await brokers.get(owner_id, account_id)
        account = await broker.account()
        if account.id != account_id:
            raise LonoraError("broker_account_mismatch", 409)
        history: list[dict[str, Any]] = []
        complete = False
        for _ in range(PAGES):
            page = await broker.history(start, end, PAGE)
            history.extend(page)
            if len(page) < PAGE:
                complete = True
                break
            # A full page continues from its last deal; deals read twice are one row.
            last = max((_time(deal) for deal in page if deal.get("time")), default=start)
            if last <= start:
                break
            start = last
        # Read after the history: a position a listed exit closed is gone from it.
        positions = await broker.positions()
    if len(positions) > PAGE:
        raise LonoraError("broker_snapshot_limit", 409)
    open_ids = {position.id for position in positions}
    deals = [deal for deal in history if trade_deal(deal)]
    recorded = 0
    async with db.sessions() as session, session.begin():
        closed = set(
            await session.scalars(
                select(ClosedTradeRow.position_id).where(
                    ClosedTradeRow.owner_id == owner_id,
                    ClosedTradeRow.account_id == account_id,
                    ClosedTradeRow.position_id.in_({str(deal["positionId"]) for deal in deals}),
                )
            )
        )
        for deal in deals:
            position_id = str(deal["positionId"])
            if position_id in closed:
                continue  # A deal re-read after its trade was recorded.
            await session.execute(
                insert(BrokerDealRow)
                .values(
                    owner_id=owner_id,
                    account_id=account_id,
                    deal_id=str(deal["id"]),
                    position_id=position_id,
                    time=_time(deal),
                    payload=deal,
                )
                .on_conflict_do_nothing()
            )
        await session.flush()
        kept = list(
            await session.scalars(
                select(BrokerDealRow).where(
                    BrokerDealRow.owner_id == owner_id, BrokerDealRow.account_id == account_id
                )
            )
        )
        by_position: dict[str, list[dict[str, Any]]] = {}
        for row in kept:
            by_position.setdefault(row.position_id, []).append(row.payload)
        finished = [
            position_id
            for position_id, payloads in by_position.items()
            if position_id not in open_ids and any(_entry(payload) in EXITS for payload in payloads)
        ]
        for position_id in finished:
            recorded += await close_position(
                session,
                owner_id,
                account_id,
                position_id,
                by_position[position_id],
                account.currency,
            )
        if finished:
            await session.execute(
                delete(BrokerDealRow).where(
                    BrokerDealRow.owner_id == owner_id,
                    BrokerDealRow.account_id == account_id,
                    BrokerDealRow.position_id.in_(finished),
                )
            )
        # A complete read moves to its end; an unfinished one resumes at its last page.
        read_to = end if complete else start
        await session.execute(
            insert(ClosedTradeCursorRow)
            .values(
                owner_id=owner_id,
                account_id=account_id,
                read_to=read_to,
                complete=complete,
                updated_at=utcnow(),
            )
            .on_conflict_do_update(
                index_elements=["owner_id", "account_id"],
                set_={"read_to": read_to, "complete": complete, "updated_at": utcnow()},
            )
        )
    return recorded


async def maintenance_closed_trades(db: Database, brokers: BrokerManager, owner_id: str) -> int:
    """The Gateway step: every enabled connection, each read on its own."""
    async with db.sessions() as session:
        ids = list(
            await session.scalars(
                select(BrokerSessionRow.id)
                .where(
                    BrokerSessionRow.owner_id == owner_id,
                    BrokerSessionRow.payload["enabled"].as_boolean().is_(True),
                )
                .order_by(BrokerSessionRow.id)
                .limit(32)
            )
        )
    results = await asyncio.gather(
        *(record_closed_trades(db, brokers, owner_id, identifier) for identifier in ids),
        return_exceptions=True,
    )
    for result in results:
        if isinstance(result, BaseException):
            log.info(
                "closed_trades_unavailable",
                extra={"code": getattr(result, "code", type(result).__name__)},
            )
    return sum(result for result in results if isinstance(result, int))
