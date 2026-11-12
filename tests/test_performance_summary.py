"""Statistics per judgment label from broker-confirmed closes (mandate 5.5.4, 6.4).

"The system computes, per label, the count and net realized P&L from broker-confirmed
closes, and gives them to the agent on wake." A closed trade counts once, with its
whole realized P&L, under the label of its opening order, per account currency (never
added across currencies); management labels count without money. Only broker deals
make a profit number: an operation the owner settled (``resolved``) adds nothing. The
numbers equal the broker deals of the fixture. Runs on the real migrated PostgreSQL
schema (skipped without LONORA_DATABASE_URL).
"""

from datetime import timedelta
from decimal import Decimal
from typing import Any
from uuid import uuid4

import pytest
from lonora_contracts.domain import utcnow
from test_closed_trades import add_history, deal, record
from test_proactive_wakes import database, journal, retire, simulation


def entry(
    fixture: Any,
    connection: str,
    agent: str,
    action: str,
    *,
    label: str,
    order: str | None = None,
    status: str = "confirmed",
) -> Any:
    row = journal(
        "op-" + uuid4().hex[:10],
        {"action": action, "symbol": "XAUUSD"},
        agent_id=agent,
        status=status,
        updated_at=utcnow() - timedelta(minutes=30),
    )
    row.owner_id, row.account_id = fixture.owner, connection
    row.request = {**row.request, "account_id": connection}
    row.annotation = {"reason": "Fixture", "tolerance": None, "label": label}
    if order:
        row.result = {**row.result, "details": {**row.result["details"], "order_id": order}}
    return row


@pytest.mark.asyncio
async def test_statistics_per_label_equal_the_broker_deals() -> None:
    database()
    from check_streaming import Fixture
    from lonora_trading.statistics import statistics_block

    fixture = await Fixture().open()
    usd = eur = ""
    try:
        gold = await fixture.agent("Statistics", supervised=True)
        other = await fixture.agent("Someone else", supervised=True)
        usd = await simulation(fixture, [])
        eur = await simulation(fixture, [])
        from lonora_db.schema import TradingAccountRow

        async with fixture.runtime.db.sessions() as session, session.begin():
            account = await session.get(TradingAccountRow, eur, with_for_update=True)
            assert account is not None
            account.payload = {**account.payload, "currency": "EUR"}
            session.add_all(
                [
                    entry(fixture, usd, gold["id"], "buy", label="scale_in", order="u-1"),
                    entry(fixture, usd, gold["id"], "buy", label="scale_in", order="u-2"),
                    entry(fixture, usd, gold["id"], "sell", label="", order="u-3"),
                    entry(fixture, eur, gold["id"], "buy", label="scale_in", order="e-1"),
                    entry(fixture, usd, other["id"], "buy", label="scale_in", order="o-1"),
                    # Management labels: counted without money, confirmed only.
                    entry(fixture, usd, gold["id"], "modify_position", label="secure_then_add"),
                    entry(fixture, usd, gold["id"], "close_position", label="secure_then_add"),
                    entry(
                        fixture,
                        usd,
                        gold["id"],
                        "close_position",
                        label="partial_profit",
                        status="resolved",
                    ),
                    # An entry the owner settled as executed: no broker deal, no number.
                    entry(fixture, usd, gold["id"], "buy", label="settled", status="resolved"),
                ]
            )
        await add_history(
            fixture,
            usd,
            deal("u-1", "IN", "BUY", minutes=20, order="u-1", commission="-1"),
            deal("u-1", "OUT", "SELL", minutes=19, profit="30.5", swap="-0.5"),
            deal("u-2", "IN", "BUY", minutes=18, order="u-2"),
            deal("u-2", "OUT", "SELL", minutes=17, profit="-12"),
            deal("u-3", "IN", "SELL", minutes=16, order="u-3"),
            deal("u-3", "OUT", "BUY", minutes=15, profit="4"),
            deal("o-1", "IN", "BUY", minutes=14, order="o-1"),
            deal("o-1", "OUT", "SELL", minutes=13, profit="100"),
            # The owner's own terminal trade: no agent's statistics.
            deal("m-1", "IN", "BUY", minutes=12),
            deal("m-1", "OUT", "SELL", minutes=11, profit="55"),
        )
        await add_history(
            fixture,
            eur,
            deal("e-1", "IN", "BUY", minutes=20, order="e-1"),
            deal("e-1", "OUT", "SELL", minutes=10, profit="7"),
        )
        assert await record(fixture, usd) == 5 and await record(fixture, eur) == 1
        async with fixture.runtime.db.sessions() as session:
            block = await statistics_block(session, fixture.owner, gold["id"])
            only_usd = await statistics_block(session, fixture.owner, gold["id"], account_id=usd)
        assert block["closed_trades"] == [
            # 30.5 - 0.5 - 1 = 29; 29 - 12 = 17 (USD); EUR is its own row.
            {"label": "scale_in", "currency": "USD", "count": 2, "net_realized_pnl": "17"},
            {"label": "scale_in", "currency": "EUR", "count": 1, "net_realized_pnl": "7"},
            {"label": "unlabelled", "currency": "USD", "count": 1, "net_realized_pnl": "4"},
        ]
        assert block["management"] == [{"label": "secure_then_add", "count": 2}]
        assert [row["currency"] for row in only_usd["closed_trades"]] == ["USD", "USD"]
        assert "insufficient" not in str(block)
        assert sum(Decimal(row["net_realized_pnl"]) for row in only_usd["closed_trades"]) == 21
    finally:
        await retire(fixture, usd, eur)
        await fixture.close()


@pytest.mark.asyncio
async def test_a_close_without_broker_profit_is_counted_and_adds_nothing() -> None:
    database()
    from check_streaming import Fixture
    from lonora_trading.statistics import statistics_block

    fixture = await Fixture().open()
    connection = ""
    try:
        agent = await fixture.agent("Unpriced", supervised=True)
        connection = await simulation(fixture, [])
        async with fixture.runtime.db.sessions() as session, session.begin():
            session.add(entry(fixture, connection, agent["id"], "buy", label="breakout", order="x"))
            session.add(entry(fixture, connection, agent["id"], "buy", label="breakout", order="y"))
        await add_history(
            fixture,
            connection,
            deal("x", "IN", "BUY", minutes=9, order="x"),
            deal("x", "OUT", "SELL", minutes=8, profit=None),
            deal("y", "IN", "BUY", minutes=7, order="y"),
            deal("y", "OUT", "SELL", minutes=6, profit="-3.25"),
        )
        assert await record(fixture, connection) == 2
        async with fixture.runtime.db.sessions() as session:
            block = await statistics_block(session, fixture.owner, agent["id"])
        assert block["closed_trades"] == [
            {
                "label": "breakout",
                "currency": "USD",
                "count": 2,
                "net_realized_pnl": "-3.25",
                "unpriced": 1,
            }
        ]
    finally:
        await retire(fixture, connection)
        await fixture.close()
