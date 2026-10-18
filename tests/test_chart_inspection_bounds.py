"""Tool-only chart projections retain authoritative versions and aligned evidence."""

import copy
import json
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from typing import Any, cast

import pytest
from lonora_core.user_error import LonoraError
from lonora_tools import chart as chart_tools
from lonora_tools import chart_state
from lonora_tools.context import ToolContext
from pydantic import ValidationError


def context() -> ToolContext:
    return cast(
        ToolContext,
        SimpleNamespace(
            db=object(),
            owner_id="owner",
            brokers=object(),
            lease=object(),
            agent_id="agent",
            thread_id="thread",
            resource_id="chart",
        ),
    )


def inspection(symbol: str = "XAUUSDm", timeframe: str = "15m") -> dict[str, Any]:
    candles = [
        {
            "symbol": symbol,
            "timeframe": timeframe,
            "time": (datetime(2026, 10, 16, tzinfo=UTC) + timedelta(minutes=index)).isoformat(),
            "open": str(index + 10),
            "high": str(index + 12),
            "low": str(index + 9),
            "close": str(index + 11),
        }
        for index in range(1000)
    ]
    scene = {
        "symbol": symbol,
        "timeframe": timeframe,
        "data_revision": "scene-data-revision",
        "candles": candles,
        "indicators": [
            {
                "name": "sma",
                "period": 14,
                "series": {"value": [None if index < 13 else index + 0.5 for index in range(1000)]},
            },
            {
                "name": "macd",
                "period": 26,
                "series": {
                    "macd": list(range(1000)),
                    "signal": list(range(1000)),
                    "histogram": list(range(1000)),
                },
            },
        ],
        "annotations": [{"type": "price", "price": 123, "label": "Owner level"}],
        "quote": {"symbol": symbol, "bid": "1010", "ask": "1011"},
    }
    return {
        "chart": {
            "id": "chart",
            "version": 4,
            "payload": {
                "account_id": "account",
                "symbol": symbol,
                "timeframe": timeframe,
                "indicators": [{"name": "sma", "period": 14}],
                "annotations": scene["annotations"],
            },
            "state": {
                "scene_status": "ready",
                "scene_revision": 4,
                "scene_version": "revision-4",
                "scene_updated_at": "2026-10-16T12:00:00Z",
                "scene": scene,
            },
        },
        "scene": scene,
    }


def stub_inspection(
    monkeypatch: pytest.MonkeyPatch, result: dict[str, Any], actor: ToolContext
) -> None:
    async def load(db: Any, owner_id: str, chart_id: str) -> dict[str, Any]:
        assert db is actor.db and owner_id == actor.owner_id and chart_id == "chart"
        return result

    monkeypatch.setattr(chart_state, "inspect_chart", load)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("symbol", "timeframe"),
    [("EURUSD.a", "5m"), ("XAUUSDm", "15m"), ("US30.cash", "1h"), ("BTCUSD#", "1d")],
)
async def test_inspect_defaults_to_aligned_bounded_scene_for_any_asset(
    monkeypatch: pytest.MonkeyPatch, symbol: str, timeframe: str
) -> None:
    actor = context()
    original = inspection(symbol, timeframe)
    unchanged = copy.deepcopy(original)
    stub_inspection(monkeypatch, original, actor)
    tool = next(item for item in chart_state.tools() if item.name == "chart_inspect")
    args = tool.input_type.model_validate({"chart_id": "chart"}).model_dump()
    result = await tool.handler(actor, args)

    assert len(json.dumps(original)) > 120_000
    assert len(json.dumps(result)) < 25_000
    assert result["chart"]["version"] == 4
    assert result["chart"]["payload"]["symbol"] == symbol
    assert result["scene"]["symbol"] == symbol and result["scene"]["timeframe"] == timeframe
    assert result["scene"]["candles"] == original["scene"]["candles"][-60:]
    assert result["scene"]["indicators"][0]["series"]["value"] == [
        index + 0.5 for index in range(940, 1000)
    ]
    assert result["scene"]["quote"] == original["scene"]["quote"]
    assert "scene" not in result["chart"]["state"]
    assert result["scene_summary"] == {
        "available": True,
        "included": True,
        "total_candles": 1000,
        "returned_candles": 60,
        "candles_truncated": True,
        "total_indicator_values": 4000,
        "returned_indicator_values": 240,
        "indicator_values_truncated": True,
        "first_candle_at": original["scene"]["candles"][0]["time"],
        "last_candle_at": original["scene"]["candles"][-1]["time"],
    }
    assert original == unchanged  # The API/durable state still retains the full scene.


@pytest.mark.asyncio
async def test_scene_can_be_omitted_without_losing_version_or_reporting_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    actor, original = context(), inspection()
    stub_inspection(monkeypatch, original, actor)
    result = await chart_state.inspect(actor, {"chart_id": "chart", "include_scene": False})
    assert result["scene"] is None
    assert "code" not in result and "error" not in result
    assert result["chart"]["payload"] == original["chart"]["payload"]
    assert result["chart"]["state"]["scene_status"] == "ready"
    assert result["chart"]["version"] == 4
    assert "scene" not in result["chart"]["state"]
    assert result["scene_summary"]["available"] is True
    assert result["scene_summary"]["included"] is False
    assert result["scene_summary"]["returned_candles"] == 0


@pytest.mark.asyncio
async def test_failed_scene_keeps_actual_error_and_does_not_leak_stale_large_scene(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    actor, original = context(), inspection()
    original["scene"] = None
    original["code"] = "symbol_not_found"
    original["chart"]["state"]["scene_status"] = "failed"
    stub_inspection(monkeypatch, original, actor)
    result = await chart_state.inspect(actor, {"chart_id": "chart"})
    assert result["code"] == "symbol_not_found"
    assert result["scene"] is None and result["scene_summary"]["available"] is False
    assert "scene" not in result["chart"]["state"]


@pytest.mark.asyncio
async def test_incomplete_indicator_series_keeps_candle_indices(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    actor, original = context(), inspection()
    original["scene"]["indicators"][0]["series"]["value"] = list(range(997))
    stub_inspection(monkeypatch, original, actor)
    result = await chart_state.inspect(actor, {"chart_id": "chart", "tail": 5})
    assert result["scene"]["indicators"][0]["series"]["value"] == [995, 996, None, None, None]
    assert len(result["scene"]["candles"]) == 5


@pytest.mark.asyncio
async def test_read_indicator_can_still_read_more_than_inspection_default(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    actor, original = context(), inspection()
    stub_inspection(monkeypatch, original, actor)
    result = await chart_state.read_indicator(
        actor, {"chart_id": "chart", "name": "sma", "period": 14, "tail": 200}
    )
    assert result["times"] == [candle["time"] for candle in original["scene"]["candles"][-200:]]
    assert result["series"]["value"] == [index + 0.5 for index in range(800, 1000)]
    assert result["scene_revision"] == result["version"] == 4


@pytest.mark.asyncio
async def test_edit_reads_full_current_state_and_bounds_only_tool_result(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    actor, original = context(), inspection()
    stub_inspection(monkeypatch, original, actor)

    async def update(
        db: Any, brokers: Any, owner: str, chart_id: str, version: int, state: Any, *, lease: Any
    ):
        assert db is actor.db and brokers is actor.brokers and lease is actor.lease
        assert owner == "owner" and chart_id == "chart" and version == 4
        assert state.symbol == "XAUUSDm" and state.timeframe == "4h"
        assert state.annotations == original["chart"]["payload"]["annotations"]
        assert state.indicators[0].name == "sma" and state.indicators[0].period == 14
        saved = copy.deepcopy(original)
        saved["chart"]["version"] = 5
        saved["chart"]["payload"] = state.model_dump(mode="json")
        saved["chart"]["state"]["scene_revision"] = 5
        saved["scene"]["timeframe"] = "4h"
        return saved

    monkeypatch.setattr(chart_state, "update_chart", update)
    result = await chart_state.set_timeframe(
        actor, {"chart_id": "chart", "version": 4, "timeframe": "4h"}
    )
    assert result["chart"]["version"] == result["chart"]["state"]["scene_revision"] == 5
    assert result["scene"]["timeframe"] == "4h" and len(result["scene"]["candles"]) == 60
    with pytest.raises(LonoraError, match="version_conflict"):
        await chart_state.set_timeframe(
            actor, {"chart_id": "chart", "version": 3, "timeframe": "1h"}
        )


@pytest.mark.asyncio
async def test_open_returns_real_chart_identity_with_bounded_scene(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    actor, original = context(), inspection()

    async def create(db: Any, brokers: Any, owner: str, state: Any, **kwargs: Any):
        assert db is actor.db and brokers is actor.brokers and owner == "owner"
        assert state.symbol == "XAUUSDm"
        assert kwargs["resource_id"] == actor.resource_id and kwargs["lease"] is actor.lease
        return original

    monkeypatch.setattr(chart_tools, "create_chart", create)
    result = await chart_tools.create(actor, original["chart"]["payload"])
    assert result["chart"]["id"] == "chart" and result["chart"]["version"] == 4
    assert len(result["scene"]["candles"]) == 60
    assert result["scene_summary"]["candles_truncated"] is True


@pytest.mark.parametrize("tail", [0, 201])
def test_inspection_schema_enforces_bounded_tail(tail: int) -> None:
    with pytest.raises(ValidationError):
        chart_state.ChartInspectInput.model_validate({"chart_id": "chart", "tail": tail})
