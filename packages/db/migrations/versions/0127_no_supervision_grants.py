"""Supervision grants are deleted (mandate 3.3.3, 14.2.6): only Lonora leads, by its role.

The upgrade deletes the owner-action cards of the three grant kinds (``supervise``,
``supervision_created``, ``supervision_stopped``; 14.3.9: a stored row of a removed kind
is migrated, never left for a client that no longer renders it), ends the pauses team
supervisors held (14.3.18.6) and drops ``ln_supervision_grants``.

A team supervisor's pause is a live hold with ``source='agent'`` whose holder is not
Lonora. It ends with its role: the hold is released (``released_by='owner'``: the
owner's mandate ended it, as W-AUTH's data migration records it) and the work resumes as
its own control resumes it. A paused agent runs again (the gateway restarts a Full
agent's continuous task and answers what the owner sent it while paused); a routine is
switched back on; a watch resumes unless it is past its expiry, the agent cancelled it
itself, or its Task has ended. A Task resumes as its own resume (``task_control``) takes
it: a pause asked of it that it has not reached is withdrawn, so it never takes effect,
and a paused Task whose Run waits for takeover is queued again with its Run (a question
to the owner its Run held is cancelled, as the resume cancels it). A paused Task the
resume does not take that way (paused while waiting to retry, or with no Run waiting for
takeover) stays paused with no hold, for its agent or the owner to resume. An ended Task
keeps its state. Pauses the owner holds and pauses Lonora made stay (4.7.2), and so do
their ``supervision_paused`` cards; the card of an ended pause stops offering Resume.

The downgrade recreates the grant table empty and restores nothing else: no grant, no
deleted card and no ended pause comes back. The code below this revision leads by role
(``lonora_db.lead``) and needs no grant; code older than the lead role read Lonora's
access from 0041's ``default`` grants, which this downgrade does not recreate.
"""

import json
from datetime import UTC, datetime
from typing import Any

import sqlalchemy as sa
from alembic import op

revision = "0127_no_supervision_grants"
down_revision = "0125_flat_team_creation"
branch_labels = None
depends_on = None

# Frozen copies of a live Run's statuses and of lonora_db.tasks.ATTENTION_RESUMED.
LIVE_RUNS = ("queued", "leased", "running", "waiting_input", "waiting_takeover")
ATTENTION_RESUMED = "owner_attention_resumed"


def upgrade() -> None:
    op.execute(
        sa.text(
            "DELETE FROM ln_owner_actions"
            " WHERE kind IN ('supervise', 'supervision_created', 'supervision_stopped')"
        )
    )
    end_team_supervisor_pauses(op.get_bind(), datetime.now(UTC))
    op.drop_table("ln_supervision_grants")


def _json(value: Any) -> dict[str, Any]:
    if isinstance(value, str):
        value = json.loads(value)
    return dict(value or {})


def end_team_supervisor_pauses(bind: sa.Connection, now: datetime) -> None:
    """Frozen: each live hold a team supervisor set on its own ends, and its work resumes
    as the item's own control resumes it (``supervision._apply``, ``control_watch``)."""
    holds = bind.execute(
        sa.text(
            "SELECT h.id, h.target_kind, h.target_id"
            " FROM ln_supervision_holds h LEFT JOIN ln_agents p ON p.id = h.holder_agent_id"
            " WHERE h.released_at IS NULL AND h.source = 'agent'"
            " AND (p.role IS NULL OR p.role <> 'personal') ORDER BY h.id FOR UPDATE OF h"
        )
    ).all()
    for hold in holds:
        if hold.target_kind == "agent":
            bind.execute(
                sa.text("UPDATE ln_agents SET paused = false WHERE id = :id AND paused"),
                {"id": hold.target_id},
            )
        elif hold.target_kind == "routine":
            bind.execute(
                sa.text("UPDATE ln_routines SET enabled = true WHERE id = :id AND NOT enabled"),
                {"id": hold.target_id},
            )
        elif hold.target_kind == "watch":
            resume_watch(bind, hold.target_id, now)
        elif hold.target_kind == "task":
            resume_task(bind, hold.target_id, now)
        bind.execute(
            sa.text(
                "UPDATE ln_supervision_holds SET released_at = :now, released_by = 'owner'"
                " WHERE id = :id"
            ),
            {"id": hold.id, "now": now},
        )


def resume_task(bind: sa.Connection, task_id: str, now: datetime) -> None:
    """Frozen ``control_task(..., 'resume')``, locking the Task's Run before the Task as
    it does. "Its Run" is the newest live Run among the 20 newest Runs of the Task's
    agent in the Task's thread (``task_runs``)."""
    ticket = bind.execute(
        sa.text("SELECT thread_id, agent_id FROM ln_tickets WHERE id = :id"), {"id": task_id}
    ).first()
    if ticket is None:
        return
    runs = bind.execute(
        sa.text(
            "SELECT id, status FROM ln_runs WHERE thread_id = :thread AND agent_id = :agent"
            " ORDER BY created_at DESC LIMIT 20"
        ),
        {"thread": ticket.thread_id, "agent": ticket.agent_id},
    ).all()
    live = next((run for run in runs if run.status in LIVE_RUNS), None)
    run = (
        bind.execute(
            sa.text("SELECT id, status, execution_state FROM ln_runs WHERE id = :id FOR UPDATE"),
            {"id": live.id},
        ).first()
        if live is not None
        else None
    )
    row = bind.execute(
        sa.text("SELECT payload, state FROM ln_tickets WHERE id = :id FOR UPDATE"),
        {"id": task_id},
    ).first()
    assert row is not None
    state = _json(row.state)
    task = _json(state.get("task"))
    if not task or task.get("status") in {"completed", "cancelled", "failed"}:
        return
    changed = task.get("control_requested") == "pause"
    if changed:
        # Not reached yet: withdrawn, so the ended pause never takes effect.
        task["control_requested"] = None
    if (
        task.get("status") == "paused"
        and task.get("phase") != "retry_paused"
        and run is not None
        and run.status == "waiting_takeover"
    ):
        execution = _json(run.execution_state)
        question = execution.get("pending_input_request")
        if isinstance(question, dict) and question.get("kind") == "owner_attention":
            # Frozen release_attention: the work resumes, not the question.
            execution["input_requests"] = [
                {**item, "status": "cancelled"}
                if item.get("id") == question.get("id") and item.get("status") == "pending"
                else item
                for item in execution.get("input_requests", [])
            ]
            execution[ATTENTION_RESUMED] = {"action": "resume", "question_id": question.get("id")}
            execution.pop("pending_input_request", None)
        bind.execute(
            sa.text(
                "UPDATE ln_runs SET status = 'queued', execution_state = CAST(:state AS JSON),"
                " lease_expires_at = NULL WHERE id = :id"
            ),
            {"id": run.id, "state": json.dumps(execution)},
        )
        task.update(status="queued", phase="queued", control_requested=None)
        if task.get("waiting_reason") == "owner_attention":
            task["waiting_reason"] = None
        changed = True
    if not changed:
        return
    # Frozen save_task: the ticket's status label follows the Task's.
    status = task["status"]
    label = {"queued": "todo", "running": "working", "paused": "waiting"}.get(status, status)
    bind.execute(
        sa.text(
            "UPDATE ln_tickets SET state = CAST(:state AS JSON), payload = CAST(:payload AS JSON),"
            " version = version + 1, updated_at = :now WHERE id = :id"
        ),
        {
            "id": task_id,
            "state": json.dumps({**state, "task": task}),
            "payload": json.dumps({**_json(row.payload), "status": label}),
            "now": now,
        },
    )


def resume_watch(bind: sa.Connection, watch_id: str, now: datetime) -> None:
    """Frozen ``control_watch(..., 'resume')`` by the agent's own control: a watch the
    agent cancelled itself while held, one past its expiry and one whose Task has ended
    stay off."""
    watch = bind.execute(
        sa.text("SELECT payload, state FROM ln_market_watches WHERE id = :id FOR UPDATE"),
        {"id": watch_id},
    ).first()
    if watch is None:
        return
    payload, state = _json(watch.payload), _json(watch.state)
    if payload.get("enabled", True) and state.get("lifecycle") != "expired":
        return
    if state.get("code") == "watch_cancelled":
        return
    expires = payload.get("expires_at")
    if expires and datetime.fromisoformat(str(expires)) <= now:
        return
    task = bind.execute(
        sa.text("SELECT state FROM ln_tickets WHERE id = :id"),
        {"id": str(state.get("task_id") or "")},
    ).first()
    if task is not None:
        current = _json(_json(task.state).get("task"))
        if current.get("status") in {"cancelled", "completed"} or current.get(
            "control_requested"
        ) in {"cancel", "complete"}:
            return
    state = {key: value for key, value in state.items() if key != "code"}
    if state.get("lifecycle") == "expired":
        state["lifecycle"] = "pending"
        state.pop("lifecycle_reason", None)
    state = {**state, "steered_by": "agent", "steered_at": now.isoformat()}
    bind.execute(
        sa.text(
            "UPDATE ln_market_watches SET payload = CAST(:payload AS JSON),"
            " state = CAST(:state AS JSON), version = version + 1, updated_at = :now"
            " WHERE id = :id"
        ),
        {
            "id": watch_id,
            "payload": json.dumps({**payload, "enabled": True}),
            "state": json.dumps(state),
            "now": now,
        },
    )


def downgrade() -> None:
    op.create_table(
        "ln_supervision_grants",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "owner_id",
            sa.String(36),
            sa.ForeignKey("ln_owners.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "supervisor_agent_id",
            sa.String(36),
            sa.ForeignKey("ln_agents.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "supervised_agent_id",
            sa.String(36),
            sa.ForeignKey("ln_agents.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("created_via", sa.String(16), nullable=False),
        sa.Column(
            "source_message_id",
            sa.String(36),
            sa.ForeignKey("ln_messages.id", ondelete="SET NULL"),
        ),
        sa.Column("created_by_agent_id", sa.String(36)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=True)),
        sa.Column("revoked_via", sa.String(16)),
        sa.CheckConstraint(
            "created_via IN ('default','owner_ui','owner_message','owner_card')",
            name="ln_supervision_grant_created_via",
        ),
        sa.CheckConstraint(
            "revoked_via IS NULL OR revoked_via IN ('owner_ui','owner_card','owner_message')",
            name="ln_supervision_grant_revoked_via",
        ),
        sa.CheckConstraint(
            "supervisor_agent_id <> supervised_agent_id", name="ln_supervision_grant_distinct"
        ),
    )
    op.create_index(
        "ln_supervision_grant_supervisor",
        "ln_supervision_grants",
        ["owner_id", "supervisor_agent_id", "revoked_at"],
    )
    op.create_index(
        "ln_supervision_grant_supervised",
        "ln_supervision_grants",
        ["owner_id", "supervised_agent_id", "revoked_at"],
    )
    op.create_index(
        "ln_supervision_grant_active_pair",
        "ln_supervision_grants",
        ["supervisor_agent_id", "supervised_agent_id"],
        unique=True,
        postgresql_where=sa.text("revoked_at IS NULL"),
    )
