"""The R facts of a closed trade, from its ledger row and the journal; never estimated.

Entry and exit prices are volume-weighted from the trade's IN and OUT deals (a netting
reversal deal carries the part of the trade's volume the other deals leave). The initial
stop and take-profit are those of the opening journaled order's request; when it had
none, the first confirmed modify that set one on the trade's ticket before its first
exit. R is the side-signed (exit - entry) / (entry - initial stop): ``price_r`` from the
prices alone, ``r_multiple`` from the trade's realized money (profit, commission and
swap) over what its initial risk was worth at the trade's own money per price unit (its
deals' profit over its price move), so no tick value is guessed.

When R cannot be computed it is None, with ``r_unknown``: ``no_initial_stop``;
``no_initial_risk`` (the initial stop was at or beyond the entry, on the profit side);
``unpriced`` (the deals do not give the money or the prices); ``no_price_move`` (exit
equals entry, so the deals give no money per price unit). This module reads the ledger
and the journal and writes nothing.
"""

from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation
from typing import Any
from uuid import UUID

from lonora_db.schema import ClosedTradeRow, TradingJournalRow
from lonora_market.sessions import session_clock
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from .realized import TRADE_DEALS

MODIFIES = ("modify_order", "modify_position")
EXITS = frozenset({"OUT", "OUT_BY", "INOUT"})


def _entry(deal: dict[str, Any]) -> str:
    return str(deal.get("entryType") or "").strip().upper().removeprefix("DEAL_ENTRY_")


def _trading(deal: dict[str, Any]) -> bool:
    return str(deal.get("type") or "").strip().upper().removeprefix("DEAL_TYPE_") in TRADE_DEALS


def _number(value: Any) -> Decimal | None:
    try:
        number = Decimal(str(value))
    except InvalidOperation:
        return None
    return number if number.is_finite() else None


def _time(deal: dict[str, Any]) -> datetime:
    value = datetime.fromisoformat(str(deal["time"]).replace("Z", "+00:00"))
    return value if value.tzinfo else value.replace(tzinfo=UTC)


def _average(deals: list[dict[str, Any]], total: Decimal | None) -> Decimal | None:
    """The volume-weighted price of deals that together carry ``total``."""
    if total is None:
        return None
    legs: list[tuple[Decimal, Decimal]] = []
    for deal in sorted(deals, key=lambda deal: _entry(deal) == "INOUT"):
        price = _number(deal.get("price"))
        # A reversal deal (sorted last) carries what the other deals leave of the trade.
        size = (
            total - sum((size for _, size in legs), Decimal(0))
            if _entry(deal) == "INOUT"
            else _number(deal.get("volume"))
        )
        if price is None or size is None or size <= 0:
            return None
        legs.append((price, size))
    if not legs or sum((size for _, size in legs), Decimal(0)) != total:
        return None
    # Rounded to the ledger's ten decimal places.
    return round(sum((price * size for price, size in legs), Decimal(0)) / total, 10)


def r_text(value: Decimal | None) -> str | None:
    return format(round(value, 2).normalize(), "f") if value is not None else None


def session_at_open(opened_at: datetime | None) -> str | None:
    """The FX sessions open when the trade opened, joined by "+"; "none" outside them."""
    if opened_at is None:
        return None
    return "+".join(session_clock(opened_at)["active_sessions"]) or "none"


def _is_id(value: str) -> bool:
    try:
        return str(UUID(value)) == value
    except ValueError:
        return False


def r_facts(
    trade: ClosedTradeRow, opening: TradingJournalRow | None, modifies: list[TradingJournalRow]
) -> dict[str, Any]:
    """The trade's R facts (pure). ``modifies``: confirmed modifies of its ticket."""
    deals = [deal for deal in trade.deals if _trading(deal)]
    # A trade a reversal opened starts with that deal, whose money closed the trade before.
    reopened = (
        bool(deals)
        and _entry(deals[0]) == "INOUT"
        and str(deals[0].get("id")) != trade.closing_deal_id
    )
    own = deals[1:] if reopened else deals
    exits = [deal for deal in own if _entry(deal) in EXITS]
    volume = _number(trade.volume)
    entry = _average(
        ([deals[0]] if reopened else []) + [deal for deal in own if _entry(deal) == "IN"], volume
    )
    exit = _average(exits, volume)
    request = opening.request if opening is not None else {}
    start = (opening.submitted_at if opening is not None else None) or trade.opened_at
    first_exit = min((_time(deal) for deal in exits), default=trade.closed_at)
    later = sorted(
        (
            row
            for row in modifies
            if row.submitted_at is not None
            and (start is None or row.submitted_at >= start)
            and row.submitted_at < first_exit
        ),
        key=lambda row: row.submitted_at or first_exit,
    )
    requests = [request, *(row.request for row in later)]
    stop, take_profit = (
        next(filter(None, (_number(item.get(key)) for item in requests)), None)
        for key in ("stop_loss", "take_profit")
    )
    side = 1 if trade.side == "buy" else -1
    realized = _number(trade.realized_pnl)
    profit = sum((_number(deal.get("profit")) or Decimal(0) for deal in own), Decimal(0))
    price_r = r_multiple = None
    if stop is None:
        unknown = "no_initial_stop"
    elif entry is None or exit is None:
        unknown = "unpriced"
    elif side * (entry - stop) <= 0:
        unknown = "no_initial_risk"
    else:
        risk, move = side * (entry - stop), side * (exit - entry)
        price_r = move / risk
        if realized is None:
            unknown = "unpriced"
        elif move == 0:
            unknown = "no_price_move"
        elif profit * move <= 0:
            unknown = "unpriced"  # The deals' profit and prices disagree: no money per unit.
        else:
            # The money per price unit is profit / move; the initial risk was worth that
            # times risk.
            r_multiple, unknown = realized * move / (profit * risk), None
    thesis = str(request.get("thesis_id") or "")
    return {
        "entry_price": entry,
        "exit_price": exit,
        "initial_stop": stop,
        "initial_take_profit": take_profit,
        "r_multiple": r_multiple,
        "price_r": price_r,
        "r_unknown": unknown,
        "had_adds": sum(
            _entry(deal) == "IN" and str(deal.get("orderId") or "") != trade.position_id
            for deal in own
        ),
        "partial_exits": max(len(exits) - 1, 0),
        "opening_operation_id": trade.opening_operation_id,
        # The field is the agent's: only the server's id form is shown, never other text.
        "thesis_id": thesis if _is_id(thesis) else None,
    }


async def read_r_facts(
    session: AsyncSession, trades: list[ClosedTradeRow]
) -> dict[str, dict[str, Any]]:
    """The R facts of one owner's trades by trade id, from two journal reads."""
    if not trades:
        return {}
    journal, owner = TradingJournalRow, trades[0].owner_id
    operations = sorted({trade.opening_operation_id or "" for trade in trades} - {""})
    openings = {
        row.operation_id: row
        for row in await session.scalars(
            select(journal).where(journal.owner_id == owner, journal.operation_id.in_(operations))
        )
    }
    tickets = sorted({trade.position_id for trade in trades})
    modifies: dict[tuple[str, str], list[TradingJournalRow]] = {}
    for row in await session.scalars(
        select(journal).where(
            journal.owner_id == owner,
            journal.status == "confirmed",
            journal.request["action"].as_string().in_(MODIFIES),
            or_(
                journal.request["position_id"].as_string().in_(tickets),
                journal.request["order_id"].as_string().in_(tickets),
            ),
        )
    ):
        ticket = str(row.request.get("position_id") or row.request.get("order_id"))
        modifies.setdefault((row.account_id, ticket), []).append(row)
    return {
        trade.id: r_facts(
            trade,
            openings.get(trade.opening_operation_id or ""),
            modifies.get((trade.account_id, trade.position_id), []),
        )
        for trade in trades
    }
