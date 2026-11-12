"""The closed-trade ledger (mandate 5.5.1, 3.3.4).

"A trade is closed when its position's volume reaches zero at the broker, whatever the
cause." Every close of the test broker creates exactly one ledger row: a close the
agent's own order made, a stop loss the broker hit, a trade opened and closed between
two reads, again after a restart. The row's owner is the agent whose journaled order
opened the position, else the owner; its realized P&L is the profit, commission and swap
of the position's broker deals in the account currency. The PostgreSQL cases use the
real migrated schema and the simulation broker (skipped without LONORA_DATABASE_URL).
"""

from datetime import timedelta
from decimal import Decimal
from typing import Any
from uuid import uuid4

import pytest
from lonora_contracts.account import Position
from lonora_contracts.domain import utcnow
from lonora_contracts.trading import TradingControl
from lonora_trading.closed_trades import realized, trade_deal
from test_proactive_wakes import call, database, journal, retire, set_positions, simulation


def deal(
    position: str,
    entry: str,
    kind: str,
    *,
    volume: str = "0.1",
    profit: str | None = "0",
    minutes: int = 0,
    order: str | None = None,
    client: str | None = None,
    **extra: Any,
) -> dict[str, Any]:
    value: dict[str, Any] = {
        "id": "deal-" + uuid4().hex[:10],
        "positionId": position,
        "orderId": order or "order-" + uuid4().hex[:8],
        "symbol": "XAUUSD",
        "type": "DEAL_TYPE_" + kind,
        "entryType": "DEAL_ENTRY_" + entry,
        "volume": volume,
        "price": "100",
        "time": (utcnow() - timedelta(minutes=minutes)).isoformat(),
        **({"profit": profit} if profit is not None else {}),
        **({"clientId": client} if client else {}),
        **extra,
    }
    return value


def test_realized_pnl_is_profit_commission_and_swap_of_the_deals() -> None:
    deals = [
        deal("P", "IN", "BUY", profit="0", commission="-1.5"),
        deal("P", "OUT", "SELL", volume="0.05", profit="20", swap="-0.25"),
        deal("P", "OUT", "SELL", volume="0.05", profit="-4", commission="-0.5"),
    ]
    assert realized(deals) == Decimal("13.75")
    # An exit without a broker-reported profit: the P&L is unknown, never computed.
    assert realized([deal("P", "IN", "BUY"), deal("P", "OUT", "SELL", profit=None)]) is None
    # Only buy and sell deals of a position make up a trade.
    assert trade_deal(deal("P", "OUT", "SELL"))
    assert not trade_deal({**deal("P", "IN", "BUY"), "type": "DEAL_TYPE_BALANCE"})
    assert not trade_deal({**deal("P", "IN", "BUY"), "positionId": None})


TICKS = {"profit_tick_value": "1", "loss_tick_value": "1"}


async def quote(fixture: Any, connection: str, bid: str, ask: str) -> None:
    from lonora_db.schema import TradingAccountRow

    async with fixture.runtime.db.sessions() as session, session.begin():
        account = await session.get(TradingAccountRow, connection, with_for_update=True)
        assert account is not None
        account.payload = {
            **account.payload,
            "quotes": {
                "XAUUSD": {
                    "symbol": "XAUUSD",
                    "bid": bid,
                    "ask": ask,
                    "observed_at": utcnow().isoformat(),
                    "source": "ledger-fixture",
                    **TICKS,
                }
            },
        }


async def add_history(fixture: Any, connection: str, *deals: dict[str, Any]) -> None:
    from lonora_db.schema import TradingAccountRow

    async with fixture.runtime.db.sessions() as session, session.begin():
        account = await session.get(TradingAccountRow, connection, with_for_update=True)
        assert account is not None
        account.payload = {
            **account.payload,
            "history": [*account.payload.get("history", []), *deals],
        }


async def ledger(fixture: Any, connection: str) -> list[Any]:
    from lonora_db.schema import ClosedTradeRow
    from sqlalchemy import select

    async with fixture.runtime.db.sessions() as session:
        return list(
            await session.scalars(
                select(ClosedTradeRow)
                .where(ClosedTradeRow.account_id == connection)
                .order_by(ClosedTradeRow.closed_at)
            )
        )


async def record(fixture: Any, connection: str) -> int:
    from lonora_trading.closed_trades import record_closed_trades

    return await record_closed_trades(
        fixture.runtime.db,
        fixture.runtime.services(fixture.owner).brokers,
        fixture.owner,
        connection,
    )


@pytest.mark.asyncio
async def test_every_close_of_the_test_broker_creates_exactly_one_row() -> None:
    database()
    from check_streaming import Fixture
    from lonora_db.schema import BrokerDealRow, ClosedTradeCursorRow
    from lonora_db.trading_mode import set_trading_mode
    from lonora_trading.controls import read_controls, save_controls
    from sqlalchemy import delete, func, select

    fixture = await Fixture().open()
    original = await read_controls(fixture.runtime.db)
    connection = ""
    try:
        connection = await simulation(fixture, [])
        await quote(fixture, connection, "100", "101")
        await save_controls(fixture.runtime.db, TradingControl(enabled=True))
        agent = await fixture.agent("Ledger", supervised=True)
        async with fixture.runtime.db.sessions() as session, session.begin():
            await set_trading_mode(session, fixture.owner, agent["id"], "full", by="owner_tap")
        context = await fixture.lease(await fixture.run(agent, await fixture.conversation(agent)))
        opened = await call(
            context,
            "trade_execute",
            action="buy",
            symbol="XAUUSD",
            volume="0.2",
            stop_loss="95",
            account_id=connection,
            reason="Breakout",
        )
        assert opened["status"] == "confirmed", opened
        ticket = opened["broker_id"]
        assert await record(fixture, connection) == 0 and await ledger(fixture, connection) == []
        # A partial close leaves volume at the broker: not a closed trade.
        await quote(fixture, connection, "103", "104")
        partial = await call(
            context,
            "trade_execute",
            action="close_position",
            symbol="XAUUSD",
            position_id=ticket,
            volume="0.1",
            account_id=connection,
            reason="Half at the first target",
        )
        assert partial["status"] == "confirmed", partial
        assert await record(fixture, connection) == 0 and await ledger(fixture, connection) == []
        # The rest closes: volume zero at the broker, one row.
        await quote(fixture, connection, "99", "100")
        closed = await call(
            context,
            "trade_execute",
            action="close_position",
            symbol="XAUUSD",
            position_id=ticket,
            account_id=connection,
            reason="Reason for the trade broke",
        )
        assert closed["status"] == "confirmed", closed
        assert await record(fixture, connection) == 1
        rows = await ledger(fixture, connection)
        assert len(rows) == 1
        row = rows[0]
        assert row.position_id == ticket and row.side == "buy" and row.symbol == "XAUUSD"
        assert row.agent_id == agent["id"]
        assert row.opening_operation_id == opened["operation_id"]
        assert row.currency == "USD" and Decimal(row.volume) == Decimal("0.2")
        # Entry at 101; 0.1 out at 103 (+200 ticks), 0.1 out at 99 (-200 ticks); 1 per tick.
        assert Decimal(row.realized_pnl) == Decimal("0")
        assert [item["entryType"] for item in row.deals] == [
            "DEAL_ENTRY_IN",
            "DEAL_ENTRY_OUT",
            "DEAL_ENTRY_OUT",
        ]
        # Reading again, and after a restart with the cursor lost, adds nothing.
        assert await record(fixture, connection) == 0
        async with fixture.runtime.db.sessions() as session, session.begin():
            await session.execute(
                delete(ClosedTradeCursorRow).where(ClosedTradeCursorRow.account_id == connection)
            )
        # A restarted process: a new broker manager over the same database.
        from lonora_adapters.brokers.base import BrokerManager
        from lonora_trading.closed_trades import record_closed_trades

        services = fixture.runtime.services(fixture.owner).brokers
        restarted = BrokerManager(fixture.runtime.db, services.secrets)
        try:
            assert (
                await record_closed_trades(fixture.runtime.db, restarted, fixture.owner, connection)
                == 0
            )
        finally:
            await restarted.close()
        assert len(await ledger(fixture, connection)) == 1
        async with fixture.runtime.db.sessions() as session:
            kept = await session.scalar(
                select(func.count())
                .select_from(BrokerDealRow)
                .where(BrokerDealRow.account_id == connection)
            )
            assert kept == 0  # The closed trade's deals live on its row only.
    finally:
        await save_controls(fixture.runtime.db, original)
        await retire(fixture, connection)
        await fixture.close()


@pytest.mark.asyncio
async def test_stop_loss_fast_trades_and_the_owners_tickets() -> None:
    database()
    from check_streaming import Fixture
    from lonora_session.idempotency import broker_operation_tag

    fixture = await Fixture().open()
    connection = ""
    try:
        gold = await fixture.agent("Gold", supervised=True)
        silver = await fixture.agent("Silver", supervised=True)
        held = Position(
            id="sl-1",
            symbol="XAUUSD",
            side="buy",
            volume=Decimal("0.1"),
            open_price=Decimal(100),
            stop_loss=Decimal(95),
        )
        connection = await simulation(fixture, [held])
        opening = "gold-entry-" + uuid4().hex[:8]
        added = "silver-add-" + uuid4().hex[:8]
        async with fixture.runtime.db.sessions() as session, session.begin():
            for row in (
                journal(opening, {"action": "buy", "symbol": "XAUUSD"}, agent_id=gold["id"]),
                journal(added, {"action": "buy", "symbol": "XAUUSD"}, agent_id=silver["id"]),
            ):
                row.owner_id, row.account_id = fixture.owner, connection
                row.request = {**row.request, "account_id": connection}
                session.add(row)
            # MetaApi receipts: the opening order is the position's ticket; the add
            # order on the same netting position has its own order id.
            gold_row = await session.get(type(row), opening)
            silver_row = await session.get(type(row), added)
            assert gold_row is not None and silver_row is not None
            gold_row.result = {
                **gold_row.result,
                "details": {**gold_row.result["details"], "order_id": "sl-1"},
            }
            silver_row.result = {
                **silver_row.result,
                "details": {**silver_row.result["details"], "order_id": "add-7"},
            }
        await add_history(
            fixture,
            connection,
            deal("sl-1", "IN", "BUY", minutes=30, order="sl-1"),
            deal("sl-1", "IN", "BUY", minutes=20, order="add-7"),
            # Opened by code deployed outside the door: no journaled order.
            deal("ea-1", "IN", "SELL", minutes=10, client="EA_magic_42"),
            # The owner's broker-terminal trade, opened and closed between two reads.
            deal("fast-1", "IN", "BUY", minutes=5),
            deal("fast-1", "OUT", "SELL", minutes=4, profit="12", commission="-1"),
            # A door order matched only by the operation tag it sent as the client id.
            deal("tag-1", "IN", "SELL", minutes=3, client=broker_operation_tag(opening)),
            deal("tag-1", "OUT", "BUY", minutes=2, profit="-3"),
            {"id": "cash-1", "type": "DEAL_TYPE_BALANCE", "time": utcnow().isoformat()},
        )
        assert await record(fixture, connection) == 2
        # The broker hits the stop loss of sl-1, and the EA closes its own position.
        await set_positions(fixture, connection, [])
        await add_history(
            fixture,
            connection,
            deal("sl-1", "OUT", "SELL", volume="0.2", profit="-100", swap="-2"),
            deal("ea-1", "OUT", "BUY", profit="7"),
        )
        assert await record(fixture, connection) == 2
        rows = {row.position_id: row for row in await ledger(fixture, connection)}
        assert set(rows) == {"sl-1", "ea-1", "fast-1", "tag-1"}
        assert rows["sl-1"].agent_id == gold["id"] and rows["sl-1"].opening_operation_id == opening
        assert Decimal(rows["sl-1"].realized_pnl) == Decimal(-102)
        assert Decimal(rows["sl-1"].volume) == Decimal("0.2")
        assert rows["tag-1"].agent_id == gold["id"] and rows["tag-1"].side == "sell"
        for owners in ("ea-1", "fast-1"):
            assert rows[owners].agent_id is None and rows[owners].opening_operation_id is None
        assert Decimal(rows["fast-1"].realized_pnl) == Decimal(11)
        assert await record(fixture, connection) == 0
    finally:
        await retire(fixture, connection)
        await fixture.close()


@pytest.mark.asyncio
async def test_a_full_page_of_history_is_paged_from_its_last_deal(monkeypatch: Any) -> None:
    database()
    from check_streaming import Fixture
    from lonora_db.schema import ClosedTradeCursorRow
    from lonora_trading import closed_trades

    fixture = await Fixture().open()
    connection = ""
    try:
        connection = await simulation(fixture, [])
        await add_history(
            fixture,
            connection,
            deal("p-1", "IN", "BUY", minutes=50),
            deal("p-1", "OUT", "SELL", minutes=40, profit="1"),
            deal("p-2", "IN", "BUY", minutes=30),
            deal("p-2", "OUT", "SELL", minutes=20, profit="2"),
        )
        monkeypatch.setattr(closed_trades, "PAGE", 2)
        # One page per read: the cursor stays at the page and the next read resumes there.
        monkeypatch.setattr(closed_trades, "PAGES", 1)
        assert await record(fixture, connection) == 1
        async with fixture.runtime.db.sessions() as session:
            cursor = await session.get(ClosedTradeCursorRow, (fixture.owner, connection))
            assert cursor is not None and not cursor.complete
        # Several pages in one read: it reads on to the end.
        monkeypatch.setattr(closed_trades, "PAGES", 20)
        assert await record(fixture, connection) == 1
        async with fixture.runtime.db.sessions() as session:
            cursor = await session.get(
                ClosedTradeCursorRow, (fixture.owner, connection), populate_existing=True
            )
            assert cursor is not None and cursor.complete
        assert [row.position_id for row in await ledger(fixture, connection)] == ["p-1", "p-2"]
    finally:
        await retire(fixture, connection)
        await fixture.close()
