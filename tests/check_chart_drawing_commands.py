"""Isolated SQLite checks, or --postgres for native tools on an explicit disposable DB.

PostgreSQL mode uses imported simulation candles only; neither mode submits orders.
"""

import asyncio
from unittest.mock import patch

from lonora_charts.state import update_chart
from lonora_contracts.chart import ChartState
from lonora_core.user_error import LonoraError
from lonora_db.client import Database
from lonora_db.cloud_charts import CloudChartRepository
from lonora_db.schema import Base, BrokerSessionRow, EventRow, OwnerRow, TradingJournalRow
from lonora_tools.chart_state import apply_drawing_operations
from sqlalchemy import func, select


async def main():
    db = Database.connect("sqlite+aiosqlite:///:memory:")
    repository = CloudChartRepository()
    try:
        async with db.engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)
        async with db.sessions() as session, session.begin():
            session.add(
                OwnerRow(id="owner", email="isolated@example.invalid", password_hash="unused")
            )
            session.add(BrokerSessionRow(id="account", owner_id="owner", payload={}))
        charts = []
        for symbol in ("EURUSDm", "XAUUSDm", "BTCUSD#", "US500.cash"):
            for timeframe in ("15m", "1h"):
                state = ChartState(
                    account_id="account",
                    symbol=symbol,
                    timeframe=timeframe,
                    annotations=[{"type": "price", "price": 100, "id": "manual"}],
                )
                async with db.sessions() as session, session.begin():
                    row = await repository.create(session, "owner", state.model_dump(mode="json"))
                    charts.append((row.id, state))

        # Keep real transaction/update/inspection, replacing only the broker refresh.
        async def refresh(*args, **kwargs):
            return None

        with patch("lonora_charts.state.refresh_chart", refresh):
            for chart_id, state in charts:
                state.annotations = apply_drawing_operations(
                    state,
                    {
                        "operations": [
                            {
                                "op": "add",
                                "id": "scenario",
                                "annotation": {
                                    "type": "scenario",
                                    "start": {"time": "2026-10-01T00:00:00Z", "price": 100},
                                    "end": {"time": "2026-10-01T01:00:00Z", "price": 110},
                                    "stop": 95,
                                },
                            }
                        ]
                    },
                    agent_id="agent",
                    chart_id=chart_id,
                    mutation_id=chart_id,
                )
                saved = await update_chart(
                    db, None, "owner", chart_id, 1, state, actor_agent_id="agent"
                )
                assert saved["chart"]["version"] == 2
                assert saved["chart"]["payload"]["annotations"] == state.annotations
                try:
                    await update_chart(
                        db, None, "owner", chart_id, 1, state, actor_agent_id="agent"
                    )
                    raise AssertionError("stale mutation accepted")
                except LonoraError as error:
                    assert error.code == "version_conflict"
                tampered = state.model_copy(deep=True)
                tampered.annotations = tampered.annotations[1:]
                try:
                    await update_chart(
                        db, None, "owner", chart_id, 2, tampered, actor_agent_id="agent"
                    )
                    raise AssertionError("manual annotation removed")
                except LonoraError as error:
                    assert error.code == "chart_annotation_forbidden"
                try:
                    await update_chart(
                        db, None, "other-owner", chart_id, 2, state, actor_agent_id="agent"
                    )
                    raise AssertionError("cross-owner mutation accepted")
                except LonoraError as error:
                    assert error.code == "cloud_charts_not_found"
                # The authenticated owner retains the ability to edit/delete any own layer.
                async with db.sessions() as session, session.begin():
                    edited = await repository.update(
                        session, "owner", chart_id, tampered.model_dump(mode="json"), 2
                    )
                    assert edited.version == 3
        async with db.sessions() as session:
            assert await session.scalar(select(func.count()).select_from(TradingJournalRow)) == 0
            events = list(
                (
                    await session.scalars(
                        select(EventRow).where(EventRow.kind == "cloud_charts.updated")
                    )
                ).all()
            )
            assert len(events) == 16
            assert all(event.payload["version"] in (2, 3) for event in events)
        print(
            "PASS 8 isolated charts: exact symbols/timeframes, atomic versions, Agent/manual protection, owner isolation, update events; zero financial orders"
        )
    finally:
        await db.close()


async def postgres_commands():
    """Exercise native commands/effects and competing PG writers in a disposable DB."""
    from datetime import UTC, datetime, timedelta
    from uuid import uuid4

    from check_streaming import Fixture
    from lonora_adapter_kit.types import ToolCall
    from lonora_db.schema import CloudChartRow
    from lonora_tools.loader import load_tools

    fixture = await Fixture().open()
    connection_id = None
    try:
        agent = await fixture.agent("Drawing command PG verification")
        thread = await fixture.conversation(agent)
        actor = await fixture.lease(await fixture.run(agent, thread))
        connection = await fixture.request(
            "POST",
            "/trading/connections",
            {"provider": "simulation", "account_id": "drawing-" + uuid4().hex, "enabled": True},
        )
        connection_id = connection["id"]
        candles = [
            {
                "symbol": "XAUUSDm",
                "timeframe": "1h",
                "time": (datetime(2026, 10, 1, tzinfo=UTC) + timedelta(hours=index)).isoformat(),
                "open": "100",
                "high": "112",
                "low": "95",
                "close": "105",
            }
            for index in range(8)
        ]
        await fixture.request(
            "POST",
            "/trading/connections/" + connection_id + "/simulation",
            {
                "snapshot": {
                    "balance": "10000",
                    "currency": "USD",
                    "candles": {"XAUUSDm:1h": candles},
                }
            },
        )
        registry = load_tools()

        async def command(args, identity=None):
            return await registry.execute(
                ToolCall(id=identity or uuid4().hex, name="chart_annotate", arguments=args), actor
            )

        opened = await registry.execute(
            ToolCall(
                id="open-drawing-chart",
                name="chart_open",
                arguments={"account_id": connection_id, "symbol": "XAUUSDm", "timeframe": "1h"},
            ),
            actor,
        )
        chart_id = opened["chart"]["id"]
        add = {
            "chart_id": chart_id,
            "version": 1,
            "operations": [
                {
                    "op": "add",
                    "annotation": {
                        "type": "ray",
                        "start": {"time": candles[0]["time"], "price": 100},
                        "end": {"time": candles[1]["time"], "price": 105},
                    },
                }
            ],
        }
        accepted = await command(add, "stable-drawing-command")
        try:
            await command(add, "stable-drawing-command")
            raise AssertionError("duplicate mutation accepted")
        except LonoraError as error:
            assert error.code == "version_conflict"
        drawing_id = accepted["chart"]["payload"]["annotations"][0]["id"]
        async with fixture.runtime.db.sessions() as session:
            row = await CloudChartRepository().get(session, fixture.owner, chart_id)
            assert row.version == 2 and len(row.payload["annotations"]) == 1
        # A coherent batch fails before any write when its last operation is invalid.
        bad = {
            "chart_id": chart_id,
            "version": 2,
            "operations": [{"op": "delete", "id": drawing_id}, {"op": "delete", "id": "missing"}],
        }
        try:
            await command(bad)
            raise AssertionError("partial batch accepted")
        except LonoraError as error:
            assert error.code == "chart_annotation_not_found"
        async with fixture.runtime.db.sessions() as session:
            row = await CloudChartRepository().get(session, fixture.owner, chart_id)
            assert row.version == 2 and row.payload["annotations"][0]["id"] == drawing_id
        # Both native commands inspect revision 2; row locking admits exactly one write.
        race = [
            {
                "chart_id": chart_id,
                "version": 2,
                "operations": [
                    {
                        "op": "update",
                        "id": drawing_id,
                        "annotation": {"type": "price", "price": price},
                    }
                ],
            }
            for price in (101, 102)
        ]
        outcomes = await asyncio.gather(*(command(item) for item in race), return_exceptions=True)
        assert sum(isinstance(item, dict) for item in outcomes) == 1
        assert (
            sum(
                isinstance(item, LonoraError) and item.code == "version_conflict"
                for item in outcomes
            )
            == 1
        )
        async with fixture.runtime.db.sessions() as session:
            row = await CloudChartRepository().get(session, fixture.owner, chart_id)
            assert row.version == 3 and len(row.payload["annotations"]) == 1
            assert row.payload["annotations"][0]["id"] == drawing_id
            assert await session.scalar(select(func.count()).select_from(TradingJournalRow)) == 0
            assert (
                await session.scalar(
                    select(func.count())
                    .select_from(CloudChartRow)
                    .where(CloudChartRow.id == chart_id)
                )
                == 1
            )
        print(
            "PASS PostgreSQL duplicate command prevention, atomic invalid batch, row-lock/version writer race, stable drawing identity, zero orders"
        )
    finally:
        if connection_id:
            await fixture.request("DELETE", "/trading/connections/" + connection_id)
        await fixture.close()


if __name__ == "__main__":
    import sys

    asyncio.run(postgres_commands() if "--postgres" in sys.argv else main())
