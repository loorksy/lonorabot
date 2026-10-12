from typing import Any

from lonora_contracts.chart import ChartState
from lonora_contracts.market import Candle

from .indicators import indicator_series


def chart_scene(state: ChartState, candles: list[Candle]) -> dict[str, Any]:
    return {
        "symbol": state.symbol,
        "timeframe": state.timeframe,
        "candles": [c.model_dump(mode="json") for c in candles],
        "indicators": [
            {
                "name": i.name,
                "period": i.period,
                "series": indicator_series(i.name, candles, i.period),
            }
            for i in state.indicators
        ],
        "annotations": state.annotations,
    }
