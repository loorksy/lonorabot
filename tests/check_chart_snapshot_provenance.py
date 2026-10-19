"""Native snapshot provenance/recovery checks on an explicit disposable PostgreSQL DB."""

import asyncio
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from io import BytesIO
from pathlib import Path
from typing import Any
from uuid import uuid4

from check_streaming import Fixture
from lonora_adapter_kit.types import ToolCall
from lonora_core.user_error import LonoraError
from lonora_db.artifacts import ArtifactRepository
from lonora_security.runtime_storage import confined_path
from lonora_tools.context import ToolContext
from lonora_tools.loader import load_tools
from PIL import Image


async def main() -> None:
    fixture = await Fixture().open()
    connection_id: str | None = None
    paths: list[Path] = []
    try:
        agent = await fixture.agent("Snapshot provenance checks")
        thread = await fixture.conversation(agent)
        actor = await fixture.lease(await fixture.run(agent, thread))
        registry = load_tools()

        async def call(
            name: str,
            args: dict[str, Any],
            identity: str | None = None,
            context: ToolContext = actor,
        ) -> dict[str, Any]:
            return await registry.execute(
                ToolCall(id=identity or uuid4().hex, name=name, arguments=args), context
            )

        async def fails(
            args: dict[str, Any], identity: str, code: str, context: ToolContext = actor
        ) -> None:
            try:
                await call("chart_snapshot", args, identity, context)
                raise AssertionError("expected " + code)
            except LonoraError as error:
                assert error.code == code

        connection = await fixture.request(
            "POST",
            "/trading/connections",
            {"provider": "simulation", "account_id": "snapshot-" + uuid4().hex, "enabled": True},
        )
        connection_id = str(connection["id"])
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
                    "candles": {
                        symbol + ":" + timeframe: [
                            {**bar, "symbol": symbol, "timeframe": timeframe} for bar in candles
                        ]
                        for symbol in ("EURUSDm", "XAUUSDm", "US500.cash", "BTCUSD#")
                        for timeframe in ("15m", "1h")
                    },
                }
            },
        )
        opened = await call(
            "chart_open",
            {
                "account_id": connection_id,
                "symbol": "XAUUSDm",
                "timeframe": "1h",
                "annotations": [
                    {
                        "type": "scenario",
                        "start": {"time": candles[0]["time"], "price": 100},
                        "end": {"time": candles[1]["time"], "price": 110},
                        "stop": 95,
                        "label": "Original scenario",
                    }
                ],
            },
        )
        chart_id = opened["chart"]["id"]
        originals: dict[str, dict[str, Any]] = {}
        original_bytes: dict[str, bytes] = {}
        for fmt in ("svg", "png"):
            result = await call(
                "chart_snapshot", {"chart_id": chart_id, "format": fmt}, "saved-" + fmt
            )
            originals[fmt] = result
            path = confined_path(actor.artifact_root, result["payload"]["key"])
            paths.append(path)
            original_bytes[fmt] = path.read_bytes()
            descriptor = result["chart_snapshot"]
            assert descriptor["source"] == "saved_semantic_scene" and descriptor["format"] == fmt
            assert descriptor["account_id"] == connection_id and descriptor["chart_id"] == chart_id
            assert descriptor["data_revision"] == opened["scene"]["data_revision"]
            assert (
                descriptor["scene_revision"] == 1
                and descriptor["scene_version"] == opened["scene"]["scene_version"]
            )
            assert datetime.fromisoformat(descriptor["last_candle_at"]) == datetime.fromisoformat(
                candles[-1]["time"]
            )
            assert result["state"]["chart_snapshot"] == descriptor
            if fmt == "svg":
                assert (
                    b"Original scenario" in original_bytes[fmt] and b"<line" in original_bytes[fmt]
                )
            else:
                with Image.open(BytesIO(original_bytes[fmt])) as png:
                    assert png.format == "PNG" and "Original scenario" in png.info["Description"]
        await call(
            "chart_annotate",
            {
                "chart_id": chart_id,
                "version": 1,
                "annotation": {"type": "price", "price": 120, "label": "New revision"},
            },
        )
        for fmt in ("svg", "png"):
            replay = await call(
                "chart_snapshot", {"chart_id": chart_id, "format": fmt}, "saved-" + fmt
            )
            assert replay["id"] == originals[fmt]["id"]
            assert replay["chart_snapshot"] == originals[fmt]["chart_snapshot"]
            assert replay["scene_revision"] == 1
            assert (
                confined_path(actor.artifact_root, replay["payload"]["key"]).read_bytes()
                == original_bytes[fmt]
            )
        semantic_replay = await call(
            "chart_snapshot",
            {"chart_id": chart_id, "renderer": "semantic", "locale": "ar"},
            "saved-png",
        )
        assert semantic_replay["chart_snapshot"] == originals["png"]["chart_snapshot"]
        await fails({"chart_id": chart_id, "format": "png"}, "saved-svg", "artifact_nonce_conflict")
        await fails(
            {"account_id": connection_id, "symbol": "XAUUSDm", "timeframe": "1h"},
            "saved-png",
            "artifact_nonce_conflict",
        )
        await fails(
            {"chart_id": chart_id},
            "saved-png",
            "artifacts_not_found",
            replace(actor, thread_id="different-thread"),
        )
        other_agent = await fixture.agent("Snapshot isolated agent")
        await fails(
            {"chart_id": chart_id},
            "saved-png",
            "artifacts_not_found",
            replace(actor, agent_id=other_agent["id"]),
        )
        await fails(
            {"chart_id": chart_id},
            "saved-png",
            "stale_lease",
            replace(actor, lease=actor.lease.model_copy(update={"fence": actor.lease.fence + 1})),
        )
        # No source timestamp is invented from a candle's opening timestamp.
        market_args = {
            "account_id": connection_id,
            "symbol": "XAUUSDm",
            "timeframe": "1h",
            "limit": 8,
        }
        market = await call("chart_snapshot", market_args, "broker-png")
        paths.append(confined_path(actor.artifact_root, market["payload"]["key"]))
        assert market["chart_snapshot"]["source"] == "broker_candles"
        assert "source_observed_at" not in market["chart_snapshot"]
        assert "scene_revision" not in market["chart_snapshot"]
        assert (await call("chart_snapshot", market_args, "broker-png"))[
            "chart_snapshot"
        ] == market["chart_snapshot"]
        await fails({**market_args, "limit": 7}, "broker-png", "artifact_nonce_conflict")
        for symbol in ("EURUSDm", "XAUUSDm", "US500.cash", "BTCUSD#"):
            for timeframe in ("15m", "1h"):
                result = await call(
                    "chart_snapshot",
                    {**market_args, "symbol": symbol, "timeframe": timeframe},
                )
                paths.append(confined_path(actor.artifact_root, result["payload"]["key"]))
                assert result["chart_snapshot"]["symbol"] == symbol
                assert result["chart_snapshot"]["timeframe"] == timeframe
                assert result["chart_snapshot"]["account_id"] == connection_id
        await fails(
            {**market_args, "symbol": "UNAVAILABLE.symbol"},
            "unknown-symbol",
            "chart_data_unavailable",
        )
        # Missing receipts must not regenerate an image from newer state.
        paths[1].unlink()
        try:
            await fails({"chart_id": chart_id}, "saved-png", "artifact_file_missing")
        finally:
            paths[1].write_bytes(original_bytes["png"])
        # A legacy receipt has bytes, but cannot truthfully recover source revisions.
        async with fixture.runtime.db.sessions() as session, session.begin():
            row = await ArtifactRepository().get(session, actor.owner_id, originals["svg"]["id"])
            row.state = {key: value for key, value in row.state.items() if key != "chart_snapshot"}
        legacy = await call("chart_snapshot", {"chart_id": chart_id}, "saved-svg")
        assert legacy["chart_snapshot"] == {"source": "unknown", "format": "svg"}
        assert "scene_revision" not in legacy and "chart_id" not in legacy
        assert paths[0].read_bytes() == original_bytes["svg"]
        corrupted = paths[1]
        corrupted.write_bytes(b"wrong bytes")
        try:
            await fails({"chart_id": chart_id}, "saved-png", "artifact_integrity_failed")
        finally:
            corrupted.write_bytes(original_bytes["png"])
        print(
            "PASS native SVG/PNG immutable provenance and bytes, broker source identity, legacy unknown, format/argument/scope/fence conflicts, integrity verification"
        )
    finally:
        if connection_id:
            await fixture.request("DELETE", "/trading/connections/" + connection_id)
        await fixture.close()
        for path in paths:
            path.unlink(missing_ok=True)
            if path.parent.exists() and not any(path.parent.iterdir()):
                path.parent.rmdir()


if __name__ == "__main__":
    asyncio.run(main())
