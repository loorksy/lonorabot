from typing import Any

from lonora_charts.state import create_chart
from lonora_contracts.chart import ChartState

from .base import Tool
from .chart_state import apply_drawing_operations, bounded_inspection
from .context import ToolContext


async def create(context: ToolContext, args: dict[str, Any]) -> dict[str, Any]:
    state = ChartState.model_validate(args)
    if state.annotations:
        initial = state.annotations
        state.annotations = []
        state.annotations = apply_drawing_operations(
            state,
            {"operations": [{"op": "add", "annotation": item} for item in initial]},
            agent_id=context.agent_id,
            chart_id=context.resource_id,
            mutation_id=context.resource_id,
        )
    current = await create_chart(
        context.db,
        context.brokers,
        context.owner_id,
        state,
        agent_id=context.agent_id,
        thread_id=context.thread_id,
        resource_id=context.resource_id,
        lease=context.lease,
    )
    return bounded_inspection(current)


def tools() -> list[Tool]:
    return [
        Tool(
            "chart_open",
            "Read candles and indicators and persist chart state on the server.",
            ChartState,
            create,
            replay_safe=True,
        )
    ]
