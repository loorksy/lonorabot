"""Remove Shadow (virtual) trading entirely (owner decision Q57).

A former Shadow agent becomes an ordinary agent, so before its mode disappears it is
made safe: it must not wake up holding live authority it was never meant to use.

- Every pending or active signed grant of a Shadow agent is revoked, and the grant's
  account-management Task is cancelled (as ``stop_management_task`` does).
- Its stored trading level becomes "No trading" (``analysis``), the lowest rung: the
  owner raises it again explicitly if they want this agent to trade. Its non-executable
  customization draft is kept. A missing level row is written explicitly.
- Every unfinished Shadow goal (any agent, paused ones included) is cancelled with the
  code ``shadow_trading_removed``; a finished one stays as history. Without this, a
  paused virtual plan could be resumed as a live one.
- Pending or approved Shadow approval cards are cancelled.
- Virtual journal receipts (``execution_mode = 'shadow'``) are deleted: no broker ever
  saw them, and once the column is gone every live-only reader (risk limits,
  reconciliation, obligations, performance) would otherwise count them as live.
- ``ln_shadow_trades`` and both ``execution_mode`` columns are dropped.

Runs a Shadow agent started keep ``execution_mode: shadow`` in their metadata, and the
executor still refuses any trade for such a Run, so an in-flight virtual Run never sends.

The downgrade is structural: the columns come back with every row at ``live`` (safe,
since the former Shadow agents now hold no grant and the "No trading" level) and an
empty ``ln_shadow_trades``. Deleted virtual receipts and positions do not come back.

Chained to 0045 by the author; the lead re-chains it at merge.
"""

import json
from datetime import UTC, datetime
from hashlib import sha256
from typing import Any, cast
from uuid import NAMESPACE_URL, uuid5

import sqlalchemy as sa
from alembic import op

revision = "0053_remove_shadow_trading"
down_revision = "0052_usage_cost"
branch_labels = None
depends_on = None

TABLES = ("ln_agents", "ln_trading_journal")
TERMINAL_GOALS = ("cancelled", "completed")
TERMINAL_TASKS = ("completed", "failed", "cancelled")


def permission_key(owner_id: str, agent_id: str) -> str:
    """Frozen copy of lonora_db.agent_permissions.permission_key."""
    return "agent-permission:" + sha256((owner_id + ":" + agent_id).encode()).hexdigest()


def payload_of(value: Any) -> dict[str, Any]:
    if isinstance(value, str):
        value = json.loads(value)
    return cast(dict[str, Any], value) if isinstance(value, dict) else {}


def dump(value: Any) -> str:
    return json.dumps(value, separators=(",", ":"), ensure_ascii=False)


def cancel_management_task(
    connection: sa.Connection, grant_id: str, owner_id: str, agent_id: str, now: datetime
) -> None:
    """Frozen copy of stop_management_task + finish_task(..., "cancelled")."""
    task_id = str(uuid5(NAMESPACE_URL, grant_id + ":account-management-task"))
    row = connection.execute(
        sa.text("SELECT owner_id, agent_id, payload, state FROM ln_tickets WHERE id = :id"),
        {"id": task_id},
    ).first()
    if row is None or row.owner_id != owner_id or row.agent_id != agent_id:
        return
    state = payload_of(row.state)
    task = payload_of(state.get("task"))
    if not task or task.get("status") in TERMINAL_TASKS:
        return
    task.update(status="cancelled", phase="cancelled", control_requested=None, waiting_reason=None)
    connection.execute(
        sa.text(
            "UPDATE ln_tickets SET state = CAST(:state AS JSON), payload = CAST(:payload AS JSON),"
            " version = version + 1, updated_at = :now WHERE id = :id"
        ),
        {
            "id": task_id,
            "state": dump({**state, "task": task}),
            "payload": dump({**payload_of(row.payload), "status": "cancelled"}),
            "now": now,
        },
    )


def settle_agent(connection: sa.Connection, owner_id: str, agent_id: str, now: datetime) -> None:
    grants = connection.execute(
        sa.text(
            "SELECT id, status FROM ln_account_authorities WHERE owner_id = :owner"
            " AND agent_id = :agent AND status IN ('pending','active') ORDER BY id"
        ),
        {"owner": owner_id, "agent": agent_id},
    ).all()
    for grant in grants:
        connection.execute(
            sa.text(
                "UPDATE ln_account_authorities SET status = 'revoked', updated_at = :now"
                " WHERE id = :id"
            ),
            {"id": grant.id, "now": now},
        )
        cancel_management_task(connection, grant.id, owner_id, agent_id, now)
    key = permission_key(owner_id, agent_id)
    stored = connection.execute(
        sa.text("SELECT payload FROM ln_settings WHERE key = :key"), {"key": key}
    ).scalar()
    if stored is None:
        record = {
            "owner_id": owner_id,
            "agent_id": agent_id,
            "revision": 1,
            "fallback_level": "analysis",
            "customization": None,
        }
        connection.execute(
            sa.text(
                "INSERT INTO ln_settings (key, payload, updated_at)"
                " VALUES (:key, CAST(:payload AS JSON), :now)"
            ),
            {"key": key, "payload": dump(record), "now": now},
        )
        return
    record = payload_of(stored)
    record.update(fallback_level="analysis", revision=int(record.get("revision") or 0) + 1)
    connection.execute(
        sa.text(
            "UPDATE ln_settings SET payload = CAST(:payload AS JSON), updated_at = :now"
            " WHERE key = :key"
        ),
        {"key": key, "payload": dump(record), "now": now},
    )


def settle_goals(connection: sa.Connection, now: datetime) -> None:
    goals = connection.execute(
        sa.text(
            "SELECT id, state FROM ln_trading_goals"
            " WHERE CAST(state AS JSONB) ->> 'execution_mode' = 'shadow'"
        )
    ).all()
    for goal in goals:
        state = payload_of(goal.state)
        if state.get("status") in TERMINAL_GOALS:
            continue
        state.update(status="cancelled", code="shadow_trading_removed")
        connection.execute(
            sa.text(
                "UPDATE ln_trading_goals SET state = CAST(:state AS JSON),"
                " version = version + 1, updated_at = :now WHERE id = :id"
            ),
            {"id": goal.id, "state": dump(state), "now": now},
        )


def upgrade() -> None:
    connection = op.get_bind()
    now = datetime.now(UTC)
    for agent in connection.execute(
        sa.text("SELECT id, owner_id FROM ln_agents WHERE execution_mode = 'shadow' ORDER BY id")
    ).all():
        settle_agent(connection, str(agent.owner_id), str(agent.id), now)
    settle_goals(connection, now)
    connection.execute(
        sa.text(
            "UPDATE ln_trade_approvals SET status = 'cancelled', updated_at = :now"
            " WHERE status IN ('pending','approved')"
            " AND CAST(broker_snapshot AS JSONB) -> 'execution_mode' ->> 'value' = 'shadow'"
        ),
        {"now": now},
    )
    connection.execute(sa.text("DELETE FROM ln_trading_journal WHERE execution_mode = 'shadow'"))
    op.drop_table("ln_shadow_trades")
    op.drop_index("ix_ln_trading_journal_execution_mode", table_name="ln_trading_journal")
    for table in TABLES:
        op.drop_constraint(table + "_execution_mode", table, type_="check")
        op.drop_column(table, "execution_mode")


def downgrade() -> None:
    for table in TABLES:
        op.add_column(
            table, sa.Column("execution_mode", sa.String(12), nullable=False, server_default="live")
        )
        op.create_check_constraint(
            table + "_execution_mode", table, "execution_mode IN ('live','shadow')"
        )
    op.create_index(
        "ix_ln_trading_journal_execution_mode", "ln_trading_journal", ["execution_mode"]
    )
    op.create_table(
        "ln_shadow_trades",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "owner_id",
            sa.String(),
            sa.ForeignKey("ln_owners.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("agent_id", sa.String(36), sa.ForeignKey("ln_agents.id", ondelete="CASCADE")),
        sa.Column("thread_id", sa.String(36), sa.ForeignKey("ln_threads.id", ondelete="CASCADE")),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.Column("state", sa.JSON(), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("account_id", sa.String(120), nullable=False),
        sa.Column("symbol", sa.String(80), nullable=False),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("decision_id", sa.String(36)),
        sa.Column("thesis_id", sa.String(36)),
    )
    for column in ("owner_id", "account_id", "symbol", "status"):
        op.create_index("ix_ln_shadow_trades_" + column, "ln_shadow_trades", [column])
