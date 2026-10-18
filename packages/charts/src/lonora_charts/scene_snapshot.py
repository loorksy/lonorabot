import math
from datetime import datetime
from typing import Any
from xml.etree.ElementTree import Element, SubElement, tostring

from lonora_core.chart_annotations import FIBONACCI_LEVELS
from lonora_core.user_error import LonoraError


def scene_svg(scene: dict[str, Any]) -> str:
    """Render the saved semantic scene; no browser/provider request or invented values."""
    candles = scene["candles"]
    if len(candles) < 2:
        raise LonoraError("chart_data_unavailable", 409)
    indicators = scene.get("indicators", [])
    overlays = [item for item in indicators if item["name"] in {"sma", "ema", "bollinger"}]
    panes = [item for item in indicators if item["name"] not in {"sma", "ema", "bollinger"}]
    height = 420 + 130 * len(panes)
    root = Element(
        "svg",
        {
            "xmlns": "http://www.w3.org/2000/svg",
            "width": "960",
            "height": str(height),
            "viewBox": f"0 0 960 {height}",
        },
    )
    SubElement(root, "rect", {"width": "100%", "height": "100%", "fill": "#111215"})

    def label(text: str, y: float, color: str = "#ececee") -> None:
        SubElement(
            root, "text", {"x": "30", "y": str(y), "fill": color, "font-size": "13"}
        ).text = text

    label(
        f"{scene['symbol']} · {scene['timeframe']} · saved scene {scene.get('scene_version', '')}",
        24,
    )
    label(f"{candles[0]['time']} — {candles[-1]['time']}", height - 12)
    price_values = [float(candle[key]) for candle in candles for key in ("low", "high")]
    for indicator in overlays:
        price_values.extend(
            float(value)
            for series in indicator["series"].values()
            for value in series
            if value is not None and math.isfinite(float(value))
        )
    annotations = [
        item
        for item in scene.get("annotations", [])
        if item.get("scope", {}).get("symbol", scene["symbol"]) == scene["symbol"]
        and scene["timeframe"] in item.get("timeframes", [scene["timeframe"]])
    ]
    price_values.extend(
        float(item["price"])
        for item in annotations
        if item.get("type") in {"price", "horizontal_line"} and item.get("price") is not None
    )
    price_values.extend(
        float(item[point]["price"])
        for item in annotations
        if "start" in item and "end" in item
        for point in ("start", "end")
    )
    price_values.extend(float(item["stop"]) for item in annotations if "stop" in item)
    price_values.extend(
        float(item["parallel"]["price"]) for item in annotations if "parallel" in item
    )
    low, high = min(price_values), max(price_values)

    def x(index: int) -> float:
        return 30 + index * 900 / (len(candles) - 1)

    def y(value: float) -> float:
        return 365 - (value - low) * 315 / (high - low or 1)

    body_width = min(8, max(1, 650 / len(candles)))
    for index, candle in enumerate(candles):
        opened, closed = float(candle["open"]), float(candle["close"])
        color = "#4fc79b" if closed >= opened else "#ef6b73"
        SubElement(
            root,
            "line",
            {
                "x1": str(x(index)),
                "x2": str(x(index)),
                "y1": str(y(float(candle["high"]))),
                "y2": str(y(float(candle["low"]))),
                "stroke": color,
            },
        )
        SubElement(
            root,
            "rect",
            {
                "x": str(x(index) - body_width / 2),
                "y": str(min(y(opened), y(closed))),
                "width": str(body_width),
                "height": str(max(1, abs(y(opened) - y(closed)))),
                "fill": color,
            },
        )

    def plot(
        values: list[Any], floor: float, ceiling: float, top: float, bottom: float, color: str
    ) -> None:
        segments: list[str] = []

        def flush() -> None:
            if segments:
                SubElement(
                    root,
                    "polyline",
                    {
                        "fill": "none",
                        "stroke": color,
                        "stroke-width": "1.5",
                        "points": " ".join(segments),
                    },
                )
                segments.clear()

        for index, value in enumerate(values):
            if value is None or not math.isfinite(float(value)):
                flush()
                continue
            position = bottom - (float(value) - floor) * (bottom - top) / (ceiling - floor or 1)
            segments.append(f"{x(index):.2f},{position:.2f}")
        flush()

    colors = ["#7c83fd", "#e7b85a", "#48b5d4", "#d685e0"]
    for index, indicator in enumerate(overlays):
        label(f"{indicator['name']}({indicator['period']})", 42 + index * 15, colors[index % 4])
        for series in indicator["series"].values():
            plot(series, low, high, 50, 365, colors[index % 4])
    for index, indicator in enumerate(panes):
        top, bottom = 420 + index * 130, 510 + index * 130
        label(f"{indicator['name']}({indicator['period']})", top - 10)
        numeric = [
            float(value)
            for series in indicator["series"].values()
            for value in series
            if value is not None and math.isfinite(float(value))
        ]
        if numeric:
            floor, ceiling = (
                (0.0, 100.0) if indicator["name"] == "rsi" else (min(numeric), max(numeric))
            )
            for series_index, series in enumerate(indicator["series"].values()):
                plot(series, floor, ceiling, top, bottom, colors[series_index % 4])
    first = datetime.fromisoformat(str(candles[0]["time"]).replace("Z", "+00:00")).timestamp()
    last = datetime.fromisoformat(str(candles[-1]["time"]).replace("Z", "+00:00")).timestamp()

    def anchor(point: dict[str, Any]) -> tuple[float, float]:
        time = datetime.fromisoformat(str(point["time"]).replace("Z", "+00:00")).timestamp()
        return 30 + (time - first) * 900 / (last - first or 1), y(float(point["price"]))

    for index, annotation in enumerate(annotations):
        kind = annotation["type"]
        style = annotation.get("style", {})
        color = style.get("color", "#e7b85a")
        label_text = str(annotation.get("label", annotation.get("text", "")))[:1000]

        def segment(
            start: tuple[float, float],
            end: tuple[float, float],
            color: str = color,
            style: dict[str, Any] = style,
        ) -> None:
            SubElement(
                root,
                "line",
                {
                    "x1": str(start[0]),
                    "y1": str(start[1]),
                    "x2": str(end[0]),
                    "y2": str(end[1]),
                    "stroke": color,
                    "stroke-width": str(style.get("line_width", 1)),
                    "stroke-dasharray": {"solid": "none", "dashed": "5 4", "dotted": "1 3"}[
                        style.get("line_style", "solid")
                    ],
                },
            )

        if kind in {"price", "horizontal_line"}:
            position = y(float(annotation["price"]))
            segment((30, position), (930, position))
            label(label_text, position - 4, color)
        elif kind == "note":
            if "time" in annotation and "price" in annotation:
                px, py = anchor(annotation)
                SubElement(
                    root, "text", {"x": str(px), "y": str(py), "fill": color}
                ).text = label_text
            else:
                label(label_text, 385 + min(index, 1) * 14, color)
        else:
            start, end = anchor(annotation["start"]), anchor(annotation["end"])
            if kind == "price_zone":
                SubElement(
                    root,
                    "rect",
                    {
                        "x": str(min(start[0], end[0])),
                        "y": str(min(start[1], end[1])),
                        "width": str(abs(end[0] - start[0])),
                        "height": str(abs(end[1] - start[1])),
                        "fill": "#35302a",
                    },
                )
                segment(start, (end[0], start[1]))
                segment((start[0], end[1]), end)
            elif kind == "fibonacci":
                for level in annotation.get("levels", FIBONACCI_LEVELS):
                    position = start[1] + float(level) * (end[1] - start[1])
                    segment((start[0], position), (end[0], position))
                    label(str(level), position - 3, color)
            elif kind == "scenario":
                stop = y(float(annotation["stop"]))
                segment(start, (end[0], start[1]))
                segment((start[0], stop), (end[0], stop))
                segment((start[0], end[1]), end)
                label("Entry / stop / target · illustration", start[1] - 4, color)
            else:
                if kind == "ray":
                    edge = 930.0 if end[0] > start[0] else 30.0
                    end = (
                        edge,
                        start[1] + (end[1] - start[1]) * (edge - start[0]) / (end[0] - start[0]),
                    )
                segment(start, end)
                if kind == "channel":
                    parallel = anchor(annotation["parallel"])
                    offset = parallel[1] - (
                        start[1]
                        + (end[1] - start[1]) * (parallel[0] - start[0]) / (end[0] - start[0])
                    )
                    segment((start[0], start[1] + offset), (end[0], end[1] + offset))
                if kind == "arrow":
                    angle = math.atan2(end[1] - start[1], end[0] - start[0])
                    for delta in (-0.45, 0.45):
                        segment(
                            end,
                            (
                                end[0] - 12 * math.cos(angle + delta),
                                end[1] - 12 * math.sin(angle + delta),
                            ),
                        )
            if label_text:
                label(label_text, min(start[1], end[1]) - 5, color)
    return tostring(root, encoding="unicode")
