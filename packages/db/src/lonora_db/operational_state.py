"""Protected operational state, re-read from the server records on every model turn.

Summaries, recalled evidence and earlier transcript text can be stale or lossy.
The identities an Agent must never lose track of (unresolved financial
operations, goal steps in flight, pending approvals and active watches) are
projected here from their own tables instead, bounded and without request bodies,
prompts or broker payloads. Grants, waits and tasks are already in the live state.
"""

from typing import Any, cast

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from .schema import (
    GoalDecisionRow,
    MarketWatchRow,
    RunRow,
    TradeApprovalRow,
    TradingGoalRow,
    TradingJournalRow,
)

OPERATION_LIMIT = 8
CANDIDATE_LIMIT = 64
STEP_LIMIT = 5
APPROVAL_LIMIT = 6
WATCH_LIMIT = 8
REQUEST_KEYS = ("action", "side", "symbol", "volume", "order_type", "account_id")


def _short(value: Any) -> Any:
    if isinstance(value, str):
        return value[:120]
    if isinstance(value, bool | int | float) or value is None:
        return value
    return str(value)[:120]


async def protected_operational_state(
    session: AsyncSession, owner_id: str, agent_id: str
) -> dict[str, list[dict[str, Any]]]:
    # Unresolved entries per owner are few (status index); attributing them to
    # this agent's Runs then uses primary-key lookups, not a scan of all Runs.
    candidates = list(
        await session.scalars(
            select(TradingJournalRow)
            .where(
                TradingJournalRow.owner_id == owner_id,
                TradingJournalRow.execution_mode == "live",
                TradingJournalRow.status.in_(["submitted", "ambiguous"]),
            )
            .order_by(TradingJournalRow.updated_at.desc())
            .limit(CANDIDATE_LIMIT)
        )
    )

    def producers(row: TradingJournalRow) -> set[str]:
        details: Any = row.result.get("details", {})
        found: set[str] = set()
        if isinstance(details, dict):
            for key in ("lease", "execution"):
                part: Any = cast(dict[str, Any], details).get(key)
                if isinstance(part, dict):
                    run_id: Any = cast(dict[str, Any], part).get("run_id")
                    if isinstance(run_id, str):
                        found.add(run_id)
        return found

    run_ids = set[str]().union(*(producers(row) for row in candidates))
    mine = (
        set(
            await session.scalars(
                select(RunRow.id).where(RunRow.id.in_(run_ids), RunRow.agent_id == agent_id)
            )
        )
        if run_ids
        else set[str]()
    )
    operations = [
        {
            "operation_id": row.operation_id,
            "account_id": row.account_id,
            "status": row.status,
            "submitted_at": row.submitted_at.isoformat() if row.submitted_at else None,
            "next_action": "reconcile_before_any_resend",
            **{key: _short(row.request.get(key)) for key in REQUEST_KEYS if key in row.request},
        }
        for row in candidates
        if producers(row) & mine
    ][:OPERATION_LIMIT]
    steps = [
        {
            "decision_id": row.id,
            "goal_id": row.goal_id,
            "step_id": row.step_id,
            "operation_id": row.operation_id,
            "status": row.status,
        }
        for row in await session.scalars(
            select(GoalDecisionRow)
            .join(TradingGoalRow, TradingGoalRow.id == GoalDecisionRow.goal_id)
            .where(
                GoalDecisionRow.owner_id == owner_id,
                TradingGoalRow.agent_id == agent_id,
                GoalDecisionRow.status.in_(["ambiguous", "submitted", "executing"]),
            )
            .order_by(GoalDecisionRow.updated_at.desc())
            .limit(STEP_LIMIT)
        )
    ]
    approvals = [
        {
            "approval_id": row.id,
            "created_at": row.created_at.isoformat(),
            "requests": [
                {key: _short(item.get(key)) for key in REQUEST_KEYS if key in item}
                for item in row.requests[:4]
            ],
        }
        for row in await session.scalars(
            select(TradeApprovalRow)
            .where(
                TradeApprovalRow.owner_id == owner_id,
                TradeApprovalRow.agent_id == agent_id,
                TradeApprovalRow.status == "pending",
            )
            .order_by(TradeApprovalRow.created_at.desc())
            .limit(APPROVAL_LIMIT)
        )
    ]
    watches = [
        {
            "watch_id": row.id,
            **{
                key: _short(row.payload.get(key))
                for key in ("kind", "account_id", "symbol", "timeframe", "condition", "expires_at")
                if row.payload.get(key) not in (None, "")
            },
        }
        for row in await session.scalars(
            select(MarketWatchRow)
            .where(
                MarketWatchRow.owner_id == owner_id,
                MarketWatchRow.agent_id == agent_id,
                MarketWatchRow.payload["enabled"].as_boolean().is_(True),
            )
            .order_by(MarketWatchRow.updated_at.desc())
            .limit(WATCH_LIMIT)
        )
    ]
    return {
        key: value
        for key, value in (
            ("unresolved_operations", operations),
            ("goal_steps_in_flight", steps),
            ("pending_approvals", approvals),
            ("active_watches", watches),
        )
        if value
    }
