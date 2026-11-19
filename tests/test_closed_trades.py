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
from lonora_trading.closed_trades import position_deal, realized, trades
from test_proactive_wakes import database, journal, retire, set_positions, simulation


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
        # A position id is the ticket of the order that opened it.
        "orderId": order or (position if entry == "IN" else "order-" + uuid4().hex[:8]),
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
    assert position_deal(deal("P", "OUT", "SELL"))
    assert not position_deal({**deal("P", "IN", "BUY"), "type": "DEAL_TYPE_BALANCE"})
    assert not position_deal({**deal("P", "IN", "BUY"), "positionId": None})
    # A charge booked on the position is the position's; it only lowers the P&L.
    charge = {**deal("P", "IN", "BUY"), "type": "DEAL_TYPE_COMMISSION", "entryType": None}
    assert position_deal(charge)
    assert realized([*deals, {**charge, "profit": "-2"}]) == Decimal("11.75")
    assert realized([*deals, {**charge, "profit": "2"}]) == Decimal("13.75")
    # A broker time without a zone is UTC, so mixed times still sort.
    naive = {**deal("P", "OUT", "SELL"), "time": "2099-01-01T00:00:00"}
    closed, running = trades("P", [deal("P", "IN", "BUY"), naive])
    assert closed == [] and running is not None and running.opening is not None


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


async def send(fixture: Any, context: Any, name: str, **arguments: Any) -> dict[str, Any]:
    """The agent's own order through the door: approved by the owner when it asks."""
    from lonora_adapter_kit.types import ToolCall
    from lonora_db.schema import RunRow
    from lonora_tools.loader import load_tools

    tool_call = ToolCall(id=name + "-" + uuid4().hex, name=name, arguments=arguments)
    answer = await load_tools().execute(tool_call, context)
    if not answer.get("approval_id") or answer.get("status") == "confirmed":
        return answer
    async with fixture.runtime.db.sessions() as session, session.begin():
        run = await session.get(RunRow, context.lease.run_id, with_for_update=True)
        assert run is not None
        run.status = "waiting_input"
    approved = await fixture.client.post(
        f"/api/trading/approvals/{answer['approval_id']}/decision", json={"decision": "approve"}
    )
    assert approved.status_code == 200, approved.text
    async with fixture.runtime.db.sessions() as session, session.begin():
        run = await session.get(RunRow, context.lease.run_id, with_for_update=True)
        assert run is not None
        run.status = "running"
    sent = await load_tools().execute(tool_call, context)
    return {**sent, **(sent["results"][0] if sent.get("results") else {})}


@pytest.mark.asyncio
async def test_every_close_of_the_test_broker_creates_exactly_one_row() -> None:
    database()
    from check_streaming import Fixture
    from lonora_db.schema import BrokerDealRow, ClosedTradeCursorRow
    from sqlalchemy import delete, func, select

    fixture = await Fixture().open()
    connection = ""
    try:
        connection = await simulation(fixture, [])
        await quote(fixture, connection, "100", "101")
        agent = await fixture.agent("Ledger", supervised=True)
        context = await fixture.lease(await fixture.run(agent, await fixture.conversation(agent)))
        opened = await send(
            fixture,
            context,
            "trade_execute",
            action="buy",
            symbol="XAUUSD",
            volume="0.2",
            stop_loss="95",
            account_id=connection,
            tolerance="5",
            reason="Fixture request",
        )
        assert opened["status"] == "confirmed", opened
        ticket = opened["broker_id"]
        assert await record(fixture, connection) == 0 and await ledger(fixture, connection) == []
        # A partial close leaves volume at the broker: not a closed trade.
        await quote(fixture, connection, "103", "104")
        partial = await send(
            fixture,
            context,
            "trade_execute",
            action="close_position",
            symbol="XAUUSD",
            position_id=ticket,
            volume="0.1",
            account_id=connection,
        )
        assert partial["status"] == "confirmed", partial
        assert await record(fixture, connection) == 0 and await ledger(fixture, connection) == []
        # The rest closes: volume zero at the broker, one row.
        await quote(fixture, connection, "99", "100")
        closed = await send(
            fixture,
            context,
            "trade_execute",
            action="close_position",
            symbol="XAUUSD",
            position_id=ticket,
            account_id=connection,
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
        # A restarted process: no broker connection survives, only the database.
        fixture.runtime.services(fixture.owner).brokers.connections.clear()
        assert await record(fixture, connection) == 0
        assert len(await ledger(fixture, connection)) == 1
        async with fixture.runtime.db.sessions() as session:
            kept = await session.scalar(
                select(func.count())
                .select_from(BrokerDealRow)
                .where(BrokerDealRow.account_id == connection)
            )
            assert kept == 0  # The closed trade's deals live on its row only.
    finally:
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


async def journaled(fixture: Any, connection: str, agent: str, action: str, order: str) -> str:
    identity = action + "-" + uuid4().hex[:8]
    async with fixture.runtime.db.sessions() as session, session.begin():
        row = journal(identity, {"action": action, "symbol": "XAUUSD"}, agent_id=agent)
        row.owner_id, row.account_id = fixture.owner, connection
        row.request = {**row.request, "account_id": connection}
        row.result = {**row.result, "details": {**row.result["details"], "order_id": order}}
        session.add(row)
    return identity


def held(ticket: str, side: str = "buy", volume: str = "0.1") -> Position:
    return Position(
        id=ticket, symbol="XAUUSD", side=side, volume=Decimal(volume), open_price=Decimal(100)
    )


@pytest.mark.asyncio
async def test_reversals_partial_reads_and_positions_older_than_the_ledger() -> None:
    database()
    from check_streaming import Fixture
    from lonora_db.schema import BrokerDealRow
    from sqlalchemy import func, select
    from sqlalchemy.dialects.postgresql import insert

    fixture = await Fixture().open()
    connection = ""
    try:
        gold = await fixture.agent("Opens", supervised=True)
        euro = await fixture.agent("Reverses", supervised=True)
        connection = await simulation(fixture, [held("net-1"), held("half-1", volume="0.2")])
        opened = await journaled(fixture, connection, gold["id"], "buy", "net-1")
        reversing = await journaled(fixture, connection, euro["id"], "sell", "rev-9")
        old = await journaled(fixture, connection, gold["id"], "buy", "old-1")
        await add_history(
            fixture,
            connection,
            # A netting position reversed through zero: 0.1 long, then a 0.3 sell.
            deal("net-1", "IN", "BUY", minutes=30),
            deal("net-1", "INOUT", "SELL", volume="0.3", minutes=25, order="rev-9", profit="5"),
            # Half closed; the position read below is missing it although 0.1 is open.
            deal("half-1", "IN", "BUY", volume="0.2", minutes=24),
            deal("half-1", "OUT", "SELL", minutes=23, profit="1"),
            # Opened before the ledger's first read: only its exit is in history.
            deal("old-1", "OUT", "SELL", minutes=22, profit="9"),
            # Also older than the ledger, and reversed: 0.1 long taken to 0.2 short.
            deal("anc-1", "INOUT", "SELL", volume="0.3", minutes=21, profit="4"),
        )
        await set_positions(
            fixture,
            connection,
            [held("net-1", side="sell", volume="0.2"), held("anc-1", side="sell", volume="0.2")],
        )
        assert await record(fixture, connection) == 3
        rows = {
            (row.position_id, row.closing_deal_id): row for row in await ledger(fixture, connection)
        }
        first = next(row for (ticket, _), row in rows.items() if ticket == "net-1")
        # The reversal closed the first trade: its opener's, 0.1 long, the reversal's money.
        assert first.agent_id == gold["id"] and first.opening_operation_id == opened
        assert first.side == "buy" and Decimal(first.volume) == Decimal("0.1")
        assert Decimal(first.realized_pnl) == 5
        # A position the broker does not list whose exits do not cover its entries is
        # not closed; one older than the ledger is closed with an unknown P&L.
        assert not any(ticket == "half-1" for ticket, _ in rows)
        older = next(row for (ticket, _), row in rows.items() if ticket == "old-1")
        assert older.agent_id == gold["id"] and older.opening_operation_id == old
        assert older.realized_pnl is None
        # The reversal closed a trade the ledger never saw open: recorded, the owner's
        # by the position's ticket, with its volume and P&L unknown.
        unseen = next(row for (ticket, _), row in rows.items() if ticket == "anc-1")
        assert unseen.agent_id is None and unseen.side == "buy"
        assert unseen.volume is None and unseen.realized_pnl is None
        # The reversed trade closes; the rest of the half-closed one closes too.
        await add_history(
            fixture,
            connection,
            deal("net-1", "OUT", "BUY", volume="0.2", minutes=5, profit="-3", commission="-1"),
            deal("half-1", "OUT", "SELL", minutes=4, profit="2"),
            deal("anc-1", "OUT", "BUY", volume="0.2", minutes=3, profit="-1"),
        )
        await set_positions(fixture, connection, [])
        assert await record(fixture, connection) == 3
        rows = {
            (row.position_id, row.closing_deal_id): row for row in await ledger(fixture, connection)
        }
        second = [
            row for (ticket, _), row in rows.items() if ticket == "net-1" and row.id != first.id
        ]
        assert len(second) == 1 and second[0].id != first.id
        assert second[0].agent_id == euro["id"] and second[0].opening_operation_id == reversing
        assert second[0].side == "sell" and Decimal(second[0].volume) == Decimal("0.2")
        assert Decimal(second[0].realized_pnl) == -4
        half = next(row for (ticket, _), row in rows.items() if ticket == "half-1")
        assert Decimal(half.realized_pnl) == 3 and Decimal(half.volume) == Decimal("0.2")
        # A deal another process re-read after its trade was recorded is dropped.
        async with fixture.runtime.db.sessions() as session, session.begin():
            stale = half.deals[0]
            await session.execute(
                insert(BrokerDealRow).values(
                    owner_id=fixture.owner,
                    account_id=connection,
                    deal_id=stale["id"],
                    position_id="half-1",
                    time=utcnow(),
                    payload=stale,
                )
            )
        assert await record(fixture, connection) == 0
        async with fixture.runtime.db.sessions() as session:
            kept = await session.scalar(
                select(func.count())
                .select_from(BrokerDealRow)
                .where(BrokerDealRow.account_id == connection)
            )
        reversed_ = [row for row in await ledger(fixture, connection) if row.position_id == "anc-1"]
        assert len(reversed_) == 2
        after = next(row for row in reversed_ if row.volume is not None)
        assert after.side == "sell" and Decimal(after.realized_pnl) == -1
        assert kept == 0 and len(await ledger(fixture, connection)) == 6
    finally:
        await retire(fixture, connection)
        await fixture.close()
