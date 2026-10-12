import asyncio
from collections.abc import AsyncIterator
from typing import Any

from lonora_adapters.brokers.base import BrokerManager
from lonora_contracts.chart import ChartState

from .controller import render_scene


async def chart_stream(
    brokers: BrokerManager, owner_id: str, state: ChartState
) -> AsyncIterator[dict[str, Any]]:
    while True:
        yield await render_scene(brokers, owner_id, state)
        await asyncio.sleep(5)
