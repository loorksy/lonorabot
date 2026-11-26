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
    **request: Any,
) -> Any:
    row = journal(
        "op-" + uuid4().hex[:10],
        {"action": action, "symbol": "XAUUSD", **request},
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


def money(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """The count and money of each row, without its outcomes and R."""
    keys = ("label", "currency", "count", "net_realized_pnl", "unpriced")
    return [{key: row[key] for key in keys if key in row} for row in rows]


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
        assert money(block["closed_trades"]) == [
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
        assert money(block["closed_trades"]) == [
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


@pytest.mark.asyncio
async def test_a_netting_add_counts_its_label_and_unknown_pnl_is_never_zero() -> None:
    database()
    from check_streaming import Fixture
    from lonora_trading.statistics import statistics_block

    fixture = await Fixture().open()
    connection = ""
    try:
        agent = await fixture.agent("Adds", supervised=True)
        connection = await simulation(fixture, [])
        async with fixture.runtime.db.sessions() as session, session.begin():
            session.add(
                entry(fixture, connection, agent["id"], "buy", label="breakout", order="n-1")
            )
            # An add to the open netting position: an entry action, not its opening.
            session.add(
                entry(fixture, connection, agent["id"], "buy", label="scale_in", order="a-7")
            )
            session.add(entry(fixture, connection, agent["id"], "sell", label="fade", order="f-1"))
        await add_history(
            fixture,
            connection,
            deal("n-1", "IN", "BUY", minutes=9),
            deal("n-1", "IN", "BUY", minutes=8, order="a-7"),
            deal("n-1", "OUT", "SELL", volume="0.2", minutes=7, profit="6"),
            deal("f-1", "IN", "SELL", minutes=6),
            deal("f-1", "OUT", "BUY", minutes=5, profit=None),
        )
        assert await record(fixture, connection) == 2
        async with fixture.runtime.db.sessions() as session:
            block = await statistics_block(session, fixture.owner, agent["id"])
        assert money(block["closed_trades"]) == [
            {"label": "breakout", "currency": "USD", "count": 1, "net_realized_pnl": "6"},
            # Every trade of the row has an unknown P&L: no net, never "0".
            {
                "label": "fade",
                "currency": "USD",
                "count": 1,
                "net_realized_pnl": None,
                "unpriced": 1,
            },
        ]
        assert block["management"] == [{"label": "scale_in", "count": 1}]
    finally:
        await retire(fixture, connection)
        await fixture.close()


@pytest.mark.asyncio
async def test_r_groups_and_the_team_scope_of_lonora_and_a_team_agent() -> None:
    """R per group from the journaled stop; wins shown with their sample. A team agent
    sees only its own unless it asks for the team, which combines every agent's closes;
    Lonora sees the team per agent, with the owner's own tickets as agent null."""
    database()
    from check_streaming import Fixture
    from lonora_contracts.execution_quality import PerformanceRead
    from lonora_db.personal_agent import ensure_personal_agent
    from lonora_trading.performance import performance_snapshot

    fixture = await Fixture().open()
    connection = ""
    try:
        gold = (await fixture.agent("Gold", supervised=True))["id"]
        silver = (await fixture.agent("Silver", supervised=True))["id"]
        async with fixture.runtime.db.sessions() as session, session.begin():
            lonora = (await ensure_personal_agent(session, fixture.owner)).id
        connection = await simulation(fixture, [])
        async with fixture.runtime.db.sessions() as session, session.begin():
            session.add_all(
                [
                    entry(
                        fixture,
                        connection,
                        gold,
                        "buy",
                        label="breakout",
                        order="g-1",
                        stop_loss="95",
                    ),
                    entry(fixture, connection, gold, "sell", label="breakout", order="g-2"),
                    entry(
                        fixture,
                        connection,
                        silver,
                        "buy",
                        label="fade",
                        order="s-1",
                        stop_loss="98",
                    ),
                ]
            )
        await add_history(
            fixture,
            connection,
            deal("g-1", "IN", "BUY", minutes=20, order="g-1", commission="-1"),
            deal("g-1", "OUT", "SELL", minutes=19, profit="20", price="110"),
            deal("g-2", "IN", "SELL", minutes=18, order="g-2"),
            deal("g-2", "OUT", "BUY", minutes=17, profit="-6", price="103"),
            deal("s-1", "IN", "BUY", minutes=16, order="s-1"),
            deal("s-1", "OUT", "SELL", minutes=15, profit="-2", price="99"),
            deal("m-1", "IN", "BUY", minutes=14),
            deal("m-1", "OUT", "SELL", minutes=13, profit="5", price="101"),
        )
        assert await record(fixture, connection) == 4

        async def read(agent: str, **params: Any) -> list[dict[str, Any]]:
            body = PerformanceRead(account_id=connection, **params)
            block = await performance_snapshot(fixture.runtime.db, fixture.owner, agent, body)
            return block["closed_trades"]

        # 10 of a 5 risk is 2 R; the net, 19 after commission, is 1.9 R. No stop: no R.
        assert await read(gold) == [
            {
                "label": "breakout",
                "currency": "USD",
                "count": 2,
                "outcomes": {"wins": 1, "losses": 1, "flat": 0, "of": 2},
                "net_realized_pnl": "13",
                "r": {
                    "n": 1,
                    "mean": "1.9",
                    "sum": "1.9",
                    "mean_win": "1.9",
                    "mean_loss": None,
                    "unknown": {"no_initial_stop": 1},
                },
            }
        ]
        assert [(row["side"], row["count"]) for row in await read(gold, group_by="side")] == [
            ("buy", 1),
            ("sell", 1),
        ]
        assert [
            (row["label"], row["symbol"]) for row in await read(gold, group_by="label_symbol")
        ] == [("breakout", "XAUUSD")]
        assert set((await read(gold, group_by="session"))[0]) >= {"session", "count", "r"}
        assert await read(gold, since=utcnow()) == []
        # The team for a team agent: every agent's closes combined, never the owner's.
        team = await read(gold, scope="team")
        assert [(row["label"], row["count"]) for row in team] == [("breakout", 2), ("fade", 1)]
        assert team[1]["r"]["mean"] == "-0.5" and "agent_id" not in team[0]
        # Lonora: per agent, and the owner's own ticket as agent null.
        lead = await read(lonora, scope="team")
        assert [(row["agent_id"], row["label"], row["count"]) for row in lead] == [
            (gold, "breakout", 2),
            (silver, "fade", 1),
            (None, "unlabelled", 1),
        ]
        assert await read(lonora) == []
    finally:
        await retire(fixture, connection)
        await fixture.close()
