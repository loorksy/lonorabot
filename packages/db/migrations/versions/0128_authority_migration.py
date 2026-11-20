"""Existing data moves to the trading mode before the old permission code is deleted
(mandate 14.3.18, 14.3.9).

1. No agent's mode is written where the owner's tap set it (owner decision Q1): 0060
   made every agent Ask, and since then only the owner's tap on the Mandate card sets
   Full; writing Ask over such a tap would undo it. The ladder still runs at the door
   until it is deleted, so every agent whose stored level, or whose default when none is
   stored, is "No trading" (``analysis``) gets an explicit "Ask me" record
   (``supervised``): "No trading" never refuses what Ask allows. The record keeps exactly
   its own fields, its customization draft included. An agent in Full whose level was "No
   trading" is the exception: the door refused its every send, so its Full never took
   effect, and "Ask me" would make it trade on its own without the owner's tap
   (14.3.18.1). It is switched to Ask as the live switch does it, by the system: its
   Full-mode task ends as ``close_task`` ends it (as in item 3), its Mandate cards read
   the mode again, ``agent.trading_mode.updated`` records it, and its Mandate card is
   shown once as in item 2, so the owner can tap Full knowingly.
2. For each agent that holds an active, unexpired grant (``status = 'active'`` and no
   ``valid_until`` in the past), Lonora shows that agent's Mandate card once, in Lonora's
   conversation, as a system card. Its payload names the old grants (``previous_grants``:
   account, Full delegation or the markets), which the clients show as one line in the
   owner's language. The card id is fixed per agent, so it is never shown twice; it
   replaces an older pending Mandate card of the same agent.
3. Every active or pending grant is revoked (a passkey would turn a pending grant into
   authority after this step), as the live revoke does: ``account_authority.updated`` and
   the agent's permission revision bumped. The grant's account-management Task is stopped
   (a failed Task becomes cancelled, a Task the owner asked to complete becomes
   completed). What its agent set up outlives it, as it outlives the Full-mode task
   (``close_task``, 4.5.3): a Run suspended on its own wait is cancelled, since only the
   Task could resume it, and a timer it waited on becomes a one-shot routine of the agent
   in its conversation; the kickoff Run that never started is cancelled; a Run queued
   after a wake, or waiting for the owner, leaves the Task and goes on as an ordinary Run
   of the agent, under its mode, with its Trade Approval cards still decidable; a Run a
   worker holds reads the stopped Task at its next checkpoint. The Task's watches stay the
   agent's own, moved to its conversation without the Task. A paused Task's live watches
   and its timer stay paused, under the Task's hold when it has one (4.7.2); with none
   (its agent paused it, or 0127 left it so), with no hold, for its agent or the owner to
   resume. A Task the owner had already ended keeps its watches as they were, and its
   waiting Runs end as the owner's cancel ends them. Every waiting activation review
   (``trigger = 'activation'``, an observe-only review of a grant, all revoked now) is
   cancelled. Cancelled Runs take their pending and approved Trade Approval cards with
   them. An agent in Full then gets its own continuous task from the gateway
   (``reconcile_management_tasks``), as after a live revoke.
   Every owner-action card of the ``grant_authority`` kind is deleted, the confirmed ones
   included (14.3.9: the kind leaves with the grants), each with ``owner_action.updated``
   so an open client reads its conversation's cards again and drops it.
4. Delegated, child and supervisor-template agents become ordinary team agents: no
   parent, role ``specialist``, flexible, no binding, and no template where it was
   ``supervisor``, each with ``agent.updated``. A bound account and symbol become one line
   at the end of the agent's method (its OPERATING.md) in the owner's language, with a
   memory revision by the system: the symbol, and the account as the owner knows it
   (broker · login · server once the broker verified the connection as it now is, else
   its provider and account number), never an internal id. The server-written supervisor
   line leaves the method. Nothing is written to ``ln_supervision_grants``: 0127 dropped
   it.
5. Pending Trade Approval rows keep their stored expiry: nothing is written.
6. A pause a team agent set on its own that is still open (0127 ended every one it
   found; this ends one left since, such as the hold item 3 copies from a team agent's
   pause of a Task onto its watches) is released as stale (owner decision Q6), and its
   work resumes as 0127 resumes it: an agent runs again, a routine is switched back on, a
   watch resumes unless it is past its expiry, the agent cancelled it itself or its Task
   has ended. The agent and the watch are told as their own resume tells them
   (``agent.updated``, ``market_watches.updated``). A Task is only released: the owner or
   its agent resumes it. Nothing is woken. Pauses the owner holds and pauses Lonora made
   stay (4.7.2).
7. Positions are attributed from the journal when they are read (``ticket_agent``,
   3.3.4): nothing is written.

Item 8 is void under Amendment 1 (Stop is removed, 0150). Restrictions and goals ended
with their features (0086, 0068).

The downgrade restores nothing and never widens authority: grants stay revoked, Tasks
and Runs stay ended or detached, kept timers stay routines, agents switched to Ask stay in
Ask, levels stay "Ask me", deleted cards stay deleted, Mandate cards stay
(the owner may have tapped them), flattened agents and their method lines stay, released
pauses stay released. A second upgrade applies the items again to the data it then
finds; it shows no Mandate card twice.
"""

import json
import re
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from hashlib import sha256
from typing import Any, cast
from uuid import NAMESPACE_URL, uuid4, uuid5

import sqlalchemy as sa
from alembic import op

revision = "0128_authority_migration"
down_revision = "0127_no_supervision_grants"
branch_labels = None
depends_on = None

# Frozen copy of lonora_db.owner_actions.LIFETIME["trading_mode"].
MANDATE_LIFETIME = timedelta(days=3650)
# Frozen copies of lonora_contracts.account_authority.
ALL_AUTHORITY_ACTIONS = {
    "buy",
    "sell",
    "buy_limit",
    "sell_limit",
    "buy_stop",
    "sell_stop",
    "close_position",
    "modify_position",
    "cancel_order",
    "modify_order",
}
AUTHORITY_CAPS = (
    "maximum_order_volume",
    "maximum_symbol_volume",
    "maximum_positions",
    "maximum_pending_orders",
    "maximum_actions",
    "minimum_equity",
)
# Frozen copy of the supervisor template's line (agent_create TEMPLATE_NOTES before the
# team stack removed templates).
SUPERVISOR_LINE = (
    "Supervisor: you review the work of the agents the owner named and message them;"
    " you never trade for them."
)
# The line a bound agent's method gets, in the owner's language.
ASSIGNED = {
    "en": "Your assigned market, kept from your former fixed assignment: {symbol} on"
    " {account}. Work on this symbol on this account unless the owner or Lonora assigns"
    " another.",
    "ar": "السوق المُسنَد إليك، باقٍ من تكليفك الثابت السابق: {symbol} على {account}."
    " اعمل على هذا الرمز في هذا الحساب ما لم يُسنِد إليك المالك أو لونورا غيره.",
}
GONE = {"en": "an account that is no longer connected", "ar": "حساب لم يعد متصلًا"}
PROVIDERS = {
    "en": {"metaapi": "MetaApi", "simulation": "simulation"},
    "ar": {"metaapi": "MetaApi", "simulation": "المحاكاة"},
}
# Frozen copy of lonora_db.memory.VIEW_HEADING.
VIEW_HEADING = re.compile(r"(?m)^# (USER\.md|OPERATING\.md|(?:memory/)?MEMORY\.md)[ \t]*\n")
OPERATING = "OPERATING.md"
TERMINAL = ("completed", "failed", "cancelled")
WAITING_RUNS = ("queued", "waiting_input", "waiting_takeover")
# Frozen copies of lonora_db.management_task: the Full-mode task's marker, the mark
# close_task sets on it, and the prompt of a timer kept as a routine, whose title is
# lonora_bus attention_messages "full_mode_follow_up".
MODE_TASK = "account_management_agent"
CLOSED = "account_management_closed"
TIMER_PROMPT = (
    "A timer you set while running your continuous account-management task is due "
    "(set for {due_at}). That task has ended; you work under your current trading mode. "
    "Re-check your open positions, pending orders and the market, then decide."
)
FOLLOW_UP = {"en": "Review positions and pending orders", "ar": "مراجعة الصفقات والأوامر المعلقة"}
# A paused Task's hold: its holder, its source and the owner's message it came from.
Hold = tuple[str | None, str, str | None]
# The columns agent_data reads.
AGENT_COLUMNS = (
    "id, name, title, description, avatar, color, instructions, paused, role, template,"
    " scope_mode, scope_revision, trading_account_id, trading_symbol, trading_mode,"
    " parent_id, created_at"
)


def dump(value: Any) -> str:
    return json.dumps(value, separators=(",", ":"), ensure_ascii=False)


def payload_of(value: Any) -> dict[str, Any]:
    if isinstance(value, str):
        value = json.loads(value)
    return cast(dict[str, Any], value) if isinstance(value, dict) else {}


def stable_id(scope: str, nonce: str) -> str:
    """Frozen copy of lonora_session.idempotency.stable_id."""
    return str(uuid5(NAMESPACE_URL, scope + ":" + nonce))


def request_hash(value: Any) -> str:
    """Frozen copy of lonora_session.idempotency.request_hash."""
    encoded = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return sha256(encoded.encode()).hexdigest()


def permission_key(owner_id: str, agent_id: str) -> str:
    """Frozen copy of lonora_db.agent_permissions.permission_key."""
    return "agent-permission:" + sha256((owner_id + ":" + agent_id).encode()).hexdigest()


def full_delegation(envelope: dict[str, Any]) -> bool:
    """Frozen copy of lonora_contracts.account_authority.full_delegation."""
    return (
        envelope.get("management_mode") == "full"
        and envelope.get("symbol_scope") == "account"
        and set(envelope.get("actions") or ()) == ALL_AUTHORITY_ACTIONS
        and envelope.get("valid_until") is None
        and envelope.get("allow_manual_positions") is True
        and all(envelope.get(name) is None for name in AUTHORITY_CAPS)
    )


def stamp(value: datetime | None) -> str | None:
    return value.isoformat() if value is not None else None


class Migration:
    def __init__(self, connection: sa.Connection) -> None:
        self.c = connection
        self.now = datetime.now(UTC)

    def rows(self, query: str, **parameters: Any) -> list[Any]:
        return list(self.c.execute(sa.text(query), parameters).all())

    def run(self, query: str, **parameters: Any) -> None:
        self.c.execute(sa.text(query), parameters)

    def emit(
        self,
        owner_id: str,
        kind: str,
        payload: dict[str, Any] | None,
        *,
        agent_id: str | None = None,
        thread_id: str | None = None,
        run_id: str | None = None,
    ) -> None:
        """Frozen copy of lonora_db.events.emit (cursors are published later)."""
        self.run(
            "INSERT INTO ln_events (owner_id, thread_id, agent_id, run_id, kind, payload,"
            " created_at) VALUES (:owner, :thread, :agent, :run, :kind,"
            " CAST(:payload AS JSON), :now)",
            owner=owner_id,
            thread=thread_id,
            agent=agent_id,
            run=run_id,
            kind=kind,
            payload=dump(payload or {}),
            now=self.now,
        )

    def card_event(self, card: Any, transition: str | None = None) -> None:
        """Frozen copy of lonora_db.owner_actions.owner_action_event."""
        self.emit(
            card.owner_id,
            "owner_action.updated",
            {
                "id": card.id,
                "kind": card.kind,
                "status": card.status,
                "status_reason": card.status_reason,
                "thread_id": card.thread_id,
                "transition_id": card.id + ":" + (transition or card.status),
            },
            agent_id=card.agent_id,
            thread_id=card.thread_id,
            run_id=card.run_id,
        )

    def lock(self) -> None:
        """The locks a live process takes, in the order a card decision takes them
        (lock_owner_actions, then authority_lock), so a database migrated while the
        previous release still runs never interleaves with a tap or a send."""
        for (owner_id,) in self.rows("SELECT id FROM ln_owners ORDER BY id"):
            self.run(
                "SELECT pg_advisory_xact_lock(hashtextextended(:key, 0))",
                key="owner-actions:" + owner_id,
            )
        for (agent_id,) in self.rows("SELECT id FROM ln_agents ORDER BY id"):
            self.run(
                "SELECT pg_advisory_xact_lock(hashtextextended(:key, 0))",
                key="super-bot:" + agent_id,
            )

    def conversation(self, owner_id: str, agent_id: str) -> Any:
        """Frozen conversation_thread: the agent's earliest direct conversation, created
        when it has none."""
        found = self.rows(
            "SELECT id, next_seq FROM ln_threads WHERE owner_id = :owner AND agent_id = :agent"
            " AND group_id IS NULL AND purpose = 'conversation' ORDER BY created_at, id"
            " LIMIT 1",
            owner=owner_id,
            agent=agent_id,
        )
        if found:
            return found[0]
        thread_id = str(uuid4())
        self.run(
            "INSERT INTO ln_threads (id, owner_id, agent_id, group_id, title, purpose, next_seq,"
            " options, context_summary, summary_seq, created_at) VALUES (:id, :owner, :agent,"
            " NULL, '', 'conversation', 1, CAST('{}' AS JSON), '', 0, :now)",
            id=thread_id,
            owner=owner_id,
            agent=agent_id,
            now=self.now,
        )
        return self.rows("SELECT id, next_seq FROM ln_threads WHERE id = :id", id=thread_id)[0]

    # -- item 2 --------------------------------------------------------------------------

    def shown_grants(self) -> list[Any]:
        """Grants active and unexpired now, of agents that still exist; read before item 3."""
        return self.rows(
            "SELECT g.id, g.owner_id, g.agent_id, g.account_id, g.envelope"
            " FROM ln_account_authorities g"
            " JOIN ln_agents a ON a.id = g.agent_id AND a.owner_id = g.owner_id"
            " WHERE g.status = 'active' AND (g.valid_until IS NULL OR g.valid_until > :now)"
            " ORDER BY g.owner_id, a.role = 'personal' DESC, a.created_at, a.id,"
            " g.account_id, g.id",
            now=self.now,
        )

    def mandate_cards(self, grants: list[Any], switched: list[Any]) -> None:
        """One Mandate card for each agent that held an active grant (naming the grants)
        and for each agent item 1 switched to Ask (naming none)."""
        shown: dict[tuple[str, str], list[Any]] = {}
        for grant in grants:
            shown.setdefault((grant.owner_id, grant.agent_id), []).append(grant)
        for agent in switched:
            shown.setdefault((agent.owner_id, agent.id), [])
        order = 0
        for (owner_id, agent_id), held in shown.items():
            card_id = stable_id(owner_id, "owner-action:trading_mode:mandate-migration:" + agent_id)
            if self.rows("SELECT 1 FROM ln_owner_actions WHERE id = :id", id=card_id):
                continue  # Shown once.
            lonora = self.rows(
                "SELECT id FROM ln_agents WHERE owner_id = :owner AND role = 'personal'",
                owner=owner_id,
            )
            shower = lonora[0].id if lonora else agent_id
            thread = self.conversation(owner_id, shower)
            previous: list[dict[str, Any]] = []
            for grant in sorted(held, key=lambda grant: (grant.account_id, grant.id)):
                envelope = payload_of(grant.envelope)
                selected = envelope.get("symbol_scope") != "account"
                previous.append(
                    {
                        "account_id": grant.account_id,
                        "full_delegation": full_delegation(envelope),
                        "symbol_scope": "selected" if selected else "account",
                        "symbols": list(envelope.get("symbols") or []) if selected else [],
                    }
                )
            subject = "trading_mode:" + agent_id
            # It replaces an older pending Mandate card of this agent (supersede_subject).
            for card in self.rows(
                "UPDATE ln_owner_actions SET status = CASE WHEN expires_at <= :now"
                " THEN 'expired' ELSE 'superseded' END, status_reason = CASE"
                " WHEN expires_at <= :now THEN 'expired' ELSE 'mandate_migration' END,"
                " superseded_by = :by, updated_at = :now WHERE status = 'pending'"
                " AND owner_id = :owner AND kind = 'trading_mode' AND subject = :subject"
                " RETURNING id, owner_id, agent_id, thread_id, run_id, kind, status,"
                " status_reason",
                by=card_id,
                owner=owner_id,
                subject=subject,
                now=self.now,
            ):
                self.card_event(card)
            created = self.now + timedelta(microseconds=order)
            order += 1
            self.run(
                "INSERT INTO ln_owner_actions (id, owner_id, agent_id, thread_id, run_id, source,"
                " kind, subject, payload, payload_hash, status, status_reason, superseded_by,"
                " result, timeline_seq, expires_at, decided_at, decided_via, created_at,"
                " updated_at) VALUES (:id, :owner, :shower, :thread, NULL, 'system',"
                " 'trading_mode', :subject, CAST(:payload AS JSON), :hash, 'pending', NULL, NULL,"
                " CAST('{}' AS JSON), :seq, :expires, NULL, NULL, :created, :created)",
                id=card_id,
                owner=owner_id,
                shower=shower,
                thread=thread.id,
                subject=subject,
                payload=dump(
                    {"agent_id": agent_id, **({"previous_grants": previous} if previous else {})}
                ),
                # Frozen lonora_db.owner_actions.payload_hash: a Mandate card's effect is
                # its agent's switch; the line naming an old grant is not part of it.
                hash=request_hash({"kind": "trading_mode", "payload": {"agent_id": agent_id}}),
                seq=thread.next_seq,
                expires=self.now + MANDATE_LIFETIME,
                created=created,
            )
            self.emit(
                owner_id,
                "owner_action.updated",
                {
                    "id": card_id,
                    "kind": "trading_mode",
                    "status": "pending",
                    "status_reason": None,
                    "thread_id": thread.id,
                    "transition_id": card_id + ":pending",
                },
                agent_id=shower,
                thread_id=thread.id,
            )

    # -- item 3 --------------------------------------------------------------------------

    def revoke_grants(self) -> set[str]:
        revoked_agents: set[str] = set()
        for grant in self.rows(
            "UPDATE ln_account_authorities SET status = 'revoked', updated_at = :now"
            " WHERE status IN ('pending','active') RETURNING id, owner_id, agent_id, thread_id,"
            " account_id, envelope, activation_expires_at, valid_until, created_at, updated_at",
            now=self.now,
        ):
            revoked_agents.add(grant.agent_id)
            # Frozen lonora_db.account_authority.authority_data of a revoked grant.
            self.emit(
                grant.owner_id,
                "account_authority.updated",
                {
                    "id": grant.id,
                    "agent_id": grant.agent_id,
                    "thread_id": grant.thread_id,
                    "account_id": grant.account_id,
                    "status": "revoked",
                    "envelope": payload_of(grant.envelope),
                    "activation_expires_at": stamp(grant.activation_expires_at),
                    "valid_until": stamp(grant.valid_until),
                    "created_at": stamp(grant.created_at),
                    "updated_at": stamp(grant.updated_at),
                },
                agent_id=grant.agent_id,
                thread_id=grant.thread_id,
            )
            self.stop_management_task(grant)
        # Every waiting activation review: an observe-only review of a grant, and every
        # grant is revoked now.
        self.cancel_runs(
            self.rows(
                "SELECT id FROM ln_runs WHERE trigger = 'activation' AND status = ANY(:waiting)"
                " ORDER BY created_at, id FOR UPDATE",
                waiting=list(WAITING_RUNS),
            )
        )
        return revoked_agents

    def cancel_runs(self, runs: list[Any]) -> None:
        """Frozen cancel_locked over these Runs: their unfinished children end with them,
        and so do their pending and approved cards, which no Run will act on now."""
        if not runs:
            return
        cancelled = self.rows(
            "UPDATE ln_runs r SET status = 'cancelled', lease_owner = NULL,"
            " lease_expires_at = NULL, lease_fence = r.lease_fence + 1, updated_at = :now"
            " FROM ln_threads t WHERE t.id = r.thread_id AND r.id = ANY(:ids)"
            " AND r.status <> ALL(:terminal) RETURNING r.id, r.thread_id, r.agent_id, t.owner_id",
            ids=[run.id for run in runs],
            terminal=list(TERMINAL),
            now=self.now,
        )
        if not cancelled:
            return
        cancelled += self.rows(
            "UPDATE ln_runs r SET status = 'cancelled', lease_owner = NULL,"
            " lease_expires_at = NULL, lease_fence = r.lease_fence + 1, updated_at = :now"
            " FROM ln_threads t WHERE t.id = r.thread_id AND r.parent_run_id = ANY(:runs)"
            " AND r.status <> ALL(:terminal) RETURNING r.id, r.thread_id, r.agent_id,"
            " t.owner_id",
            runs=[run.id for run in cancelled],
            terminal=list(TERMINAL),
            now=self.now,
        )
        for run in cancelled:
            self.emit(
                run.owner_id,
                "run.cancelled",
                None,
                agent_id=run.agent_id,
                thread_id=run.thread_id,
                run_id=run.id,
            )
        for approval in self.rows(
            "UPDATE ln_trade_approvals SET status = 'cancelled', updated_at = :now"
            " WHERE run_id = ANY(:runs) AND status IN ('pending','approved') RETURNING *",
            runs=[run.id for run in cancelled],
            now=self.now,
        ):
            self.emit(
                approval.owner_id,
                "trading.approval.updated",
                approval_data(approval),
                agent_id=approval.agent_id,
                thread_id=approval.thread_id,
                run_id=approval.run_id,
            )

    def task_runs(self, task_id: str, grant_id: str | None = None) -> list[Any]:
        """A Task's Runs that no worker holds, locked before the Task as the Task's own
        work locks them (a Run a worker holds reads the ended Task at its next
        checkpoint); with ``grant_id``, also a Run of that grant's management."""
        return self.rows(
            "SELECT id, status, execution_state, model_metadata FROM ln_runs"
            " WHERE status = ANY(:waiting) AND (CAST(model_metadata AS JSONB) ->> 'task_id' = :task"
            " OR CAST(model_metadata AS JSONB) ->> 'account_management_id' = :grant)"
            " ORDER BY created_at, id FOR UPDATE",
            waiting=list(WAITING_RUNS),
            task=task_id,
            grant=grant_id or task_id,
        )

    def save_task(
        self,
        task_id: str,
        owner_id: str,
        agent_id: str,
        state: dict[str, Any],
        task: dict[str, Any],
        marks: dict[str, Any] | None = None,
    ) -> None:
        """Frozen save_task: the Task's state, its board status (and ``marks``) and
        ``task.updated``."""
        payload = payload_of(
            self.rows("SELECT payload FROM ln_tickets WHERE id = :id", id=task_id)[0].payload
        )
        shown = {"queued": "todo", "running": "working", "paused": "waiting"}.get(
            task["status"], task["status"]
        )
        version = self.rows(
            "UPDATE ln_tickets SET state = CAST(:state AS JSON),"
            " payload = CAST(:payload AS JSON), version = version + 1, updated_at = :now"
            " WHERE id = :id RETURNING version",
            id=task_id,
            state=dump({**state, "task": task}),
            payload=dump({**payload, **(marks or {}), "status": shown}),
            now=self.now,
        )[0].version
        self.emit(
            owner_id,
            "task.updated",
            {
                "id": task_id,
                "version": version,
                "status": task["status"],
                "waiting_reason": task.get("waiting_reason"),
            },
            agent_id=agent_id,
            thread_id=task.get("origin_thread_id"),
        )

    def stop_management_task(self, grant: Any) -> None:
        """Frozen stop_management_task (finish_task(..., 'cancelled'), a failed Task
        cancelled). What its agent set up outlives it as it outlives the Full-mode task
        (close_task, 4.5.3): its waiting Runs end or go on as ordinary Runs of the agent
        (end_task_runs), and its watches stay the agent's own (keep_task_watches)."""
        task_id = stable_id(grant.id, "account-management-task")
        runs = self.task_runs(task_id, grant.id)
        found = self.rows(
            "SELECT owner_id, agent_id, payload, state FROM ln_tickets WHERE id = :id FOR UPDATE",
            id=task_id,
        )
        state = payload_of(found[0].state) if found else {}
        task = payload_of(state.get("task"))
        if not task or found[0].owner_id != grant.owner_id or found[0].agent_id != grant.agent_id:
            # No Task of this grant to keep anything for.
            self.cancel_runs(
                [
                    run
                    for run in runs
                    if payload_of(run.model_metadata).get("account_management_id") == grant.id
                ]
            )
            return
        payload = payload_of(found[0].payload)
        status = task.get("status")
        # Frozen task_ended: the owner's cancel or complete counts from the request.
        ended_before = status in {"cancelled", "completed"} or task.get("control_requested") in {
            "cancel",
            "complete",
        }
        paused = not ended_before and (
            status == "paused" or task.get("control_requested") == "pause"
        )
        if ended_before:
            # The owner ended it: its waiting Runs end as the owner's cancel ends them, and
            # its watches stay as they were.
            self.cancel_runs(runs)
        else:
            hold = self.task_hold(task_id) if paused else None
            self.end_task_runs(runs, grant.owner_id, grant.agent_id, task_id, paused, hold)
            self.keep_task_watches(grant.owner_id, grant.agent_id, task_id, paused, hold)
        if status == "failed":
            task.update(status="cancelled", phase="cancelled")
        elif status not in TERMINAL:
            ended = "completed" if task.get("control_requested") == "complete" else "cancelled"
            task.update(status=ended, phase=ended, control_requested=None, waiting_reason=None)
        shown = {"queued": "todo", "running": "working", "paused": "waiting"}.get(
            task["status"], task["status"]
        )
        if task.get("status") != status or payload.get("status") != shown:
            self.save_task(task_id, grant.owner_id, grant.agent_id, state, task)

    def end_task_runs(
        self,
        runs: list[Any],
        owner_id: str,
        agent_id: str,
        task_id: str,
        paused: bool,
        hold: Hold | None,
    ) -> None:
        """Frozen close_task over the Task's Runs no worker holds: one suspended on its own
        wait is cancelled, since only the Task could resume it, and a timer it waited on
        becomes a one-shot routine of the agent (keep_timer); the kickoff that never
        started is cancelled; one queued after a wake, or waiting for the owner, leaves
        the Task and goes on as an ordinary Run of the agent, its cards still decidable
        (10.3.1.3) and its request decided under the agent's mode (detach)."""
        cancel: list[Any] = []
        for run in runs:
            execution = payload_of(run.execution_state)
            environment = payload_of(execution.get("environment"))
            wait = payload_of(environment.get("wait"))
            if run.status == "waiting_takeover":
                if wait.get("kind") == "timer" and wait.get("due_at"):
                    self.keep_timer(owner_id, agent_id, str(wait["due_at"]), task_id, paused, hold)
                cancel.append(run)
            elif run.status == "queued" and not (
                execution.get("messages") or environment.get("last_wake")
            ):
                cancel.append(run)
            else:
                metadata = {
                    key: value
                    for key, value in payload_of(run.model_metadata).items()
                    if key not in {"task_id", "ticket_id", "account_management_id"}
                }
                self.run(
                    "UPDATE ln_runs SET model_metadata = CAST(:metadata AS JSON),"
                    " updated_at = :now WHERE id = :id",
                    id=run.id,
                    metadata=dump(metadata),
                    now=self.now,
                )
        self.cancel_runs(cancel)

    def keep_timer(
        self,
        owner_id: str,
        agent_id: str,
        due_at: str,
        task_id: str,
        paused: bool,
        hold: Hold | None,
    ) -> None:
        """Frozen management_task.keep_timer: the agent's pending timer outlives the Task,
        the same wake at the same time in the agent's conversation, as a one-shot routine.
        A paused Task's timer stays paused as its watches do (keep_task_watches)."""
        thread = self.conversation(owner_id, agent_id)
        when = datetime.fromisoformat(due_at)
        routine_id = str(uuid4())
        self.run(
            "INSERT INTO ln_routines (id, owner_id, agent_id, thread_id, prompt, title, run_at,"
            " interval_seconds, cron, timezone, enabled, next_run_at, last_run_at) VALUES"
            " (:id, :owner, :agent, :thread, :prompt, :title, :at, NULL, NULL, 'UTC', :enabled,"
            " :at, NULL)",
            id=routine_id,
            owner=owner_id,
            agent=agent_id,
            thread=thread.id,
            # What it is, not the ended Task's name (0.4).
            title=FOLLOW_UP[self.locale(owner_id, agent_id)],
            prompt=TIMER_PROMPT.format(due_at=when.isoformat()),
            at=when,
            enabled=not paused,
        )
        if paused and hold is not None:
            self.copy_hold("routine", routine_id, owner_id, agent_id, task_id, hold)

    def task_hold(self, task_id: str) -> Hold | None:
        """Who holds a paused Task: its live hold's holder, source and the owner's message
        it came from. None when no hold names it: its own agent paused it, or 0127 left it
        paused with no hold, for its agent or the owner to resume."""
        holds = self.rows(
            "SELECT holder_agent_id, source, source_message_id FROM ln_supervision_holds"
            " WHERE target_kind = 'task' AND target_id = :id AND released_at IS NULL",
            id=task_id,
        )
        if not holds:
            return None
        return holds[0].holder_agent_id, holds[0].source, holds[0].source_message_id

    def copy_hold(
        self, kind: str, target_id: str, owner_id: str, agent_id: str, task_id: str, hold: Hold
    ) -> None:
        """The paused Task's hold on work that leaves it, so only who paused the Task lifts
        the pause (4.7.2)."""
        if self.rows(
            "SELECT id FROM ln_supervision_holds WHERE target_kind = :kind"
            " AND target_id = :id AND released_at IS NULL",
            kind=kind,
            id=target_id,
        ):
            return
        self.run(
            "INSERT INTO ln_supervision_holds (id, owner_id, holder_agent_id, agent_id,"
            " target_kind, target_id, source, source_message_id, created_at) VALUES (:id,"
            " :owner, :holder, :agent, :kind, :target, :source, :message, :now)",
            id=stable_id(task_id, "mandate-migration-hold:" + target_id),
            owner=owner_id,
            holder=hold[0],
            agent=agent_id,
            kind=kind,
            target=target_id,
            source=hold[1],
            message=hold[2],
            now=self.now,
        )

    def keep_task_watches(
        self, owner_id: str, agent_id: str, task_id: str, paused: bool, hold: Hold | None
    ) -> None:
        """Ending the Task never cancels its watches (4.5.3): each leaves the Task for the
        agent's conversation (frozen management_task.keep_watches). A paused Task's live
        watches stay paused (frozen stop_watch 'watch_paused'), under the Task's hold when
        it has one, so only who paused the Task lifts the pause."""
        watches = self.rows(
            "SELECT id, agent_id, payload, state FROM ln_market_watches"
            " WHERE owner_id = :owner AND CAST(state AS JSONB) ->> 'task_id' = :task"
            " ORDER BY id FOR UPDATE",
            owner=owner_id,
            task=task_id,
        )
        if not watches:
            return
        thread = self.conversation(owner_id, agent_id)
        for watch in watches:
            payload = payload_of(watch.payload)
            state = {
                key: value
                for key, value in payload_of(watch.state).items()
                if key not in {"task_id", "task_run_id"}
            }
            if paused and payload.get("enabled", True):
                payload = {**payload, "enabled": False}
                state = {
                    **{
                        key: value
                        for key, value in state.items()
                        if key not in {"evaluation_status", "next_check"}
                    },
                    "code": "watch_paused",
                }
                if hold is not None:
                    self.copy_hold(
                        "watch", watch.id, owner_id, watch.agent_id or agent_id, task_id, hold
                    )
            version = self.rows(
                "UPDATE ln_market_watches SET payload = CAST(:payload AS JSON),"
                " state = CAST(:state AS JSON), thread_id = :thread, version = version + 1,"
                " updated_at = :now WHERE id = :id RETURNING version",
                id=watch.id,
                payload=dump(payload),
                state=dump(state),
                thread=thread.id,
                now=self.now,
            )[0].version
            self.emit(
                owner_id,
                "market_watches.updated",
                {"id": watch.id, "version": version},
                agent_id=watch.agent_id,
                thread_id=thread.id,
            )

    def delete_grant_cards(self) -> None:
        """14.3.9: no row of the grant card kind outlives it; an open client re-reads its
        conversation's cards on the event and the card is gone."""
        for card in self.rows(
            "DELETE FROM ln_owner_actions WHERE kind = 'grant_authority' RETURNING id,"
            " owner_id, agent_id, thread_id, run_id, kind, status, status_reason"
        ):
            self.card_event(card, "deleted")

    # -- item 1 --------------------------------------------------------------------------

    def ladder_level(self, agent: Any) -> tuple[bool, dict[str, Any] | None, str]:
        """Whether a PermissionRecord is stored, the record, and its level: the stored one,
        else the frozen default_level before this revision (Lonora and a root specialist
        "Ask me", every other agent "No trading"). Read from the role the agent has before
        item 4."""
        stored = self.rows(
            "SELECT payload FROM ln_settings WHERE key = :key FOR UPDATE",
            key=permission_key(agent.owner_id, agent.id),
        )
        record = payload_of(stored[0].payload) if stored else None
        level = (
            str(record.get("fallback_level"))
            if record is not None
            else "supervised"
            if agent.role == "personal" or (agent.role == "specialist" and agent.parent_id is None)
            else "analysis"
        )
        return bool(stored), record, level

    def no_trading_in_full(self) -> list[Any]:
        """Agents in Full whose level, stored or by default, is "No trading": the door
        refused their every send (``agent_analysis_only``), so Full never took effect, and
        "Ask me" (below) must not make it take effect now without the owner's tap."""
        return [
            agent
            for agent in self.rows(
                "SELECT id, owner_id, role, parent_id FROM ln_agents"
                " WHERE trading_mode = 'full' ORDER BY owner_id, created_at, id FOR UPDATE"
            )
            if self.ladder_level(agent)[2] == "analysis"
        ]

    def switch_to_ask(self, agent: Any) -> None:
        """Frozen change_trading_mode(..., 'ask') by the system: the Full-mode task ends
        as close_task ends it, the mode is written, the agent's Mandate cards read it
        again (refresh_mandate_cards) and the change is recorded
        (``agent.trading_mode.updated``)."""
        for task in self.rows(
            "SELECT id FROM ln_tickets WHERE owner_id = :owner AND agent_id = :agent"
            " AND CAST(payload AS JSONB) ->> '" + MODE_TASK + "' = :agent"
            " ORDER BY created_at DESC, id",
            owner=agent.owner_id,
            agent=agent.id,
        ):
            self.close_mode_task(task.id, agent.owner_id, agent.id)
        self.run("UPDATE ln_agents SET trading_mode = 'ask' WHERE id = :id", id=agent.id)
        for card in self.rows(
            "SELECT id, owner_id, agent_id, thread_id, run_id, kind, status, status_reason"
            " FROM ln_owner_actions WHERE owner_id = :owner AND subject = :subject"
            " AND status IN ('pending','confirmed') ORDER BY created_at, id",
            owner=agent.owner_id,
            subject="trading_mode:" + agent.id,
        ):
            self.card_event(card)
        self.emit(
            agent.owner_id,
            "agent.trading_mode.updated",
            {"agent_id": agent.id, "trading_mode": "ask", "by": "system"},
            agent_id=agent.id,
        )

    def close_mode_task(self, task_id: str, owner_id: str, agent_id: str) -> None:
        """Frozen close_task of one Full-mode task: a task the owner already ended, or one
        that is over, is left as it is; otherwise its work outlives it (end_task_runs,
        keep_task_watches) and it is cancelled and marked closed."""
        runs = self.task_runs(task_id)
        found = self.rows("SELECT state FROM ln_tickets WHERE id = :id FOR UPDATE", id=task_id)
        state = payload_of(found[0].state)
        task = payload_of(state.get("task"))
        if task.get("status") in {"completed", "cancelled"} or task.get("control_requested") in {
            "cancel",
            "complete",
        }:
            return
        paused = task.get("status") == "paused" or task.get("control_requested") == "pause"
        hold = self.task_hold(task_id) if paused else None
        self.end_task_runs(runs, owner_id, agent_id, task_id, paused, hold)
        self.keep_task_watches(owner_id, agent_id, task_id, paused, hold)
        failure = payload_of(task.get("failure"))
        task.update(status="cancelled", phase="cancelled", control_requested=None)
        task["waiting_reason"] = None
        if failure:
            task["failure"] = {**failure, "next_retry_at": None}
        self.save_task(task_id, owner_id, agent_id, state, task, {CLOSED: True})

    def ask_me_levels(self, revoked_agents: set[str]) -> None:
        """Frozen initial_permission and bump_permission over a PermissionRecord: exactly
        its five fields. "No trading", stored or by default, becomes "Ask me"; an agent
        whose grant item 3 revoked gets its revision bumped, as the live revoke does."""
        for agent in self.rows(
            "SELECT id, owner_id, role, parent_id FROM ln_agents ORDER BY owner_id, id"
        ):
            stored, record, level = self.ladder_level(agent)
            if level != "analysis" and agent.id not in revoked_agents:
                continue
            key = permission_key(agent.owner_id, agent.id)
            revision_number = int(record.get("revision", 0)) + 1 if record else 1
            payload = {
                "owner_id": agent.owner_id,
                "agent_id": agent.id,
                "revision": revision_number,
                "fallback_level": "supervised",
                "customization": record.get("customization") if record else None,
            }
            if stored:
                self.run(
                    "UPDATE ln_settings SET payload = CAST(:payload AS JSON), updated_at = :now"
                    " WHERE key = :key",
                    key=key,
                    payload=dump(payload),
                    now=self.now,
                )
            else:
                self.run(
                    "INSERT INTO ln_settings (key, payload, updated_at)"
                    " VALUES (:key, CAST(:payload AS JSON), :now)",
                    key=key,
                    payload=dump(payload),
                    now=self.now,
                )
            self.emit(
                agent.owner_id,
                "agent.permission.updated",
                {"agent_id": agent.id, "revision": revision_number},
                agent_id=agent.id,
            )

    # -- item 4 --------------------------------------------------------------------------

    def team_agents(self) -> None:
        for agent in self.rows(
            "SELECT id, owner_id, template, trading_account_id, trading_symbol FROM ln_agents"
            " WHERE role <> 'personal' AND (role = 'delegated' OR parent_id IS NOT NULL"
            " OR template = 'supervisor') ORDER BY owner_id, created_at, id FOR UPDATE"
        ):
            line: str | None = None
            if agent.trading_account_id and agent.trading_symbol:
                language = self.locale(agent.owner_id, agent.id)
                line = ASSIGNED[language].format(
                    symbol=agent.trading_symbol,
                    account=self.account_name(agent.trading_account_id, language),
                )
            supervisor = agent.template == "supervisor"

            def method(view: str, line: str | None = line, supervisor: bool = supervisor) -> str:
                if supervisor:
                    view = without_supervisor_line(view)
                return with_operating_line(view, line) if line else view

            self.edit_method(agent, method)
            flattened = self.rows(
                "UPDATE ln_agents SET parent_id = NULL, role = 'specialist',"
                " scope_mode = 'flexible',"
                " template = CASE WHEN template = 'supervisor' THEN NULL ELSE template END,"
                " trading_account_id = NULL, trading_symbol = NULL,"
                " scope_revision = scope_revision + 1 WHERE id = :id RETURNING " + AGENT_COLUMNS,
                id=agent.id,
            )[0]
            self.emit(agent.owner_id, "agent.updated", agent_data(flattened), agent_id=agent.id)
        # The record of how a supervisor-template agent was created names its template.
        for origin in self.rows(
            "SELECT key, payload FROM ln_settings WHERE key LIKE 'agent-origin:%'"
            " AND CAST(payload AS JSONB) ->> 'template' = 'supervisor' FOR UPDATE"
        ):
            self.run(
                "UPDATE ln_settings SET payload = CAST(:payload AS JSON), updated_at = :now"
                " WHERE key = :key",
                key=origin.key,
                payload=dump({**payload_of(origin.payload), "template": None}),
                now=self.now,
            )

    def locale(self, owner_id: str, agent_id: str) -> str:
        """Frozen conversation_locale of the agent's conversation: the owner profile's
        reply language, else the owner's latest messages there, else the language of the
        owner's attention policy; Arabic when nothing says."""
        profile = self.rows(
            "SELECT reply_language FROM ln_owner_profile WHERE owner_id = :owner", owner=owner_id
        )
        if profile and profile[0].reply_language in ("ar", "en"):
            return str(profile[0].reply_language)
        for message in self.rows(
            "SELECT m.content FROM ln_messages m WHERE m.role = 'user' AND m.thread_id = ("
            " SELECT id FROM ln_threads WHERE owner_id = :owner AND agent_id = :agent"
            " AND group_id IS NULL AND purpose = 'conversation' ORDER BY created_at, id"
            " LIMIT 1) ORDER BY m.seq DESC LIMIT 16",
            owner=owner_id,
            agent=agent_id,
        ):
            text = str(message.content)[:1600]
            if re.search(r"[ؠ-ي]", text):
                return "ar"
            if " " in text and len(re.findall(r"[A-Za-z]", text)) >= 8:
                return "en"
        policy = self.rows(
            "SELECT payload FROM ln_settings WHERE key = :key", key="attention-policy:" + owner_id
        )
        return "en" if policy and payload_of(policy[0].payload).get("locale") == "en" else "ar"

    def account_name(self, account_id: str, language: str) -> str:
        """The account as the owner recognizes it (frozen owner_actions.account_facts:
        broker · login · server once the broker verified this connection), else its
        provider and the broker's account number; never an internal id."""
        found = self.rows(
            "SELECT payload, state, version FROM ln_broker_sessions WHERE id = :id", id=account_id
        )
        if not found:
            return GONE[language]
        payload = payload_of(found[0].payload)
        identity = payload_of(payload_of(found[0].state).get("broker_identity"))
        if identity.get("connection_version") == found[0].version:
            parts = [identity.get(key) for key in ("broker", "login", "server")]
            label = " · ".join(str(part) for part in parts if isinstance(part, str) and part)
            if label:
                return ("الحساب " if language == "ar" else "the account ") + label
        provider = PROVIDERS[language].get(str(payload.get("provider")), "")
        number = str(payload.get("account_id") or "")
        if language == "ar":
            return " ".join(part for part in ("حساب", provider, number) if part)
        return " ".join(part for part in ("the", provider, "account", number) if part)

    def edit_method(self, agent: Any, transform: Callable[[str], str]) -> None:
        """Frozen commit_memory(transform=...) by the system: one revision, retired
        sections kept as they are, no write when nothing changes."""
        found = self.rows(
            "SELECT content, version FROM ln_memory WHERE agent_id = :id FOR UPDATE", id=agent.id
        )
        view, legacy = split_legacy(found[0].content if found else "")
        new_view = transform(view)
        if new_view == view:
            return
        if found:
            version = self.rows(
                "UPDATE ln_memory SET content = :content, version = version + 1,"
                " updated_at = :now WHERE agent_id = :id RETURNING version",
                id=agent.id,
                content=with_legacy(new_view, legacy),
                now=self.now,
            )[0].version
        else:
            version = 1
            self.run(
                "INSERT INTO ln_memory (agent_id, content, version, updated_at)"
                " VALUES (:id, :content, 1, :now)",
                id=agent.id,
                content=new_view,
                now=self.now,
            )
        self.run(
            "INSERT INTO ln_memory_revisions (id, owner_id, document, agent_id, version,"
            " previous_content, content, author, author_agent_id, source_message_id,"
            " source_run_id, change, reverted_revision_id, created_at) VALUES (:rid, :owner,"
            " 'agent_memory', :id, :version, :previous, :content, 'system', NULL, NULL, NULL,"
            " 'operations', NULL, :now)",
            rid=str(uuid4()),
            owner=agent.owner_id,
            id=agent.id,
            version=version,
            previous=view,
            content=new_view,
            now=self.now,
        )
        self.emit(
            agent.owner_id,
            "memory.updated",
            {"version": version, "source": "system", "change": "operations"},
            agent_id=agent.id,
        )

    # -- item 6 --------------------------------------------------------------------------

    def end_supervisor_pauses(self) -> None:
        """Frozen 0127 end_team_supervisor_pauses, released as stale and without resuming
        a Task (owner decision Q6). An agent that runs again and a watch that resumes are
        told as their own resume tells them (``agent.updated``, ``market_watches.updated``),
        so an open client does not keep showing them paused."""
        for hold in self.rows(
            "SELECT h.id, h.owner_id, h.target_kind, h.target_id"
            " FROM ln_supervision_holds h LEFT JOIN ln_agents p ON p.id = h.holder_agent_id"
            " WHERE h.released_at IS NULL AND h.source = 'agent'"
            " AND (p.role IS NULL OR p.role <> 'personal') ORDER BY h.id FOR UPDATE OF h"
        ):
            if hold.target_kind == "agent":
                for agent in self.rows(
                    "UPDATE ln_agents SET paused = false WHERE id = :id AND paused"
                    " RETURNING " + AGENT_COLUMNS,
                    id=hold.target_id,
                ):
                    self.emit(hold.owner_id, "agent.updated", agent_data(agent), agent_id=agent.id)
            elif hold.target_kind == "routine":
                self.run(
                    "UPDATE ln_routines SET enabled = true WHERE id = :id AND NOT enabled",
                    id=hold.target_id,
                )
            elif hold.target_kind == "watch":
                resumed = self.resume_watch(hold.target_id)
                if resumed is not None:
                    self.emit(
                        hold.owner_id,
                        "market_watches.updated",
                        {"id": hold.target_id, "version": resumed.version},
                        agent_id=resumed.agent_id,
                        thread_id=resumed.thread_id,
                    )
            self.run(
                "UPDATE ln_supervision_holds SET released_at = :now, released_by = 'stale'"
                " WHERE id = :id",
                id=hold.id,
                now=self.now,
            )

    def resume_watch(self, watch_id: str) -> Any:
        """Frozen 0127 resume_watch (``control_watch(..., 'resume')`` by the agent's own
        control): a watch the agent cancelled itself, one past its expiry and one whose
        Task has ended stay off. Returns the resumed watch's version, agent and thread, or
        None."""
        found = self.rows(
            "SELECT payload, state FROM ln_market_watches WHERE id = :id FOR UPDATE", id=watch_id
        )
        if not found:
            return None
        payload, state = payload_of(found[0].payload), payload_of(found[0].state)
        if payload.get("enabled", True) and state.get("lifecycle") != "expired":
            return None
        if state.get("code") == "watch_cancelled":
            return None
        expires = payload.get("expires_at")
        if expires and datetime.fromisoformat(str(expires)) <= self.now:
            return None
        task = self.rows(
            "SELECT state FROM ln_tickets WHERE id = :id", id=str(state.get("task_id") or "")
        )
        if task:
            current = payload_of(payload_of(task[0].state).get("task"))
            if current.get("status") in {"cancelled", "completed"} or current.get(
                "control_requested"
            ) in {"cancel", "complete"}:
                return None
        state = {key: value for key, value in state.items() if key != "code"}
        if state.get("lifecycle") == "expired":
            state["lifecycle"] = "pending"
            state.pop("lifecycle_reason", None)
        state = {**state, "steered_by": "agent", "steered_at": self.now.isoformat()}
        return self.rows(
            "UPDATE ln_market_watches SET payload = CAST(:payload AS JSON),"
            " state = CAST(:state AS JSON), version = version + 1, updated_at = :now"
            " WHERE id = :id RETURNING version, agent_id, thread_id",
            id=watch_id,
            payload=dump({**payload, "enabled": True}),
            state=dump(state),
            now=self.now,
        )[0]


def loaded(value: Any) -> Any:
    return json.loads(value) if isinstance(value, str) else value


def approval_data(row: Any) -> dict[str, Any]:
    """Frozen copy of lonora_db.trade_approvals.approval_data for a cancelled card."""
    validity = payload_of(row.validity)
    reference = payload_of(validity.get("reference"))
    return {
        "id": row.id,
        "run_id": row.run_id,
        "thread_id": row.thread_id,
        "agent_id": row.agent_id,
        "timeline_seq": row.timeline_seq,
        "requests": loaded(row.requests),
        "contracts": payload_of(row.broker_snapshot).get("contracts", []),
        "status": row.status,
        "results": loaded(row.results),
        "reason": row.reason,
        "tolerance": validity.get("tolerance"),
        "reference_price": reference.get("price"),
        "expires_at": stamp(row.expires_at),
        "created_at": stamp(row.created_at),
    }


def agent_data(row: Any) -> dict[str, Any]:
    """Frozen copy of lonora_db.agents.agent_data with agent_binding.scope_data, for an
    agent item 4 made a flexible root specialist or item 6 resumed. Item 3 revoked every
    grant and item 1 switched to Ask every agent in Full that could not trade, so only
    Full marks it as trading on its own (agent_on_its_own)."""
    return {
        "scope_mode": row.scope_mode,
        "scope_revision": row.scope_revision,
        "id": row.id,
        "name": row.name,
        "title": row.title,
        "description": row.description,
        "avatar": row.avatar,
        "color": row.color,
        "instructions": row.instructions,
        "paused": row.paused,
        "trading_mode": "full" if row.trading_mode == "full" else "ask",
        "trades_on_its_own": row.trading_mode == "full" and not row.paused,
        "role": row.role,
        "template": row.template,
        "scope": {
            "mode": row.scope_mode,
            "role": row.role,
            "account_id": row.trading_account_id,
            "broker_symbol": row.trading_symbol,
            "visibility": "owner_accounts",
            "execution_authority": "existing_server_controls",
        },
        "trading_account_id": row.trading_account_id,
        "trading_symbol": row.trading_symbol,
        "parent_id": row.parent_id,
        "created_at": row.created_at.isoformat(),
    }


def split_legacy(content: str) -> tuple[str, str]:
    """Frozen copy of lonora_db.memory.split_legacy."""
    matches = list(VIEW_HEADING.finditer(content))
    if not any(match[1] == "USER.md" for match in matches):
        return content, ""
    kept = [content[: matches[0].start()]]
    legacy: list[str] = []
    for position, match in enumerate(matches):
        end = matches[position + 1].start() if position + 1 < len(matches) else len(content)
        part = content[match.start() : end]
        if match[1] == "USER.md":
            legacy.append(part.strip())
        else:
            kept.append(part)
    view = re.sub(r"\n{3,}", "\n\n", "".join(kept)).strip()
    return (view + "\n" if view else ""), "\n\n".join(legacy) + "\n"


def with_legacy(view: str, legacy: str) -> str:
    """Frozen copy of lonora_db.memory.with_legacy."""
    if not legacy:
        return view
    head = view.rstrip("\n")
    return (head + "\n\n" if head.strip() else "") + legacy


def normalize(content: str) -> str:
    """Frozen copy of lonora_memory.markdown_memory.normalize_memory."""
    return content.replace("\r\n", "\n").strip() + ("\n" if content.strip() else "")


def with_operating_line(view: str, line: str) -> str:
    """The line at the end of the OPERATING.md section, which is added when there is none."""
    if line in view.split("\n"):
        return view
    headings = list(VIEW_HEADING.finditer(view))
    for position, heading in enumerate(headings):
        if heading[1] == OPERATING:
            end = headings[position + 1].start() if position + 1 < len(headings) else len(view)
            rest = view[end:]
            return normalize(
                view[:end].rstrip("\n") + "\n" + line + ("\n\n" + rest if rest else "")
            )
    return normalize(view.rstrip("\n") + "\n\n# " + OPERATING + "\n" + line)


def without_supervisor_line(view: str) -> str:
    """Frozen agent_create._remove_note: only the exact line inside OPERATING.md."""
    lines = view.split("\n")
    section = None
    for index, line in enumerate(lines):
        heading = VIEW_HEADING.match(line + "\n")
        if heading:
            section = heading[1]
        elif section == OPERATING and line.strip() == SUPERVISOR_LINE:
            del lines[index]
            return normalize("\n".join(lines))
    return view


def upgrade() -> None:
    migration = Migration(op.get_bind())
    migration.lock()
    shown = migration.shown_grants()
    # Before item 1 rewrites the levels and item 4 the roles they are read from.
    switched = migration.no_trading_in_full()
    revoked_agents = migration.revoke_grants()
    for agent in switched:
        migration.switch_to_ask(agent)
    migration.delete_grant_cards()
    migration.mandate_cards(shown, switched)
    # Before item 4: an agent's default level is read from the role it had.
    migration.ask_me_levels(revoked_agents)
    migration.team_agents()
    migration.end_supervisor_pauses()


def downgrade() -> None:
    """Nothing is restored (see the module docstring); a downgrade never widens authority."""
