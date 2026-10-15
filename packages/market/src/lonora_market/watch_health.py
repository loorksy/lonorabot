"""Persist meaningful watch health changes in the existing transactional event stream."""

from datetime import datetime
from typing import Any

from lonora_contracts.market_health import HealthSnapshot
from lonora_db.events import emit
from lonora_db.schema import MarketWatchRow
from sqlalchemy.ext.asyncio import AsyncSession


def record_watch_health(
    session: AsyncSession,
    row: MarketWatchRow,
    health: HealthSnapshot,
    *,
    next_check: datetime,
) -> dict[str, Any]:
    previous = row.state.get("health", {})
    state = {
        **row.state,
        "health": health.model_dump(mode="json"),
        "evaluation_status": "active" if health.healthy else "suspended_health",
        "next_check": next_check.isoformat(),
    }
    # Refresh measurements but emit only a meaningful health-state/reason change.
    # Initial healthy observations are routine telemetry, not user notifications.
    changed = (previous.get("state"), previous.get("reason_code")) != (
        health.state,
        health.reason_code,
    )
    if changed and (previous or not health.healthy):
        emit(
            session,
            row.owner_id,
            "watch.resumed_health" if health.healthy else "watch.suspended_health",
            agent_id=row.agent_id,
            thread_id=row.thread_id,
            payload={"watch_id": row.id, "health": health.model_dump(mode="json")},
        )
    if health.healthy:
        state.pop("code", None)
    else:
        state["code"] = health.reason_code
    return state
