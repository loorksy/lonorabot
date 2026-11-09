"""Protected operational state, re-read from the server records on every model turn.

Summaries, recalled evidence and earlier transcript text can be stale or lossy.
The identities an Agent must never lose track of (unresolved financial
operations, goal steps in flight, pending approvals and active watches) are
projected here from their own tables instead, bounded and without request bodies,
prompts or broker payloads. Grants, waits and tasks are already in the live state.

Financial operations follow the journal lifecycle (``lonora_contracts.trading``):
``reserved`` (journaled, provably not sent yet), ``submitted`` and ``ambiguous``
(possibly sent; they block new risk on their market or ticket) are unresolved.
Two settled-but-not-plain states stay visible for a day: ``confirmed`` with
state verification still pending (the broker acknowledged it; its resulting
state is unverified), and ``resolved`` (settled by an owner attestation or a
vanished target, never broker confirmation). Owner restrictions and monetary
limits are not repeated here: the permission frame of the same routing frame
re-reads them every turn. Live risk usage needs a broker snapshot and is not
projected per turn.
"""

from datetime import timedelta
from typing import Any, cast

from lonora_contracts.domain import utcnow
from lonora_contracts.trading import IN_PROGRESS_STATUSES, UNRESOLVED_STATUSES
from sqlalchemy import or_, select
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
SETTLED_LIMIT = 4
CANDIDATE_LIMIT = 64
# How long a resolved or verification-pending operation stays in the frame.
SETTLED_WINDOW = timedelta(hours=24)
OPEN_STATUSES = IN_PROGRESS_STATUSES | UNRESOLVED_STATUSES
NEXT_ACTIONS = {
    # Identity journaled before the send boundary: the executor or recovery
    # settles it (an abandoned reservation is released as not sent).
    "reserved": "await_outcome_never_resend",
    "submitted": "reconcile_before_any_resend",
    "ambiguous": "reconcile_before_any_resend",
    "confirmed": "executed_awaiting_state_verification_never_resend",
    "resolved": "settled_without_broker_confirmation_never_resend",
}
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
    # Unresolved entries per owner are few (status index), and settled ones are
    # bounded by a recent window; attributing them to this agent's Runs then
    # uses primary-key lookups, not a scan of all Runs. Two statements, so
    # recently settled rows can never crowd an unresolved one out of the limit.
    recent = utcnow() - SETTLED_WINDOW
    candidates: list[TradingJournalRow] = []
    for condition in (
        TradingJournalRow.status.in_(sorted(OPEN_STATUSES)),
        or_(
            (TradingJournalRow.status == "resolved") & (TradingJournalRow.updated_at >= recent),
            (TradingJournalRow.status == "confirmed")
            & (TradingJournalRow.updated_at >= recent)
            & (
                TradingJournalRow.result["details"]["verification"]["status"].as_string()
                == "pending"
            ),
        ),
    ):
        candidates.extend(
            await session.scalars(
                select(TradingJournalRow)
                .where(
                    TradingJournalRow.owner_id == owner_id,
                    TradingJournalRow.execution_mode == "live",
                    condition,
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

    def operation(row: TradingJournalRow) -> dict[str, Any]:
        entry: dict[str, Any] = {
            "operation_id": row.operation_id,
            "account_id": row.account_id,
            "status": row.status,
            "submitted_at": row.submitted_at.isoformat() if row.submitted_at else None,
            "next_action": NEXT_ACTIONS[row.status],
            **{key: _short(row.request.get(key)) for key in REQUEST_KEYS if key in row.request},
        }
        if row.status in UNRESOLVED_STATUSES:
            # Scoped block: new risk on this market or ticket; exits stay admissible.
            entry["blocks"] = "new_risk_on_this_symbol_or_ticket"
        if row.status == "resolved":
            details: Any = row.result.get("details", {})
            resolution: Any = (
                cast(dict[str, Any], details).get("resolution")
                if isinstance(details, dict)
                else None
            )
            if isinstance(resolution, dict):
                attested = cast(dict[str, Any], resolution)
                entry["resolution"] = {
                    key: _short(attested[key])
                    for key in ("source", "outcome", "basis")
                    if attested.get(key) is not None
                }
            entry["broker_confirmed"] = False
            entry["resolved_at"] = row.updated_at.isoformat()
        return entry

    attributed = [row for row in candidates if producers(row) & mine]
    operations = [operation(row) for row in attributed if row.status in OPEN_STATUSES][
        :OPERATION_LIMIT
    ]
    verifying = [operation(row) for row in attributed if row.status == "confirmed"][:SETTLED_LIMIT]
    resolved = [operation(row) for row in attributed if row.status == "resolved"][:SETTLED_LIMIT]
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
            ("operations_awaiting_verification", verifying),
            ("recently_resolved_operations", resolved),
            ("goal_steps_in_flight", steps),
            ("pending_approvals", approvals),
            ("active_watches", watches),
        )
        if value
    }
