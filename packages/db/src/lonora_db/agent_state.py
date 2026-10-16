"""Derived state only: no second runtime/cache and no fabricated progress."""

from typing import Any

from lonora_contracts.agent_state import AgentLiveState
from lonora_contracts.domain import utcnow
from lonora_session.idempotency import stable_id
from sqlalchemy import and_, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from .schema import (
    BrokerSessionRow,
    CollaborationSessionRow,
    MarketWatchRow,
    RunRow,
    SuperBotRequestRow,
    TicketRow,
    TradeApprovalRow,
    TradingGoalRow,
)
from .tasks import snapshot
from .transactions import owned_agent


async def agent_live_state(session: AsyncSession, owner_id: str, agent_id: str) -> AgentLiveState:
    agent = await owned_agent(session, owner_id, agent_id)
    runs = list(
        await session.scalars(
            select(RunRow)
            .where(
                RunRow.agent_id == agent.id,
                RunRow.status.in_(
                    ["queued", "leased", "running", "waiting_input", "waiting_takeover"]
                ),
            )
            .order_by(RunRow.updated_at.desc())
            .limit(6)
        )
    )
    task_rows = list(
        await session.scalars(
            select(TicketRow)
            .where(
                TicketRow.owner_id == owner_id,
                TicketRow.agent_id == agent.id,
                or_(
                    TicketRow.state["task"]["status"]
                    .as_string()
                    .in_(["queued", "running", "waiting", "paused"]),
                    and_(
                        TicketRow.state["task"]["status"].as_string() == "failed",
                        TicketRow.state["task"]["failure"]["recovery"]
                        .as_string()
                        .in_(["owner", "modify_plan", "reconcile"]),
                    ),
                ),
            )
            .order_by(TicketRow.updated_at.desc())
            .limit(3)
        )
    )
    tasks = [await snapshot(session, row) for row in task_rows]
    # Live summaries deliberately omit plan descriptions, checkpoints and historical tool bodies.
    task_summaries = [
        {
            **{
                key: task[key]
                for key in (
                    "id",
                    "title",
                    "status",
                    "phase",
                    "waiting_reason",
                    "version",
                    "can_pause",
                    "can_resume",
                    "can_cancel",
                )
            },
            "attempt": task["attempt"],
            "failure_code": task["failure"]["code"] if task["failure"] else None,
            "recovery": task["failure"]["recovery"] if task["failure"] else None,
            "retry_at": task["failure"]["next_retry_at"] if task["failure"] else None,
        }
        for task in tasks
    ]
    approvals = int(
        await session.scalar(
            select(func.count())
            .select_from(TradeApprovalRow)
            .where(
                TradeApprovalRow.owner_id == owner_id,
                TradeApprovalRow.agent_id == agent.id,
                TradeApprovalRow.status == "pending",
            )
        )
        or 0
    )
    watches = int(
        await session.scalar(
            select(func.count())
            .select_from(MarketWatchRow)
            .where(
                MarketWatchRow.owner_id == owner_id,
                MarketWatchRow.agent_id == agent.id,
                MarketWatchRow.payload["enabled"].as_boolean().is_(True),
            )
        )
        or 0
    )
    sessions = list(
        await session.scalars(
            select(CollaborationSessionRow)
            .where(
                CollaborationSessionRow.owner_id == owner_id,
                CollaborationSessionRow.agent_id == agent.id,
                CollaborationSessionRow.state["status"]
                .as_string()
                .in_(["collaborating", "synthesizing"]),
            )
            .order_by(CollaborationSessionRow.updated_at.desc())
            .limit(3)
        )
    )
    connection_query = select(BrokerSessionRow).where(BrokerSessionRow.owner_id == owner_id)
    if agent.trading_account_id:
        connection_query = connection_query.where(BrokerSessionRow.id == agent.trading_account_id)
    connections = list(await session.scalars(connection_query.limit(32)))
    health: list[dict[str, Any]] = []
    for connection in connections:
        recovery = connection.state.get("broker_recovery", {})
        if recovery and recovery.get("status") != "connected":
            health.append(
                {
                    "account_id": connection.id,
                    "state": recovery["status"],
                    "reason_code": recovery["reason_code"],
                    "observed_at": recovery["observed_at"],
                }
            )
        for value in connection.state.get("market_health", {}).values():
            if value.get("state") != "healthy" and (
                not agent.trading_symbol or value.get("symbol") == agent.trading_symbol
            ):
                health.append(
                    {
                        key: value.get(key)
                        for key in (
                            "account_id",
                            "symbol",
                            "timeframe",
                            "state",
                            "reason_code",
                            "observed_at",
                            "last_good_at",
                        )
                    }
                )
    pending_authorizations = int(
        await session.scalar(
            select(func.count())
            .select_from(SuperBotRequestRow)
            .where(
                SuperBotRequestRow.owner_id == owner_id,
                SuperBotRequestRow.agent_id == agent.id,
                SuperBotRequestRow.status == "pending",
                SuperBotRequestRow.expires_at > utcnow(),
            )
        )
        or 0
    )
    grants = (
        await session.execute(
            select(SuperBotRequestRow, TradingGoalRow)
            .join(TradingGoalRow, TradingGoalRow.id == SuperBotRequestRow.goal_id)
            .where(
                SuperBotRequestRow.owner_id == owner_id,
                SuperBotRequestRow.agent_id == agent.id,
                TradingGoalRow.owner_id == owner_id,
                TradingGoalRow.agent_id == agent.id,
                or_(
                    and_(
                        SuperBotRequestRow.status == "pending",
                        SuperBotRequestRow.expires_at > utcnow(),
                    ),
                    and_(
                        SuperBotRequestRow.status.in_(["activated", "paused"]),
                        SuperBotRequestRow.id
                        == TradingGoalRow.state["super_bot_request_id"].as_string(),
                    ),
                ),
            )
            .order_by(
                (SuperBotRequestRow.status == "activated").desc(),
                SuperBotRequestRow.created_at.desc(),
            )
            .limit(3)
        )
    ).all()
    authority_summaries: list[dict[str, Any]] = []
    for grant, goal in grants:
        if grant.status == "pending" and grant.expires_at <= utcnow():
            continue
        if grant.status != "pending" and goal.state.get("super_bot_request_id") != grant.id:
            continue
        review = await session.get(RunRow, stable_id(grant.id, "activation-review"))
        authority_summaries.append(
            {
                "request_id": grant.id,
                "goal_id": goal.id,
                "title": str(goal.payload["title"])[:80],
                "mode": grant.mode,
                "authorization_status": grant.status,
                "goal_status": goal.state.get("status"),
                "current_step": goal.state.get("current_step"),
                "reason_code": goal.state.get("code"),
                "review_status": review.status if review else None,
                "review_error_code": review.error_code if review else None,
                "autonomous": grant.status == "activated"
                and goal.state.get("super_bot_request_id") == grant.id
                and bool(goal.state.get("autonomous")),
            }
        )
        if len(authority_summaries) == 3:
            break
    state: Any = (
        "paused"
        if agent.paused
        else "degraded"
        if health
        else "action_required"
        if approvals
        or pending_authorizations
        or any(
            item["review_status"] == "failed" or item["goal_status"] == "blocked"
            for item in authority_summaries
        )
        or any(
            task.get("failure")
            and task["failure"]["recovery"] in {"owner", "modify_plan"}
            and task["status"] == "failed"
            for task in tasks
        )
        else "working"
        if any(run.status in {"leased", "running", "queued"} for run in runs)
        else "waiting"
        if runs or watches or tasks
        else "idle"
    )
    phase = (
        (
            str(tasks[0]["phase"])
            if tasks
            else "thinking"
            if any(run.status == "running" for run in runs)
            else "queued"
        )
        if state == "working"
        else str(tasks[0]["phase"])
        if tasks and state == "waiting"
        else "monitoring"
        if watches and state == "waiting"
        else state
    )
    reason = (
        "agent_paused"
        if agent.paused
        else str(health[0].get("reason_code"))
        if health
        else "approval_required"
        if approvals
        else "device_authorization_required"
        if pending_authorizations
        else "activation_review_failed"
        if any(item["review_status"] == "failed" for item in authority_summaries)
        else "goal_requires_review"
        if any(item["goal_status"] == "blocked" for item in authority_summaries)
        else "task_recovery_required"
        if state == "action_required"
        else "retry_backoff"
        if any(task["waiting_reason"] == "retry_backoff" for task in tasks)
        else "market_watch"
        if watches and state == "waiting"
        else None
    )
    return AgentLiveState(
        agent_id=agent.id,
        observed_at=utcnow(),
        state=state,
        phase=phase,
        reason_code=reason,
        reason_params={"pending_approvals": approvals} if approvals else {},
        tasks=task_summaries,
        runs=[
            {
                "id": row.id,
                "status": row.status,
                "trigger": row.trigger,
                "updated_at": row.updated_at.isoformat(),
            }
            for row in runs
        ],
        pending_approval_count=approvals,
        watch_count=watches,
        pending_authorization_count=pending_authorizations,
        super_bot=authority_summaries,
        collaborations=[
            {
                "id": row.id,
                "status": row.state.get("status"),
                "participant_count": len(row.state.get("participants", [])),
            }
            for row in sessions
        ],
        health=health[:6],
    )
