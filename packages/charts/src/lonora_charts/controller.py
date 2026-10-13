from typing import Any

from lonora_adapters.brokers.base import BrokerManager
from lonora_contracts.chart import ChartState
from lonora_core.chart_controller import validate_timeframe
from lonora_core.chart_indicator import validate_indicator
from lonora_core.user_error import LonoraError
from lonora_market.broker import broker_market
from lonora_market.candles import validate_candle_series

from .annotations import validate_annotations
from .scene import chart_scene


async def render_scene(brokers: BrokerManager, owner_id: str, state: ChartState) -> dict[str, Any]:
    validate_timeframe(state.timeframe)
    for indicator in state.indicators:
        validate_indicator(indicator.name, indicator.period)
    validate_annotations(state.annotations)
    provider = await broker_market(brokers, owner_id, state.account_id)
    candles = validate_candle_series(await provider.candles(state.symbol, state.timeframe, 500))
    if not candles:
        raise LonoraError("chart_data_unavailable", 409)
    scene = chart_scene(state, candles)
    try:
        scene["quote"] = (await provider.quote(state.symbol)).model_dump(mode="json")
    except LonoraError as error:
        scene["quote"] = None
        scene["quote_error_code"] = error.code
    return scene
