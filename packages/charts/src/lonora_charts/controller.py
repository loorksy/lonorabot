from typing import Any

from lonora_adapters.brokers.base import BrokerManager
from lonora_contracts.chart import ChartState
from lonora_core.chart_controller import validate_timeframe
from lonora_core.chart_indicator import validate_indicator
from lonora_market.broker import broker_market
from lonora_market.candles import validate_candle_series

from .scene import chart_scene


async def render_scene(brokers: BrokerManager, owner_id: str, state: ChartState) -> dict[str, Any]:
    validate_timeframe(state.timeframe)
    for indicator in state.indicators:
        validate_indicator(indicator.name, indicator.period)
    provider = await broker_market(brokers, owner_id, state.account_id)
    candles = validate_candle_series(await provider.candles(state.symbol, state.timeframe, 500))
    return chart_scene(state, candles)
