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
"""

from decimal import Decimal
from typing import Any

from lonora_db.schema import ClosedTradeRow, TradingJournalRow
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from .exposure import ENTRY_ACTIONS

# What a trade opened without a label counts under.
UNLABELLED = "unlabelled"
# Bounded: the most used labels first.
MAXIMUM_ROWS = 20


def _amount(value: Any) -> str | None:
    # None: no trade of the row has a known P&L; never shown as zero.
    return format(Decimal(value).normalize(), "f") if value is not None else None


async def netting_adds(
    session: AsyncSession, owner_id: str, account_id: str | None, symbol: str | None
) -> set[str]:
    """Broker order ids that added to a closed netting trade without opening it.

    A position id is the ticket of the order that opened it, so an entry deal with
    another order id added to the position: its order's label is a management label.
    """
    query = select(ClosedTradeRow.position_id, ClosedTradeRow.deals).where(
        ClosedTradeRow.owner_id == owner_id
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


async def statistics_block(
    session: AsyncSession,
    owner_id: str,
    agent_id: str,
    *,
    account_id: str | None = None,
    symbol: str | None = None,
) -> dict[str, Any]:
    """The agent's statistics: closed trades per opening label and currency, and its
    management labels. It is what ``market_performance_read`` returns.

    Labels are slugs (``LABEL_PATTERN``) and currencies come from the broker account, so
    the block carries no free text.
    """
    label = func.coalesce(func.nullif(ClosedTradeRow.label, ""), UNLABELLED)
    trades = (
        select(
            label.label("label"),
            ClosedTradeRow.currency,
            func.count().label("count"),
            func.sum(ClosedTradeRow.realized_pnl).label("net"),
            func.count().filter(ClosedTradeRow.realized_pnl.is_(None)).label("unpriced"),
        )
        .where(ClosedTradeRow.owner_id == owner_id, ClosedTradeRow.agent_id == agent_id)
        .group_by(label, ClosedTradeRow.currency)
        .order_by(func.count().desc(), label, ClosedTradeRow.currency)
        .limit(MAXIMUM_ROWS)
    )
    if account_id:
        trades = trades.where(ClosedTradeRow.account_id == account_id)
    if symbol:
        trades = trades.where(ClosedTradeRow.symbol == symbol)
    managed = TradingJournalRow.annotation["label"].as_string()
    agent = TradingJournalRow.result["details"]["execution"]["agent_id"].as_string()
    management = (
        select(managed.label("label"), func.count().label("count"))
        .where(
            TradingJournalRow.owner_id == owner_id,
            TradingJournalRow.status == "confirmed",
            agent == agent_id,
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
    return {
        "closed_trades": [
            {
                "label": row.label,
                "currency": row.currency,
                "count": row.count,
                "net_realized_pnl": _amount(row.net),
                **({"unpriced": row.unpriced} if row.unpriced else {}),
            }
            for row in await session.execute(trades)
        ],
        "management": [
            {"label": row.label, "count": row.count} for row in await session.execute(management)
        ],
    }
