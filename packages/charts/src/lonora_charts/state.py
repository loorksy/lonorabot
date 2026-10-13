from typing import Any, cast

from lonora_adapters.brokers.base import BrokerManager
from lonora_contracts.chart import ChartState
from lonora_contracts.runs import Lease
from lonora_core.user_error import LonoraError
from lonora_db.client import Database
from lonora_db.cloud_charts import CloudChartRepository
from lonora_db.runs import require_lease
from lonora_db.transactions import resource_data

from .runtime import refresh_chart, refresh_identity


def stored_scene(data: dict[str, Any], version: int) -> dict[str, Any]:
    if data.get("scene_revision") != version:
        raise LonoraError("chart_initializing", 409)
    if data.get("scene_status") != "ready":
        raise LonoraError(str(data.get("error_code") or "chart_data_unavailable"), 409)
    scene = data.get("scene")
    if not isinstance(scene, dict):
        raise LonoraError("chart_initializing", 409)
    return cast(dict[str, Any], scene)


async def load_chart_state(db: Database, owner_id: str, chart_id: str) -> ChartState:
    async with db.sessions() as session:
        row = await CloudChartRepository().get(session, owner_id, chart_id)
        return ChartState.model_validate(row.payload)


async def inspect_chart(db: Database, owner_id: str, chart_id: str) -> dict[str, Any]:
    async with db.sessions() as session:
        row = await CloudChartRepository().get(session, owner_id, chart_id)
        chart = resource_data(row)
        try:
            scene = stored_scene(row.state, row.version)
        except LonoraError as error:
            return {"chart": chart, "scene": None, "code": error.code}
        return {"chart": chart, "scene": scene}


async def create_chart(
    db: Database,
    brokers: BrokerManager,
    owner_id: str,
    state: ChartState,
    *,
    agent_id: str | None = None,
    thread_id: str | None = None,
    resource_id: str | None = None,
    lease: Lease | None = None,
) -> dict[str, Any]:
    async with db.sessions() as session, session.begin():
        if lease:
            await require_lease(session, lease, lock=True)
        row = await session.get(CloudChartRepository.row_type, resource_id) if resource_id else None
        if row is not None:
            if row.owner_id != owner_id:
                raise LonoraError("cloud_charts_not_found", 404)
        else:
            row = await CloudChartRepository().create(
                session,
                owner_id,
                state.model_dump(mode="json"),
                agent_id=agent_id,
                thread_id=thread_id,
                resource_id=resource_id,
            )
        chart_id = row.id
    await refresh_chart(db, brokers, owner_id, chart_id, refresh_identity(), lease, force=True)
    return await inspect_chart(db, owner_id, chart_id)


async def update_chart(
    db: Database,
    brokers: BrokerManager,
    owner_id: str,
    chart_id: str,
    version: int,
    state: ChartState,
    lease: Lease | None = None,
) -> dict[str, Any]:
    async with db.sessions() as session, session.begin():
        if lease:
            await require_lease(session, lease, lock=True)
        await CloudChartRepository().update(
            session, owner_id, chart_id, state.model_dump(mode="json"), version
        )
    await refresh_chart(db, brokers, owner_id, chart_id, refresh_identity(), lease, force=True)
    return await inspect_chart(db, owner_id, chart_id)
