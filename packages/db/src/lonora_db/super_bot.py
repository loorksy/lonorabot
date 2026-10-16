"""One durable, owner-authorized Agent capability over existing trading goals."""

from datetime import timedelta
from decimal import Decimal
from typing import Any, Literal, cast

from lonora_contracts.domain import utcnow
from lonora_contracts.super_bot import SuperBotEnvelope, SuperBotProposal
from lonora_contracts.trading_goal import GoalStep
from lonora_core.user_error import LonoraError
from lonora_session.idempotency import request_hash
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from .agent_binding import assert_payload_binding, require_financial_agent
from .events import emit
from .schema import DeviceCredentialRow, SuperBotRequestRow, TradingGoalRow


async def authority_lock(session: AsyncSession, agent_id: str) -> None:
    if session.get_bind().dialect.name == "postgresql":
        await session.execute(
            text("SELECT pg_advisory_xact_lock(hashtextextended(:key,0))"),
            {"key": "super-bot:" + agent_id},
        )


def plan_hash(goal: TradingGoalRow) -> str:
    return request_hash(
        {
            key: value
            for key, value in goal.payload.items()
            if key not in {"maximum_volume", "max_trade_actions"}
        }
    )


def request_data(row: SuperBotRequestRow) -> dict[str, Any]:
    return {
        "id": row.id,
        "agent_id": row.agent_id,
        "thread_id": row.thread_id,
        "goal_id": row.goal_id,
        "mode": row.mode,
        "status": "expired"
        if row.status == "pending" and row.expires_at <= utcnow()
        else row.status,
        "envelope": row.envelope,
        "expires_at": row.expires_at.isoformat(),
        "updated_at": row.updated_at.isoformat(),
    }


def changed(session: AsyncSession, row: SuperBotRequestRow) -> None:
    row.updated_at = utcnow()
    emit(
        session,
        row.owner_id,
        "super_bot.updated",
        agent_id=row.agent_id,
        thread_id=row.thread_id,
        payload=request_data(row),
    )


async def owned_request(
    session: AsyncSession, owner_id: str, identifier: str, *, lock: bool = False
) -> SuperBotRequestRow:
    row = await session.get(
        SuperBotRequestRow, identifier, with_for_update=lock, populate_existing=True
    )
    if row is None or row.owner_id != owner_id:
        raise LonoraError("super_bot_request_not_found", 404)
    return row


async def propose(
    session: AsyncSession, owner_id: str, agent_id: str, body: SuperBotProposal
) -> SuperBotRequestRow:
    from .trading_goals import owned_goal, require_autonomous_limits

    await authority_lock(session, agent_id)
    agent = await require_financial_agent(session, owner_id, agent_id)
    goal = await owned_goal(session, owner_id, body.goal_id, True)
    if goal.agent_id != agent_id or goal.state.get("status") in {"completed", "cancelled"}:
        raise LonoraError("goal_run_mismatch", 409)
    assert_payload_binding(agent, goal.payload)
    if body.mode == "autonomous":
        require_autonomous_limits(goal)
        steps = [GoalStep.model_validate(step) for step in goal.payload["steps"]]
        manual_steps = [
            step
            for step in steps
            if step.trade
            and step.trade.action
            in {"modify_position", "close_position", "modify_order", "cancel_order"}
            and not step.trade.target_step_id
        ]
        if manual_steps and not body.allow_manual_positions:
            raise LonoraError("super_bot_manual_permission_required", 409)
    envelope = SuperBotEnvelope(
        goal_id=goal.id,
        account_id=goal.payload["account_id"],
        symbol=goal.payload["symbol"],
        plan_version=goal.state.get("plan_version", 1),
        plan_hash=plan_hash(goal),
        mode=body.mode,
        maximum_volume=goal.payload.get("maximum_volume"),
        max_trade_actions=goal.payload["max_trade_actions"],
        allow_manual_positions=body.allow_manual_positions,
        execution_mode=cast(Literal["live", "shadow"], agent.execution_mode),
        goal_title=goal.payload["title"],
        objective=goal.payload["objective"],
        steps=[GoalStep.model_validate(step) for step in goal.payload["steps"]],
    )
    data = envelope.model_dump(mode="json")
    digest = request_hash(data)
    previous = await session.scalar(
        select(SuperBotRequestRow)
        .where(
            SuperBotRequestRow.owner_id == owner_id,
            SuperBotRequestRow.agent_id == agent_id,
            SuperBotRequestRow.envelope_hash == digest,
            SuperBotRequestRow.status == "pending",
            SuperBotRequestRow.expires_at > utcnow(),
        )
        .limit(1)
    )
    if previous:
        return previous
    row = SuperBotRequestRow(
        owner_id=owner_id,
        agent_id=agent_id,
        thread_id=goal.thread_id,
        goal_id=goal.id,
        mode=body.mode,
        envelope=data,
        envelope_hash=digest,
        expires_at=utcnow() + timedelta(minutes=10),
    )
    session.add(row)
    await session.flush()
    changed(session, row)
    return row


async def require_goal_authority(
    session: AsyncSession, goal: TradingGoalRow, *, mode: str = "autonomous"
) -> SuperBotRequestRow:
    row = await session.get(SuperBotRequestRow, goal.state.get("super_bot_request_id", ""))
    if (
        row is None
        or row.owner_id != goal.owner_id
        or row.agent_id != goal.agent_id
        or row.goal_id != goal.id
        or row.status != "activated"
        or row.mode != mode
    ):
        raise LonoraError("device_authorization_required", 403)
    device = await session.get(DeviceCredentialRow, row.device_id or "")
    envelope = SuperBotEnvelope.model_validate(row.envelope)
    if envelope.mode != mode and not (mode == "supervised" and envelope.mode == "autonomous"):
        raise LonoraError("device_authorization_required", 403)
    if device is None or device.owner_id != goal.owner_id or device.revoked:
        raise LonoraError("device_authorization_required", 403)
    if (
        request_hash(row.envelope) != row.envelope_hash
        or plan_hash(goal) != envelope.plan_hash
        or goal.state.get("plan_version", 1) != envelope.plan_version
    ):
        raise LonoraError("super_bot_plan_changed", 409)
    agent = await require_financial_agent(session, goal.owner_id, goal.agent_id or "")
    if (
        agent.execution_mode != envelope.execution_mode
        or envelope.account_id != goal.payload["account_id"]
        or envelope.symbol != goal.payload["symbol"]
    ):
        raise LonoraError("super_bot_scope_changed", 409)
    maximum = goal.payload.get("maximum_volume")
    if (
        (mode == "autonomous" and (envelope.maximum_volume is None or maximum is None))
        or (
            envelope.maximum_volume is not None
            and (maximum is None or Decimal(str(maximum)) > envelope.maximum_volume)
        )
        or goal.payload["max_trade_actions"] > envelope.max_trade_actions
    ):
        raise LonoraError("super_bot_authority_expansion", 403)
    return row


async def stop_request(session: AsyncSession, row: SuperBotRequestRow, status: str) -> None:
    from .trading_goals import owned_goal, update_goal_state

    goal = await owned_goal(session, row.owner_id, row.goal_id, True)
    if goal.state.get("super_bot_request_id") == row.id:
        update_goal_state(session, goal, {**goal.state, "autonomous": False})
    row.status = status
    changed(session, row)
