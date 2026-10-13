"""Gateway-owned, fenced chart refresh. Browser requests read durable derived evidence."""

import asyncio
from datetime import datetime, timedelta
from typing import Any
from uuid import uuid4

from lonora_adapters.brokers.base import BrokerManager
from lonora_contracts.chart import ChartState
from lonora_contracts.domain import utcnow
from lonora_contracts.runs import Lease
from lonora_core.user_error import LonoraError
from lonora_db.client import Database
from lonora_db.events import emit
from lonora_db.runs import require_lease
from lonora_db.schema import CloudChartRow, MarketWatchRow
from sqlalchemy import select

from .controller import render_scene


async def refresh_chart(
    db: Database,
    brokers: BrokerManager,
    owner_id: str,
    chart_id: str,
    identity: str,
    lease: Lease | None = None,
    *,
    force: bool = False,
) -> bool:
    now = utcnow()
    async with db.sessions() as session, session.begin():
        row = await session.get(CloudChartRow, chart_id, with_for_update=True)
        if row is None or row.owner_id != owner_id:
            raise LonoraError("cloud_charts_not_found", 404)
        if lease:
            await require_lease(session, lease)
        state = row.state
        expires = state.get("runtime_lease_until")
        if (
            expires
            and datetime.fromisoformat(expires) > now
            and state.get("runtime_owner") != identity
        ):
            return False
        refreshed = state.get("scene_updated_at")
        if (
            not force
            and not state.get("refresh_requested")
            and state.get("scene_revision") == row.version
            and refreshed
            and datetime.fromisoformat(refreshed) > now - timedelta(seconds=10)
        ):
            return False
        fence = int(state.get("runtime_fence", 0)) + 1
        revision, config = row.version, ChartState.model_validate(row.payload)
        row.state = {
            **state,
            "runtime_owner": identity,
            "runtime_fence": fence,
            "runtime_lease_until": (now + timedelta(seconds=90)).isoformat(),
        }
    scene: dict[str, Any] | None = None
    code: str | None = None
    try:
        scene = await render_scene(brokers, owner_id, config)
    except LonoraError as error:
        code = error.code
    except Exception:
        code = "chart_refresh_unavailable"
    async with db.sessions() as session, session.begin():
        row = await session.get(CloudChartRow, chart_id, with_for_update=True)
        if row is None or row.owner_id != owner_id or row.version != revision:
            return False
        state = row.state
        if (
            state.get("runtime_owner") != identity
            or state.get("runtime_fence") != fence
            or datetime.fromisoformat(str(state["runtime_lease_until"])) <= utcnow()
        ):
            return False
        if lease:
            await require_lease(session, lease)
        version = int(state.get("scene_version", 0)) + 1
        updated = utcnow().isoformat()
        next_state = {
            **state,
            "scene_revision": revision,
            "scene_version": version,
            "scene_updated_at": updated,
            "scene_status": "failed" if code else "ready",
            "runtime_lease_until": None,
            "refresh_requested": False,
        }
        if scene is not None:
            next_state["scene"] = {
                **scene,
                "chart_id": row.id,
                "revision": revision,
                "scene_version": version,
                "status": "ready",
                "updated_at": updated,
            }
            next_state.pop("error_code", None)
        else:
            next_state["error_code"] = code
        row.state = next_state
        emit(
            session,
            owner_id,
            "cloud_charts.scene_updated",
            agent_id=row.agent_id,
            thread_id=row.thread_id,
            payload={
                "id": row.id,
                "version": revision,
                "scene_version": version,
                "status": next_state["scene_status"],
                "code": code,
            },
        )
    return True


async def chart_runtime_tick(
    db: Database,
    brokers: BrokerManager,
    owner_id: str,
    identity: str,
    *,
    maintain_streams: bool = True,
) -> int:
    async with db.sessions() as session:
        charts = list(
            (
                await session.scalars(
                    select(CloudChartRow).where(CloudChartRow.owner_id == owner_id)
                )
            ).all()
        )
        watches = list(
            (
                await session.scalars(
                    select(MarketWatchRow).where(MarketWatchRow.owner_id == owner_id)
                )
            ).all()
        )
    if maintain_streams and brokers.market:
        targets = {(str(row.payload["account_id"]), str(row.payload["symbol"])) for row in charts}
        targets.update(
            (str(row.payload["account_id"]), str(row.payload["symbol"]))
            for row in watches
            if row.payload.get("enabled", True)
            and row.payload.get("kind", "price") in {"price", "indicator"}
        )
        await brokers.market.synchronize(targets)
    semaphore = asyncio.Semaphore(8)

    async def refresh(row: CloudChartRow) -> bool:
        async with semaphore:
            try:
                return await refresh_chart(db, brokers, owner_id, row.id, identity)
            except LonoraError:
                return False

    return sum(await asyncio.gather(*(refresh(row) for row in charts)))


def refresh_identity() -> str:
    return "chart-refresh:" + uuid4().hex
