from typing import Any

from pydantic import Field

from .domain import Contract


class IndicatorSpec(Contract):
    name: str
    period: int = Field(default=14, ge=2, le=500)


class ChartState(Contract):
    account_id: str
    symbol: str
    timeframe: str = "1h"
    indicators: list[IndicatorSpec] = Field(default_factory=list[IndicatorSpec], max_length=12)
    annotations: list[dict[str, Any]] = Field(default_factory=list[dict[str, Any]], max_length=100)
