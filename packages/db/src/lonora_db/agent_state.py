"""Derived state only: no second runtime/cache and no fabricated progress."""

from typing import Any

from lonora_contracts.agent_state import AgentLiveState
from lonora_contracts.domain import utcnow
from lonora_core.runtime_failure import MODEL_RETRY_REASON
from lonora_core.user_error import LonoraError
from lonora_session.idempotency import stable_id
from sqlalchemy import and_, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from .agent_binding import fixed_market
from .schema import (
    AccountAuthorityRow,
    BrokerSessionRow,
    CollaborationSessionRow,
    MarketWatchRow,
    RunRow,
    TicketRow,
    TradeApprovalRow,
)
from .tasks import OWNER_ATTENTION, snapshot
from .trading_readiness import account_money_limits, trading_readiness
from .transactions import owned_agent


def attention(task: dict[str, Any]) -> bool:
    """Unfinished Task work held for its owner's direction."""
    return task["status"] == "waiting" and task["waiting_reason"] == OWNER_ATTENTION


async def agent_live_state(
    session: AsyncSession, owner_id: str, agent_id: str, *, readiness: bool = False
) -> AgentLiveState:
    """``readiness`` adds the owner-facing trading readiness (presentation only).

    The model's routing frame leaves it out: its permission frame re-reads the same
    records every turn, so the agent never sees the same facts twice.
    """
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
    if fixed_market(agent):
        connection_query = connection_query.where(BrokerSessionRow.id == agent.trading_account_id)
    connections = list(await session.scalars(connection_query.limit(32)))
    health: list[dict[str, Any]] = []
    for connection in connections:
        recovery = connection.state.get("broker_recovery", {})
        if recovery and recovery.get("status") != "connected":
            health.append(
                {
                    "account_id": connection.id,
                    "kind": "broker",
                    "state": recovery["status"],
                    "reason_code": recovery["reason_code"],
                    "observed_at": recovery["observed_at"],
                }
            )
        for value in connection.state.get("market_health", {}).values():
            if value.get("state") != "healthy" and (
                not fixed_market(agent) or value.get("symbol") == agent.trading_symbol
            ):
                health.append(
                    {
                        "kind": "market",
                        **{
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
                        },
                    }
                )
    pending_authorizations = int(
        await session.scalar(
            select(func.count())
            .select_from(AccountAuthorityRow)
            .where(
                AccountAuthorityRow.owner_id == owner_id,
                AccountAuthorityRow.agent_id == agent.id,
                AccountAuthorityRow.status == "pending",
                AccountAuthorityRow.activation_expires_at > utcnow(),
                or_(
                    AccountAuthorityRow.valid_until.is_(None),
                    AccountAuthorityRow.valid_until > utcnow(),
                ),
            )
        )
        or 0
    )
    account_authorities: list[dict[str, Any]] = []
    account_grants = await session.scalars(
        select(AccountAuthorityRow)
        .where(
            AccountAuthorityRow.owner_id == owner_id,
            AccountAuthorityRow.agent_id == agent.id,
            AccountAuthorityRow.status.in_(["pending", "active"]),
            or_(
                AccountAuthorityRow.valid_until.is_(None),
                AccountAuthorityRow.valid_until > utcnow(),
            ),
        )
        .order_by(
            (AccountAuthorityRow.status == "active").desc(),
            AccountAuthorityRow.created_at.desc(),
        )
        .limit(6)
    )
    from .account_authority import require_authority

    for account_grant in account_grants:
        if account_grant.status == "pending" and account_grant.activation_expires_at <= utcnow():
            continue
        if account_grant.status == "active":
            try:
                await require_authority(session, owner_id, agent.id, account_grant.id)
            except LonoraError:
                continue
        envelope = account_grant.envelope
        review = (
            await session.get(RunRow, stable_id(account_grant.id, "activation-review"))
            if account_grant.status == "active"
            else None
        )
        account_authorities.append(
            {
                "id": account_grant.id,
                "account_id": account_grant.account_id,
                "status": account_grant.status,
                "symbols": envelope.get("symbols", [])[:100],
                "actions": envelope.get("actions", [])[:10],
                "valid_until": account_grant.valid_until.isoformat()
                if account_grant.valid_until
                else None,
                "management_mode": envelope.get("management_mode", "bounded"),
                "symbol_scope": envelope.get("symbol_scope", "selected"),
                "maximum_order_volume": envelope.get("maximum_order_volume"),
                "maximum_symbol_volume": envelope.get("maximum_symbol_volume"),
                "maximum_positions": envelope.get("maximum_positions"),
                "maximum_pending_orders": envelope.get("maximum_pending_orders"),
                "maximum_actions": envelope.get("maximum_actions"),
                "minimum_equity": envelope.get("minimum_equity"),
                "allow_manual_positions": bool(envelope.get("allow_manual_positions")),
                "review_status": review.status if review else None,
                # The owner's view adds the account's money limits; the agent reads
                # them in its permission frame instead of twice per turn.
                **(
                    {
                        "money_limits": await account_money_limits(
                            session, owner_id, account_grant.account_id
                        )
                    }
                    if readiness
                    else {}
                ),
            }
        )
        if len(account_authorities) == 3:
            break
    runtime_waits: list[dict[str, Any]] = []
    for run in runs:
        environment = run.execution_state.get("environment", {})
        retry, wait = environment.get("retry"), environment.get("wait")
        if run.status == "queued" and retry:
            # A model outage backoff is not a tool read retry; clients say which.
            kind = "model_retry" if retry.get("reason_code") == MODEL_RETRY_REASON else "read_retry"
            runtime_waits.append({"run_id": run.id, "kind": kind, "retry_at": retry["not_before"]})
        elif (
            run.status == "waiting_takeover"
            and wait
            and not any(
                task["id"] == wait["task_id"] and task["status"] == "paused" for task in tasks
            )
        ):
            runtime_waits.append(
                {"run_id": run.id, "kind": wait["kind"], "retry_at": wait.get("due_at")}
            )
    waiting_runs = {item["run_id"] for item in runtime_waits}
    state: Any = (
        "paused"
        if agent.paused
        else "degraded"
        if health
        else "action_required"
        if approvals
        or pending_authorizations
        or any(item["review_status"] == "failed" for item in account_authorities)
        or any(
            task.get("failure")
            and task["failure"]["recovery"] in {"owner", "modify_plan"}
            and task["status"] == "failed"
            for task in tasks
        )
        or any(attention(task) for task in tasks)
        else "working"
        if any(
            run.status in {"leased", "running", "queued"} and run.id not in waiting_runs
            for run in runs
        )
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
        else "recovering"
        if runtime_waits and runtime_waits[0]["kind"] in {"read_retry", "model_retry"}
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
        if any(item["review_status"] == "failed" for item in account_authorities)
        else "task_attention_required"
        if any(attention(task) for task in tasks)
        else "task_recovery_required"
        if state == "action_required"
        else MODEL_RETRY_REASON
        if any(item["kind"] == "model_retry" for item in runtime_waits)
        else "retry_backoff"
        if any(task["waiting_reason"] == "retry_backoff" for task in tasks)
        or any(item["kind"] == "read_retry" for item in runtime_waits)
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
        runtime_waits=runtime_waits,
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
        account_authorities=account_authorities,
        collaborations=[
            {
                "id": row.id,
                "status": row.state.get("status"),
                "participant_count": len(row.state.get("participants", [])),
            }
            for row in sessions
        ],
        health=health[:6],
        trading_readiness=await trading_readiness(session, owner_id, agent) if readiness else None,
    )
