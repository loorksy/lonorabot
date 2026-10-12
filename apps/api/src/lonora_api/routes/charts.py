from typing import Any

from fastapi import Depends, Request
from lonora_auth.identity import OwnerIdentity
from lonora_charts.controller import render_scene
from lonora_contracts.chart import ChartState
from lonora_db.cloud_charts import CloudChartRepository

from ..middleware.auth import require_owner, runtime
from . import resource_router

router = resource_router("/charts", CloudChartRepository())


@router.get("/{chart_id}/scene")
async def scene(
    request: Request, chart_id: str, owner: OwnerIdentity = Depends(require_owner)
) -> dict[str, Any]:
    async with runtime(request).db.sessions() as session:
        row = await CloudChartRepository().get(session, owner.id, chart_id)
    return await render_scene(
        runtime(request).services(owner.id).brokers,
        owner.id,
        ChartState.model_validate(row.payload),
    )
