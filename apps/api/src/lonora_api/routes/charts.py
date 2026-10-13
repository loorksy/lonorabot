from typing import Any

from fastapi import Depends, Request
from lonora_auth.identity import OwnerIdentity
from lonora_charts.state import stored_scene
from lonora_db.cloud_charts import CloudChartRepository
from lonora_db.events import emit

from ..middleware.auth import require_owner, runtime
from . import resource_router

router = resource_router("/charts", CloudChartRepository(), omit_catalog_state=("scene",))


@router.get("/{chart_id}/scene")
async def scene(
    request: Request, chart_id: str, owner: OwnerIdentity = Depends(require_owner)
) -> dict[str, Any]:
    async with runtime(request).db.sessions() as session:
        row = await CloudChartRepository().get(session, owner.id, chart_id)
    return stored_scene(row.state, row.version)


@router.post("/{chart_id}/refresh")
async def refresh(
    request: Request, chart_id: str, owner: OwnerIdentity = Depends(require_owner)
) -> dict[str, bool]:
    async with runtime(request).db.sessions() as session, session.begin():
        row = await CloudChartRepository().get(session, owner.id, chart_id, lock=True)
        row.state = {**row.state, "refresh_requested": True}
        emit(
            session,
            owner.id,
            "cloud_charts.refresh_requested",
            agent_id=row.agent_id,
            thread_id=row.thread_id,
            payload={"id": row.id},
        )
    return {"requested": True}
