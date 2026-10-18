from datetime import UTC
from xml.etree.ElementTree import Element, SubElement, tostring

from lonora_contracts.market import Candle
from lonora_core.user_error import LonoraError


def svg_snapshot(symbol: str, candles: list[Candle], width: int = 960, height: int = 480) -> str:
    """Render broker OHLC, including wicks; a close-price line loses evidence."""
    if len(candles) < 2:
        raise LonoraError("chart_data_unavailable", 409)
    if not (320 <= width <= 1920 and 240 <= height <= 2048):
        raise LonoraError("chart_snapshot_too_large", 413)
    root = Element(
        "svg",
        {
            "xmlns": "http://www.w3.org/2000/svg",
            "width": str(width),
            "height": str(height),
            "viewBox": f"0 0 {width} {height}",
        },
    )
    SubElement(root, "rect", {"width": "100%", "height": "100%", "fill": "#111215"})

    def label(text: str, x: float, y: float, color: str = "#a8adb7") -> None:
        SubElement(
            root, "text", {"x": str(x), "y": str(y), "fill": color, "font-size": "13"}
        ).text = text

    label(f"{symbol} · {candles[-1].timeframe}", 24, 26, "#ececee")
    left, right, top, bottom = 24.0, width - 130.0, 52.0, height - 52.0
    low, high = min(float(c.low) for c in candles), max(float(c.high) for c in candles)
    padding = (high - low) * 0.06 or max(abs(high) * 0.001, 0.000001)
    low, high = low - padding, high + padding

    def y(value: float) -> float:
        return bottom - (value - low) * (bottom - top) / (high - low)

    def line(x1: float, y1: float, x2: float, y2: float, color: str) -> None:
        SubElement(
            root,
            "line",
            {"x1": str(x1), "y1": str(y1), "x2": str(x2), "y2": str(y2), "stroke": color},
        )

    precision = min(
        8,
        max(2, max(-int(c.close.normalize().as_tuple().exponent) for c in candles)),
    )
    for index in range(5):
        price = low + (high - low) * index / 4
        position = y(price)
        line(left, position, right, position, "#252832")
        label(f"{price:.{precision}f}", right + 10, position + 4)

    spacing = (right - left) / len(candles)
    body_width = min(12.0, max(0.5, spacing * 0.7))
    for index, candle in enumerate(candles):
        center = left + (index + 0.5) * spacing
        opened, closed = y(float(candle.open)), y(float(candle.close))
        color = "#4fc79b" if candle.close >= candle.open else "#ef6b73"
        line(center, y(float(candle.high)), center, y(float(candle.low)), color)
        SubElement(
            root,
            "rect",
            {
                "x": str(center - body_width / 2),
                "y": str(min(opened, closed)),
                "width": str(body_width),
                "height": str(max(1.0, abs(opened - closed))),
                "fill": color,
            },
        )

    tick_count = min(4, len(candles))
    for tick in range(tick_count):
        index = round(tick * (len(candles) - 1) / (tick_count - 1))
        position = left + (index + 0.5) * spacing
        timestamp = candles[index].time
        timestamp = timestamp.replace(tzinfo=UTC) if timestamp.tzinfo is None else timestamp
        text = timestamp.astimezone(UTC).strftime("%m-%d %H:%M")
        line(position, bottom, position, bottom + 5, "#a8adb7")
        label(text, max(left, min(position - 42, right - 100)), bottom + 24)
    label("UTC", right + 10, bottom + 24)
    return tostring(root, encoding="unicode")
