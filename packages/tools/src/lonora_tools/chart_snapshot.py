import math
from datetime import datetime
from typing import Any
from xml.etree.ElementTree import Element, SubElement, tostring

from lonora_charts.snapshot import svg_snapshot
from lonora_charts.state import inspect_chart
from lonora_contracts.domain import Contract
from lonora_core.user_error import LonoraError
from lonora_market.broker import broker_market
from pydantic import Field, model_validator

from .artifacts import store_artifact
from .base import Tool
from .context import ToolContext


class SnapshotInput(Contract):
    chart_id: str | None = Field(default=None, min_length=1, max_length=36)
    account_id: str | None = None
    symbol: str | None = None
    timeframe: str | None = None
    limit: int = Field(default=300, ge=2, le=1000)

    @model_validator(mode="after")
    def source(self) -> "SnapshotInput":
        market = (self.account_id, self.symbol, self.timeframe)
        if self.chart_id and any(value is not None for value in market):
            raise ValueError("Use chart_id or explicit market fields, not both")
        if not self.chart_id and not all(market):
            raise ValueError("Provide chart_id or account_id, symbol and timeframe")
        return self


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
    annotations = scene.get("annotations", [])
    price_values.extend(
        float(item["price"])
        for item in annotations
        if item.get("type") in {"price", "horizontal_line"} and item.get("price") is not None
    )
    price_values.extend(
        float(item[point]["price"])
        for item in annotations
        if item.get("type") == "trend_line"
        for point in ("start", "end")
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
    for index, annotation in enumerate(annotations):
        label_text = str(annotation.get("label", annotation.get("text", "")))[:1000]
        if (
            annotation.get("type") in {"price", "horizontal_line"}
            and annotation.get("price") is not None
        ):
            position = y(float(annotation["price"]))
            SubElement(
                root,
                "line",
                {
                    "x1": "30",
                    "x2": "930",
                    "y1": str(position),
                    "y2": str(position),
                    "stroke": "#e7b85a",
                    "stroke-dasharray": "5 4",
                },
            )
            label(label_text, position - 4, "#e7b85a")
        elif label_text:
            label(f"{annotation.get('type', 'annotation')}: {label_text}", 385 + min(index, 1) * 14)
        if annotation.get("type") == "trend_line":
            first = datetime.fromisoformat(
                str(candles[0]["time"]).replace("Z", "+00:00")
            ).timestamp()
            last = datetime.fromisoformat(
                str(candles[-1]["time"]).replace("Z", "+00:00")
            ).timestamp()
            points: list[tuple[float, float]] = []
            for point in (annotation["start"], annotation["end"]):
                timestamp = datetime.fromisoformat(
                    str(point["time"]).replace("Z", "+00:00")
                ).timestamp()
                points.append(
                    (
                        max(30, min(930, 30 + (timestamp - first) * 900 / (last - first))),
                        y(float(point["price"])),
                    )
                )
            SubElement(
                root,
                "line",
                {
                    "x1": str(points[0][0]),
                    "y1": str(points[0][1]),
                    "x2": str(points[1][0]),
                    "y2": str(points[1][1]),
                    "stroke": "#e7b85a",
                },
            )
    return tostring(root, encoding="unicode")


async def snapshot(context: ToolContext, args: dict[str, Any]) -> dict[str, Any]:
    if args.get("chart_id"):
        result = await inspect_chart(context.db, context.owner_id, args["chart_id"])
        scene = result.get("scene")
        if scene is None:
            raise LonoraError(str(result.get("code", "chart_data_unavailable")), 409)
        image = scene_svg(scene)
        artifact = await store_artifact(
            context, scene["symbol"] + ".svg", image.encode(), "image/svg+xml"
        )
        return {
            **artifact,
            "chart_id": result["chart"]["id"],
            "scene_revision": result["chart"]["state"]["scene_revision"],
            "scene_version": scene["scene_version"],
        }
    provider = await broker_market(context.brokers, context.owner_id, args["account_id"])
    candles = await provider.candles(args["symbol"], args["timeframe"], args["limit"])
    image = svg_snapshot(args["symbol"], candles)
    return await store_artifact(context, args["symbol"] + ".svg", image.encode(), "image/svg+xml")


def tools() -> list[Tool]:
    return [
        Tool(
            "chart_snapshot",
            "Save a durable SVG chart image. Pass chart_id to capture its persisted candles, indicators and annotations; alternatively pass account_id/symbol/timeframe for a candle-only market snapshot. No execution or trading approval is implied.",
            SnapshotInput,
            snapshot,
        )
    ]
