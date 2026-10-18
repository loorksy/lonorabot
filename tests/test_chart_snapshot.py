from datetime import UTC, datetime, timedelta
from decimal import Decimal
from io import BytesIO
from xml.etree.ElementTree import fromstring

import pytest
from lonora_charts.snapshot import svg_snapshot
from lonora_charts.snapshot_render import png_snapshot
from lonora_contracts.market import Candle
from lonora_core.user_error import LonoraError
from PIL import Image


def bars(symbol: str, timeframe: str, base: str) -> list[Candle]:
    value = Decimal(base)
    unit = value / 1000
    return [
        Candle(
            symbol=symbol,
            timeframe=timeframe,
            time=datetime(2026, 10, 16, tzinfo=UTC) + timedelta(minutes=index * 15),
            open=value,
            high=value + 3 * unit,
            low=value - 2 * unit,
            close=value + direction * unit,
        )
        for index, direction in enumerate([1, -1, 0])
    ]


@pytest.mark.parametrize(
    ("symbol", "timeframe", "base"),
    [
        ("EURUSDm", "1m", "1.08543"),
        ("XAUUSDm", "15m", "4161.43"),
        ("US500.cash", "1h", "6500.12"),
        ("BTCUSD#", "1d", "100000.25"),
    ],
)
def test_market_snapshot_uses_ohlc_wicks_and_colored_bodies(
    symbol: str, timeframe: str, base: str
) -> None:
    candles = bars(symbol, timeframe, base)
    svg = svg_snapshot(symbol, candles)
    root = fromstring(svg)
    elements = list(root)
    bodies = [e for e in elements if e.tag.endswith("rect") and e.get("x") is not None]
    wicks = [
        e for e in elements if e.tag.endswith("line") and e.get("stroke") in {"#4fc79b", "#ef6b73"}
    ]
    assert len(bodies) == len(wicks) == 3
    assert not any(e.tag.endswith("polyline") for e in elements)
    assert [e.get("fill") for e in bodies] == ["#4fc79b", "#ef6b73", "#4fc79b"]
    assert all(float(e.get("height", "0")) >= 1 for e in bodies)
    # Wick extremes must extend above and below each body, rather than drawing close only.
    for wick, body in zip(wicks, bodies, strict=True):
        assert float(wick.attrib["y1"]) < float(body.attrib["y"])
        assert float(wick.attrib["y2"]) > float(body.attrib["y"]) + float(body.attrib["height"])
    labels = " ".join(root.itertext())
    assert symbol in labels and timeframe in labels and "UTC" in labels
    assert "10-16 00:00" in labels
    with Image.open(BytesIO(png_snapshot(svg))) as image:
        assert image.size == (960, 480)
        colors = {color for _, color in image.getcolors(image.width * image.height) or []}
        assert (79, 199, 155) in colors and (239, 107, 115) in colors
        assert symbol in image.info["Description"]


def test_same_close_different_high_low_changes_snapshot() -> None:
    candles = bars("EURUSDm", "5m", "1.08543")
    before = svg_snapshot("EURUSDm", candles)
    candles[1] = candles[1].model_copy(update={"high": Decimal("1.1")})
    assert svg_snapshot("EURUSDm", candles) != before


def test_flat_doji_and_escaped_symbol_are_renderable() -> None:
    candles = bars("A&B<test>", "1w", "1")
    candles = [
        c.model_copy(
            update={"open": Decimal(1), "high": Decimal(1), "low": Decimal(1), "close": Decimal(1)}
        )
        for c in candles
    ]
    svg = svg_snapshot("A&B<test>", candles)
    assert "A&B<test>" in " ".join(fromstring(svg).itertext())
    assert "<test>" not in svg
    assert png_snapshot(svg).startswith(b"\x89PNG")


def test_no_data_does_not_invent_chart() -> None:
    with pytest.raises(LonoraError) as caught:
        svg_snapshot("XAUUSDm", [])
    assert caught.value.code == "chart_data_unavailable"
