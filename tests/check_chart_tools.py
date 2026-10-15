"""Real PG/shared chart controller checks with explicitly imported simulation candles."""

import asyncio
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from io import BytesIO
from pathlib import Path
from typing import Any
from uuid import uuid4
from xml.etree.ElementTree import fromstring

from check_streaming import Fixture
from lonora_adapter_kit.types import ToolCall
from lonora_core.user_error import LonoraError
from lonora_db.schema import CloudChartRow
from lonora_security.runtime_storage import confined_path
from lonora_tools.context import ToolContext
from lonora_tools.loader import load_tools
from PIL import Image
from sqlalchemy import func, select


async def main() -> None:
    fixture = await Fixture().open()
    connection_id: str | None = None
    snapshot_paths: list[Path] = []
    try:
        agent = await fixture.agent("Chart tool fixture")
        thread = await fixture.conversation(agent)
        context = await fixture.lease(await fixture.run(agent, thread))
        connection = await fixture.request(
            "POST",
            "/trading/connections",
            {
                "provider": "simulation",
                "account_id": "chart-fixture-" + uuid4().hex,
                "enabled": True,
            },
        )
        connection_id = connection["id"]
        assert isinstance(connection_id, str)
        candles: dict[str, list[dict[str, Any]]] = {}
        for symbol in ("XAUUSD", "EURUSD"):
            for timeframe, minutes in (("1h", 60), ("15m", 15)):
                candles[symbol + ":" + timeframe] = [
                    {
                        "symbol": symbol,
                        "timeframe": timeframe,
                        "time": (
                            datetime(2026, 10, 1, tzinfo=UTC) + timedelta(minutes=index * minutes)
                        ).isoformat(),
                        "open": str(100 + index),
                        "high": str(104 + index),
                        "low": str(99 + index),
                        "close": str(102 + index),
                    }
                    for index in range(60)
                ]
        await fixture.request(
            "POST",
            "/trading/connections/" + connection_id + "/simulation",
            {"snapshot": {"balance": "10000", "currency": "USD", "candles": candles}},
        )
        registry = load_tools()

        async def call(
            name: str,
            arguments: dict[str, Any],
            *,
            identity: str | None = None,
            actor: ToolContext = context,
            read_only: bool = False,
        ) -> dict[str, Any]:
            return await registry.execute(
                ToolCall(id=identity or uuid4().hex, name=name, arguments=arguments),
                actor,
                read_only=read_only,
            )

        state = {"account_id": connection_id, "symbol": "XAUUSD", "timeframe": "1h"}
        opened = await call("chart_open", state, identity="stable-chart-open")
        reopened = await call("chart_open", state, identity="stable-chart-open")
        chart_id = opened["chart"]["id"]
        assert reopened["chart"]["id"] == chart_id
        async with fixture.runtime.db.sessions() as session:
            assert (
                await session.scalar(
                    select(func.count())
                    .select_from(CloudChartRow)
                    .where(CloudChartRow.id == chart_id)
                )
                == 1
            )
        persisted = await call("chart_inspect", {"chart_id": chart_id}, read_only=True)
        assert len(persisted["scene"]["candles"]) == 60
        assert persisted["chart"]["state"]["scene_revision"] == persisted["chart"]["version"]
        directory = await call("chart_list", {"thread_id": thread["id"]}, read_only=True)
        entry = next(item for item in directory["charts"] if item["chart_id"] == chart_id)
        assert entry["symbol"] == "XAUUSD" and "scene" not in entry and "payload" not in entry
        print(
            "PASS chart_open replay returns one persistent chart and inspect reads its saved scene"
        )

        version = persisted["chart"]["version"]
        changed = await call(
            "chart_set_symbol", {"chart_id": chart_id, "version": version, "symbol": "EURUSD"}
        )
        assert changed["scene"]["symbol"] == "EURUSD"
        changed = await call(
            "chart_set_timeframe",
            {"chart_id": chart_id, "version": changed["chart"]["version"], "timeframe": "15m"},
        )
        assert changed["scene"]["timeframe"] == "15m"
        changed = await call(
            "chart_add_indicator",
            {
                "chart_id": chart_id,
                "version": changed["chart"]["version"],
                "name": "RSI",
                "period": 14,
            },
        )
        values = await call(
            "chart_read_indicator",
            {"chart_id": chart_id, "name": "rsi", "period": 14, "tail": 60},
            read_only=True,
        )
        assert len(values["times"]) == 60 and len(values["series"]["value"]) == 60
        assert values["series"]["value"][:14] == [None] * 14
        assert values["series"]["value"][-1] == 100.0
        assert values["version"] == changed["chart"]["version"] and values["symbol"] == "EURUSD"
        print(
            "PASS symbol/timeframe/indicator edits persist; read_indicator uses matching saved scene and real warmup"
        )

        changed = await call(
            "chart_annotate",
            {
                "chart_id": chart_id,
                "version": changed["chart"]["version"],
                "annotation": {"type": "price", "price": 125, "label": "Explicit fixture support"},
            },
        )
        assert changed["scene"]["annotations"][0]["price"] == 125
        picture = await call("chart_snapshot", {"chart_id": chart_id, "format": "svg"})
        path = confined_path(context.artifact_root, picture["payload"]["key"])
        snapshot_paths.append(path)
        svg = fromstring(path.read_text())
        labels = " ".join(svg.itertext())
        assert "rsi(14)" in labels and "Explicit fixture support" in labels and "EURUSD" in labels
        assert picture["scene_revision"] == changed["chart"]["version"]
        assert picture["payload"]["media_type"] == "image/svg+xml"
        assert any(element.tag.endswith("polyline") for element in svg.iter())
        legacy = await call(
            "chart_snapshot", {"account_id": connection_id, "symbol": "XAUUSD", "timeframe": "1h"}
        )
        snapshot_paths.append(confined_path(context.artifact_root, legacy["payload"]["key"]))
        assert legacy["payload"]["media_type"] == "image/png"
        with Image.open(BytesIO(snapshot_paths[-1].read_bytes())) as png:
            assert png.format == "PNG" and png.width == 960
        print(
            "PASS persisted scene snapshot includes configured indicators/annotations and legacy candle snapshot remains available"
        )
        changed = await call(
            "chart_remove_indicator",
            {
                "chart_id": chart_id,
                "version": changed["chart"]["version"],
                "name": "rsi",
                "period": 14,
            },
        )
        assert changed["scene"]["indicators"] == []
        assert changed["chart"]["payload"]["annotations"][0]["price"] == 125
        print("PASS annotations and indicator removal preserve unrelated chart state")

        async def fails(name: str, arguments: dict[str, Any], code: str, **kwargs: Any):
            try:
                await call(name, arguments, **kwargs)
            except LonoraError as error:
                assert error.code == code, (error.code, code)
            else:
                raise AssertionError("Expected " + code)

        await fails(
            "chart_set_symbol",
            {"chart_id": chart_id, "version": version, "symbol": "XAUUSD"},
            "version_conflict",
        )
        await fails(
            "chart_inspect",
            {"chart_id": chart_id},
            "agent_not_found",  # Agent ownership now fails before any chart lookup.
            actor=replace(context, owner_id="unrelated-owner"),
        )
        await fails(
            "chart_set_symbol",
            {"chart_id": chart_id, "version": changed["chart"]["version"], "symbol": "XAUUSD"},
            "tool_not_allowed",
            read_only=True,
        )
        await fails(
            "chart_set_symbol",
            {"chart_id": chart_id, "version": changed["chart"]["version"], "symbol": "XAUUSD"},
            "stale_lease",
            actor=replace(
                context, lease=context.lease.model_copy(update={"fence": context.lease.fence + 1})
            ),
        )
        assert (await call("chart_inspect", {"chart_id": chart_id}))["chart"]["version"] == changed[
            "chart"
        ]["version"]
        print("PASS stale edits/leases, unrelated owners and read-only mutations are rejected")

        results = await asyncio.gather(
            call(
                "chart_set_timeframe",
                {"chart_id": chart_id, "version": changed["chart"]["version"], "timeframe": "1h"},
            ),
            call(
                "chart_set_symbol",
                {"chart_id": chart_id, "version": changed["chart"]["version"], "symbol": "XAUUSD"},
            ),
            return_exceptions=True,
        )
        assert sum(isinstance(result, dict) for result in results) == 1
        assert (
            sum(
                isinstance(result, LonoraError) and result.code == "version_conflict"
                for result in results
            )
            == 1
        )
        print("PASS concurrent chart edits with the same version accept exactly one writer")
    finally:
        if connection_id:
            await fixture.request("DELETE", "/trading/connections/" + connection_id)
        await fixture.close()
        for path in snapshot_paths:
            path.unlink(missing_ok=True)
            path.parent.rmdir()


if __name__ == "__main__":
    asyncio.run(main())
