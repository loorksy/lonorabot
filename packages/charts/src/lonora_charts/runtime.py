"""Gateway-owned, fenced chart refresh. Browser requests read durable derived evidence."""

import asyncio
import logging
from datetime import datetime, timedelta
from typing import Any, cast
from uuid import uuid4

from lonora_adapters.brokers.base import BrokerManager
from lonora_contracts.chart import ChartState
from lonora_contracts.domain import utcnow
from lonora_contracts.market import Candle, Quote
from lonora_contracts.runs import Lease
from lonora_core.error_logging import safe_exception_message
from lonora_core.user_error import LonoraError
from lonora_db.client import Database
from lonora_db.events import emit
from lonora_db.market_snapshots import snapshot_id
from lonora_db.runs import require_lease
from lonora_db.schema import BrokerSessionRow, CloudChartRow, MarketSnapshotRow, MarketWatchRow
from sqlalchemy import select

from .controller import render_scene
from .scene import chart_scene

logger = logging.getLogger(__name__)


def log_safe_exception(logger: logging.Logger, event: str, error: Exception, *, code: str) -> None:
    logger.warning(
        "%s code=%s error_type=%s message=%s",
        event,
        code,
        (error.diagnostic_type if isinstance(error, LonoraError) else None) or type(error).__name__,
        safe_exception_message(error),
    )


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
        retry_at = state.get("scene_retry_at")
        if (
            not force
            and not state.get("refresh_requested")
            and state.get("scene_revision") == row.version
            and state.get("error_code") == "broker_market_data_billing_required"
            and retry_at
            and datetime.fromisoformat(retry_at) > now
        ):
            return False
        if (
            not force
            and not state.get("refresh_requested")
            and state.get("scene_revision") == row.version
            and refreshed
            and datetime.fromisoformat(refreshed) > now - timedelta(seconds=10)
        ):
            return False
        fence = int(state.get("runtime_fence", 0)) + 1
        revision, payload = row.version, row.payload
        scene_before = int(state.get("scene_version", 0))
        row.state = {
            **state,
            "runtime_owner": identity,
            "runtime_fence": fence,
            "runtime_lease_until": (now + timedelta(seconds=90)).isoformat(),
        }
    scene: dict[str, Any] | None = None
    config: ChartState | None = None
    code: str | None = None
    try:
        config = ChartState.model_validate(payload)
        scene = await render_scene(brokers, owner_id, config)
    except LonoraError as error:
        code = error.code
        log_safe_exception(logger, "chart_refresh_failed", error, code=code)
    except Exception as error:
        code = "chart_refresh_unavailable"
        log_safe_exception(logger, "chart_refresh_failed", error, code=code)
    async with db.sessions() as session, session.begin():
        # Account-before-chart lock ordering matches stream publication. No remote
        # request runs under either lock, and history never requires the stream lease.
        connection = None
        if brokers.market and isinstance(payload.get("account_id"), str):
            connection = await session.get(
                BrokerSessionRow, payload["account_id"], with_for_update=True
            )
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
        # Merge with the latest persisted official bars under the account fence.
        # Streams remain live during REST, and neither quote ticks nor corrected
        # candles can be replaced by the older rendered result.
        if (
            scene is not None
            and config is not None
            and connection
            and connection.owner_id == owner_id
        ):
            snapshot = await session.get(
                MarketSnapshotRow,
                snapshot_id(owner_id, connection.id, config.symbol, config.timeframe),
            )
            if snapshot and snapshot.connection_version == connection.version:
                latest = [
                    Candle.model_validate(value) for value in snapshot.payload.get("candles", [])
                ][-500:]
                if latest:
                    scene = {**scene, **chart_scene(config, latest)}
                    scene["candle_observed_at"] = snapshot.payload.get(
                        "stream_updated_at"
                    ) or snapshot.payload.get("history_updated_at")
            quote_snapshot = await session.get(
                MarketSnapshotRow, snapshot_id(owner_id, connection.id, config.symbol, "")
            )
            if quote_snapshot and quote_snapshot.connection_version == connection.version:
                scene["quote"] = Quote.model_validate(quote_snapshot.payload).model_dump(
                    mode="json"
                )
        elif int(state.get("scene_version", 0)) != scene_before:
            row.state = {**state, "runtime_lease_until": None}
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
        next_state.pop("scene_retry_at", None)
        if code == "broker_market_data_billing_required":
            next_state["scene_retry_at"] = (utcnow() + timedelta(minutes=5)).isoformat()
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


async def publish_stream_update(
    db: Database,
    owner_id: str,
    connection_id: str,
    symbol: str,
    timeframe: str | None,
    identity: str,
) -> int:
    """Derive durable chart scenes from official snapshots, never fetching history.

    Lock the account before each chart, matching market snapshot publication. A
    quote changes only the quote; authoritative streamed bars recalculate indicators.
    """
    async with db.sessions() as session:
        query = select(CloudChartRow.id).where(
            CloudChartRow.owner_id == owner_id,
            CloudChartRow.payload["account_id"].as_string() == connection_id,
            CloudChartRow.payload["symbol"].as_string() == symbol,
        )
        if timeframe is not None:
            query = query.where(CloudChartRow.payload["timeframe"].as_string() == timeframe)
        ids = list((await session.scalars(query)).all())
    count = 0
    for chart_id in ids:
        try:
            async with db.sessions() as session, session.begin():
                connection = await session.get(
                    BrokerSessionRow, connection_id, with_for_update=True
                )
                if (
                    connection is None
                    or connection.owner_id != owner_id
                    or not connection.payload.get("enabled")
                    or connection.state.get("market_stream_owner") != identity
                    or not connection.state.get("market_stream_until")
                    or datetime.fromisoformat(connection.state["market_stream_until"]) <= utcnow()
                ):
                    return count
                row = await session.get(CloudChartRow, chart_id, with_for_update=True)
                if row is None or row.owner_id != owner_id:
                    continue
                config = ChartState.model_validate(row.payload)
                if (
                    config.account_id != connection_id
                    or config.symbol != symbol
                    or (timeframe is not None and config.timeframe != timeframe)
                ):
                    continue
                bars = await session.get(
                    MarketSnapshotRow,
                    snapshot_id(owner_id, connection_id, symbol, config.timeframe),
                )
                if (
                    bars is None
                    or bars.connection_version != connection.version
                    or not bars.payload.get("history_updated_at")
                ):
                    # A stream's first packet cannot replace an uninitialized history window.
                    continue
                candles = [
                    Candle.model_validate(value) for value in bars.payload.get("candles", [])
                ][-500:]
                if not candles:
                    continue
                quote_row = await session.get(
                    MarketSnapshotRow, snapshot_id(owner_id, connection_id, symbol, "")
                )
                quote = (
                    Quote.model_validate(quote_row.payload).model_dump(mode="json")
                    if quote_row and quote_row.connection_version == connection.version
                    else None
                )
                previous = row.state.get("scene")
                if (
                    timeframe is None
                    and isinstance(previous, dict)
                    and row.state.get("scene_revision") == row.version
                    and row.state.get("scene_status") == "ready"
                ):
                    scene: dict[str, Any] = {**cast(dict[str, Any], previous), "quote": quote}
                else:
                    scene = {**chart_scene(config, candles), "quote": quote}
                version = int(row.state.get("scene_version", 0)) + 1
                updated = utcnow().isoformat()
                scene.update(
                    chart_id=row.id,
                    revision=row.version,
                    scene_version=version,
                    status="ready",
                    updated_at=updated,
                )
                scene["observation_source"] = (
                    "broker_candle_stream" if timeframe else "broker_quote_stream"
                )
                scene["candle_observed_at"] = bars.payload.get(
                    "stream_updated_at"
                ) or bars.payload.get("history_updated_at")
                next_state = {
                    **row.state,
                    "scene": scene,
                    "scene_status": "ready",
                    "scene_updated_at": updated,
                    "scene_revision": row.version,
                    "scene_version": version,
                }
                next_state.pop("error_code", None)
                next_state.pop("scene_retry_at", None)
                row.state = next_state
                emit(
                    session,
                    owner_id,
                    "cloud_charts.scene_updated",
                    agent_id=row.agent_id,
                    thread_id=row.thread_id,
                    payload={
                        "id": row.id,
                        "version": row.version,
                        "scene_version": version,
                        "status": "ready",
                        "code": None,
                    },
                )
                count += 1
        except Exception as error:
            log_safe_exception(
                logger,
                "chart_stream_update_failed",
                error,
                code=error.code if isinstance(error, LonoraError) else "chart_refresh_unavailable",
            )
    return count


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
            except LonoraError as error:
                log_safe_exception(logger, "chart_runtime_failed", error, code=error.code)
                return False
            except Exception as error:
                log_safe_exception(
                    logger, "chart_runtime_failed", error, code="chart_refresh_unavailable"
                )
                return False

    return sum(await asyncio.gather(*(refresh(row) for row in charts)))


def refresh_identity() -> str:
    return "chart-refresh:" + uuid4().hex
