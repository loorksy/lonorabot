"""Vendor-independent drawing geometry and bounded, inert presentation metadata."""

import re
from datetime import datetime
from decimal import Decimal, InvalidOperation
from typing import Any

from lonora_core.chart_controller import validate_timeframe
from lonora_core.user_error import LonoraError

ANNOTATION_TYPES = frozenset(
    {
        "price",
        "horizontal_line",
        "trend_line",
        "note",
        "price_zone",
        "ray",
        "channel",
        "fibonacci",
        "arrow",
        "scenario",
    }
)
FIBONACCI_LEVELS = [0, 0.236, 0.382, 0.5, 0.618, 1]


def validate_annotations(annotations: list[dict[str, Any]]) -> list[dict[str, Any]]:
    if len(annotations) > 100:
        raise LonoraError("too_many_chart_annotations")
    identities: set[str] = set()
    for annotation in annotations:
        kind = annotation.get("type")
        if not isinstance(kind, str) or kind not in ANNOTATION_TYPES:
            raise LonoraError("unsupported_annotation")
        try:

            def price(value: Any) -> Decimal:
                result = Decimal(str(value))
                if not result.is_finite() or result <= 0 or result > Decimal("1e100"):
                    raise ValueError("invalid_price")
                return result

            def timestamp(value: Any) -> datetime:
                result = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
                if result.tzinfo is None:
                    raise ValueError("invalid_time")
                return result

            def point(value: Any) -> tuple[datetime, Decimal]:
                return timestamp(value["time"]), price(value["price"])

            common = {
                "type",
                "id",
                "label",
                "text",
                "source",
                "author_id",
                "scope",
                "timeframes",
                "style",
            }
            geometry = (
                {"price", "time"}
                if kind in {"price", "horizontal_line", "note"}
                else {"start", "end"}
            )
            geometry |= {"parallel"} if kind == "channel" else set()
            geometry |= {"levels"} if kind == "fibonacci" else set()
            geometry |= {"stop"} if kind == "scenario" else set()
            if set(annotation) - common - geometry:
                raise ValueError("unknown_field")
            for key in ("label", "text"):
                if key in annotation and (
                    not isinstance(annotation[key], str) or len(annotation[key]) > 1000
                ):
                    raise ValueError("invalid_label")
            for key in ("id", "author_id"):
                if key in annotation and (
                    not isinstance(annotation[key], str) or not 1 <= len(annotation[key]) <= 100
                ):
                    raise ValueError("invalid_identity")
            identity = annotation.get("id")
            if identity:
                if identity in identities:
                    raise ValueError("duplicate_identity")
                identities.add(identity)
            if annotation.get("source", "user") not in {"user", "agent"}:
                raise ValueError("invalid_source")
            if "scope" in annotation:
                scope: dict[str, Any] = annotation["scope"]
                if (
                    type(scope) is not dict
                    or set(scope) != {"account_id", "symbol", "chart_id"}
                    or any(not isinstance(v, str) or not 1 <= len(v) <= 100 for v in scope.values())
                ):
                    raise ValueError("invalid_scope")
            if "timeframes" in annotation:
                frames: list[str] = annotation["timeframes"]
                if type(frames) is not list or not 1 <= len(frames) <= 20:
                    raise ValueError("invalid_timeframes")
                for frame in frames:
                    validate_timeframe(frame)
            style: dict[str, Any] = annotation.get("style", {})
            if type(style) is not dict or set(style) - {"color", "line_width", "line_style"}:
                raise ValueError("invalid_style")
            if "color" in style and not re.fullmatch(r"#[0-9a-fA-F]{6}", str(style["color"])):
                raise ValueError("invalid_color")
            if "line_width" in style and (
                type(style["line_width"]) is not int or not 1 <= style["line_width"] <= 5
            ):
                raise ValueError("invalid_width")
            if style.get("line_style", "solid") not in {"solid", "dashed", "dotted"}:
                raise ValueError("invalid_style")
            if kind in {"price", "horizontal_line"}:
                price(annotation["price"])
            elif kind == "note":
                if "time" in annotation:
                    timestamp(annotation["time"])
                if "price" in annotation:
                    price(annotation["price"])
            else:
                start, end = point(annotation["start"]), point(annotation["end"])
                if start[0] == end[0]:
                    raise ValueError("degenerate_geometry")
                if kind in {"price_zone", "fibonacci"} and start[1] == end[1]:
                    raise ValueError("degenerate_geometry")
                if kind == "channel":
                    parallel = point(annotation["parallel"])
                    slope = (end[1] - start[1]) / Decimal(str((end[0] - start[0]).total_seconds()))
                    if parallel[1] == start[1] + slope * Decimal(
                        str((parallel[0] - start[0]).total_seconds())
                    ):
                        raise ValueError("degenerate_channel")
                if kind == "fibonacci":
                    levels: list[Any] = annotation.get("levels", FIBONACCI_LEVELS)
                    if type(levels) is not list or not 2 <= len(levels) <= 16:
                        raise ValueError("invalid_levels")
                    parsed = [Decimal(str(level)) for level in levels]
                    if any(not level.is_finite() or not 0 <= level <= 1 for level in parsed) or len(
                        set(parsed)
                    ) != len(parsed):
                        raise ValueError("invalid_levels")
                if kind == "scenario":
                    stop = price(annotation["stop"])
                    if (
                        not (stop < start[1] < end[1] or end[1] < start[1] < stop)
                        or end[0] <= start[0]
                    ):
                        raise ValueError("invalid_scenario")
        except (KeyError, ValueError, TypeError, InvalidOperation, OverflowError):
            raise LonoraError("invalid_chart_annotation") from None
    return annotations


def protect_agent_annotations(
    previous: list[dict[str, Any]], following: list[dict[str, Any]], agent_id: str
) -> None:
    """An Agent may only change its attributed layer; legacy/manual layers are protected."""
    for annotation in previous:
        if annotation.get("source", "user") != "agent" or annotation.get("author_id") != agent_id:
            if annotation not in following:
                raise LonoraError("chart_annotation_forbidden", 403)
    for annotation in following:
        if annotation not in previous and (
            annotation.get("source") != "agent" or annotation.get("author_id") != agent_id
        ):
            raise LonoraError("chart_annotation_forbidden", 403)
