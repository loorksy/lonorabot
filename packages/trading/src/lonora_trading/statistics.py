"""An agent's results per judgment label, from broker-confirmed closes (mandate 5.5.4).

"The system computes, per label, the count and net realized P&L from broker-confirmed
closes." A closed trade (``ln_closed_trades``, read from broker deals) counts once, with
its whole realized P&L, under the label of the order that opened it, and per account
currency: amounts in different currencies are never added. A trade whose P&L the broker
deals do not fully give (an exit without a profit, or an opening deal the ledger never
read) is counted as ``unpriced`` and adds nothing to the net; a row whose trades are all
unpriced has no net (None), never zero. Labels on later orders that managed a position
(a close, a stop moved, a partial take, an add to a closed netting trade) are counted
without money, from the journal's confirmed operations only. Nothing here reads an
operation the owner settled by attestation (``resolved``): only broker evidence makes a
profit number (6.4).

Each row also gives its outcomes (wins, losses and flat by the sign of the net P&L, of the
priced trades: a win rate is always shown with its sample, never as a percentage) and its
R from ``trade_r`` (n, mean, sum, mean of wins and of losses; the trades without R counted
by reason). There is no sample floor: the reader weighs the numbers. Rows can group by
label, symbol, session at open, side, or label and symbol, within a window from ``since``.
``team`` scope combines every agent's closes; for Lonora (the lead) each agent is its own
row, and the owner's own tickets are a row with agent_id None (3.1.3, 3.1.4).
"""

from collections import Counter
from collections.abc import Callable
from datetime import datetime
from decimal import Decimal
from typing import Any

from lonora_db.schema import AgentRow, ClosedTradeRow, TradingJournalRow
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from .exposure import ENTRY_ACTIONS
from .trade_r import r_text, read_r_facts, session_at_open

# What a trade opened without a label counts under.
UNLABELLED = "unlabelled"
# Bounded: the most used labels first.
MAXIMUM_ROWS = 20
# How many recent closed trades are read for netting adds.
ADDS_SCANNED = 1000
# How many of the most recent matching closed trades the rows are made from; a window
# (``since``) is the reader's choice.
TRADES_READ = 1000
FIELDS: dict[str, Callable[[ClosedTradeRow], str | None]] = {
    "label": lambda trade: trade.label or UNLABELLED,
    "symbol": lambda trade: trade.symbol,
    "side": lambda trade: trade.side,
    "session": lambda trade: session_at_open(trade.opened_at),
}


def _amount(value: Any) -> str | None:
    # None: no trade of the row has a known P&L; never shown as zero.
    return format(Decimal(value).normalize(), "f") if value is not None else None


async def netting_adds(
    session: AsyncSession, owner_id: str, account_id: str | None, symbol: str | None
) -> set[str]:
    """Broker order ids that added to a closed netting trade without opening it.

    A position id is the ticket of the order that opened it, so an entry deal with
    another order id added to the position: its order's label is a management label.
    Only the ``ADDS_SCANNED`` most recent closed trades are read, so an add whose trade
    closed before them no longer counts under its label.
    """
    # Bounded: the most recent closed trades, newest first.
    query = (
        select(ClosedTradeRow.position_id, ClosedTradeRow.deals)
        .where(ClosedTradeRow.owner_id == owner_id)
        .order_by(ClosedTradeRow.closed_at.desc())
        .limit(ADDS_SCANNED)
    )
    if account_id:
        query = query.where(ClosedTradeRow.account_id == account_id)
    if symbol:
        query = query.where(ClosedTradeRow.symbol == symbol)
    adds: set[str] = set()
    for position_id, deals in await session.execute(query):
        for deal in deals:
            entry = str(deal.get("entryType") or "").upper().removeprefix("DEAL_ENTRY_")
            order = str(deal.get("orderId") or "")
            if entry == "IN" and order and order != position_id:
                adds.add(order)
    return adds


def _mean(values: list[Decimal]) -> str | None:
    return r_text(sum(values, Decimal(0)) / len(values)) if values else None


def _results(trades: list[ClosedTradeRow], facts: dict[str, dict[str, Any]]) -> dict[str, Any]:
    pnl = [Decimal(trade.realized_pnl) for trade in trades if trade.realized_pnl is not None]
    known: list[Decimal] = [
        facts[trade.id]["r_multiple"]
        for trade in trades
        if facts[trade.id]["r_multiple"] is not None
    ]
    unknown = Counter(
        facts[trade.id]["r_unknown"] for trade in trades if facts[trade.id]["r_multiple"] is None
    )
    return {
        "count": len(trades),
        "outcomes": {
            "wins": sum(value > 0 for value in pnl),
            "losses": sum(value < 0 for value in pnl),
            "flat": sum(value == 0 for value in pnl),
            "of": len(pnl),
        },
        "net_realized_pnl": _amount(sum(pnl, Decimal(0))) if pnl else None,
        **({"unpriced": len(trades) - len(pnl)} if len(pnl) < len(trades) else {}),
        "r": {
            "n": len(known),
            "mean": _mean(known),
            "sum": r_text(sum(known, Decimal(0))) if known else None,
            "mean_win": _mean([value for value in known if value > 0]),
            "mean_loss": _mean([value for value in known if value < 0]),
            **({"unknown": dict(sorted(unknown.items()))} if unknown else {}),
        },
    }


async def statistics_block(
    session: AsyncSession,
    owner_id: str,
    agent_id: str,
    *,
    account_id: str | None = None,
    symbol: str | None = None,
    group_by: str = "label",
    since: datetime | None = None,
    until: datetime | None = None,
    scope: str = "own",
) -> dict[str, Any]:
    """The agent's statistics: closed trades per group and currency, and its management
    labels. It is what ``market_performance_read`` returns.

    Labels are slugs (``LABEL_PATTERN``), symbols, sides and sessions are broker or server
    values, and currencies come from the broker account, so the block carries no free text.
    """
    closed = select(ClosedTradeRow).where(ClosedTradeRow.owner_id == owner_id)
    lead = False
    if scope == "own":
        closed = closed.where(ClosedTradeRow.agent_id == agent_id)
    else:
        agent = await session.get(AgentRow, agent_id)
        lead = agent is not None and agent.role == "personal"
        if not lead:
            closed = closed.where(ClosedTradeRow.agent_id.is_not(None))
    if account_id:
        closed = closed.where(ClosedTradeRow.account_id == account_id)
    if symbol:
        closed = closed.where(ClosedTradeRow.symbol == symbol)
    if since:
        closed = closed.where(ClosedTradeRow.closed_at >= since)
    if until:
        closed = closed.where(ClosedTradeRow.closed_at < until)
    trades = list(
        await session.scalars(closed.order_by(ClosedTradeRow.closed_at.desc()).limit(TRADES_READ))
    )
    facts = await read_r_facts(session, trades)
    names = group_by.split("_")
    groups: dict[tuple[tuple[str | None, ...], str, str | None], list[ClosedTradeRow]] = {}
    for trade in trades:
        key = (
            tuple(FIELDS[name](trade) for name in names),
            trade.currency,
            trade.agent_id if lead else None,
        )
        groups.setdefault(key, []).append(trade)
    ranked = sorted(
        groups.items(),
        key=lambda item: (
            -len(item[1]),
            [str(value or "") for value in (*item[0][0], *item[0][1:])],
        ),
    )
    managed = TradingJournalRow.annotation["label"].as_string()
    agent_of = TradingJournalRow.result["details"]["execution"]["agent_id"].as_string()
    management = (
        select(managed.label("label"), func.count().label("count"))
        .where(
            TradingJournalRow.owner_id == owner_id,
            TradingJournalRow.status == "confirmed",
            agent_of == agent_id,
            func.coalesce(managed, "") != "",
            or_(
                TradingJournalRow.request["action"].as_string().not_in(sorted(ENTRY_ACTIONS)),
                TradingJournalRow.result["details"]["order_id"]
                .as_string()
                .in_(sorted(await netting_adds(session, owner_id, account_id, symbol))),
            ),
        )
        .group_by(managed)
        .order_by(func.count().desc(), managed)
        .limit(MAXIMUM_ROWS)
    )
    if account_id:
        management = management.where(TradingJournalRow.account_id == account_id)
    if symbol:
        management = management.where(TradingJournalRow.request["symbol"].as_string() == symbol)
    if since:
        management = management.where(TradingJournalRow.updated_at >= since)
    if until:
        management = management.where(TradingJournalRow.updated_at < until)
    return {
        "closed_trades": [
            {
                **dict(zip(names, fields, strict=True)),
                "currency": currency,
                **({"agent_id": agent} if lead else {}),
                **_results(rows, facts),
            }
            for (fields, currency, agent), rows in ranked[:MAXIMUM_ROWS]
        ],
        "management": [
            {"label": row.label, "count": row.count} for row in await session.execute(management)
        ],
        **({"latest_trades_read": TRADES_READ} if len(trades) == TRADES_READ else {}),
    }
