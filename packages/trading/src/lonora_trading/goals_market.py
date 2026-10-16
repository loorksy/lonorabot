from datetime import timedelta
from decimal import Decimal
from typing import Any

from lonora_adapters.brokers.base import BrokerManager
from lonora_charts.indicators import indicator_series
from lonora_contracts.domain import utcnow
from lonora_core.market_watch import condition_met
from lonora_core.user_error import LonoraError
from lonora_db.client import Database
from lonora_db.goal_scope import goal_mode
from lonora_db.schema import MarketWakeReceiptRow, MarketWatchRow, RunRow
from lonora_db.trading_goals import owned_goal, planned_step

from .goal_broker import goal_broker
from .goals_targets import resolve_condition


async def fresh_goal_evidence(
    db: Database,
    brokers: BrokerManager,
    owner_id: str,
    goal_id: str,
    step_id: str,
    run_id: str | None = None,
) -> dict[str, Any]:
    async with db.sessions() as session:
        goal = await owned_goal(session, owner_id, goal_id)
        step = planned_step(goal, step_id)
        symbol = str(goal.payload["symbol"])
    config = (
        await resolve_condition(db, brokers, owner_id, goal_id, step.condition)
        if step.condition
        else None
    )
    trigger: dict[str, Any] = {}
    if step.condition and step.condition.condition in {"cross_above", "cross_below", "changed"}:
        async with db.sessions() as session:
            run = await session.get(RunRow, run_id) if run_id else None
            watch = (
                await session.get(MarketWatchRow, run.model_metadata.get("watch_id"))
                if run and run.model_metadata.get("watch_id")
                else None
            )
            receipt = (
                await session.get(MarketWakeReceiptRow, run.model_metadata.get("wake_receipt_id"))
                if run and run.model_metadata.get("wake_receipt_id")
                else None
            )
            if (
                run is None
                or watch is None
                or receipt is None
                or watch.owner_id != owner_id
                or receipt.owner_id != owner_id
                or receipt.payload.get("run_id") != run.id
                or watch.payload.get("goal_id") != goal_id
                or watch.payload.get("step_id") != step_id
                or watch.payload.get("condition") != step.condition.condition
                or str(watch.payload.get("level")) != str(step.condition.level)
            ):
                raise LonoraError("goal_watch_evidence_required", 409)
            if watch.payload.get("goal_plan_version") != goal.state.get("plan_version", 1):
                raise LonoraError("goal_watch_evidence_required", 409)
            if config is not None:
                expected = config.model_dump(mode="json")
                fields = (
                    "kind",
                    "account_id",
                    "symbol",
                    "condition",
                    "level",
                    "timeframe",
                    "indicator",
                    "period",
                    "series",
                    "metric",
                    "position_id",
                    "integration_id",
                    "event_id",
                    "currency",
                )
                if any(watch.payload.get(field) != expected.get(field) for field in fields):
                    raise LonoraError("goal_watch_evidence_required", 409)
            trigger = run.model_metadata
    broker = await goal_broker(db, brokers, goal)
    local_cancel = (
        goal_mode(goal) == "shadow"
        and step.trade is not None
        and step.trade.action == "cancel_order"
        and config is None
    )
    account = None if local_cancel else await broker.account()
    positions = await broker.positions()
    orders = await broker.orders()
    evidence: dict[str, Any] = {
        "fetched_at": utcnow().isoformat(),
        "execution_mode": goal.state.get("execution_mode", "live"),
        "account": account.model_dump(mode="json") if account else None,
        "account_source": "broker" if account else "not_required_for_local_virtual_cancel",
        "positions": [
            {
                **position.model_dump(mode="json"),
                **({"profit": None, "mode": "shadow"} if goal_mode(goal) == "shadow" else {}),
            }
            for position in positions[:200]
        ],
        "orders": [order.model_dump(mode="json") for order in orders[:200]],
    }
    if config is None:
        return evidence
    if config.kind == "price":
        quote = await broker.quote(symbol)
        if (
            quote.symbol != symbol
            or quote.observed_at < utcnow() - timedelta(seconds=60)
            or quote.observed_at > utcnow() + timedelta(seconds=30)
        ):
            raise LonoraError("goal_condition_stale", 409)
        current = quote.bid
        evidence["quote"] = quote.model_dump(mode="json")
    elif config.kind == "account":
        assert account is not None
        current = Decimal(str(account.model_dump(mode="json")[config.metric]))
    elif config.kind == "position":
        if (
            goal_mode(goal) == "shadow"
            and config.condition not in {"opened", "closed"}
            and config.metric == "profit"
        ):
            raise LonoraError("shadow_monetary_pnl_unavailable", 409)
        position = next(
            (item for item in positions if item.id == config.position_id and item.symbol == symbol),
            None,
        )
        current = (
            Decimal(int(position is not None))
            if config.condition in {"opened", "closed"}
            else Decimal(
                str(position.model_dump(mode="json").get(config.metric, 0) if position else 0)
            )
        )
    elif config.kind == "indicator":
        candles = await broker.candles(symbol, config.timeframe, max(100, config.period + 35))
        values = indicator_series(config.indicator, candles, config.period).get(config.series)
        if not values or values[-1] is None:
            raise LonoraError("goal_condition_unavailable", 409)
        current = Decimal(str(values[-1]))
        evidence["indicator"] = {
            "name": config.indicator,
            "value": str(current),
            "time": candles[-1].time.isoformat(),
        }
    else:
        # Calendar wakes are context, not authorization for an immediate financial mutation.
        raise LonoraError("goal_calendar_requires_market_condition", 409)
    condition = {"cross_above": "above", "cross_below": "below"}.get(
        config.condition, config.condition
    )
    matched = (
        current == 0
        if condition == "closed"
        else current > 0
        if condition == "opened"
        else condition_met(
            condition,
            config.level,
            current,
            Decimal(str(trigger["previous_value"]))
            if trigger.get("previous_value") is not None
            else None,
        )
    )
    if not matched:
        raise LonoraError("goal_condition_unmet", 409)
    evidence["condition"] = {
        "kind": config.kind,
        "condition": config.condition,
        "level": str(config.level),
        "observed": str(current),
        "matched": True,
    }
    return evidence
