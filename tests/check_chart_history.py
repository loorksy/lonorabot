"""Real PostgreSQL chart-history isolation, fencing and recovery regression checks."""

import asyncio
import logging
from datetime import UTC, datetime, timedelta
from io import StringIO
from unittest.mock import AsyncMock, patch
from uuid import uuid4

from check_streaming import Fixture
from lonora_charts.controller import render_scene
from lonora_charts.runtime import chart_runtime_tick, log_safe_exception, refresh_chart
from lonora_charts.state import inspect_chart
from lonora_contracts.chart import ChartState
from lonora_core.error_logging import safe_exception_message
from lonora_core.user_error import LonoraError
from lonora_db.schema import BrokerSessionRow, CloudChartRow


async def main() -> None:
    fixture = await Fixture().open()
    connection_id: str | None = None
    ids: list[str] = []
    try:
        connection = await fixture.request(
            "POST",
            "/trading/connections",
            {
                "provider": "simulation",
                "account_id": "history-" + uuid4().hex,
                "enabled": True,
            },
        )
        connection_id = str(connection["id"])
        pairs = [
            ("EURUSD", "15m", 15),
            ("XAUUSD", "4h", 240),
            ("US100.cash", "1h", 60),
            ("BTCUSD", "5m", 5),
        ]
        candles = {
            symbol + ":" + timeframe: [
                {
                    "symbol": symbol,
                    "timeframe": timeframe,
                    "time": (
                        datetime(2026, 10, 1, tzinfo=UTC) + timedelta(minutes=i * minutes)
                    ).isoformat(),
                    "open": str(100 + i),
                    "high": str(104 + i),
                    "low": str(99 + i),
                    "close": str(102 + i),
                }
                for i in range(60)
            ]
            for symbol, timeframe, minutes in pairs
        }
        await fixture.request(
            "POST",
            f"/trading/connections/{connection_id}/simulation",
            {
                "snapshot": {"balance": "10000", "currency": "USD", "candles": candles},
            },
        )
        # Use the actual broker without a gateway cache: no tick-driven redesign in this hotfix.
        brokers = fixture.runtime.services(fixture.owner).brokers
        rows = await asyncio.gather(
            *(
                fixture.request(
                    "POST",
                    "/charts",
                    {
                        "payload": {
                            "account_id": connection_id,
                            "symbol": symbol,
                            "timeframe": timeframe,
                            "indicators": [{"name": "rsi", "period": 14}],
                            "annotations": [],
                        }
                    },
                )
                for symbol, timeframe, _ in pairs
            )
        )
        ids.extend(str(row["id"]) for row in rows)
        results = await asyncio.gather(
            *(
                refresh_chart(
                    fixture.runtime.db,
                    brokers,
                    fixture.owner,
                    chart_id,
                    "history-concurrent",
                    force=True,
                )
                for chart_id in ids
            )
        )
        assert all(results)
        for chart_id, (symbol, timeframe, _) in zip(ids, pairs, strict=True):
            data = await inspect_chart(fixture.runtime.db, fixture.owner, chart_id)
            assert data["scene"]["symbol"] == symbol
            assert data["scene"]["timeframe"] == timeframe
            assert len(data["scene"]["candles"]) == 60
            assert data["chart"]["state"]["runtime_lease_until"] is None
        print(
            "PASS concurrent Forex, metal, exact index and crypto history charts retain independent scenes"
        )

        # A history reader may coexist with a different host's live stream lease.
        async with fixture.runtime.db.sessions() as session, session.begin():
            connection = await session.get(BrokerSessionRow, connection_id, with_for_update=True)
            assert connection is not None
            connection.state = {
                **connection.state,
                "market_stream_owner": "another-live-stream-host",
                "market_stream_until": (datetime.now(UTC) + timedelta(minutes=5)).isoformat(),
            }
        brokers.market = fixture.runtime.services(fixture.owner).market
        assert await refresh_chart(
            fixture.runtime.db,
            brokers,
            fixture.owner,
            ids[0],
            "independent-history-reader",
            force=True,
        )
        recovered = await inspect_chart(fixture.runtime.db, fixture.owner, ids[0])
        assert recovered["scene"] is not None and len(recovered["scene"]["candles"]) == 60
        async with fixture.runtime.db.sessions() as session:
            connection = await session.get(BrokerSessionRow, connection_id)
            assert connection is not None
            assert connection.state["market_stream_owner"] == "another-live-stream-host"
        brokers.market = None
        print(
            "PASS durable history snapshots load without borrowing or changing another host's stream lease"
        )

        target = ids[0]
        before = await inspect_chart(fixture.runtime.db, fixture.owner, target)

        async def unavailable(*args: object, **kwargs: object) -> dict[str, object]:
            raise RuntimeError("secret-token=must-never-appear-in-logs")

        logs = StringIO()
        handler = logging.StreamHandler(logs)
        logger = logging.getLogger("lonora_charts.runtime")
        logger.addHandler(handler)
        with patch("lonora_charts.runtime.render_scene", unavailable):
            assert await refresh_chart(
                fixture.runtime.db, brokers, fixture.owner, target, "history-failure", force=True
            )
        nested = LonoraError("broker_candles_unavailable", 503)
        nested.__cause__ = RuntimeError("SDK rejected short-secret abc12")
        log_safe_exception(logger, "chart_refresh_failed", nested, code=nested.code)
        provider_error = TimeoutError("history timed out abc12")
        diagnosed = LonoraError(
            "broker_candles_timeout",
            503,
            diagnostic_message=safe_exception_message(provider_error, ("abc12",)),
            diagnostic_type=type(provider_error).__name__,
        )
        diagnosed.__cause__ = provider_error
        log_safe_exception(logger, "chart_refresh_failed", diagnosed, code=diagnosed.code)
        logger.removeHandler(handler)
        assert "TimeoutError" in logs.getvalue() and "history timed out" in logs.getvalue()
        assert "abc12" not in logs.getvalue()
        assert "broker_candles_unavailable" in logs.getvalue()
        assert "RuntimeError" in logs.getvalue()
        assert "must-never-appear-in-logs" not in logs.getvalue()
        failed = await inspect_chart(fixture.runtime.db, fixture.owner, target)
        assert failed["scene"] is None and failed["code"] == "chart_refresh_unavailable"
        assert failed["chart"]["state"]["runtime_lease_until"] is None
        assert await refresh_chart(
            fixture.runtime.db, brokers, fixture.owner, target, "history-recovery", force=True
        )
        recovered = await inspect_chart(fixture.runtime.db, fixture.owner, target)
        assert recovered["scene"]["scene_version"] > before["scene"]["scene_version"]
        assert "error_code" not in recovered["chart"]["state"]
        print(
            "PASS failed provider refresh hides stale scene, releases fence and immediately recovers"
        )

        billing = AsyncMock(side_effect=LonoraError("broker_market_data_billing_required", 409))
        with patch("lonora_charts.runtime.render_scene", billing):
            assert await refresh_chart(
                fixture.runtime.db, brokers, fixture.owner, target, "billing-first", force=True
            )
            failed_billing = await inspect_chart(fixture.runtime.db, fixture.owner, target)
            assert failed_billing["scene"] is None
            assert failed_billing["code"] == "broker_market_data_billing_required"
            assert failed_billing["chart"]["state"]["runtime_lease_until"] is None
            assert not await refresh_chart(
                fixture.runtime.db, brokers, fixture.owner, target, "billing-cooldown"
            )
            assert billing.await_count == 1
            assert await refresh_chart(
                fixture.runtime.db, brokers, fixture.owner, target, "billing-manual", force=True
            )
            async with fixture.runtime.db.sessions() as session, session.begin():
                row = await session.get(CloudChartRow, target, with_for_update=True)
                assert row is not None
                row.state = {**row.state, "refresh_requested": True}
            assert await refresh_chart(
                fixture.runtime.db, brokers, fixture.owner, target, "billing-requested"
            )
            assert billing.await_count == 3
        # A changed configuration cannot inherit the old revision's retry fence.
        async with fixture.runtime.db.sessions() as session, session.begin():
            row = await session.get(CloudChartRow, target, with_for_update=True)
            assert row is not None
            row.version += 1
        assert await refresh_chart(
            fixture.runtime.db, brokers, fixture.owner, target, "billing-revision"
        )
        billing_recovered = await inspect_chart(fixture.runtime.db, fixture.owner, target)
        assert billing_recovered["scene"] is not None
        assert "scene_retry_at" not in billing_recovered["chart"]["state"]
        assert "error_code" not in billing_recovered["chart"]["state"]
        with patch("lonora_charts.runtime.render_scene", billing):
            assert await refresh_chart(
                fixture.runtime.db, brokers, fixture.owner, target, "billing-again", force=True
            )
        async with fixture.runtime.db.sessions() as session, session.begin():
            row = await session.get(CloudChartRow, target, with_for_update=True)
            assert row is not None
            row.state = {
                **row.state,
                "scene_retry_at": (datetime.now(UTC) - timedelta(seconds=1)).isoformat(),
                "scene_updated_at": (datetime.now(UTC) - timedelta(seconds=11)).isoformat(),
            }
        assert await refresh_chart(
            fixture.runtime.db, brokers, fixture.owner, target, "billing-expired"
        )
        assert (
            "scene_retry_at"
            not in (await inspect_chart(fixture.runtime.db, fixture.owner, target))["chart"][
                "state"
            ]
        )
        print(
            "PASS provider billing preserves exact failure, bounds automatic chart retries and recovers after expiry or revision"
        )

        async with fixture.runtime.db.sessions() as session, session.begin():
            row = await session.get(CloudChartRow, target, with_for_update=True)
            assert row is not None
            original = row.payload
            row.payload = {**original, "indicators": "malformed"}
            row.state = {**row.state, "refresh_requested": True}
        other_versions = {}
        async with fixture.runtime.db.sessions() as session, session.begin():
            for chart_id in ids[1:]:
                other = await session.get(CloudChartRow, chart_id, with_for_update=True)
                assert other is not None
                other_versions[chart_id] = other.state["scene_version"]
                other.state = {**other.state, "refresh_requested": True}
        await chart_runtime_tick(
            fixture.runtime.db, brokers, fixture.owner, "history-invalid", maintain_streams=False
        )
        invalid = await inspect_chart(fixture.runtime.db, fixture.owner, target)
        assert invalid["code"] == "chart_refresh_unavailable"
        assert invalid["chart"]["state"]["runtime_lease_until"] is None
        for chart_id in ids[1:]:
            other = await inspect_chart(fixture.runtime.db, fixture.owner, chart_id)
            assert other["scene"]["scene_version"] > other_versions[chart_id]
        async with fixture.runtime.db.sessions() as session, session.begin():
            row = await session.get(CloudChartRow, target, with_for_update=True)
            assert row is not None
            row.payload = original
        assert await refresh_chart(
            fixture.runtime.db, brokers, fixture.owner, target, "history-valid", force=True
        )
        print(
            "PASS malformed persisted chart fails safely without stopping other charts and recovers"
        )

        started, release = asyncio.Event(), asyncio.Event()

        async def blocked(manager: object, owner: str, state: ChartState) -> dict[str, object]:
            started.set()
            await release.wait()
            return await render_scene(brokers, owner, state)

        with patch("lonora_charts.runtime.render_scene", blocked):
            first = asyncio.create_task(
                refresh_chart(
                    fixture.runtime.db, brokers, fixture.owner, target, "history-owner", force=True
                )
            )
            await started.wait()
            second = await refresh_chart(
                fixture.runtime.db, brokers, fixture.owner, target, "history-competitor", force=True
            )
            assert second is False
            release.set()
            assert await first
        print(
            "PASS another runtime cannot refresh a chart while its unexpired resident fence is held"
        )
    finally:
        for chart_id in ids:
            await fixture.request("DELETE", "/charts/" + chart_id)
        if connection_id:
            await fixture.request("DELETE", "/trading/connections/" + connection_id)
        await fixture.close()


if __name__ == "__main__":
    asyncio.run(main())
