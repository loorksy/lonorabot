"""Remove Shadow (virtual) trading entirely (owner decision Q57).

A former Shadow agent becomes an ordinary agent, so before its mode disappears it is
made safe: it must not wake up holding live authority it was never meant to use.

- Every pending or active signed grant of a Shadow agent is revoked the way
  ``lonora_db.account_authority.revoke`` revokes one: the status becomes ``revoked`` (the
  envelope row stays), the grant's account-management Task is cancelled, the agent's
  permission revision moves on, and an ``account_authority.updated`` event records it,
  attributed to the system with the reason ``shadow_trading_removed``.
- Its stored trading level becomes "No trading" (``analysis``), the lowest rung: the
  owner raises it again explicitly if they want this agent to trade. Its non-executable
  customization draft is kept. A missing level row is written explicitly.
- Every unfinished Shadow goal (any agent, paused ones included) is cancelled with the
  code ``shadow_trading_removed``; a finished one stays as history. Without this, a
  paused virtual plan could be resumed as a live one.
- Pending or approved Shadow approval cards are cancelled.
- Nothing is erased. Virtual journal receipts (``execution_mode = 'shadow'``) move to
  ``ln_trading_journal_shadow_retired`` (no broker ever saw them; left in place, every
  live-only reader would count them as live once the column is gone), the virtual book
  ``ln_shadow_trades`` is renamed ``ln_shadow_trades_retired``, and the former Shadow agents
  are listed in ``ln_shadow_agents_retired``. Nothing reads these tables.
- Both ``execution_mode`` columns are dropped.

Runs a Shadow agent started keep ``execution_mode: shadow`` in their metadata, and the
executor still refuses any trade for such a Run, so an in-flight virtual Run never sends.

The downgrade puts the structure and the retired data back: the columns return at
``live``, the listed agents return to ``shadow``, the virtual receipts return to the
journal and the virtual book to ``ln_shadow_trades``. Revoked grants stay revoked and the
levels stay at "No trading": a downgrade never widens authority.
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
        connection.execute(
            sa.text(
                "INSERT INTO ln_events (owner_id, kind, agent_id, payload, created_at)"
                " VALUES (:owner, 'account_authority.updated', :agent,"
                " CAST(:payload AS JSON), :now)"
            ),
            {
                "owner": owner_id,
                "agent": agent_id,
                "now": now,
                "payload": dump(
                    {
                        "id": grant.id,
                        "agent_id": agent_id,
                        "status": "revoked",
                        "previous_status": grant.status,
                        "author": "system",
                        "reason": "shadow_trading_removed",
                    }
                ),
            },
        )
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
    op.create_table(
        "ln_shadow_agents_retired",
        sa.Column("agent_id", sa.String(36), primary_key=True),
        sa.Column("owner_id", sa.String(36), nullable=False),
        sa.Column("retired_at", sa.DateTime(timezone=True), nullable=False),
    )
    for agent in connection.execute(
        sa.text("SELECT id, owner_id FROM ln_agents WHERE execution_mode = 'shadow' ORDER BY id")
    ).all():
        connection.execute(
            sa.text(
                "INSERT INTO ln_shadow_agents_retired (agent_id, owner_id, retired_at)"
                " VALUES (:agent, :owner, :now)"
            ),
            {"agent": str(agent.id), "owner": str(agent.owner_id), "now": now},
        )
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
    # Moved, not erased: the virtual receipts keep every column, execution_mode included.
    connection.execute(
        sa.text(
            "CREATE TABLE ln_trading_journal_shadow_retired AS"
            " SELECT * FROM ln_trading_journal WHERE execution_mode = 'shadow'"
        )
    )
    connection.execute(sa.text("DELETE FROM ln_trading_journal WHERE execution_mode = 'shadow'"))
    op.rename_table("ln_shadow_trades", "ln_shadow_trades_retired")
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
    op.rename_table("ln_shadow_trades_retired", "ln_shadow_trades")
    connection = op.get_bind()
    connection.execute(
        sa.text(
            "UPDATE ln_agents SET execution_mode = 'shadow'"
            " WHERE id IN (SELECT agent_id FROM ln_shadow_agents_retired)"
        )
    )
    names = [
        column["name"]
        for column in sa.inspect(connection).get_columns("ln_trading_journal_shadow_retired")
    ]
    listed = ", ".join(names)
    connection.execute(
        sa.text(
            f"INSERT INTO ln_trading_journal ({listed})"
            f" SELECT {listed} FROM ln_trading_journal_shadow_retired"
        )
    )
    op.drop_table("ln_trading_journal_shadow_retired")
    op.drop_table("ln_shadow_agents_retired")
