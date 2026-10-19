from typing import Any

from lonora_charts.state import create_chart, replay_chart_command
from lonora_contracts.chart import ChartState

from .base import Tool
from .chart_state import apply_drawing_operations, bounded_inspection, chart_command
from .context import ToolContext


async def create(context: ToolContext, args: dict[str, Any]) -> dict[str, Any]:
    command = chart_command(context, args, "chart_open")
    prior = await replay_chart_command(context.db, command, context.lease)
    if prior is not None:
        return bounded_inspection(prior)
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
        command=command,
    )
    return bounded_inspection(current)


def tools() -> list[Tool]:
    return [
        Tool(
            "chart_open",
            "Create a persistent server chart and return its configuration acknowledgment. Then use chart_inspect for current candles/indicators or chart_snapshot for an image; those reads prepare an initializing scene through the existing market runtime. Replaying this command returns its original configuration without overwriting later owner edits. If an older chart lacks a creation receipt, list/inspect it rather than treating its current state as the original outcome.",
            ChartState,
            create,
            replay_safe=True,
        )
    ]
