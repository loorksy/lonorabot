from copy import deepcopy

import pytest
from lonora_charts.scene_snapshot import scene_svg
from lonora_charts.snapshot_render import png_snapshot
from lonora_contracts.chart import ChartState
from lonora_core.chart_annotations import validate_annotations
from lonora_core.user_error import LonoraError
from lonora_tools.chart_state import AnnotateInput, apply_drawing_operations

START = {"time": "2026-10-01T00:00:00Z", "price": 100}
END = {"time": "2026-10-01T01:00:00Z", "price": 110}


def drawing(kind):
    item = {"type": kind, "start": START, "end": END, "label": "analysis"}
    if kind == "channel":
        item["parallel"] = {**START, "price": 105}
    if kind == "scenario":
        item["stop"] = 95
    return item


@pytest.mark.parametrize(
    "kind", ["trend_line", "price_zone", "ray", "channel", "fibonacci", "arrow", "scenario"]
)
def test_geometry_has_real_snapshot_mapping(kind):
    annotation = drawing(kind)
    assert validate_annotations([annotation]) == [annotation]
    scene = {
        "symbol": "XAUUSDm",
        "timeframe": "1h",
        "annotations": [annotation],
        "candles": [
            {"time": START["time"], "open": 99, "high": 102, "low": 98, "close": 100},
            {"time": END["time"], "open": 108, "high": 112, "low": 107, "close": 110},
        ],
    }
    svg = scene_svg(scene)
    assert "analysis" in svg
    assert len(png_snapshot(svg)) > 100
    plain = scene_svg({**scene, "annotations": []})
    assert svg != plain


@pytest.mark.parametrize(
    "annotation",
    [
        {"type": "ray", "start": START, "end": START},
        {"type": "price_zone", "start": START, "end": {**END, "price": 100}},
        {**drawing("scenario"), "stop": 120},
        {**drawing("fibonacci"), "levels": [0, float("nan")]},
        {**drawing("channel"), "parallel": START},
        {"type": "price", "price": float("inf")},
        {**drawing("arrow"), "vendor_script": "execute()"},
        {**drawing("arrow"), "style": {"color": "url(https://example.com)"}},
    ],
)
def test_invalid_geometry_is_rejected(annotation):
    with pytest.raises(LonoraError):
        validate_annotations([annotation])


def apply(state, args, agent="agent-a"):
    return apply_drawing_operations(
        state, args, agent_id=agent, chart_id="chart-a", mutation_id="run:call"
    )


def test_atomic_identity_attribution_and_manual_protection():
    manual = {"type": "price", "price": 90, "id": "user-level"}
    state = ChartState(account_id="account-a", symbol="XAUUSDm", annotations=[manual])
    args = {"annotation": drawing("scenario")}
    result = apply(state, args)
    assert result == apply(state, args)
    assert result[1]["source"] == "agent" and result[1]["author_id"] == "agent-a"
    assert result[1]["scope"] == {
        "account_id": "account-a",
        "symbol": "XAUUSDm",
        "chart_id": "chart-a",
    }
    state.annotations = result
    updated = apply(
        state,
        {"operations": [{"op": "update", "id": result[1]["id"], "annotation": drawing("arrow")}]},
    )
    assert updated[1]["id"] == result[1]["id"]
    assert updated[1]["type"] == "arrow"
    for identity in ("user-level", result[1]["id"]):
        with pytest.raises(LonoraError, match="chart_annotation_forbidden"):
            apply(state, {"operations": [{"op": "delete", "id": identity}]}, agent="other")
    before = deepcopy(state.annotations)
    with pytest.raises(LonoraError):
        apply(
            state,
            {
                "operations": [
                    {"op": "add", "annotation": drawing("ray")},
                    {"op": "delete", "id": "missing"},
                ]
            },
        )
    assert state.annotations == before
    assert apply(state, {"operations": [{"op": "delete", "id": result[1]["id"]}]}) == [manual]


def test_scope_and_duplicate_identity():
    state = ChartState(account_id="a", symbol="EURUSDm")
    state.annotations = apply(state, {"annotation": drawing("ray")})
    identity = state.annotations[0]["id"]
    with pytest.raises(LonoraError, match="already_exists"):
        apply(
            state, {"operations": [{"op": "add", "id": identity, "annotation": drawing("arrow")}]}
        )
    state.symbol = "XAUUSDm"
    with pytest.raises(LonoraError, match="scope_mismatch"):
        apply(
            state, {"operations": [{"op": "update", "id": identity, "annotation": drawing("ray")}]}
        )


def test_legacy_input_still_valid_and_batch_exclusive():
    assert AnnotateInput(
        chart_id="chart", version=1, annotation={"type": "note", "text": "hello"}
    ).annotation
    with pytest.raises(ValueError):
        AnnotateInput(
            chart_id="chart", version=1, annotation={}, operations=[{"op": "delete", "id": "a"}]
        )


def test_scene_filters_scope_and_timeframes_without_deleting_saved_layers():
    from lonora_charts.scene import chart_scene

    state = ChartState(account_id="a", symbol="EURUSDm", timeframe="1h")
    first = apply(state, {"annotation": drawing("ray")})[0]
    other_symbol = {**first, "id": "other-symbol", "scope": {**first["scope"], "symbol": "XAUUSDm"}}
    other_account = {**first, "id": "other-account", "scope": {**first["scope"], "account_id": "b"}}
    other_timeframe = {**first, "id": "other-timeframe", "timeframes": ["15m"]}
    manual = {"type": "price", "price": 90}
    state.annotations = [first, other_symbol, other_account, other_timeframe, manual]
    assert chart_scene(state, [])["annotations"] == [first, manual]
    assert len(state.annotations) == 5
    state.timeframe = "15m"
    assert chart_scene(state, [])["annotations"] == [first, other_timeframe, manual]


def test_agent_cannot_overwrite_another_agents_identity():
    state = ChartState(account_id="a", symbol="EURUSDm")
    state.annotations = apply(state, {"annotation": drawing("ray")})
    identity = state.annotations[0]["id"]
    with pytest.raises(LonoraError, match="chart_annotation_forbidden"):
        apply(
            state,
            {"operations": [{"op": "update", "id": identity, "annotation": drawing("arrow")}]},
            agent="agent-b",
        )
    assert state.annotations[0]["type"] == "ray"
