"""Existing data moves to the trading mode before the old permission code is deleted
(mandate 14.3.18, items 1-7; item 8 is void under Amendment 1).

1. Every agent's mode becomes Ask, whatever its stored level or grants. An agent that
   was in Full gets the mode event and its Mandate cards are refreshed. The ladder still
   runs at the door until it is deleted, so every agent's stored level becomes "Ask me"
   (``supervised``, the next revision): a stored "No trading" never refuses what Ask
   allows. The record keeps exactly its own fields; its customization draft stays.
2. For each agent that had an active, unexpired grant (``status = 'active'`` and no
   ``valid_until`` in the past), Lonora shows that agent's Mandate card once, in Lonora's
   conversation, as a system card. Its payload names the old grants
   (``previous_grants``: account, Full delegation or the markets), which the card shows
   as one line. The card id is fixed per agent, so it is never shown twice; it replaces
   an older pending Mandate card of the same agent.
3. Active grants are revoked, and so are pending ones (a passkey would turn a pending
   grant into authority after this step). Each revocation is the live one:
   ``account_authority.updated`` with reason ``mandate_migration``, the grant's
   account-management Task stopped (a failed Task becomes cancelled, a Task the owner
   asked to complete becomes completed), its waiting Run
   and any waiting activation review of the grant cancelled with their pending and
   approved Trade Approval cards (as the owner's cancel of a Task), and pending grant
   cards superseded. Ending a Task never cancels its watches (4.5.3): each stays the
   agent's own, without the Task, and a pause on it (the owner's too) can still lift. A
   paused Task's live watches stay paused under the Task's hold (4.7.2); a Task the owner
   had already ended keeps its watches as they were.
4. Delegated, child and supervisor agents become ordinary team agents: no parent, role
   ``general``, flexible, no binding, template ``supervisor`` becomes ``general``, each
   with the live ``agent.updated``. A bound account and symbol become one plain line at
   the end of the agent's method (its OPERATING.md), with a memory revision: the symbol,
   and the account as the owner knows it (broker · login · server once the broker verified
   the connection as it now is, else its provider and account number), never an internal
   id. The server-written supervisor line leaves it. Supervision grants of any agent
   other than Lonora are revoked; Lonora's stay until the role check replaces them.
5. Pending Trade Approval rows keep their stored expiry: no expiry is written.
6. Restrictions ended with their feature (0086, which runs before this update), goals
   in 0068. A pause a supervisor set on its own ends and the work resumes: an agent runs again (with
   ``agent.updated``), a routine is switched back on, a watch resumes as the agent's own
   control resumes it, and a Task resumes as the live resume does (``control_task``),
   each Task it changes with ``task.updated``:

   - a pause asked of a Task whose Run a worker holds is withdrawn, which the Run reads at
     its next checkpoint;
   - a paused Task whose Run waits for takeover is queued again with its Run, also when it
     failed once before (only a failure still being retried is the retry's);
   - a paused Task, or one asked to pause, whose Run holds the owner's question resumes
     the work, not the question: the question is cancelled, the Run queued without its
     lease, and the owner-attention wait cleared;
   - a Task paused after a failure, waiting to retry, or failed (the live resume hands it
     to the retry, ``resume_failure``, which the migration does not reproduce) is
     released as it is, and its agent is woken once, in the Task's thread, by a Run with
     fixed server text naming the Task: it is no longer held, and the agent may resume it
     (``task_control``). An agent still paused by the owner or Lonora is not woken, as
     ``create_run`` refuses a paused agent; its Task waits for it as it is;
   - a Task item 3 stopped, any other ended Task, and work no longer paused are only
     released.

   A pause the owner holds or asked for (``owner_message``, which becomes ``owner``)
   stays, and so does a pause Lonora made (4.7.2).
7. Positions are attributed from the journal per 3.3.4 when they are read
   (``ticket_agent``): nothing is written.

Item 8 is void under Amendment 1 (Stop is removed, 0150): nothing is written for it.

The downgrade restores nothing and never raises: grants stay revoked, Tasks and Runs
stay ended, levels stay "Ask me", cards stay (the owner may have tapped them), flattened
agents and their method lines stay, supervision grants stay revoked,
released pauses stay released. A second upgrade, after a downgrade, applies the items
again to the data it then finds (an agent in Full goes back to Ask); it shows no Mandate
card twice and wakes no agent twice.
"""

import json
import re
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from functools import partial
from hashlib import sha256
from typing import Any, cast
from uuid import NAMESPACE_URL, uuid4, uuid5

import sqlalchemy as sa
from alembic import op

revision = "0063_authority_migration"
down_revision = "0061_trade_approval_validity"
branch_labels = None
depends_on = None

REASON = "mandate_migration"
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
# Frozen copy of the supervisor template's line (lonora_agent agent_create TEMPLATE_NOTES).
SUPERVISOR_LINE = (
    "Supervisor: you review the work of the agents the owner named and message them;"
    " you never trade for them."
)
# Frozen copy of lonora_db.memory.VIEW_HEADING.
VIEW_HEADING = re.compile(r"(?m)^# (USER\.md|OPERATING\.md|(?:memory/)?MEMORY\.md)[ \t]*\n")
OPERATING = "OPERATING.md"
TERMINAL_TASKS = ("completed", "failed", "cancelled")
TERMINAL_RUNS = ("completed", "failed", "cancelled")
LIVE_RUNS = ("queued", "leased", "running", "waiting_input", "waiting_takeover")
# Frozen copy of lonora_db.tasks.ATTENTION_RESUMED.
ATTENTION_RESUMED = "owner_attention_resumed"
# Frozen copy of lonora_db.trade_approvals.WITHDRAWN_TRIGGER: a wake whose prompt is fixed
# server text, which the agent reads as the server's own.
WAKE_TRIGGER = "owner_card"
# The columns agent_data reads.
AGENT_COLUMNS = (
    "id, name, title, description, avatar, color, instructions, paused, role, template,"
    " scope_mode, scope_revision, trading_account_id, trading_symbol, parent_id, created_at"
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
        payload: dict[str, Any],
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
            payload=dump(payload),
            now=self.now,
        )

    def card_event(self, card: Any) -> None:
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
                "transition_id": card.id + ":" + card.status,
            },
            agent_id=card.agent_id,
            thread_id=card.thread_id,
            run_id=card.run_id,
        )

    def settle_cards(
        self, where: str, reason: str, superseded_by: str | None = None, **parameters: Any
    ) -> None:
        """Pending cards end as superseded, or as expired past their expiry, with their
        event (lonora_db.owner_actions.settle, supersede_subject)."""
        for card in self.rows(
            "UPDATE ln_owner_actions SET status = CASE WHEN expires_at <= :now THEN 'expired'"
            " ELSE 'superseded' END, status_reason = CASE WHEN expires_at <= :now"
            " THEN 'expired' ELSE :reason END,"
            " superseded_by = COALESCE(:by, superseded_by), updated_at = :now"
            " WHERE status = 'pending' AND " + where + " RETURNING id, owner_id, agent_id,"
            " thread_id, run_id, kind, status, status_reason",
            reason=reason,
            by=superseded_by,
            now=self.now,
            **parameters,
        ):
            self.card_event(card)

    # -- locks ---------------------------------------------------------------------------

    def lock(self) -> None:
        """The locks a live process takes, in the order a card decision takes them
        (lock_owner_actions, then authority_lock), so a database migrated while the
        previous release still runs never interleaves with a tap or a send."""
        for (owner_id,) in self.rows("SELECT id FROM ln_owners ORDER BY id"):
            self.run(
                "SELECT pg_advisory_xact_lock(hashtextextended(:key, 0))",
                key="owner-actions:" + owner_id,
            )
        for (agent_id,) in self.rows(
            "SELECT id FROM ln_agents UNION SELECT agent_id FROM ln_account_authorities"
            " WHERE status IN ('pending','active') ORDER BY 1"
        ):
            self.run(
                "SELECT pg_advisory_xact_lock(hashtextextended(:key, 0))",
                key="super-bot:" + agent_id,
            )

    # -- item 6 holds --------------------------------------------------------------------

    def supervisor_holds(self) -> list[Any]:
        """Live pauses a supervisor other than Lonora set on its own: they end."""
        return self.rows(
            "SELECT h.id, h.owner_id, h.agent_id, h.target_kind, h.target_id"
            " FROM ln_supervision_holds h LEFT JOIN ln_agents p ON p.id = h.holder_agent_id"
            " WHERE h.released_at IS NULL AND h.source = 'agent'"
            " AND (p.role IS NULL OR p.role <> 'personal') ORDER BY h.id FOR UPDATE OF h"
        )

    # -- item 1 --------------------------------------------------------------------------

    def ask(self) -> None:
        for agent in self.rows(
            "UPDATE ln_agents SET trading_mode = 'ask' WHERE trading_mode <> 'ask'"
            " RETURNING id, owner_id"
        ):
            self.emit(
                agent.owner_id,
                "agent.trading_mode.updated",
                {"agent_id": agent.id, "trading_mode": "ask", "by": "system"},
                agent_id=agent.id,
            )
            # Frozen refresh_mandate_cards: the cards read the mode live.
            for card in self.rows(
                "SELECT id, owner_id, agent_id, thread_id, run_id, kind, status, status_reason"
                " FROM ln_owner_actions WHERE owner_id = :owner AND subject = :subject"
                " AND status IN ('pending','confirmed') ORDER BY id",
                owner=agent.owner_id,
                subject="trading_mode:" + agent.id,
            ):
                self.card_event(card)

    def ask_me_levels(self, revoked_agents: set[str]) -> None:
        """Frozen bump_permission over a PermissionRecord: exactly its five fields."""
        for agent in self.rows("SELECT id, owner_id FROM ln_agents ORDER BY owner_id, id"):
            key = permission_key(agent.owner_id, agent.id)
            stored = self.rows(
                "SELECT payload FROM ln_settings WHERE key = :key FOR UPDATE", key=key
            )
            record = payload_of(stored[0].payload) if stored else None
            if (
                record is not None
                and record.get("fallback_level") == "supervised"
                and agent.id not in revoked_agents
            ):
                continue
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

    def conversation(self, owner_id: str, agent_id: str) -> Any:
        """Frozen conversation_thread: the agent's earliest direct conversation, created
        when it has none."""
        rows = self.rows(
            "SELECT id, next_seq FROM ln_threads WHERE owner_id = :owner AND agent_id = :agent"
            " AND group_id IS NULL AND purpose = 'conversation' ORDER BY created_at, id"
            " LIMIT 1 FOR UPDATE",
            owner=owner_id,
            agent=agent_id,
        )
        if rows:
            return rows[0]
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

    def mandate_cards(self, grants: list[Any]) -> None:
        shown: dict[tuple[str, str], list[Any]] = {}
        for grant in grants:
            shown.setdefault((grant.owner_id, grant.agent_id), []).append(grant)
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
            previous = [
                {
                    "account_id": grant.account_id,
                    "full_delegation": full_delegation(payload_of(grant.envelope)),
                    "symbol_scope": payload_of(grant.envelope).get("symbol_scope"),
                    "symbols": list(payload_of(grant.envelope).get("symbols") or [])
                    if payload_of(grant.envelope).get("symbol_scope") == "selected"
                    else [],
                }
                for grant in sorted(held, key=lambda grant: (grant.account_id, grant.id))
            ]
            payload = {"agent_id": agent_id, "previous_grants": previous}
            subject = "trading_mode:" + agent_id
            # It replaces an older pending Mandate card of this agent.
            self.settle_cards(
                "owner_id = :owner AND kind = 'trading_mode' AND subject = :subject",
                REASON,
                card_id,
                owner=owner_id,
                subject=subject,
            )
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
                payload=dump(payload),
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
        revoked_ids: list[str] = []
        for grant in self.rows(
            "UPDATE ln_account_authorities SET status = 'revoked', updated_at = :now"
            " WHERE status IN ('pending','active') RETURNING id, owner_id, agent_id, thread_id,"
            " account_id",
            now=self.now,
        ):
            revoked_agents.add(grant.agent_id)
            revoked_ids.append(grant.id)
            self.emit(
                grant.owner_id,
                "account_authority.updated",
                {
                    "id": grant.id,
                    "agent_id": grant.agent_id,
                    "thread_id": grant.thread_id,
                    "account_id": grant.account_id,
                    "status": "revoked",
                    "author": "system",
                    "reason": REASON,
                },
                agent_id=grant.agent_id,
                thread_id=grant.thread_id,
            )
            self.stop_management_task(grant)
        if revoked_ids:
            # The grant's waiting management Run and activation review end with it, with
            # their pending and approved cards, as the owner's cancel of a Task ends its
            # Run (lonora_db.tasks.control_task); a Run a worker holds reads the stopped
            # Task at its next checkpoint.
            cancelled = self.rows(
                "UPDATE ln_runs SET status = 'cancelled', error_code = :reason,"
                " lease_owner = NULL, lease_expires_at = NULL, updated_at = :now"
                " WHERE status IN ('queued','waiting_input','waiting_takeover') AND ("
                " CAST(model_metadata AS JSONB) ->> 'account_management_id' = ANY(:ids)"
                " OR (trigger = 'activation'"
                " AND CAST(model_metadata AS JSONB) ->> 'account_authority_id' = ANY(:ids)))"
                " RETURNING id",
                reason=REASON,
                now=self.now,
                ids=revoked_ids,
            )
            if cancelled:
                for approval in self.rows(
                    "UPDATE ln_trade_approvals SET status = 'cancelled', updated_at = :now"
                    " WHERE run_id = ANY(:runs) AND status IN ('pending','approved')"
                    " RETURNING *",
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
        # A pending grant card would sign a new grant after this step.
        self.settle_cards("kind = 'grant_authority'", REASON)
        return revoked_agents

    def stop_management_task(self, grant: Any) -> None:
        """Frozen stop_management_task (finish_task(..., 'cancelled'), a failed Task
        cancelled), written once; its watches are kept (keep_task_watches)."""
        task_id = stable_id(grant.id, "account-management-task")
        rows = self.rows(
            "SELECT owner_id, agent_id, payload, state FROM ln_tickets WHERE id = :id FOR UPDATE",
            id=task_id,
        )
        if not rows or rows[0].owner_id != grant.owner_id or rows[0].agent_id != grant.agent_id:
            return
        state = payload_of(rows[0].state)
        task = payload_of(state.get("task"))
        if not task:
            return
        payload = payload_of(rows[0].payload)
        status = task.get("status")
        # Frozen task_ended: the owner's cancel or complete counts from the request.
        ended_before = status in {"cancelled", "completed"} or task.get("control_requested") in {
            "cancel",
            "complete",
        }
        paused = not ended_before and (
            status == "paused" or task.get("control_requested") == "pause"
        )
        if status == "failed":
            task.update(status="cancelled", phase="cancelled")
        elif status not in TERMINAL_TASKS:
            ended = "completed" if task.get("control_requested") == "complete" else "cancelled"
            task.update(status=ended, phase=ended, control_requested=None, waiting_reason=None)
        shown = {"queued": "todo", "running": "working", "paused": "waiting"}.get(
            task["status"], task["status"]
        )
        if task.get("status") != status or payload.get("status") != shown:
            version = self.rows(
                "UPDATE ln_tickets SET state = CAST(:state AS JSON),"
                " payload = CAST(:payload AS JSON), version = version + 1, updated_at = :now"
                " WHERE id = :id RETURNING version",
                id=task_id,
                state=dump({**state, "task": task}),
                payload=dump({**payload, "status": shown}),
                now=self.now,
            )[0].version
            self.emit(
                grant.owner_id,
                "task.updated",
                {
                    "id": task_id,
                    "version": version,
                    "status": task["status"],
                    "waiting_reason": task.get("waiting_reason"),
                },
                agent_id=grant.agent_id,
                thread_id=task.get("origin_thread_id"),
            )
        if not ended_before:
            self.keep_task_watches(grant, task_id, self.task_hold(task_id) if paused else None)

    def task_hold(self, task_id: str) -> tuple[str | None, str]:
        """Who holds a paused Task: its live hold's holder and source, else the owner."""
        holds = self.rows(
            "SELECT holder_agent_id, source FROM ln_supervision_holds"
            " WHERE target_kind = 'task' AND target_id = :id AND released_at IS NULL",
            id=task_id,
        )
        return (holds[0].holder_agent_id, holds[0].source) if holds else (None, "owner")

    def keep_task_watches(
        self, grant: Any, task_id: str, hold: tuple[str | None, str] | None
    ) -> None:
        """Ending the Task never cancels its watches (4.5.3): each stays the agent's own,
        without the Task. A paused Task's live watches stay paused under the same hold
        (frozen stop_watch 'watch_paused'), so only who paused it lifts the pause."""
        for watch in self.rows(
            "SELECT id, agent_id, thread_id, payload, state FROM ln_market_watches"
            " WHERE owner_id = :owner AND CAST(state AS JSONB) ->> 'task_id' = :task"
            " ORDER BY id FOR UPDATE",
            owner=grant.owner_id,
            task=task_id,
        ):
            payload = payload_of(watch.payload)
            state = {
                key: value
                for key, value in payload_of(watch.state).items()
                if key not in {"task_id", "task_run_id"}
            }
            if hold is not None and payload.get("enabled", True):
                payload = {**payload, "enabled": False}
                state = {
                    **{
                        key: value
                        for key, value in state.items()
                        if key not in {"evaluation_status", "next_check"}
                    },
                    "code": "watch_paused",
                }
                if not self.rows(
                    "SELECT id FROM ln_supervision_holds WHERE target_kind = 'watch'"
                    " AND target_id = :id AND released_at IS NULL",
                    id=watch.id,
                ):
                    self.run(
                        "INSERT INTO ln_supervision_holds (id, owner_id, holder_agent_id,"
                        " agent_id, target_kind, target_id, source, created_at) VALUES"
                        " (:id, :owner, :holder, :agent, 'watch', :target, :source, :now)",
                        id=stable_id(task_id, "mandate-migration-hold:" + watch.id),
                        owner=grant.owner_id,
                        holder=hold[0],
                        agent=watch.agent_id or grant.agent_id,
                        target=watch.id,
                        source=hold[1],
                        now=self.now,
                    )
            version = self.rows(
                "UPDATE ln_market_watches SET payload = CAST(:payload AS JSON),"
                " state = CAST(:state AS JSON), version = version + 1, updated_at = :now"
                " WHERE id = :id RETURNING version",
                id=watch.id,
                payload=dump(payload),
                state=dump(state),
                now=self.now,
            )[0].version
            self.emit(
                grant.owner_id,
                "market_watches.updated",
                {"id": watch.id, "version": version},
                agent_id=watch.agent_id,
                thread_id=watch.thread_id,
            )

    def changed_watch(
        self,
        owner_id: str,
        watch: Any,
        payload: dict[str, Any],
        state: dict[str, Any],
        by: str,
    ) -> None:
        state = {**state, "steered_by": by, "steered_at": self.now.isoformat()}
        version = self.rows(
            "UPDATE ln_market_watches SET payload = CAST(:payload AS JSON),"
            " state = CAST(:state AS JSON), version = version + 1, updated_at = :now"
            " WHERE id = :id RETURNING version",
            id=watch.id,
            payload=dump(payload),
            state=dump(state),
            now=self.now,
        )[0].version
        self.emit(
            owner_id,
            "market_watches.updated",
            {"id": watch.id, "version": version},
            agent_id=watch.agent_id,
            thread_id=watch.thread_id,
        )

    # -- item 4 --------------------------------------------------------------------------

    def team_agents(self) -> None:
        for agent in self.rows(
            "SELECT id, owner_id, template, trading_account_id, trading_symbol FROM ln_agents"
            " WHERE role <> 'personal' AND (role = 'delegated' OR parent_id IS NOT NULL"
            " OR template = 'supervisor') ORDER BY owner_id, created_at, id FOR UPDATE"
        ):
            if agent.trading_account_id and agent.trading_symbol:
                line = (
                    "Assigned market, moved here from your former fixed assignment: "
                    + agent.trading_symbol
                    + " on "
                    + self.account_name(agent.trading_account_id)
                    + ". Work on this symbol on this account unless the owner or Lonora"
                    " assigns another."
                )
                self.edit_method(agent, partial(with_operating_line, line=line))
            if agent.template == "supervisor":
                self.edit_method(agent, without_supervisor_line)
            flattened = self.rows(
                "UPDATE ln_agents SET parent_id = NULL, role = 'general', scope_mode = 'flexible',"
                " template = CASE WHEN template = 'supervisor' THEN 'general' ELSE template END,"
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
                payload=dump({**payload_of(origin.payload), "template": "general"}),
                now=self.now,
            )
        # A team agent supervises no one; Lonora's grants stay until the role check.
        for grant in self.rows(
            "UPDATE ln_supervision_grants g SET revoked_at = :now WHERE g.revoked_at IS NULL"
            " AND NOT EXISTS (SELECT 1 FROM ln_agents p WHERE p.id = g.supervisor_agent_id"
            " AND p.role = 'personal') RETURNING id, owner_id, supervisor_agent_id,"
            " supervised_agent_id, created_via, revoked_via",
            now=self.now,
        ):
            # Frozen _grant_events: recorded for both agents.
            for agent_id in (grant.supervisor_agent_id, grant.supervised_agent_id):
                self.emit(
                    grant.owner_id,
                    "supervision.revoked",
                    {
                        "id": grant.id,
                        "supervisor_agent_id": grant.supervisor_agent_id,
                        "supervised_agent_id": grant.supervised_agent_id,
                        "created_via": grant.created_via,
                        "revoked_via": grant.revoked_via,
                    },
                    agent_id=agent_id,
                )

    def account_name(self, account_id: str) -> str:
        """The account as the owner recognizes it (frozen owner_actions.account_facts:
        broker · login · server once the broker verified this connection), else its
        provider and the broker's account number; never an internal id."""
        rows = self.rows(
            "SELECT payload, state, version FROM ln_broker_sessions WHERE id = :id", id=account_id
        )
        if not rows:
            return "an account that is no longer connected"
        payload = payload_of(rows[0].payload)
        identity = payload_of(rows[0].state).get("broker_identity")
        identity = cast(dict[str, Any], identity) if isinstance(identity, dict) else {}
        if identity.get("connection_version") == rows[0].version:
            parts = [identity.get(key) for key in ("broker", "login", "server")]
            label = " · ".join(str(part) for part in parts if isinstance(part, str) and part)
            if label:
                return "the account " + label
        parts = [payload.get("provider"), "account", payload.get("account_id")]
        return "the " + " ".join(str(part) for part in parts if part)

    def edit_method(self, agent: Any, transform: Callable[[str], str]) -> None:
        """Frozen commit_memory(transform=...) by the system: one revision, retired
        sections kept as they are, no write when nothing changes."""
        rows = self.rows(
            "SELECT content, version FROM ln_memory WHERE agent_id = :id FOR UPDATE", id=agent.id
        )
        content = rows[0].content if rows else ""
        view, legacy = split_legacy(content)
        new_view = transform(view)
        if new_view == view:
            return
        if rows:
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

    def end_supervisor_pauses(self, holds: list[Any]) -> None:
        retried: list[str] = []
        for hold in holds:
            if hold.target_kind == "agent":
                for agent in self.rows(
                    "UPDATE ln_agents SET paused = false WHERE id = :id AND paused RETURNING "
                    + AGENT_COLUMNS,
                    id=hold.target_id,
                ):
                    self.emit(hold.owner_id, "agent.updated", agent_data(agent), agent_id=agent.id)
            elif hold.target_kind == "routine":
                self.run(
                    "UPDATE ln_routines SET enabled = true WHERE id = :id AND NOT enabled",
                    id=hold.target_id,
                )
            elif hold.target_kind == "watch":
                self.resume_watch(hold.owner_id, hold.target_id)
            elif hold.target_kind == "task":
                if self.resume_task(hold.target_id):
                    retried.append(hold.target_id)
            self.run(
                "UPDATE ln_supervision_holds SET released_at = :now, released_by = 'owner'"
                " WHERE id = :id",
                id=hold.id,
                now=self.now,
            )
        if holds:
            self.settle_cards(
                "kind = 'supervision_paused' AND CAST(payload AS JSONB) ->> 'hold_id' = ANY(:ids)",
                "supervision_pause_ended",
                ids=[hold.id for hold in holds],
            )
        # After every hold has ended, so an agent a supervisor paused is woken as well.
        for task_id in retried:
            self.wake_for_task(task_id)
        # A pause the owner asked a supervisor for is the owner's.
        self.run(
            "UPDATE ln_supervision_holds SET source = 'owner'"
            " WHERE released_at IS NULL AND source = 'owner_message'"
        )

    def resume_watch(self, owner_id: str, watch_id: str) -> None:
        """Frozen control_watch(..., 'resume'): an expired watch, one the agent cancelled
        itself or one whose Task ended stays off."""
        rows = self.rows(
            "SELECT id, agent_id, thread_id, payload, state FROM ln_market_watches"
            " WHERE id = :id FOR UPDATE",
            id=watch_id,
        )
        if not rows:
            return
        watch = rows[0]
        payload, state = payload_of(watch.payload), payload_of(watch.state)
        if payload.get("enabled", True) and state.get("lifecycle") != "expired":
            return
        if state.get("code") == "watch_cancelled":
            return
        expires = payload.get("expires_at")
        if expires and datetime.fromisoformat(str(expires)) <= self.now:
            return
        task = self.rows(
            "SELECT state FROM ln_tickets WHERE id = :id", id=str(state.get("task_id") or "")
        )
        if task:
            current = payload_of(payload_of(task[0].state).get("task"))
            if current.get("status") in {"cancelled", "completed"} or current.get(
                "control_requested"
            ) in {"cancel", "complete"}:
                return
        state = {key: value for key, value in state.items() if key != "code"}
        if state.get("lifecycle") == "expired":
            state["lifecycle"] = "pending"
            state.pop("lifecycle_reason", None)
        # The holder's resume goes through the agent's own control (by "agent").
        self.changed_watch(owner_id, watch, {**payload, "enabled": True}, state, "agent")

    def resume_task(self, task_id: str) -> bool:
        """The work a supervisor's pause holds resumes (14.3.18.6); True when its agent is
        to be woken to resume it itself.

        Only work paused, or asked to pause, is the hold's (frozen work_paused): any other
        hold is stale and only released, as control_work releases one. A Task the live resume
        hands to the retry (retry_control, resume_failure, which refuses a Task with a control
        asked) has a pause asked of it withdrawn, keeps everything else, and its agent is
        woken. Otherwise as control_task(..., 'resume'): a paused Task whose Run waits for
        takeover, or one paused or asked to pause whose Run holds the owner's question, is
        queued again with its Run, the question cancelled (release_attention). Any other
        pause asked of a Task is withdrawn wherever its Run is (the Run reads it at its next
        checkpoint), so it never takes effect with no hold. An ended Task, and a paused Task
        the live resume refuses, stay as they are."""
        found = self.rows(
            "SELECT thread_id, agent_id, state FROM ln_tickets WHERE id = :id", id=task_id
        )
        if not found:
            return False
        task = payload_of(payload_of(found[0].state).get("task"))
        # Frozen work_paused: a hold on work neither paused nor asked to pause is stale.
        if task.get("status") != "paused" and task.get("control_requested") != "pause":
            return False
        # Frozen retry_control: only a failure still being retried is the retry's.
        if task.get("failure") and (
            task.get("status") == "failed"
            or task.get("waiting_reason") == "retry_backoff"
            or task.get("phase") == "retry_paused"
        ):
            if task.get("status") in ("completed", "cancelled"):
                return False
            if task.get("control_requested") == "pause":
                # Locked as resume_failure locks it: the thread, the failed Run, the Task.
                failure = payload_of(task.get("failure"))
                self.run(
                    "SELECT 1 FROM ln_threads WHERE id = :id FOR UPDATE", id=found[0].thread_id
                )
                self.run(
                    "SELECT 1 FROM ln_runs WHERE id = :id FOR UPDATE",
                    id=str(failure.get("run_id") or ""),
                )
                self.withdraw_pause(task_id)
            return True
        if task.get("status") in TERMINAL_TASKS:
            return False
        # Frozen task_runs: the newest live Run of the Task's agent in its conversation,
        # locked before the Task, as control_task locks them.
        live = next(
            (
                run
                for run in self.rows(
                    "SELECT id, status FROM ln_runs WHERE thread_id = :thread"
                    " AND agent_id = :agent ORDER BY created_at DESC LIMIT 20",
                    thread=found[0].thread_id,
                    agent=found[0].agent_id,
                )
                if run.status in LIVE_RUNS
            ),
            None,
        )
        if live is None:
            self.withdraw_pause(task_id)
            return False
        run = self.rows(
            "SELECT status, execution_state FROM ln_runs WHERE id = :id FOR UPDATE", id=live.id
        )[0]
        ticket = self.rows(
            "SELECT owner_id, agent_id, payload, state FROM ln_tickets WHERE id = :id FOR UPDATE",
            id=task_id,
        )[0]
        state = payload_of(ticket.state)
        task = payload_of(state.get("task"))
        status, asked = task.get("status"), task.get("control_requested") == "pause"
        if run.status not in LIVE_RUNS or status in TERMINAL_TASKS:
            return False
        execution_state = payload_of(run.execution_state)
        attention = (
            run.status == "waiting_input" and attention_question(execution_state) is not None
        )
        if (status == "paused" or asked) and (
            attention or (status == "paused" and run.status == "waiting_takeover")
        ):
            released = release_attention(execution_state, run.status)
            if released is None:
                self.run("UPDATE ln_runs SET status = 'queued' WHERE id = :id", id=live.id)
            else:
                self.run(
                    "UPDATE ln_runs SET status = 'queued', execution_state = CAST(:state AS JSON),"
                    " lease_expires_at = NULL WHERE id = :id",
                    id=live.id,
                    state=dump(released),
                )
            task.update(status="queued", phase="queued", control_requested=None)
            if task.get("waiting_reason") == "owner_attention":
                task["waiting_reason"] = None
        elif asked:
            # A worker holds its Run, it was queued again, or it waits for another answer.
            task["control_requested"] = None
        else:
            return False
        self.save_task(ticket, task_id, state, task)
        return False

    def withdraw_pause(self, task_id: str) -> None:
        """A pause asked of the Task is withdrawn, with task.updated; nothing else changes."""
        ticket = self.rows(
            "SELECT owner_id, agent_id, payload, state FROM ln_tickets WHERE id = :id FOR UPDATE",
            id=task_id,
        )[0]
        state = payload_of(ticket.state)
        task = payload_of(state.get("task"))
        if task.get("control_requested") == "pause":
            task["control_requested"] = None
            self.save_task(ticket, task_id, state, task)

    def wake_for_task(self, task_id: str) -> None:
        """Frozen end_card's wake (create_run): one Run of the Task's agent in the Task's
        thread with fixed server text, once (a stable id). A paused agent is not woken, as
        create_run refuses it."""
        run_id = stable_id(task_id, "mandate-migration-released-task")
        if self.rows("SELECT 1 FROM ln_runs WHERE id = :id", id=run_id):
            return
        ticket = self.rows(
            "SELECT owner_id, agent_id, thread_id FROM ln_tickets WHERE id = :id", id=task_id
        )[0]
        if ticket.thread_id is None:
            return
        thread = self.rows(
            "SELECT id, next_seq FROM ln_threads WHERE id = :id FOR UPDATE", id=ticket.thread_id
        )[0]
        if self.rows("SELECT 1 FROM ln_agents WHERE id = :id AND paused", id=ticket.agent_id):
            return
        metadata = {"released_task_id": task_id}
        self.run(
            "INSERT INTO ln_runs (id, thread_id, agent_id, parent_run_id, trigger, prompt, status,"
            " input_seq, lease_owner, lease_fence, lease_expires_at, recovery_count,"
            " execution_state, model_metadata, error_code, result, created_at, updated_at)"
            " VALUES (:id, :thread, :agent, NULL, :trigger, :prompt, 'queued', :seq, NULL, 0,"
            " NULL, 0, CAST('{}' AS JSON), CAST(:metadata AS JSON), NULL, NULL, :now, :now)",
            id=run_id,
            thread=thread.id,
            agent=ticket.agent_id,
            trigger=WAKE_TRIGGER,
            prompt=released_prompt(task_id),
            seq=thread.next_seq - 1,
            metadata=dump(metadata),
            now=self.now,
        )
        # Frozen run_data of a new Run: no question, failure, result or stream yet.
        self.emit(
            ticket.owner_id,
            "run.queued",
            {
                "run": {
                    "input_requests": [],
                    "input_request": None,
                    "id": run_id,
                    "thread_id": thread.id,
                    "agent_id": ticket.agent_id,
                    "parent_run_id": None,
                    "status": "queued",
                    "trigger": WAKE_TRIGGER,
                    "input_seq": thread.next_seq - 1,
                    "error_code": None,
                    "failure": None,
                    "result": None,
                    "model_metadata": metadata,
                    "stream": None,
                    "created_at": self.now.isoformat(),
                    "updated_at": self.now.isoformat(),
                }
            },
            agent_id=ticket.agent_id,
            thread_id=thread.id,
            run_id=run_id,
        )

    def save_task(
        self, ticket: Any, task_id: str, state: dict[str, Any], task: dict[str, Any]
    ) -> None:
        """Frozen save_task: the Task with its shown status, version + 1 and task.updated."""
        shown = {"queued": "todo", "running": "working", "paused": "waiting"}.get(
            task["status"], task["status"]
        )
        version = self.rows(
            "UPDATE ln_tickets SET state = CAST(:state AS JSON),"
            " payload = CAST(:payload AS JSON), version = version + 1, updated_at = :now"
            " WHERE id = :id RETURNING version",
            id=task_id,
            state=dump({**state, "task": task}),
            payload=dump({**payload_of(ticket.payload), "status": shown}),
            now=self.now,
        )[0].version
        self.emit(
            ticket.owner_id,
            "task.updated",
            {
                "id": task_id,
                "version": version,
                "status": task["status"],
                "waiting_reason": task.get("waiting_reason"),
            },
            agent_id=ticket.agent_id,
            thread_id=task.get("origin_thread_id"),
        )


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
        "expires_at": row.expires_at.isoformat() if row.expires_at else None,
        "created_at": row.created_at.isoformat(),
    }


def attention_question(execution_state: dict[str, Any]) -> dict[str, Any] | None:
    """Frozen copy of lonora_db.tasks.attention_question."""
    question = execution_state.get("pending_input_request")
    if not isinstance(question, dict):
        return None
    value = cast(dict[str, Any], question)
    return value if value.get("kind") == "owner_attention" else None


def release_attention(execution_state: dict[str, Any], status: str) -> dict[str, Any] | None:
    """Frozen copy of lonora_db.tasks.release_attention(run, "resume"): the Run's state
    with the owner's question cancelled, as for any superseded question, and the resume
    recorded for the loop; None when no question holds the Run."""
    question = attention_question(execution_state)
    if question is None or status not in {"waiting_input", "waiting_takeover"}:
        return None
    history = [
        {**item, "status": "cancelled"}
        if item.get("id") == question.get("id") and item.get("status") == "pending"
        else item
        for item in execution_state.get("input_requests", [])
    ]
    state: dict[str, Any] = {
        **execution_state,
        "input_requests": history,
        ATTENTION_RESUMED: {"action": "resume", "question_id": question.get("id")},
    }
    state.pop("pending_input_request", None)
    return state


def released_prompt(task_id: str) -> str:
    """Fixed text and the server's own identifier only: nothing a model wrote."""
    return (
        f"Your Task (task_id={task_id}) is no longer held: the pause a supervising agent put"
        " on it has ended, and nothing else about it changed. Read it with task_inspect; if"
        " the work should go on, resume it with task_control (action resume), otherwise"
        " tell the owner in one line why not."
    )


def agent_data(row: Any) -> dict[str, Any]:
    """Frozen copy of lonora_db.agents.agent_data with agent_binding.scope_data; no agent
    trades on its own once item 3 has revoked every grant."""
    role = row.role or "legacy"
    flexible = (
        row.scope_mode == "flexible"
        and row.parent_id is None
        and row.role in {"general", "specialist"}
    )
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
        "trades_on_its_own": False,
        "role": row.role,
        "template": row.template,
        "scope": {
            "mode": row.scope_mode or "fixed_market",
            "role": role,
            "account_id": row.trading_account_id,
            "broker_symbol": row.trading_symbol,
            "visibility": "owner_accounts"
            if row.role == "personal" or flexible
            else "bound_market"
            if row.trading_account_id
            else "delegated_research"
            if role == "delegated"
            else "legacy",
            "execution_authority": "none" if role == "delegated" else "existing_server_controls",
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
            section = OPERATING if heading[1] == OPERATING else heading[1]
        elif section == OPERATING and line.strip() == SUPERVISOR_LINE:
            del lines[index]
            return normalize("\n".join(lines))
    return view


def upgrade() -> None:
    migration = Migration(op.get_bind())
    migration.lock()
    shown = migration.shown_grants()
    migration.ask()
    revoked_agents = migration.revoke_grants()
    # After item 3: a Task it stopped is no longer paused.
    holds = migration.supervisor_holds()
    migration.ask_me_levels(revoked_agents)
    migration.mandate_cards(shown)
    migration.team_agents()
    migration.end_supervisor_pauses(holds)


def downgrade() -> None:
    """Nothing is restored (see the module docstring); a downgrade never widens authority."""
