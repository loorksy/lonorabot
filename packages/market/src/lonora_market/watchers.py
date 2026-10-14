from datetime import datetime, timedelta
from decimal import Decimal
from typing import Any, cast

from lonora_adapters.brokers.base import BrokerManager
from lonora_adapters.market.economic_calendar import EconomicCalendarAdapter
from lonora_charts.indicators import indicator_series
from lonora_contracts.domain import utcnow
from lonora_contracts.market import Candle, Quote
from lonora_contracts.market_watch import Watch
from lonora_contracts.runs import RunRequest
from lonora_core.market_watch import condition_met
from lonora_core.user_error import LonoraError
from lonora_db.broker_sessions import BrokerSessionRepository
from lonora_db.client import Database
from lonora_db.market_snapshots import snapshot_id
from lonora_db.runs import create_run
from lonora_db.schema import (
    AgentRow,
    IntegrationRow,
    MarketSnapshotRow,
    MarketWakeReceiptRow,
    MarketWatchRow,
)
from lonora_session.idempotency import request_hash, stable_id
from sqlalchemy import select

from .broker import broker_market
from .watch_control import watch_can_trigger


async def observe(
    db: Database, brokers: BrokerManager, row: MarketWatchRow, config: Watch
) -> tuple[Decimal, str, dict[str, Any]]:
    if config.kind == "calendar":
        async with db.sessions() as session:
            source = await session.get(IntegrationRow, config.integration_id or "")
        if source is None or source.owner_id != row.owner_id or not source.payload.get("enabled"):
            raise LonoraError("calendar_integration_unavailable", 409)
        events = await EconomicCalendarAdapter(source.payload["url"]).events()
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
    if config.kind == "price":
        quote = await market.quote(config.symbol)
        return quote.bid, quote.observed_at.isoformat(), {"quote": quote.model_dump(mode="json")}
    if config.kind == "indicator":
        candles = await market.candles(
            config.symbol, config.timeframe, max(100, config.period + 35)
        )
        if not candles:
            raise LonoraError("watch_candles_unavailable", 409)
        series = indicator_series(config.indicator, candles, config.period).get(config.series)
        if not series or series[-1] is None:
            raise LonoraError("watch_indicator_unavailable", 409)
        return (
            Decimal(str(series[-1])),
            candles[-1].time.isoformat(),
            {
                "indicator": config.indicator,
                "series": config.series,
                "value": series[-1],
                "time": candles[-1].time.isoformat(),
            },
        )
    if config.kind == "account":
        account = await broker.account()
        payload = account.model_dump(mode="json")
        return Decimal(str(payload[config.metric])), request_hash(payload), {"account": payload}
    positions = await broker.positions()
    position = next((item for item in positions if item.id == config.position_id), None)
    payload = position.model_dump(mode="json") if position else {}
    current = (
        Decimal(int(position is not None))
        if config.condition in {"opened", "closed"}
        else Decimal(str(payload.get(config.metric, 0)))
    )
    return current, request_hash(payload), {"position": payload, "position_id": config.position_id}


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
    if not candles:
        raise LonoraError("watch_candles_unavailable", 409)
    values = indicator_series(config.indicator, candles, config.period).get(config.series)
    if not values or values[-1] is None:
        raise LonoraError("watch_indicator_unavailable", 409)
    metadata = {
        "indicator": config.indicator,
        "series": config.series,
        "value": values[-1],
        "time": candles[-1].time.isoformat(),
        "symbol": config.symbol,
        "timeframe": config.timeframe,
    }
    return Decimal(str(values[-1])), request_hash(metadata), metadata


async def check_watches(
    db: Database,
    brokers: BrokerManager,
    *,
    price_update: Quote | None = None,
    candle_update: Candle | None = None,
    connection_id: str | None = None,
    owner_id: str | None = None,
) -> int:
    async with db.sessions() as session:
        query = (
            select(MarketWatchRow)
            .join(AgentRow, AgentRow.id == MarketWatchRow.agent_id)
            .where(AgentRow.paused.is_(False))
        )
        if owner_id:
            query = query.where(MarketWatchRow.owner_id == owner_id)
        if price_update:
            query = query.where(
                MarketWatchRow.payload["kind"].as_string() == "price",
                MarketWatchRow.payload["account_id"].as_string() == connection_id,
                MarketWatchRow.payload["symbol"].as_string() == price_update.symbol,
            )
        if candle_update:
            query = query.where(
                MarketWatchRow.payload["kind"].as_string() == "indicator",
                MarketWatchRow.payload["account_id"].as_string() == connection_id,
                MarketWatchRow.payload["symbol"].as_string() == candle_update.symbol,
                MarketWatchRow.payload["timeframe"].as_string() == candle_update.timeframe,
            )
        watches = list((await session.scalars(query.limit(200))).all())
    triggered = 0
    for original in watches:
        config = Watch.model_validate(original.payload)
        now = utcnow()
        if not config.enabled or not original.agent_id or not original.thread_id:
            continue
        if config.goal_id:
            from lonora_db.trading_goals import owned_goal

            async with db.sessions() as session:
                goal = await owned_goal(session, original.owner_id, config.goal_id)
            if (
                goal.state.get("status") in {"cancelled", "completed"}
                or config.goal_plan_version is not None
                and config.goal_plan_version != goal.state.get("plan_version", 1)
            ):
                async with db.sessions() as session, session.begin():
                    obsolete = await session.get(MarketWatchRow, original.id, with_for_update=True)
                    if obsolete is not None:
                        obsolete.payload = {**obsolete.payload, "enabled": False}
                        obsolete.version += 1
                continue
            if goal.state.get("status") == "paused":
                continue
        if (
            price_update is None
            and candle_update is None
            and original.state.get("next_check")
            and datetime.fromisoformat(original.state["next_check"]) > now
        ):
            continue
        try:
            if price_update:
                current, observation, metadata = (
                    price_update.bid,
                    price_update.observed_at.isoformat(),
                    {"quote": price_update.model_dump(mode="json")},
                )
            elif candle_update:
                current, observation, metadata = await observe_stream_indicator(
                    db, original, config
                )
            else:
                current, observation, metadata = await observe(db, brokers, original, config)
        except LonoraError as error:
            async with db.sessions() as session, session.begin():
                row = await session.get(MarketWatchRow, original.id, with_for_update=True)
                if row:
                    row.state = {
                        **row.state,
                        "code": error.code,
                        "next_check": (
                            now + timedelta(seconds=config.interval_seconds)
                        ).isoformat(),
                    }
            continue
        async with db.sessions() as session, session.begin():
            row = await session.get(MarketWatchRow, original.id, with_for_update=True)
            if (
                row is None
                or row.version != original.version
                or not row.payload.get("enabled", True)
            ):
                continue
            if (
                price_update is None
                and candle_update is None
                and row.state.get("next_check")
                and datetime.fromisoformat(row.state["next_check"]) > now
            ):
                continue
            quote_data = metadata.get("quote")
            if config.kind == "price" and isinstance(quote_data, dict):
                previous_time = row.state.get("quote_observed_at")
                if previous_time and datetime.fromisoformat(
                    previous_time
                ) >= datetime.fromisoformat(observation):
                    continue
            previous = (
                Decimal(str(row.state["last_value"]))
                if row.state.get("last_value") is not None
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
            matched = condition_met(config.condition, config.level, current, previous)
            if matched and watch_can_trigger(
                config.enabled, last_triggered, config.cooldown_seconds, now
            ):
                receipt_id = stable_id(row.id, observation + ":" + config.condition)
                if await session.get(MarketWakeReceiptRow, receipt_id) is None:
                    if config.goal_id:
                        from lonora_db.trading_goals import owned_goal
                        from lonora_db.transactions import owned_thread

                        await owned_thread(session, row.owner_id, row.thread_id or "", lock=True)
                        goal = await owned_goal(session, row.owner_id, config.goal_id, True)
                        if (
                            config.goal_plan_version is not None
                            and config.goal_plan_version != goal.state.get("plan_version", 1)
                            or goal.state.get("status") not in {"active", "waiting"}
                            or goal.state.get("current_step") != config.step_id
                            or goal.state["steps"].get(config.step_id, {}).get("status")
                            in {"completed", "blocked", "executing"}
                        ):
                            row.state = state
                            continue
                    run = await create_run(
                        session,
                        row.owner_id,
                        RunRequest(
                            thread_id=row.thread_id or "",
                            agent_id=row.agent_id or "",
                            trigger="watch",
                            prompt=config.prompt,
                            metadata={
                                "watch_id": row.id,
                                "wake_receipt_id": receipt_id,
                                "previous_value": str(previous) if previous is not None else None,
                                "current_value": str(current),
                                **(
                                    {"goal_id": config.goal_id, "step_id": config.step_id}
                                    if config.goal_id
                                    else {}
                                ),
                                "symbol": config.symbol,
                                "observation": observation,
                                **metadata,
                            },
                        ),
                    )
                    session.add(
                        MarketWakeReceiptRow(
                            id=receipt_id,
                            owner_id=row.owner_id,
                            agent_id=row.agent_id,
                            thread_id=row.thread_id,
                            payload={"watch_id": row.id, "run_id": run.id},
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
