from typing import Any

from lonora_adapters.brokers.base import BrokerManager
from lonora_contracts.market_watch import Watch
from lonora_contracts.trading import TradeRequest
from lonora_contracts.trading_goal import GoalCondition, GoalTrade
from lonora_core.user_error import LonoraError
from lonora_db.client import Database
from lonora_db.schema import GoalDecisionRow
from lonora_db.trading_goals import owned_goal
from lonora_session.idempotency import broker_operation_tag
from sqlalchemy import select


async def resolve_target(
    db: Database,
    brokers: BrokerManager,
    owner_id: str,
    goal_id: str,
    target_step_id: str,
    kind: str,
) -> str:
    async with db.sessions() as session:
        goal = await owned_goal(session, owner_id, goal_id)
        source = await session.scalar(
            select(GoalDecisionRow).where(
                GoalDecisionRow.goal_id == goal_id,
                GoalDecisionRow.step_id == target_step_id,
                GoalDecisionRow.status == "confirmed",
            )
        )
        if source is None:
            raise LonoraError("goal_target_confirmation_required", 409)
        source_id, operation_id = source.id, source.operation_id
        details: dict[str, Any] = source.result.get("details", {})
        known = source.evidence.get("targets", {}).get(kind) or details.get(kind + "_id")
        source_action = str(source.request.get("action", ""))
        same_entity = (
            kind == "position"
            and source_action in {"buy", "sell", "modify_position", "close_position"}
        ) or (
            kind == "order"
            and source_action
            in {"buy_limit", "sell_limit", "buy_stop", "sell_stop", "modify_order", "cancel_order"}
        )
        safe_broker_id = (
            source.result.get("broker_id")
            if details.get("simulation") is True and same_entity
            else None
        )
        if source_action in {"modify_position", "close_position", "modify_order", "cancel_order"}:
            known = known or source.request.get(kind + "_id")
        account_id, symbol = str(goal.payload["account_id"]), str(goal.payload["symbol"])
    broker = await brokers.get(owner_id, account_id)
    items = await broker.positions() if kind == "position" else await broker.orders()
    matches = [
        item
        for item in items
        if item.symbol == symbol
        and (
            item.id == known
            or item.id == safe_broker_id
            or item.operation_id in {operation_id, broker_operation_tag(operation_id)}
        )
    ]
    if len(matches) > 1:
        raise LonoraError("goal_target_ambiguous", 409)
    target = matches[0].id if matches else str(known or "")
    if not target:
        raise LonoraError("goal_target_not_observed", 409)
    if matches:
        async with db.sessions() as session, session.begin():
            source = await session.get(GoalDecisionRow, source_id, with_for_update=True)
            if source is not None:
                source.evidence = {
                    **source.evidence,
                    "targets": {**source.evidence.get("targets", {}), kind: target},
                }
    return target


async def resolve_trade(
    db: Database,
    brokers: BrokerManager,
    owner_id: str,
    goal_id: str,
    trade: GoalTrade,
    operation_id: str,
) -> TradeRequest:
    data = trade.model_dump(mode="json", exclude={"target_step_id"})
    if trade.target_step_id:
        kind = "position" if "position" in trade.action else "order"
        data[kind + "_id"] = await resolve_target(
            db, brokers, owner_id, goal_id, trade.target_step_id, kind
        )
    data["operation_id"] = operation_id
    return TradeRequest.model_validate(data)


async def resolve_condition(
    db: Database, brokers: BrokerManager, owner_id: str, goal_id: str, condition: GoalCondition
) -> Watch:
    data = condition.model_dump(mode="json", exclude={"target_step_id"})
    if condition.target_step_id:
        data["position_id"] = await resolve_target(
            db, brokers, owner_id, goal_id, condition.target_step_id, "position"
        )
    return Watch.model_validate(data)
