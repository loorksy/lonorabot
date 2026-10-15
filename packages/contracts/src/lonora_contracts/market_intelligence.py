"""Versioned detector observations: measured facts, never execution authority."""

from datetime import datetime
from decimal import Decimal
from typing import Any, Literal

from pydantic import Field, model_validator

from .domain import Contract

ObservationState = Literal["pending", "forming", "confirmed", "invalidated", "expired"]


class Observation(Contract):
    id: str
    schema_version: Literal["1"] = "1"
    category: Literal["quote", "candle", "level", "zone", "trendline", "composite"]
    symbol: str
    timeframe: str | None = None
    source: str
    observed_at: datetime
    detector_id: str
    detector_version: str = "1"
    state: ObservationState
    values: dict[str, Any] = Field(default_factory=dict[str, Any])
    valid_until: datetime | None = None


class TrendlineAnchor(Contract):
    time: datetime
    price: Decimal = Field(gt=0)

    @model_validator(mode="after")
    def timezone(self) -> "TrendlineAnchor":
        if self.time.tzinfo is None:
            raise ValueError("trendline_anchor_timezone_required")
        return self


class DetectorDefinition(Contract):
    id: str = Field(min_length=1, max_length=80)
    kind: Literal["level", "zone", "trendline", "candle", "all", "any", "not"]
    level: Decimal | None = Field(default=None, gt=0)
    lower: Decimal | None = Field(default=None, gt=0)
    upper: Decimal | None = Field(default=None, gt=0)
    relation: Literal["above", "below", "touch"] = "above"
    tolerance: Decimal = Field(default=Decimal(0), ge=0)
    exit_tolerance: Decimal | None = Field(default=None, ge=0)
    anchors: list[TrendlineAnchor] = Field(default_factory=list[TrendlineAnchor], max_length=2)
    pattern: (
        Literal[
            "bullish_engulfing",
            "bearish_engulfing",
            "doji",
            "inside_bar",
            "bullish_pin",
            "bearish_pin",
        ]
        | None
    ) = None
    body_ratio: Decimal = Field(default=Decimal("0.1"), gt=0, lt=1)
    children: list["DetectorDefinition"] = Field(
        default_factory=list["DetectorDefinition"], max_length=16
    )

    @model_validator(mode="after")
    def shape(self) -> "DetectorDefinition":
        if self.kind == "level" and self.level is None:
            raise ValueError("detector_level_required")
        if self.kind == "zone" and (
            self.lower is None or self.upper is None or self.lower >= self.upper
        ):
            raise ValueError("detector_zone_required")
        if self.kind == "trendline" and (
            len(self.anchors) != 2 or self.anchors[0].time >= self.anchors[1].time
        ):
            raise ValueError("detector_trendline_anchors_required")
        if self.kind == "candle" and self.pattern is None:
            raise ValueError("detector_candle_pattern_required")
        if (
            self.kind in {"all", "any"}
            and not self.children
            or self.kind == "not"
            and len(self.children) != 1
        ):
            raise ValueError("detector_children_required")
        if self.kind not in {"all", "any", "not"} and self.children:
            raise ValueError("detector_leaf_has_children")
        if self.exit_tolerance is not None and self.exit_tolerance < self.tolerance:
            raise ValueError("detector_hysteresis_invalid")
        pending: list[tuple[DetectorDefinition, int]] = [(self, 0)]
        ids: set[str] = set()
        while pending:
            child, depth = pending.pop()
            if depth > 8 or len(ids) >= 64:
                raise ValueError("detector_tree_too_large")
            if child.id in ids:
                raise ValueError("detector_id_duplicate")
            ids.add(child.id)
            pending.extend((nested, depth + 1) for nested in child.children)
        return self
