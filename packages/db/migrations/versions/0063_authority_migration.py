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
   agent's own, without the Task, and a pause on it (the owner's too) can still lift.
4. Delegated, child and supervisor agents become ordinary team agents: no parent, role
   ``general``, flexible, no binding, template ``supervisor`` becomes ``general``. A bound
   account and symbol become one line of the agent's method (its OPERATING.md), with a
   memory revision; the server-written supervisor line leaves it. Supervision grants of
   any agent other than Lonora are revoked; Lonora's stay until the role check replaces
   them.
5. Pending Trade Approval rows keep their stored expiry: no expiry is written.
6. Active and scheduled restrictions end, each with the live ``trading.restriction_revoked``
   event (goals already ended in 0068). A pause a
   supervisor set on its own ends and the work resumes. A pause the owner holds or asked
   for (``owner_message``, which becomes ``owner``) stays, and so does a pause Lonora made
   (4.7.2). A supervisor's pause on a paused Task needs the Task's Run state machine:
   the update stops with a message, and changes nothing, until the owner resumes or
   cancels that Task.
7. Positions are attributed from the journal per 3.3.4 when they are read
   (``ticket_agent``): nothing is written.

Item 8 is void under Amendment 1 (Stop is removed, 0150): nothing is written for it.

The downgrade restores nothing and never raises: grants stay revoked, Tasks and Runs
stay ended, levels stay "Ask me", cards stay (the owner may have tapped them), flattened
agents and their method lines stay, supervision grants and restrictions stay revoked,
released pauses stay released. A second upgrade, after a downgrade, applies the items
again to the data it then finds (an agent in Full goes back to Ask); it shows no Mandate
card twice.
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

    # -- item 6 guard --------------------------------------------------------------------

    def supervisor_holds(self) -> list[Any]:
        """Live pauses a supervisor other than Lonora set on its own: they end."""
        return self.rows(
            "SELECT h.id, h.owner_id, h.agent_id, h.target_kind, h.target_id"
            " FROM ln_supervision_holds h LEFT JOIN ln_agents p ON p.id = h.holder_agent_id"
            " WHERE h.released_at IS NULL AND h.source = 'agent'"
            " AND (p.role IS NULL OR p.role <> 'personal') ORDER BY h.id FOR UPDATE OF h"
        )

    def refuse_paused_tasks(self, holds: list[Any]) -> None:
        for hold in holds:
            if hold.target_kind != "task":
                continue
            ticket = self.rows("SELECT state FROM ln_tickets WHERE id = :id", id=hold.target_id)
            task = payload_of(payload_of(ticket[0].state).get("task")) if ticket else {}
            if task.get("status") not in TERMINAL_TASKS and (
                task.get("status") == "paused" or task.get("control_requested") == "pause"
            ):
                raise RuntimeError(
                    "A supervisor holds Task "
                    + hold.target_id
                    + " paused; resume or cancel it in Lonora, then run the update again"
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
        if status not in {"cancelled", "completed"}:
            self.keep_task_watches(grant.owner_id, task_id)

    def keep_task_watches(self, owner_id: str, task_id: str) -> None:
        """Ending the Task never cancels its watches (4.5.3): each stays the agent's own,
        without the Task, so it wakes the agent and a pause on it can still be lifted."""
        for watch in self.rows(
            "SELECT id, agent_id, thread_id, state FROM ln_market_watches"
            " WHERE owner_id = :owner AND CAST(state AS JSONB) ->> 'task_id' = :task"
            " ORDER BY id FOR UPDATE",
            owner=owner_id,
            task=task_id,
        ):
            state = {
                key: value
                for key, value in payload_of(watch.state).items()
                if key not in {"task_id", "task_run_id"}
            }
            version = self.rows(
                "UPDATE ln_market_watches SET state = CAST(:state AS JSON),"
                " version = version + 1, updated_at = :now WHERE id = :id RETURNING version",
                id=watch.id,
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
                    "Assigned market, moved here from your former fixed binding: account_id "
                    + json.dumps(agent.trading_account_id)
                    + ", broker_symbol "
                    + json.dumps(agent.trading_symbol)
                    + ". Work on this symbol on this account unless the owner or Lonora"
                    " assigns another."
                )
                self.edit_method(agent, partial(with_operating_line, line=line))
            if agent.template == "supervisor":
                self.edit_method(agent, without_supervisor_line)
            self.run(
                "UPDATE ln_agents SET parent_id = NULL, role = 'general', scope_mode = 'flexible',"
                " template = CASE WHEN template = 'supervisor' THEN 'general' ELSE template END,"
                " trading_account_id = NULL, trading_symbol = NULL,"
                " scope_revision = scope_revision + 1 WHERE id = :id",
                id=agent.id,
            )
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

    def end_restrictions(self) -> None:
        ended = self.rows(
            "UPDATE ln_trading_restrictions SET revoked_at = :now, updated_at = :now"
            " WHERE revoked_at IS NULL AND (valid_until IS NULL OR valid_until > :now)"
            " RETURNING *",
            now=self.now,
        )
        for row in ended:
            # Frozen revoke_restriction's event, with restriction_data.
            self.emit(
                row.owner_id,
                "trading.restriction_revoked",
                {"restriction": self.restriction_data(row), "transition_id": row.id + ":revoked"},
                agent_id=row.agent_id,
            )
        if ended:
            self.settle_cards(
                "kind = 'lift_restriction' AND subject = ANY(:subjects)",
                "restriction_already_ended",
                subjects=["restriction:" + row.id for row in ended],
            )

    def restriction_data(self, row: Any) -> dict[str, Any]:
        """Frozen copy of lonora_db.trading_restrictions.restriction_data for a row this
        migration revoked."""
        return {
            "id": row.id,
            "account_id": row.account_id,
            "agent_id": row.agent_id,
            "all_agents": row.agent_id is None,
            "symbol": row.symbol,
            "all_symbols": row.symbol is None,
            "symbol_verified": row.symbol is None or row.symbol_verified is not False,
            "action_class": row.action_class,
            "state": "revoked",
            "valid_from": row.valid_from.isoformat(),
            "valid_until": row.valid_until.isoformat() if row.valid_until else None,
            "ended_at": row.revoked_at.isoformat(),
            "applies_to_owner_manual": row.applies_to_owner_manual,
            "source": row.source,
            "source_message_id": row.source_message_id,
            "source_run_id": row.source_run_id,
            "reason": row.reason,
            "created_by": row.created_by,
            "created_by_agent_id": row.created_by_agent_id,
            "created_at": row.created_at.isoformat(),
            "revoked_at": row.revoked_at.isoformat(),
            "revoked_reason": row.revoked_reason,
            "lift": "owner_only",
        }

    def end_supervisor_pauses(self, holds: list[Any]) -> None:
        for hold in holds:
            if hold.target_kind == "agent":
                self.run(
                    "UPDATE ln_agents SET paused = false WHERE id = :id AND paused",
                    id=hold.target_id,
                )
            elif hold.target_kind == "routine":
                self.run(
                    "UPDATE ln_routines SET enabled = true WHERE id = :id AND NOT enabled",
                    id=hold.target_id,
                )
            elif hold.target_kind == "watch":
                self.resume_watch(hold.owner_id, hold.target_id)
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
    migration.refuse_paused_tasks(holds)
    migration.ask_me_levels(revoked_agents)
    migration.mandate_cards(shown)
    migration.team_agents()
    migration.end_restrictions()
    migration.end_supervisor_pauses(holds)


def downgrade() -> None:
    """Nothing is restored (see the module docstring); a downgrade never widens authority."""
