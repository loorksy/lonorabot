"""The closed-trade ledger: one row per trade whose position volume reached zero at the broker.

Mandate 5.5.1: "A trade is closed when its position's volume reaches zero at the
broker, whatever the cause." The ledger reads broker deal history from a stored cursor,
not the reconciliation snapshot diff (which stays for activity events), so a close is
recorded after a restart and for a trade opened and closed between two reads.

A position's deals are cut into trades at each reversal (``DEAL_ENTRY_INOUT``, a netting
position taken through zero to the other side): the reversing deal closes one trade and
opens the next. A trade closes at its reversing deal, or when the position has an exit
(``DEAL_ENTRY_OUT`` or ``DEAL_ENTRY_OUT_BY``), its exits add up to what its entries opened,
and a fresh broker position read taken after the history read no longer lists it. When
the ledger never saw the trade's opening deal (a position opened before its first read),
the volumes cannot be added up: the broker's position read decides alone, and the P&L is
unknown rather than a partial number.

Its realized P&L is the profit, commission and swap of its broker deals
(``realized.deal_pnl``), in the account currency. Its owner follows 3.3.4: the agent
whose confirmed journaled order opened it, else the owner. A ticket with no
agent-attributed journaled opening order, such as one opened in the broker terminal or
by code deployed outside the door, is the owner's and is never attributed to an agent.
"""

import asyncio
import logging
from datetime import UTC, datetime, timedelta
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
from sqlalchemy import and_, delete, false, or_, select, true
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from .exposure import ENTRY_ACTIONS
from .manual_activity import journal_agent
from .realized import CASH_FLOW_DEALS, TRADE_DEALS, deal_pnl

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
REVERSAL = "INOUT"


def _kind(deal: dict[str, Any]) -> str:
    return str(deal.get("type") or "").strip().upper().removeprefix("DEAL_TYPE_")


def _entry(deal: dict[str, Any]) -> str:
    return str(deal.get("entryType") or "").strip().upper().removeprefix("DEAL_ENTRY_")


def _time(deal: dict[str, Any]) -> datetime:
    value = datetime.fromisoformat(str(deal["time"]).replace("Z", "+00:00"))
    return value if value.tzinfo else value.replace(tzinfo=UTC)


def _volume(deal: dict[str, Any]) -> Decimal:
    return Decimal(str(deal.get("volume") or 0))


def _order(deals: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return sorted(deals, key=lambda deal: (_time(deal), str(deal["id"])))


def _trading(deal: dict[str, Any]) -> bool:
    return _kind(deal) in TRADE_DEALS


def position_deal(deal: dict[str, Any]) -> bool:
    """A deal of a position: a buy or sell with its entry type, or a charge booked on it.

    A charge (commission, fee or another non-trade type carrying the position) counts in
    the trade's P&L through ``deal_pnl``, which lets it lower and never raise it. Balance,
    credit and bonus cash flows are not a position's.
    """
    if not (deal.get("positionId") and deal.get("id") and deal.get("time") is not None):
        return False
    if _trading(deal):
        return _entry(deal) in {"IN", REVERSAL, *EXITS}
    return _kind(deal) not in CASH_FLOW_DEALS


def realized(deals: list[dict[str, Any]]) -> Decimal | None:
    """Profit + commission + swap of the deals; None when an exit has no broker profit."""
    if any(
        _entry(deal) in {*EXITS, REVERSAL} and deal.get("profit") in (None, "") for deal in deals
    ):
        return None
    try:
        return sum((deal_pnl(deal) for deal in deals), Decimal(0))
    except LonoraError:
        return None


class Trade:
    """One trade of a position: from its opening deal to the deal that closed it.

    A position id is the ticket of the order that opened the position from flat, so an
    entry deal with that order id is the position's opening. A trade that starts at a
    reversal is opened by the reversing deal. Otherwise the ledger never read the
    opening (the position is older than its first read), and so is a trade that a
    reversal closed before the ledger saw any other deal of it (``unseen``).
    """

    def __init__(
        self,
        position_id: str,
        deals: list[dict[str, Any]],
        reopened: Decimal | None,
        *,
        unseen: bool = False,
    ):
        # ``reopened``: what the reversal that opened this trade left open, when known.
        self.position_id, self.deals, self.reopened = position_id, deals, reopened
        first = next(deal for deal in deals if _trading(deal))
        self.after_reversal = not unseen and _entry(first) == REVERSAL
        self.opening: dict[str, Any] | None = (
            first
            if self.after_reversal
            or (_entry(first) == "IN" and str(first.get("orderId") or "") == position_id)
            else None
        )

    @property
    def own(self) -> list[dict[str, Any]]:
        """The trade's money: a reversal's own money closed the trade before it."""
        if not self.after_reversal:
            return self.deals
        return [deal for deal in self.deals if deal is not self.opening]

    @property
    def volume_known(self) -> bool:
        return self.opening is not None and (not self.after_reversal or self.reopened is not None)

    def open_volume(self) -> Decimal:
        """What is still open, counted from the opening; meaningful when ``volume_known``."""
        volume = self.reopened or Decimal(0)
        for deal in self.own:
            if _trading(deal) and _entry(deal) == "IN":
                volume += _volume(deal)
            elif _trading(deal) and _entry(deal) in EXITS:
                volume -= _volume(deal)
        return volume

    def opened_volume(self) -> Decimal:
        return (self.reopened or Decimal(0)) + sum(
            (_volume(deal) for deal in self.own if _trading(deal) and _entry(deal) == "IN"),
            Decimal(0),
        )


def trades(position_id: str, deals: list[dict[str, Any]]) -> tuple[list[Trade], Trade | None]:
    """The position's trades closed by a reversal, and the trade still running after them.

    Every reversal closes a trade: the one the kept deals hold, or, when it is the
    position's first kept trading deal, a trade the ledger never saw open.
    """
    closed: list[Trade] = []
    current: list[dict[str, Any]] = []
    reopened: Decimal | None = None
    for deal in _order(deals):
        earlier = any(_trading(item) for item in current)
        current.append(deal)
        if _trading(deal) and _entry(deal) == REVERSAL:
            trade = Trade(position_id, current, reopened, unseen=not earlier)
            closed.append(trade)
            # The reversal closed what was open; the rest of its volume opens the next.
            reopened = _volume(deal) - trade.open_volume() if trade.volume_known else None
            current = [deal]
    running = Trade(position_id, current, reopened) if any(map(_trading, current)) else None
    return closed, running


async def opening_entry(
    session: AsyncSession,
    owner_id: str,
    account_id: str,
    symbol: str,
    position_id: str,
    opening: dict[str, Any] | None,
    first: bool,
) -> TradingJournalRow | None:
    """The confirmed journaled order that opened this trade, if Lonora's door sent it.

    A broker position id is the ticket of the order that opened the position from flat,
    so the first trade's order is matched by that ticket; any trade's order by the
    opening deal's order id, by the operation tag the door sends as the client id, or
    (simulation) by the broker id. A later order that added to a netting position has
    another order id and never matches.
    """
    orders = {position_id} if first else set[str]()
    tags: set[str] = set()
    if opening is not None:
        if opening.get("orderId"):
            orders.add(str(opening["orderId"]))
        if opening.get("clientId"):
            tags.add(str(opening["clientId"]))
    entries = (
        TradingJournalRow.owner_id == owner_id,
        TradingJournalRow.account_id == account_id,
        TradingJournalRow.status == "confirmed",
        TradingJournalRow.request["action"].as_string().in_(sorted(ENTRY_ACTIONS)),
    )
    exact = await session.scalar(
        select(TradingJournalRow)
        .where(
            *entries,
            or_(
                TradingJournalRow.result["details"]["order_id"].as_string().in_(sorted(orders)),
                and_(
                    TradingJournalRow.result["details"]["simulation"].as_boolean().is_(True),
                    TradingJournalRow.result["broker_id"].as_string() == position_id,
                    true() if first else false(),
                ),
            ),
        )
        .order_by(TradingJournalRow.updated_at.desc())
        .limit(1)
    )
    if exact is not None or not tags:
        return exact
    # The tag is a digest of the operation id: compared on the symbol's recent entries.
    for entry in await session.scalars(
        select(TradingJournalRow)
        .where(*entries, TradingJournalRow.request["symbol"].as_string() == symbol)
        .order_by(TradingJournalRow.updated_at.desc())
        .limit(PAGE)
    ):
        if broker_operation_tag(entry.operation_id) in tags:
            return entry
    return None


def opening_label(journal: TradingJournalRow | None) -> str | None:
    """The judgment label the opening order carried beside its request (5.5.3)."""
    if journal is None or not isinstance(journal.annotation, dict):
        return None
    label = journal.annotation.get("label")
    return label if isinstance(label, str) and label else None


async def write_trade(
    session: AsyncSession,
    owner_id: str,
    account_id: str,
    position_id: str,
    trade: Trade,
    closing: dict[str, Any],
    currency: str,
) -> bool:
    """Write the ledger row of a closed trade once; True when this call wrote it."""
    opening = trade.opening
    symbol = str((opening or closing).get("symbol") or "")
    journal = await opening_entry(
        session,
        owner_id,
        account_id,
        symbol,
        position_id,
        opening,
        first=not trade.after_reversal,
    )
    if opening is not None:
        side = "buy" if _kind(opening) == "BUY" else "sell"
    else:
        side = "sell" if _kind(closing) == "BUY" else "buy"
    exits = [deal for deal in trade.own if _trading(deal) and _entry(deal) in EXITS]
    volume: Decimal | None = None
    if trade.volume_known:
        volume = trade.opened_volume()
    elif exits and _entry(closing) in EXITS:
        volume = sum((_volume(deal) for deal in exits), Decimal(0))
    written = await session.execute(
        insert(ClosedTradeRow)
        .values(
            id=str(
                uuid5(
                    NAMESPACE_URL,
                    f"lonora:closed-trade:{owner_id}:{account_id}:{position_id}:{closing['id']}",
                )
            ),
            owner_id=owner_id,
            account_id=account_id,
            position_id=position_id,
            closing_deal_id=str(closing["id"]),
            symbol=symbol,
            side=side,
            volume=volume,
            agent_id=journal_agent(journal) if journal is not None else None,
            opening_operation_id=journal.operation_id if journal is not None else None,
            label=opening_label(journal),
            currency=currency,
            # Without its opening deal the trade's money is not all known.
            realized_pnl=realized(trade.own) if opening is not None else None,
            opened_at=_time(opening) if opening is not None else None,
            closed_at=_time(closing),
            deals=trade.deals,
            created_at=utcnow(),
        )
        .on_conflict_do_nothing(constraint="ln_closed_trade_closing_deal")
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
            # A full page continues from its last deal (broker history is in time
            # order); deals read twice are one row.
            last = max((_time(deal) for deal in page if deal.get("time")), default=start)
            if last <= start:
                log.warning("closed_trades_page_stalled", extra={"account_id": account_id})
                break
            start = last
        # Read after the history: a position a listed exit closed is gone from it.
        positions = await broker.positions()
    if len(positions) > PAGE:
        raise LonoraError("broker_snapshot_limit", 409)
    open_ids = {position.id for position in positions}
    recorded = 0
    async with db.sessions() as session, session.begin():
        for deal in history:
            if not position_deal(deal):
                continue
            await session.execute(
                insert(BrokerDealRow)
                .values(
                    owner_id=owner_id,
                    account_id=account_id,
                    deal_id=str(deal["id"]),
                    position_id=str(deal["positionId"]),
                    time=_time(deal),
                    payload=deal,
                )
                .on_conflict_do_nothing()
            )
        await session.flush()
        by_position: dict[str, list[dict[str, Any]]] = {}
        for row in await session.scalars(
            select(BrokerDealRow).where(
                BrokerDealRow.owner_id == owner_id, BrokerDealRow.account_id == account_id
            )
        ):
            by_position.setdefault(row.position_id, []).append(row.payload)
        for position_id, deals in by_position.items():
            reversed_trades, running = trades(position_id, deals)
            for trade in reversed_trades:
                recorded += await write_trade(
                    session,
                    owner_id,
                    account_id,
                    position_id,
                    trade,
                    trade.deals[-1],
                    account.currency,
                )
            exits = (
                [deal for deal in running.own if _trading(deal) and _entry(deal) in EXITS]
                if running
                else []
            )
            if (
                running is not None
                and exits
                and position_id not in open_ids
                and (not running.volume_known or running.open_volume() == 0)
            ):
                recorded += await write_trade(
                    session, owner_id, account_id, position_id, running, exits[-1], account.currency
                )
        await forget_recorded(session, owner_id, account_id, by_position, open_ids)
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


async def forget_recorded(
    session: AsyncSession,
    owner_id: str,
    account_id: str,
    by_position: dict[str, list[dict[str, Any]]],
    open_ids: set[str],
) -> None:
    """Drop the kept deals of a position the broker no longer lists, once on a ledger row.

    A position still open keeps every deal: its trades are cut at reversals from the
    whole set. Deals another process re-read after their trade was recorded are dropped
    here as well.
    """
    done = sorted(position for position in by_position if position not in open_ids)
    if not done:
        return
    rows = await session.scalars(
        select(ClosedTradeRow.deals).where(
            ClosedTradeRow.owner_id == owner_id,
            ClosedTradeRow.account_id == account_id,
            ClosedTradeRow.position_id.in_(done),
        )
    )
    recorded = {str(deal["id"]) for deals in rows for deal in deals}
    forget = [
        str(deal["id"])
        for position in done
        for deal in by_position[position]
        if str(deal["id"]) in recorded
    ]
    if forget:
        await session.execute(
            delete(BrokerDealRow).where(
                BrokerDealRow.owner_id == owner_id,
                BrokerDealRow.account_id == account_id,
                BrokerDealRow.deal_id.in_(forget),
            )
        )


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
