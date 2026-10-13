from typing import Any

from lonora_core.chart_annotations import validate_annotations
from lonora_core.chart_controller import validate_timeframe
from lonora_core.chart_indicator import validate_indicator
from pydantic import Field, model_validator

from .domain import Contract


class IndicatorSpec(Contract):
    name: str
    period: int = Field(default=14, ge=2, le=500)

    @model_validator(mode="after")
    def check_indicator(self) -> "IndicatorSpec":
        validate_indicator(self.name, self.period)
        self.name = self.name.casefold()
        return self


class ChartState(Contract):
    account_id: str
    symbol: str
    timeframe: str = "1h"
    indicators: list[IndicatorSpec] = Field(default_factory=list[IndicatorSpec], max_length=12)
    annotations: list[dict[str, Any]] = Field(default_factory=list[dict[str, Any]], max_length=100)

    @model_validator(mode="after")
    def check_chart(self) -> "ChartState":
        validate_timeframe(self.timeframe)
        if not self.symbol or len(self.symbol) > 80:
            raise ValueError("invalid_chart_symbol")
        validate_annotations(self.annotations)
        return self
