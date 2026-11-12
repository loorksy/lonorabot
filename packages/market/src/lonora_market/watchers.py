import asyncio
from collections.abc import Awaitable, Callable
from datetime import datetime, timedelta
from decimal import Decimal
from typing import Any, cast

from lonora_adapters.brokers.base import BrokerManager
from lonora_adapters.market.economic_calendar import EconomicCalendarAdapter
from lonora_charts.indicators import indicator_series
from lonora_contracts.domain import utcnow
from lonora_contracts.market import Candle, Quote
from lonora_contracts.market_health import HealthSnapshot
from lonora_contracts.market_intelligence import DetectorDefinition, Observation
from lonora_contracts.market_watch import Watch
from lonora_contracts.relationships import MarketRelationship, RelationshipRequest
from lonora_contracts.runs import RunRequest
from lonora_core.market_watch import condition_met
from lonora_core.user_error import LonoraError
from lonora_db.agent_binding import agent_binding, assert_payload_binding, fixed_market
from lonora_db.broker_sessions import BrokerSessionRepository
from lonora_db.client import Database
from lonora_db.events import emit
from lonora_db.integrations import source_url
from lonora_db.item_failures import ItemGuard, blocked
from lonora_db.market_snapshots import snapshot_id
from lonora_db.market_watches import stop_watch
from lonora_db.runs import create_run
from lonora_db.schema import (
    AgentRow,
    IntegrationRow,
    MarketSnapshotRow,
    MarketWakeReceiptRow,
    MarketWatchRow,
    RunRow,
)
from lonora_db.threads import background_origin
from lonora_session.idempotency import request_hash, stable_id
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from .broker import broker_market
from .detectors import detector_inputs, evaluate_detector, relationship_detectors
from .health import (
    assess_account,
    assess_candles,
    assess_quote,
    require_healthy,
    timeframe_age_seconds,
)
from .relationships import measure_relationship, relationship_usable
from .watch_control import watch_can_trigger
from .watch_health import record_watch_health
from .watch_lifecycle import advance_watch

# A broker, calendar or detector observation on the poll path never holds the batch longer.
WATCH_OBSERVATION_TIMEOUT_SECONDS = 20


class WatchSkipped(Exception):
    """This evaluation has nothing to observe yet (not a failure)."""


async def disable_watch(session: AsyncSession, watch_id: str) -> bool:
    """Quarantine: a watch that keeps failing is disabled until it is re-enabled."""
    row = await session.get(MarketWatchRow, watch_id, with_for_update=True)
    if row is not None:
        stop_watch(row, "watch_quarantined")
        row.version += 1
    return True


def source_observation_time(config: Watch, metadata: dict[str, Any]) -> datetime:
    """Resolve evidence time, never the time a worker happened to process it."""
    observation = metadata.get("observation")
    if isinstance(observation, dict):
        return Observation.model_validate(observation).observed_at
    for name in ("quote", "account"):
        source = metadata.get(name)
        if isinstance(source, dict):
            timestamp = cast(dict[str, Any], source).get("observed_at")
            if isinstance(timestamp, str):
                return datetime.fromisoformat(timestamp)
    if config.kind == "calendar":
        # A batch is only as fresh as its oldest contributing event.
        return min(
            min(datetime.fromisoformat(event[key]) for key in ("scheduled_at", "observed_at"))
            for event in metadata["events"]
        )
    if config.kind == "indicator":
        opened = datetime.fromisoformat(metadata["time"])
        # The indicator includes the current live bar. Its opening time is the
        # only source time carried by Candle; do not fabricate a later update.
        return opened
    if metadata.get("observed_at"):
        return datetime.fromisoformat(metadata["observed_at"])
    raise LonoraError("watch_observation_timestamp_unavailable", 409)


async def observe_dynamic(
    db: Database,
    brokers: BrokerManager,
    row: MarketWatchRow,
    config: Watch,
    price_update: Quote | None = None,
) -> tuple[Decimal, str, dict[str, Any]]:
    assert config.detector is not None
    market = await broker_market(brokers, row.owner_id, config.account_id)
    inputs = detector_inputs(config.detector)
    now = utcnow()
    quote: Quote | None = None
    candles: list[Candle] = []
    health = HealthSnapshot(
        state="healthy",
        reason_code="market_data_healthy",
        observed_at=now,
        account_id=config.account_id,
        symbol=config.symbol,
        timeframe=config.timeframe,
        resource="watch",
    )
    if "quote" in inputs:
        quote = price_update or await market.quote(config.symbol)
        health = assess_quote(
            quote,
            account_id=config.account_id,
            symbol=config.symbol,
            now=now,
            maximum_age_seconds=max(30, config.interval_seconds * 2),
        )
        require_healthy(health)
    nodes = relationship_detectors(config.detector)
    relationships: dict[str, MarketRelationship] = {}
    if "candles" in inputs or nodes:
        limit = max([100] + [node.relationship_window * 2 + 2 for node in nodes])
        candles = await market.candles(config.symbol, config.timeframe, limit)
        health = assess_candles(
            candles,
            account_id=config.account_id,
            symbol=config.symbol,
            timeframe=config.timeframe,
            now=now,
            maximum_age_seconds=timeframe_age_seconds(config.timeframe),
        )
        require_healthy(health)
    if nodes:

        async def measure(node: DetectorDefinition) -> tuple[str, MarketRelationship]:
            assert node.related_symbol is not None
            params = RelationshipRequest(
                account_id=config.account_id,
                symbols=[config.symbol, node.related_symbol],
                timeframe=config.timeframe,
                window=node.relationship_window,
            )
            peer = await market.candles(params.symbols[1], config.timeframe, params.window * 2 + 2)
            value = measure_relationship(
                params,
                [candles[-params.window * 2 - 2 :], peer],
                identifier=stable_id(row.id, node.id),
                owner_id=row.owner_id,
                agent_id=row.agent_id or "",
                now=now,
            )
            if not relationship_usable(value, now):
                raise LonoraError(
                    value.reason_codes[0]
                    if value.reason_codes
                    else "relationship_evidence_unreliable",
                    409,
                )
            return node.id, value

        try:
            async with asyncio.timeout(25):
                relationships = dict(await asyncio.gather(*(measure(node) for node in nodes)))
        except TimeoutError as error:
            raise LonoraError("relationship_history_timeout", 504) from error
        health = HealthSnapshot(
            state="healthy",
            reason_code="market_data_healthy",
            resource="watch",
            account_id=config.account_id,
            symbol=config.symbol,
            timeframe=config.timeframe,
            observed_at=now,
            last_good_at=min(value.samples[-1].end for value in relationships.values()),
        )
    raw_previous = row.state.get("observation")
    previous = Observation.model_validate(raw_previous) if isinstance(raw_previous, dict) else None
    observation = evaluate_detector(
        config.detector,
        symbol=config.symbol,
        timeframe=config.timeframe,
        quote=quote,
        candles=candles,
        observed_at=now,
        previous=previous,
        relationships=relationships,
    )
    return (
        Decimal(int(observation.state == "confirmed")),
        observation.id,
        {
            "observation": observation.model_dump(mode="json"),
            "health": health.model_dump(mode="json"),
        },
    )


# Reads one stored secret of the watch's owner by id (``EncryptedSecretStore.read``).
SecretReader = Callable[[str], Awaitable[str]]


async def unreadable(_: str) -> str:
    """No owner store was given: a calendar whose address is in the store cannot be read."""
    raise LonoraError("calendar_integration_unavailable", 409)


async def observe(
    db: Database,
    brokers: BrokerManager,
    row: MarketWatchRow,
    config: Watch,
    *,
    read_secret: SecretReader | None = None,
) -> tuple[Decimal, str, dict[str, Any]]:
    bound_symbol = None
    if row.agent_id:
        async with db.sessions() as session:
            agent = await agent_binding(session, row.owner_id, row.agent_id)
            assert_payload_binding(agent, config.model_dump(mode="json"))
            bound_symbol = agent.trading_symbol if fixed_market(agent) else None
    if config.kind == "calendar":
        async with db.sessions() as session:
            source = await session.get(IntegrationRow, config.integration_id or "")
        if source is None or source.owner_id != row.owner_id or not source.payload.get("enabled"):
            raise LonoraError("calendar_integration_unavailable", 409)
        # A calendar saved from a Secret card keeps its address in the encrypted store,
        # read through the owner's store (never the broker layer's, 7.2.3).
        url = await source_url(source.payload, read_secret or unreadable)
        events = await EconomicCalendarAdapter(url).events()
        now = utcnow()
        due = [
            event
            for event in events
            if event.scheduled_at <= now
            and event.scheduled_at > now - timedelta(seconds=max(120, config.interval_seconds * 3))
            and (not config.currency or event.currency == config.currency)
            and (not config.event_id or event.id == config.event_id)
        ]
        fresh = [event for event in due if event.id not in row.state.get("seen_events", [])]
        return (
            Decimal(len(fresh)),
            request_hash({"events": [event.model_dump(mode="json") for event in fresh]}),
            {
                "events": [event.model_dump(mode="json") for event in fresh],
                "event_ids": [event.id for event in fresh],
            },
        )
    broker = await brokers.get(row.owner_id, config.account_id)
    market = await broker_market(brokers, row.owner_id, config.account_id)
    if config.kind == "dynamic":
        return await observe_dynamic(db, brokers, row, config)
    if config.kind == "price":
        quote = await market.quote(config.symbol)
        health = assess_quote(
            quote,
            account_id=config.account_id,
            symbol=config.symbol,
            now=utcnow(),
            maximum_age_seconds=max(30, config.interval_seconds * 2),
        )
        require_healthy(health)
        return (
            quote.bid,
            quote.observed_at.isoformat(),
            {"quote": quote.model_dump(mode="json"), "health": health.model_dump(mode="json")},
        )
    if config.kind == "indicator":
        candles = await market.candles(
            config.symbol, config.timeframe, max(100, config.period + 35)
        )
        health = assess_candles(
            candles,
            account_id=config.account_id,
            symbol=config.symbol,
            timeframe=config.timeframe,
            now=utcnow(),
            maximum_age_seconds=timeframe_age_seconds(config.timeframe),
        )
        require_healthy(health)
        series = indicator_series(config.indicator, candles, config.period).get(config.series)
        if not series or series[-1] is None:
            raise LonoraError("watch_indicator_unavailable", 409)
        return (
            Decimal(str(series[-1])),
            candles[-1].time.isoformat(),
            {
                "health": health.model_dump(mode="json"),
                "indicator": config.indicator,
                "series": config.series,
                "value": series[-1],
                "time": candles[-1].time.isoformat(),
            },
        )
    if config.kind == "account":
        account = await broker.account()
        health = assess_account(
            account,
            account_id=config.account_id,
            now=utcnow(),
            maximum_age_seconds=max(30, config.interval_seconds * 2),
        )
        require_healthy(health)
        payload = account.model_dump(mode="json")
        return (
            Decimal(str(payload[config.metric])),
            request_hash(payload),
            {"account": payload, "health": health.model_dump(mode="json")},
        )
    positions = await broker.positions()
    position = next((item for item in positions if item.id == config.position_id), None)
    if position and bound_symbol and position.symbol != bound_symbol:
        raise LonoraError("agent_trading_symbol_mismatch", 409)
    if position and config.symbol and position.symbol != config.symbol:
        raise LonoraError("watch_position_symbol_mismatch", 409)
    payload = position.model_dump(mode="json") if position else {}
    current = (
        Decimal(int(position is not None))
        if config.condition in {"opened", "closed"}
        else Decimal(str(payload.get(config.metric, 0)))
    )
    return (
        current,
        request_hash(payload),
        {
            "position": payload,
            "position_id": config.position_id,
            # Positions have no upstream timestamp in the broker-neutral contract.
            # This is an explicit completed broker read, not a cached market tick.
            "observed_at": utcnow().isoformat(),
        },
    )


async def observe_stream_indicator(
    db: Database, row: MarketWatchRow, config: Watch
) -> tuple[Decimal, str, dict[str, Any]]:
    async with db.sessions() as session:
        connection = await BrokerSessionRepository().get(session, row.owner_id, config.account_id)
        snapshot = await session.get(
            MarketSnapshotRow,
            snapshot_id(row.owner_id, config.account_id, config.symbol, config.timeframe),
        )
        if (
            snapshot is None
            or snapshot.connection_version != connection.version
            or not connection.payload.get("enabled")
        ):
            raise LonoraError("watch_candles_unavailable", 409)
        candles = [Candle.model_validate(value) for value in snapshot.payload.get("candles", [])]
    health = assess_candles(
        candles,
        account_id=config.account_id,
        symbol=config.symbol,
        timeframe=config.timeframe,
        now=utcnow(),
        maximum_age_seconds=timeframe_age_seconds(config.timeframe),
        received_at=snapshot.updated_at,
        maximum_receive_age_seconds=timeframe_age_seconds(config.timeframe),
    )
    require_healthy(health)
    values = indicator_series(config.indicator, candles, config.period).get(config.series)
    if not values or values[-1] is None:
        raise LonoraError("watch_indicator_unavailable", 409)
    metadata = {
        "health": health.model_dump(mode="json"),
        "indicator": config.indicator,
        "series": config.series,
        "value": values[-1],
        "time": candles[-1].time.isoformat(),
        "symbol": config.symbol,
        "timeframe": config.timeframe,
    }
    return (
        Decimal(str(values[-1])),
        request_hash({key: value for key, value in metadata.items() if key != "health"}),
        metadata,
    )


async def check_watches(
    db: Database,
    brokers: BrokerManager,
    *,
    price_update: Quote | None = None,
    candle_update: Candle | None = None,
    connection_id: str | None = None,
    owner_id: str | None = None,
    read_secret: SecretReader | None = None,
) -> int:
    now = utcnow().isoformat()
    next_check = MarketWatchRow.state["next_check"].as_string()
    lifecycle = MarketWatchRow.state["lifecycle"].as_string()
    expires_at = MarketWatchRow.payload["expires_at"].as_string()
    async with db.sessions() as session:
        # Filter and order in SQL: retired, disabled and quarantined rows never take a
        # slot in the batch, so new watches are not starved behind old ones.
        query = (
            select(MarketWatchRow)
            .join(AgentRow, AgentRow.id == MarketWatchRow.agent_id)
            .where(
                AgentRow.paused.is_(False),
                MarketWatchRow.agent_id.is_not(None),
                MarketWatchRow.thread_id.is_not(None),
                MarketWatchRow.payload["enabled"].as_boolean().is_not(False),
                or_(lifecycle.is_(None), lifecycle != "expired"),
                ~blocked("watch", MarketWatchRow.id),
            )
        )
        if price_update is None and candle_update is None:
            # Polling takes only watches that are due (or newly past their expiry),
            # most overdue first; never-checked watches come first.
            query = query.where(
                or_(next_check.is_(None), next_check <= now, expires_at <= now)
            ).order_by(next_check.asc().nulls_first(), MarketWatchRow.created_at)
        else:
            query = query.order_by(MarketWatchRow.created_at)
        if owner_id:
            query = query.where(MarketWatchRow.owner_id == owner_id)
        if price_update:
            query = query.where(
                MarketWatchRow.payload["kind"].as_string().in_(["price", "dynamic"]),
                MarketWatchRow.payload["account_id"].as_string() == connection_id,
                MarketWatchRow.payload["symbol"].as_string() == price_update.symbol,
            )
        if candle_update:
            query = query.where(
                MarketWatchRow.payload["kind"].as_string().in_(["indicator", "dynamic"]),
                MarketWatchRow.payload["account_id"].as_string() == connection_id,
                MarketWatchRow.payload["symbol"].as_string() == candle_update.symbol,
                MarketWatchRow.payload["timeframe"].as_string() == candle_update.timeframe,
            )
        watches = list((await session.scalars(query.limit(200))).all())
    # Each watch is isolated: one that raises backs off alone and is quarantined
    # (disabled, with an owner attention item) after repeated failures.
    guard = ItemGuard(db, "watch", quarantine=disable_watch)
    await guard.prepare(row.id for row in watches)
    triggered = 0
    for original in watches:

        async def check(original: MarketWatchRow = original) -> int:
            try:
                return await check_watch(
                    db, brokers, original, price_update, candle_update, read_secret=read_secret
                )
            except WatchSkipped:
                return 0

        triggered += await guard.run(original.id, original.owner_id, check) or 0
    return triggered


async def check_watch(
    db: Database,
    brokers: BrokerManager,
    original: MarketWatchRow,
    price_update: Quote | None,
    candle_update: Candle | None,
    *,
    read_secret: SecretReader | None = None,
) -> int:
    triggered = 0
    config = Watch.model_validate(original.payload)
    now = utcnow()
    if not config.enabled or not original.agent_id or not original.thread_id:
        return triggered
    if original.state.get("lifecycle") == "expired":
        return triggered
    if config.expires_at is not None and now >= config.expires_at:
        async with db.sessions() as session, session.begin():
            expired = await session.get(MarketWatchRow, original.id, with_for_update=True)
            if (
                expired
                and expired.version == original.version
                and expired.state.get("lifecycle") != "expired"
            ):
                expired.state = {
                    **expired.state,
                    "lifecycle": "expired",
                    "lifecycle_reason": "watch_expired",
                    "lifecycle_updated_at": now.isoformat(),
                }
                emit(
                    session,
                    expired.owner_id,
                    "watch.expired",
                    agent_id=expired.agent_id,
                    thread_id=expired.thread_id,
                    payload={"watch_id": expired.id, "reason_code": "watch_expired"},
                )
        return triggered
    if (
        price_update is None
        and candle_update is None
        and original.state.get("next_check")
        and datetime.fromisoformat(original.state["next_check"]) > now
    ):
        return triggered
    try:
        # A hung broker or source never holds the batch: the watch records an
        # unavailable observation and backs off like any other source failure.
        async with asyncio.timeout(WATCH_OBSERVATION_TIMEOUT_SECONDS):
            current, observation, metadata = await observe_watch(
                db,
                brokers,
                original,
                config,
                now,
                price_update,
                candle_update,
                read_secret=read_secret,
            )
    except (LonoraError, TimeoutError) as error:
        code = error.code if isinstance(error, LonoraError) else "watch_observation_timeout"
        async with db.sessions() as session, session.begin():
            row = await session.get(MarketWatchRow, original.id, with_for_update=True)
            if row and row.version == original.version and row.payload.get("enabled", True):
                previous_health = row.state.get("health", {})
                health = HealthSnapshot(
                    state="stale" if "stale" in code else "unavailable",
                    reason_code=code,
                    observed_at=now,
                    account_id=config.account_id,
                    symbol=config.symbol or None,
                    timeframe=config.timeframe if config.kind == "indicator" else None,
                    resource="watch",
                    last_good_at=previous_health.get("last_good_at"),
                )
                row.state = record_watch_health(
                    session,
                    row,
                    health,
                    next_check=now + timedelta(seconds=config.interval_seconds),
                )
        return triggered
    # Account for time spent awaiting the broker before checking TTL. This
    # remains processing time; evidence time is resolved independently below.
    now = utcnow()
    async with db.sessions() as session, session.begin():
        row = await session.get(MarketWatchRow, original.id, with_for_update=True)
        if row is None or row.version != original.version or not row.payload.get("enabled", True):
            return triggered
        if (
            price_update is None
            and candle_update is None
            and row.state.get("next_check")
            and datetime.fromisoformat(row.state["next_check"]) > now
        ):
            return triggered
        if config.kind == "calendar" and not metadata.get("events"):
            return triggered
        evidence_at = source_observation_time(config, metadata)
        previous_source = row.state.get("lifecycle_source_at")
        if previous_source and evidence_at < datetime.fromisoformat(previous_source):
            return triggered
        recovering = bool(row.state.get("health")) and row.state["health"].get("state") != "healthy"
        health_data = metadata.get("health")
        if isinstance(health_data, dict):
            row.state = record_watch_health(
                session,
                row,
                HealthSnapshot.model_validate(health_data),
                next_check=now + timedelta(seconds=config.interval_seconds),
            )
        quote_data = metadata.get("quote")
        if config.kind == "price" and isinstance(quote_data, dict):
            previous_time = row.state.get("quote_observed_at")
            if previous_time and datetime.fromisoformat(previous_time) >= datetime.fromisoformat(
                observation
            ):
                return triggered
        previous = (
            Decimal(str(row.state["last_value"]))
            if row.state.get("last_value") is not None and not recovering
            else None
        )
        last_triggered = (
            datetime.fromisoformat(row.state["last_triggered"])
            if row.state.get("last_triggered")
            else None
        )
        state = {
            **row.state,
            "last_value": str(current),
            "next_check": (now + timedelta(seconds=config.interval_seconds)).isoformat(),
        }
        if config.kind == "price":
            state["quote_observed_at"] = observation
        state.pop("code", None)
        matched = (
            current == 1
            if config.kind == "dynamic"
            else condition_met(config.condition, config.level, current, previous)
        )
        previous_lifecycle = state.get("lifecycle", "pending")
        state, confirmed = advance_watch(
            config,
            state,
            matched=matched,
            observation_id=observation,
            observed_at=evidence_at,
            now=now,
        )
        if isinstance(metadata.get("observation"), dict):
            state["observation"] = metadata["observation"]
            detector_state = metadata["observation"].get("state")
            if detector_state == "forming" and state["lifecycle"] == "pending":
                state["lifecycle"] = "forming"
        if previous_lifecycle != state["lifecycle"]:
            emit(
                session,
                row.owner_id,
                "watch." + state["lifecycle"],
                agent_id=row.agent_id,
                thread_id=row.thread_id,
                payload={
                    "watch_id": row.id,
                    "state": state["lifecycle"],
                    "transition_id": stable_id(
                        row.id,
                        previous_lifecycle + ":" + state["lifecycle"] + ":" + observation,
                    ),
                    "account_id": config.account_id,
                    "symbol": config.symbol,
                    "observation": metadata.get("observation"),
                },
            )
        matched = confirmed and (config.kind != "dynamic" or previous_lifecycle != "confirmed")
        if matched and watch_can_trigger(
            config.enabled, last_triggered, config.cooldown_seconds, now
        ):
            receipt_id = stable_id(row.id, observation + ":" + config.condition)
            if await session.get(MarketWakeReceiptRow, receipt_id) is None:
                # A Task-owned watch resumes that logical work through the
                # resident scheduler. Do not create a competing watch Run.
                task_run_id = row.state.get("task_run_id")
                task_run = await session.get(RunRow, task_run_id) if task_run_id else None
                if task_run_id and (
                    task_run is None or task_run.status in {"completed", "failed", "cancelled"}
                ):
                    row.state = state
                    stop_watch(row, "task_terminal")
                    row.version += 1
                    return triggered
                if task_run is not None:
                    # A tainted watch resumes its Task tainted (GENUI_PLAN §8.5); a new
                    # watch Run reads the watch's taint itself in ``create_run``.
                    from lonora_db.genui_taint import mark_row, row_taint

                    taint = await row_taint(session, "watch", row.id)
                    task_id = task_run.model_metadata.get("task_id")
                    if taint is not None and isinstance(task_id, str):
                        await mark_row(session, "ticket", task_id, taint)
                run = (
                    None
                    if task_run_id
                    else await create_run(
                        session,
                        row.owner_id,
                        RunRequest(
                            thread_id=row.thread_id or "",
                            agent_id=row.agent_id or "",
                            trigger="watch",
                            prompt=config.prompt,
                            metadata={
                                "watch_id": row.id,
                                **await background_origin(
                                    session, row.owner_id, row.agent_id or "", row.thread_id or ""
                                ),
                                "wake_receipt_id": receipt_id,
                                "previous_value": str(previous) if previous is not None else None,
                                "current_value": str(current),
                                "symbol": config.symbol,
                                "observation": observation,
                                **metadata,
                            },
                        ),
                    )
                )
                session.add(
                    MarketWakeReceiptRow(
                        id=receipt_id,
                        owner_id=row.owner_id,
                        agent_id=row.agent_id,
                        thread_id=row.thread_id,
                        payload={
                            "watch_id": row.id,
                            "run_id": task_run_id or (run.id if run else None),
                        },
                    )
                )
                state["last_triggered"] = now.isoformat()
                if config.kind == "calendar":
                    state["seen_events"] = (
                        list(state.get("seen_events", []))
                        + cast(list[str], metadata.get("event_ids", []))
                    )[-1000:]
                triggered += 1
        row.state = state
    return triggered


async def observe_watch(
    db: Database,
    brokers: BrokerManager,
    original: MarketWatchRow,
    config: Watch,
    now: datetime,
    price_update: Quote | None,
    candle_update: Candle | None,
    *,
    read_secret: SecretReader | None = None,
) -> tuple[Decimal, str, dict[str, Any]]:
    if config.kind == "dynamic":
        if (
            config.detector
            and relationship_detectors(config.detector)
            and original.state.get("next_check")
            and datetime.fromisoformat(original.state["next_check"]) > now
        ):
            raise WatchSkipped
        if price_update is not None and config.evaluation_mode in {
            "candle_update",
            "candle_close",
            "scheduled",
        }:
            raise WatchSkipped
        return await observe_dynamic(db, brokers, original, config, price_update)
    elif price_update:
        health = assess_quote(
            price_update,
            account_id=config.account_id,
            symbol=config.symbol,
            now=now,
            maximum_age_seconds=max(30, config.interval_seconds * 2),
        )
        require_healthy(health)
        return (
            price_update.bid,
            price_update.observed_at.isoformat(),
            {
                "quote": price_update.model_dump(mode="json"),
                "health": health.model_dump(mode="json"),
            },
        )
    elif candle_update:
        return await observe_stream_indicator(db, original, config)
    else:
        return await observe(db, brokers, original, config, read_secret=read_secret)
