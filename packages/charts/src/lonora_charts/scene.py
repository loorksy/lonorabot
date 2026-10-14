import json
from hashlib import sha256
from typing import Any

from lonora_contracts.chart import ChartState
from lonora_contracts.market import Candle

from .indicators import indicator_series


def chart_scene(state: ChartState, candles: list[Candle]) -> dict[str, Any]:
    candle_data = [c.model_dump(mode="json") for c in candles]
    return {
        "data_revision": sha256(
            json.dumps(
                {"state": state.model_dump(mode="json"), "candles": candle_data},
                sort_keys=True,
                separators=(",", ":"),
            ).encode()
        ).hexdigest(),
        "symbol": state.symbol,
        "timeframe": state.timeframe,
        "candles": candle_data,
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
