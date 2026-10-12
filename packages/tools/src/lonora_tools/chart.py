from typing import Any

from lonora_charts.controller import render_scene
from lonora_contracts.chart import ChartState
from lonora_db.cloud_charts import CloudChartRepository
from lonora_db.runs import require_lease
from lonora_db.transactions import resource_data

from .base import Tool
from .context import ToolContext


async def create(context: ToolContext, args: dict[str, Any]) -> dict[str, Any]:
    state = ChartState.model_validate(args)
    scene = await render_scene(context.brokers, context.owner_id, state)
    async with context.db.sessions() as session, session.begin():
        await require_lease(session, context.lease, lock=True)
        row = await session.get(CloudChartRepository.row_type, context.resource_id)
        row = row or await CloudChartRepository().create(
            session,
            context.owner_id,
            state.model_dump(mode="json"),
            agent_id=context.agent_id,
            thread_id=context.thread_id,
            resource_id=context.resource_id,
        )
        return {"chart": resource_data(row), "scene": scene}


def tools() -> list[Tool]:
    return [
        Tool(
            "chart_open",
            "Read candles and indicators and persist chart state on the server.",
            ChartState,
            create,
        )
    ]
