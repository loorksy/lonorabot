"""Migration 0063 moves existing data to the trading mode (mandate 14.3.18, items 1-7).

On a disposable PostgreSQL at head, four passes, each seeded at head and run from below
the migration:

1. The exact production shape: Lonora (stored "No trading") and Dino ("Ask me"), each
   with an active, unexpiring Full-delegation grant; Lonora's default supervision grant
   over Dino; three owner-held watch pauses. It runs from below 0060, so 0060, 0061 and
   0063 run together as on the owner's install.
2. The general cases: management Tasks in every state, expired, pending, revoked and
   orphaned grants, an activation review, every kind of pause, delegated,
   child and supervisor agents, a stored Trade Approval and journaled tickets.
3. A database already at 0061: an agent in Full and older pending Mandate cards.
4. A supervisor's pause on a Task ends like any other: a pause asked of a Task whose Run a
   worker holds is withdrawn; a paused Task waiting for takeover, one with an older
   failure and one held for the owner's question resume exactly as the live resume
   resumes an unheld twin; a Task paused after a failure (the live retry's to resume) is
   released as it is and its agent is woken once with fixed server text (an agent the
   owner paused is not woken); the update completes, and running it again wakes no one
   twice.

Item 8 is void under Amendment 1: no trading setting is written.
"""

import asyncio
import subprocess
import sys
from datetime import timedelta
from decimal import Decimal
from hashlib import md5
from typing import Any
from uuid import uuid4

from check_trading import database
from lonora_agent.context.routine import wake_context
from lonora_contracts.account import Position
from lonora_contracts.account_authority import ALL_AUTHORITY_ACTIONS, AccountAuthorityEnvelope
from lonora_contracts.agent_permissions import PermissionRecord
from lonora_contracts.domain import utcnow
from lonora_contracts.tasks import TaskControl, TaskFailure, TaskState
from lonora_contracts.trading import TradeRequest, TradeResult
from lonora_core.user_error import LonoraError
from lonora_db.agent_binding import assert_market_binding, require_financial_agent
from lonora_db.agent_creation import origin_key
from lonora_db.agent_permissions import effective_permission, permission_key
from lonora_db.agents import agent_data
from lonora_db.broker_sessions import BrokerSessionRepository
from lonora_db.client import Database
from lonora_db.owner_actions import account_facts, card_facts, payload_hash
from lonora_db.runs import run_data
from lonora_db.schema import (
    AccountAuthorityRow,
    AgentRow,
    BrokerSessionRow,
    DeviceCredentialRow,
    EventRow,
    MarketWatchRow,
    MemoryRevisionRow,
    MemoryRow,
    OwnerActionRow,
    OwnerRow,
    RoutineRow,
    RunRow,
    SettingRow,
    SupervisionGrantRow,
    SupervisionHoldRow,
    ThreadRow,
    TicketRow,
    TradeApprovalRow,
    TradingJournalRow,
)
from lonora_db.supervision import owner_resumes
from lonora_db.tasks import ATTENTION_RESUMED, control_task, get_task
from lonora_db.trading_mode import set_trading_mode, trading_mode
from lonora_session.idempotency import request_hash, stable_id
from lonora_trading.account_authority import ticket_agent
from lonora_trading.agent_permission import require_operation_permission
from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

ALEMBIC = [sys.executable, "-m", "alembic", "-c", "packages/db/alembic.ini"]
REVISION = "0063_authority_migration"
# The owner's install: 0060, 0061 and 0063 run together in one update.
BEFORE_MODE = "0060_agent_trading_mode-1"
# A database already at 0061.
BEFORE = REVISION + "-1"
SUPERVISOR_LINE = (
    "Supervisor: you review the work of the agents the owner named and message them;"
    " you never trade for them."
)


def alembic(*arguments: str) -> None:
    subprocess.run([*ALEMBIC, *arguments], check=True, capture_output=True, text=True)


def migration_card_id(owner_id: str, agent_id: str) -> str:
    return stable_id(owner_id, "owner-action:trading_mode:mandate-migration:" + agent_id)


def full_envelope(owner_id: str, agent_id: str, account_id: str, thread_id: str) -> dict[str, Any]:
    return AccountAuthorityEnvelope(
        owner_id=owner_id,
        agent_id=agent_id,
        thread_id=thread_id,
        account_id=account_id,
        management_mode="full",
        symbol_scope="account",
        actions=list(ALL_AUTHORITY_ACTIONS),
        allow_manual_positions=True,
        schema_version=2,
    ).model_dump(mode="json")


def bounded_envelope(
    owner_id: str, agent_id: str, account_id: str, thread_id: str, valid_until: Any
) -> dict[str, Any]:
    return AccountAuthorityEnvelope(
        owner_id=owner_id,
        agent_id=agent_id,
        thread_id=thread_id,
        account_id=account_id,
        symbols=["XAUUSD", "EURUSD"],
        actions=["buy", "sell", "close_position"],
        maximum_order_volume=Decimal("1"),
        maximum_symbol_volume=Decimal("2"),
        maximum_positions=3,
        maximum_pending_orders=0,
        maximum_actions=20,
        minimum_equity=Decimal("100"),
        valid_until=valid_until,
    ).model_dump(mode="json")


class Seed:
    """Rows seeded at head with the application's own tables."""

    def __init__(self, session: AsyncSession, owner_id: str, account_id: str) -> None:
        self.session, self.owner_id, self.account_id = session, owner_id, account_id
        self.device_id = ""

    async def agent(self, name: str, **fields: Any) -> AgentRow:
        agent = AgentRow(owner_id=self.owner_id, name=name, **fields)
        self.session.add(agent)
        await self.session.flush()
        return agent

    async def conversation(self, agent_id: str, next_seq: int = 1) -> ThreadRow:
        thread = ThreadRow(owner_id=self.owner_id, agent_id=agent_id, next_seq=next_seq)
        self.session.add(thread)
        await self.session.flush()
        return thread

    def level(self, agent_id: str, level: str, revision: int) -> None:
        self.session.add(
            SettingRow(
                key=permission_key(self.owner_id, agent_id),
                payload=PermissionRecord(
                    owner_id=self.owner_id,
                    agent_id=agent_id,
                    revision=revision,
                    fallback_level=level,  # type: ignore[arg-type]
                ).model_dump(mode="json"),
            )
        )

    async def grant(
        self,
        agent_id: str,
        thread_id: str,
        *,
        status: str = "active",
        envelope: dict[str, Any] | None = None,
        account_id: str | None = None,
    ) -> AccountAuthorityRow:
        account = account_id or self.account_id
        envelope = envelope or full_envelope(self.owner_id, agent_id, account, thread_id)
        valid_until = envelope.get("valid_until")
        row = AccountAuthorityRow(
            owner_id=self.owner_id,
            agent_id=agent_id,
            thread_id=thread_id,
            account_id=account,
            status=status,
            envelope=envelope,
            envelope_hash=request_hash(envelope),
            device_id=self.device_id,
            activation_expires_at=utcnow() - timedelta(days=30)
            if status != "pending"
            else utcnow() + timedelta(minutes=10),
            valid_until=AccountAuthorityEnvelope.model_validate(envelope).valid_until
            if valid_until
            else None,
            created_at=utcnow() - timedelta(days=20),
        )
        self.session.add(row)
        await self.session.flush()
        return row

    async def watch(
        self,
        agent_id: str,
        thread_id: str,
        *,
        enabled: bool,
        state: dict[str, Any] | None = None,
        symbol: str = "XAUUSD",
    ) -> MarketWatchRow:
        row = MarketWatchRow(
            owner_id=self.owner_id,
            agent_id=agent_id,
            thread_id=thread_id,
            payload={"symbol": symbol, "condition": "price_above", "enabled": enabled},
            state=state or {},
        )
        self.session.add(row)
        await self.session.flush()
        return row

    async def hold(
        self,
        agent_id: str,
        kind: str,
        target_id: str,
        source: str,
        holder: str | None,
    ) -> SupervisionHoldRow:
        row = SupervisionHoldRow(
            owner_id=self.owner_id,
            holder_agent_id=holder,
            agent_id=agent_id,
            target_kind=kind,
            target_id=target_id,
            source=source,
        )
        self.session.add(row)
        await self.session.flush()
        return row

    async def task(
        self,
        agent_id: str,
        thread_id: str,
        task_id: str,
        *,
        status: str,
        control_requested: str | None = None,
        run_id: str | None = None,
    ) -> TicketRow:
        state = TaskState(
            origin_thread_id=thread_id,
            completion_mode="continuous",
            status=status,  # type: ignore[arg-type]
            phase=status,
            control_requested=control_requested,  # type: ignore[arg-type]
        ).model_dump(mode="json")
        shown = {"queued": "todo", "running": "working", "paused": "waiting"}.get(status, status)
        row = TicketRow(
            id=task_id,
            owner_id=self.owner_id,
            agent_id=agent_id,
            thread_id=thread_id,
            payload={"title": "Manage the account", "status": shown, "run_id": run_id},
            state={"task": state},
        )
        self.session.add(row)
        await self.session.flush()
        return row

    async def card(
        self, agent_id: str, thread_id: str, kind: str, subject: str, payload: dict[str, Any]
    ) -> OwnerActionRow:
        row = OwnerActionRow(
            owner_id=self.owner_id,
            agent_id=agent_id,
            thread_id=thread_id,
            source="agent",
            kind=kind,
            subject=subject,
            payload=payload,
            payload_hash=payload_hash(kind, payload),
            status="pending",
            expires_at=utcnow() + timedelta(days=1),
        )
        self.session.add(row)
        await self.session.flush()
        return row


async def digest(db: Database, query: str, **parameters: Any) -> str:
    async with db.engine.connect() as connection:
        rows = (await connection.execute(text(query), parameters)).all()
    return md5(repr(sorted(repr(tuple(row)) for row in rows)).encode()).hexdigest()


async def last_cursor(db: Database) -> int:
    async with db.sessions() as session:
        return int(await session.scalar(select(func.max(EventRow.cursor))) or 0)


async def events_since(db: Database, cursor: int, kind: str) -> list[EventRow]:
    async with db.sessions() as session:
        return list(
            await session.scalars(
                select(EventRow)
                .where(EventRow.cursor > cursor, EventRow.kind == kind)
                .order_by(EventRow.cursor)
            )
        )


async def mandate_cards(session: AsyncSession, subject_agent: str) -> list[OwnerActionRow]:
    return list(
        await session.scalars(
            select(OwnerActionRow)
            .where(
                OwnerActionRow.kind == "trading_mode",
                OwnerActionRow.subject == "trading_mode:" + subject_agent,
            )
            .order_by(OwnerActionRow.created_at)
            .execution_options(populate_existing=True)
        )
    )


async def level_of(session: AsyncSession, owner_id: str, agent_id: str) -> PermissionRecord:
    row = await session.get(SettingRow, permission_key(owner_id, agent_id), populate_existing=True)
    assert row is not None, "every agent has a stored level after 0063"
    return PermissionRecord.model_validate(row.payload)


async def upgrade_from(db: Database, before: str) -> None:
    await db.engine.dispose()
    alembic("downgrade", before)
    alembic("upgrade", "head")


async def revision(db: Database) -> str:
    async with db.engine.connect() as connection:
        return str(await connection.scalar(text("SELECT version_num FROM lonora_v2_alembic")))


async def production_shape(db: Database, ids: dict[str, str]) -> None:
    """Pass 1: the owner's install as the lead read it, and nothing else."""
    async with db.sessions() as session, session.begin():
        owner = OwnerRow(email="authority-migration@example.test", password_hash="x")
        session.add(owner)
        await session.flush()
        account = await BrokerSessionRepository().create(
            session,
            owner.id,
            {"provider": "simulation", "account_id": "migration-" + uuid4().hex, "enabled": True},
        )
        seed = Seed(session, owner.id, account.id)
        device = DeviceCredentialRow(
            owner_id=owner.id, name="phone", credential_id="cred-" + uuid4().hex, public_key="k"
        )
        session.add(device)
        await session.flush()
        seed.device_id = device.id
        lonora = await seed.agent("Lonora", role="personal")
        dino = await seed.agent(
            "Dino", role="specialist", template="trading", scope_mode="flexible"
        )
        lonora_thread = await seed.conversation(lonora.id, next_seq=7)
        later = await seed.conversation(lonora.id)
        later.created_at = utcnow() + timedelta(seconds=1)
        dino_thread = await seed.conversation(dino.id)
        seed.level(lonora.id, "analysis", 3)
        seed.level(dino.id, "supervised", 2)
        lonora_grant = await seed.grant(lonora.id, lonora_thread.id)
        dino_grant = await seed.grant(dino.id, dino_thread.id)
        session.add(
            SupervisionGrantRow(
                owner_id=owner.id,
                supervisor_agent_id=lonora.id,
                supervised_agent_id=dino.id,
                created_via="default",
            )
        )
        # Three pauses the owner holds on EURUSDm watches, one taken over from Lonora.
        for holder in (None, None, lonora.id):
            watch = await seed.watch(
                dino.id,
                dino_thread.id,
                enabled=False,
                state={"code": "watch_paused"},
                symbol="EURUSDm",
            )
            await seed.hold(dino.id, "watch", watch.id, "owner", holder)
        ids.update(
            owner=owner.id,
            account=account.id,
            lonora=lonora.id,
            dino=dino.id,
            lonora_thread=lonora_thread.id,
            dino_thread=dino_thread.id,
            lonora_grant=lonora_grant.id,
            dino_grant=dino_grant.id,
            device=device.id,
        )

    untouched = {
        "supervision": "SELECT * FROM ln_supervision_grants",
        "holds": "SELECT * FROM ln_supervision_holds",
        "watches": "SELECT * FROM ln_market_watches",
        "control": "SELECT * FROM ln_settings WHERE key LIKE 'trading%'",
        "journal": "SELECT * FROM ln_trading_journal",
        "approvals": "SELECT id, status, expires_at FROM ln_trade_approvals",
    }
    before = {name: await digest(db, query) for name, query in untouched.items()}
    async with db.sessions() as session:
        envelopes = {
            row.id: (row.envelope, row.envelope_hash, row.device_id)
            for row in await session.scalars(select(AccountAuthorityRow))
        }
    cursor = await last_cursor(db)

    await upgrade_from(db, BEFORE_MODE)

    owner_id, lonora, dino = ids["owner"], ids["lonora"], ids["dino"]
    async with db.sessions() as session:
        # Item 1: Ask, and the old ladder no longer refuses what Ask allows.
        for agent in (lonora, dino):
            assert await trading_mode(session, owner_id, agent) == "ask"
            record = await level_of(session, owner_id, agent)
            assert record.fallback_level == "supervised", record
            assert await effective_permission(session, owner_id, agent) == "supervised"
        assert (await level_of(session, owner_id, lonora)).revision == 4
        assert (await level_of(session, owner_id, dino)).revision == 3
        # Item 3: revoked, the signed record intact.
        for grant in await session.scalars(select(AccountAuthorityRow)):
            assert grant.status == "revoked", grant.status
            assert (grant.envelope, grant.envelope_hash, grant.device_id) == envelopes[grant.id]
        # Item 2: Lonora shows each agent's Mandate card once, Lonora's own first.
        cards: list[OwnerActionRow] = []
        for agent in (lonora, dino):
            rows = await mandate_cards(session, agent)
            assert len(rows) == 1, rows
            card = rows[0]
            assert card.id == migration_card_id(owner_id, agent)
            assert card.agent_id == lonora and card.thread_id == ids["lonora_thread"]
            assert card.source == "system" and card.status == "pending" and card.run_id is None
            assert card.timeline_seq == 7 and card.result == {}
            assert card.payload == {
                "agent_id": agent,
                "previous_grants": [
                    {
                        "account_id": ids["account"],
                        "full_delegation": True,
                        "symbol_scope": "account",
                        "symbols": [],
                    }
                ],
            }, card.payload
            assert card.payload_hash == payload_hash("trading_mode", card.payload)
            assert card.expires_at > utcnow() + timedelta(days=3000)
            cards.append(card)
        assert cards[0].created_at < cards[1].created_at, "Lonora's own card comes first"
        thread = await session.get(ThreadRow, ids["lonora_thread"])
        assert thread is not None and thread.next_seq == 7
        facts, _ = await card_facts(session, cards[1], utcnow())
        assert facts["trading_mode"] == "ask" and facts["active_grant"] is False, facts
        assert facts["previous_grants"] == [
            {
                "full_delegation": True,
                "symbol_scope": "account",
                "symbols": [],
                "account": facts["previous_grants"][0]["account"],
            }
        ], facts
        assert facts["previous_grants"][0]["account"]["id"] == ids["account"], facts
    for name, query in untouched.items():
        assert await digest(db, query) == before[name], name + " changed"
    assert len(await events_since(db, cursor, "account_authority.updated")) == 2
    assert len(await events_since(db, cursor, "agent.permission.updated")) == 2
    shown = await events_since(db, cursor, "owner_action.updated")
    assert sorted(event.payload["id"] for event in shown) == sorted(
        migration_card_id(owner_id, agent) for agent in (lonora, dino)
    )
    assert not await events_since(db, cursor, "agent.trading_mode.updated")

    # The door on the migrated install: Lonora asks for new risk, never "No trading".
    async with db.sessions() as session, session.begin():
        run = RunRow(thread_id=ids["lonora_thread"], agent_id=lonora, status="running")
        session.add(run)
        await session.flush()
        buy = TradeRequest(
            account_id=ids["account"],
            operation_id="door-" + uuid4().hex,
            action="buy",
            symbol="XAUUSD",
            volume=Decimal("0.1"),
        )
        try:
            await require_operation_permission(session, owner_id, run, buy, None, reducing=False)
        except LonoraError as error:
            assert error.code == "trade_approval_required", error.code
        else:
            raise AssertionError("Ask sent new risk without an approval")
        close = buy.model_copy(update={"action": "close_position", "position_id": "p1"})
        await require_operation_permission(session, owner_id, run, close, None, reducing=True)
        await set_trading_mode(session, owner_id, lonora, "full", by="owner_tap")
        await require_operation_permission(session, owner_id, run, buy, None, reducing=False)
        await set_trading_mode(session, owner_id, lonora, "ask", by="agent")

    # Once: running it again adds no card, no event and no revision.
    cursor = await last_cursor(db)
    await upgrade_from(db, BEFORE)
    async with db.sessions() as session:
        for agent in (lonora, dino):
            assert len(await mandate_cards(session, agent)) == 1
        assert (await level_of(session, owner_id, lonora)).revision == 4
    for kind in ("owner_action.updated", "agent.permission.updated", "account_authority.updated"):
        assert not await events_since(db, cursor, kind), kind
    print(
        "PASS the production shape: both agents in Ask at the 'Ask me' level, both grants"
        " revoked intact, each agent's Mandate card shown once in Lonora's conversation with"
        " its old grant; supervision, owner pauses, watches and the trading settings untouched;"
        " the door asks Lonora for new risk and lets a close through"
    )


async def general_cases(db: Database, ids: dict[str, str]) -> None:
    """Pass 2: every other shape the old permission code could leave behind."""
    owner_id, account_id = ids["owner"], ids["account"]
    now = utcnow()
    async with db.sessions() as session, session.begin():
        seed = Seed(session, owner_id, account_id)
        seed.device_id = ids["device"]
        lonora, dino = ids["lonora"], ids["dino"]

        async def new_agent(name: str, **fields: Any) -> tuple[AgentRow, ThreadRow]:
            row = await seed.agent(name, **fields)
            return row, await seed.conversation(row.id)

        general, _ = await new_agent("General", role="general", scope_mode="flexible")
        seed.level(general.id, "analysis", 0)
        unrecorded, _ = await new_agent("Unrecorded", role="general", scope_mode="flexible")
        flexible = {"role": "specialist", "scope_mode": "flexible"}
        managers: dict[str, tuple[str, str, str, str, str]] = {}
        run_states = {"running": "waiting_takeover", "paused": "waiting_takeover"}
        for name, status, control in (
            ("Running", "running", None),
            ("Failed", "failed", None),
            ("Completing", "running", "complete"),
            ("Cancelled", "cancelled", None),
            ("Leased", "running", None),
            ("Paused", "paused", None),
            ("Held", "paused", None),
        ):
            row, thread = await new_agent(name, **flexible)
            grant = await seed.grant(row.id, thread.id)
            task_id = stable_id(grant.id, "account-management-task")
            leased = name == "Leased"
            run = RunRow(
                thread_id=thread.id,
                agent_id=row.id,
                trigger="tickets",
                status="leased" if leased else run_states.get(status, "completed"),
                lease_owner="worker-1" if leased else None,
                lease_expires_at=now + timedelta(minutes=5) if leased else None,
                model_metadata={"task_id": task_id, "account_management_id": grant.id},
            )
            session.add(run)
            await session.flush()
            await seed.task(
                row.id, thread.id, task_id, status=status, control_requested=control, run_id=run.id
            )
            managers[name] = (row.id, grant.id, task_id, run.id, thread.id)
        running_agent, _, running_task, running_run, running_thread = managers["Running"]
        # The management Task's own watches stay the agent's own when it ends (4.5.3):
        # one live, one a supervisor paused, one the owner paused.
        linked = {"task_id": running_task, "task_run_id": running_run}
        live_task_watch = await seed.watch(
            running_agent, running_thread, enabled=True, state={**linked, "lifecycle": "pending"}
        )
        task_watch = await seed.watch(
            running_agent, running_thread, enabled=False, state={**linked, "code": "watch_paused"}
        )
        owner_task_watch = await seed.watch(
            running_agent,
            running_thread,
            enabled=False,
            state={**linked, "code": "watch_paused"},
            symbol="EURUSDm",
        )
        owner_task_watch_hold = await seed.hold(
            running_agent, "watch", owner_task_watch.id, "owner", None
        )
        # Every other management Task with a watch of its own: the owner paused Held.
        held_task_hold = await seed.hold(
            managers["Held"][0], "task", managers["Held"][2], "owner", None
        )
        settled = {"code": "task_terminal", "steered_by": "task"}
        task_watches: dict[str, MarketWatchRow] = {}
        for manager, enabled, extra in (
            ("Failed", True, {"lifecycle": "pending"}),
            ("Leased", True, {"lifecycle": "pending"}),
            ("Held", True, {"lifecycle": "pending"}),
            ("Paused", True, {"lifecycle": "pending"}),
            ("Cancelled", False, settled),
            ("Completing", False, settled),
        ):
            agent_id, _, task_id, run_id, thread_id = managers[manager]
            task_watches[manager] = await seed.watch(
                agent_id,
                thread_id,
                enabled=enabled,
                state={"task_id": task_id, "task_run_id": run_id, **extra},
            )
        own_watch = await seed.watch(running_agent, running_thread, enabled=True)
        # A card the management Run waits on ends with that Run.
        stranded = TradeApprovalRow(
            id=str(uuid4()),
            owner_id=owner_id,
            agent_id=running_agent,
            run_id=managers["Running"][3],
            thread_id=running_thread,
            call_id="management",
            requests=[],
            status="pending",
            results=[],
            broker_snapshot={},
        )
        session.add(stranded)
        bounded, bounded_thread = await new_agent("Bounded", **flexible)
        bounded_grant = await seed.grant(
            bounded.id,
            bounded_thread.id,
            envelope=bounded_envelope(
                owner_id, bounded.id, account_id, bounded_thread.id, now + timedelta(days=5)
            ),
        )
        review = RunRow(
            thread_id=bounded_thread.id,
            agent_id=bounded.id,
            trigger="activation",
            status="queued",
            model_metadata={"account_authority_id": bounded_grant.id},
        )
        session.add(review)
        expired, expired_thread = await new_agent("Expired", **flexible)
        expired_grant = await seed.grant(
            expired.id,
            expired_thread.id,
            envelope=bounded_envelope(
                owner_id, expired.id, account_id, expired_thread.id, now + timedelta(days=1)
            ),
        )
        expired_grant.valid_until = now - timedelta(days=1)
        pending, pending_thread = await new_agent("Pending", **flexible)
        pending_grant = await seed.grant(pending.id, pending_thread.id, status="pending")
        revoked, revoked_thread = await new_agent("Revoked", **flexible)
        revoked_grant = await seed.grant(revoked.id, revoked_thread.id, status="revoked")
        # Runs no grant this migration revokes: they are not touched.
        unrelated_runs: list[str] = []
        for trigger, metadata in (
            ("tickets", {"task_id": "another-task"}),
            ("activation", {"account_authority_id": revoked_grant.id}),
        ):
            other = RunRow(
                thread_id=revoked_thread.id,
                agent_id=revoked.id,
                trigger=trigger,
                status="waiting_takeover" if trigger == "tickets" else "queued",
                model_metadata=metadata,
            )
            session.add(other)
            await session.flush()
            unrelated_runs.append(other.id)
        orphan_grant = await seed.grant(str(uuid4()), revoked_thread.id)
        grant_card = await seed.card(
            lonora, ids["lonora_thread"], "grant_authority", "grant:" + general.id, {"x": 1}
        )
        stale_card = await seed.card(
            lonora, ids["lonora_thread"], "grant_authority", "grant:" + pending.id, {"x": 2}
        )
        stale_card.expires_at = now - timedelta(hours=1)
        wide, wide_thread = await new_agent("Wide", **flexible)
        wide_envelope = full_envelope(owner_id, wide.id, account_id, wide_thread.id)
        wide_envelope["allow_manual_positions"] = False
        await seed.grant(wide.id, wide_thread.id, envelope=wide_envelope)

        # Item 4: delegated, child and supervisor agents.
        helper, _ = await new_agent("Helper", role="delegated", parent_id=lonora)
        parent, _ = await new_agent(
            "Parent", role="specialist", trading_account_id=account_id, trading_symbol="XAUUSD"
        )
        child, child_thread = await new_agent(
            "Child",
            role="specialist",
            parent_id=parent.id,
            trading_account_id=account_id,
            trading_symbol="EURUSD",
        )
        session.add(
            MemoryRow(
                agent_id=child.id,
                content="# OPERATING.md\nScale in at most twice.\n\n# USER.md\nOld preference.\n",
                version=4,
            )
        )
        # An account the broker verified is named as the owner sees it.
        verified_account = await BrokerSessionRepository().create(
            session,
            owner_id,
            {"provider": "simulation", "account_id": "verified-" + uuid4().hex, "enabled": True},
            broker_identity={
                "broker": "Gold Broker Ltd",
                "login": "5012345",
                "server": "GoldBroker-Demo",
            },
        )
        verified, _ = await new_agent(
            "Verified",
            role="specialist",
            parent_id=parent.id,
            trading_account_id=verified_account.id,
            trading_symbol="XAUUSDm",
        )
        # A connection changed since the broker verified it: the identity is behind it.
        stale_account = await BrokerSessionRepository().create(
            session,
            owner_id,
            {"provider": "simulation", "account_id": "stale-" + uuid4().hex, "enabled": True},
            broker_identity={
                "broker": "Silver Broker Ltd",
                "login": "7012345",
                "server": "SilverBroker-Live",
            },
        )
        stale_account.version += 1
        stale, _ = await new_agent(
            "Stale",
            role="specialist",
            parent_id=parent.id,
            trading_account_id=stale_account.id,
            trading_symbol="XAGUSD",
        )
        grandchild, _ = await new_agent("Grandchild", role="delegated", parent_id=child.id)
        stray, _ = await new_agent("Stray", role="delegated")
        supervisor, supervisor_thread = await new_agent(
            "Supervisor", role="general", scope_mode="flexible", template="supervisor"
        )
        session.add(
            MemoryRow(
                agent_id=supervisor.id,
                content="# OPERATING.md\n" + SUPERVISOR_LINE + "\nReport at noon.\n",
                version=1,
            )
        )
        session.add(
            SettingRow(
                key=origin_key(owner_id, supervisor.id),
                payload={"template": "supervisor", "report_to": None},
            )
        )

        # Pauses (item 6).
        worker, worker_thread = await new_agent("Worker", role="general", scope_mode="flexible")
        worker.paused = True
        for supervised in (dino, worker.id):
            session.add(
                SupervisionGrantRow(
                    owner_id=owner_id,
                    supervisor_agent_id=supervisor.id,
                    supervised_agent_id=supervised,
                    created_via="owner_message",
                )
            )
        session.add(
            SupervisionGrantRow(
                owner_id=owner_id,
                supervisor_agent_id=lonora,
                supervised_agent_id=worker.id,
                created_via="default",
            )
        )
        agent_hold = await seed.hold(worker.id, "agent", worker.id, "agent", supervisor.id)
        pause_card = await seed.card(
            supervisor.id,
            worker_thread.id,
            "supervision_paused",
            "supervision-hold:" + agent_hold.id,
            {"hold_id": agent_hold.id},
        )
        routine = RoutineRow(
            owner_id=owner_id,
            agent_id=worker.id,
            thread_id=worker_thread.id,
            prompt="check",
            interval_seconds=3600,
            enabled=False,
            next_run_at=now,
        )
        session.add(routine)
        await session.flush()
        asked_hold = await seed.hold(
            worker.id, "routine", routine.id, "owner_message", supervisor.id
        )
        lonora_watch = await seed.watch(
            worker.id, worker_thread.id, enabled=False, state={"code": "watch_paused"}
        )
        lonora_hold = await seed.hold(worker.id, "watch", lonora_watch.id, "agent", lonora)
        held_watch = await seed.watch(
            worker.id,
            worker_thread.id,
            enabled=False,
            state={"code": "watch_paused", "lifecycle": "expired", "lifecycle_reason": "x"},
        )
        watch_hold = await seed.hold(worker.id, "watch", held_watch.id, "agent", supervisor.id)
        routine_held = RoutineRow(
            owner_id=owner_id,
            agent_id=worker.id,
            thread_id=worker_thread.id,
            prompt="report",
            interval_seconds=3600,
            enabled=False,
            next_run_at=now,
        )
        session.add(routine_held)
        await session.flush()
        routine_hold = await seed.hold(
            worker.id, "routine", routine_held.id, "agent", supervisor.id
        )
        lapsed_watch = MarketWatchRow(
            owner_id=owner_id,
            agent_id=worker.id,
            thread_id=worker_thread.id,
            payload={
                "symbol": "XAUUSD",
                "enabled": False,
                "expires_at": (now - timedelta(hours=1)).isoformat(),
            },
            state={"code": "watch_paused"},
        )
        session.add(lapsed_watch)
        await session.flush()
        lapsed_hold = await seed.hold(worker.id, "watch", lapsed_watch.id, "agent", supervisor.id)
        task_watch_hold = await seed.hold(
            running_agent, "watch", task_watch.id, "agent", supervisor.id
        )
        # Item 3 stops this paused management Task first, so its pause is only released.
        paused_task_hold = await seed.hold(
            managers["Paused"][0], "task", managers["Paused"][2], "agent", supervisor.id
        )
        cancelled_watch = await seed.watch(
            worker.id, worker_thread.id, enabled=False, state={"code": "watch_cancelled"}
        )
        cancelled_watch_hold = await seed.hold(
            worker.id, "watch", cancelled_watch.id, "agent", supervisor.id
        )
        ended_task = await seed.task(worker.id, worker_thread.id, str(uuid4()), status="cancelled")
        ended_task_hold = await seed.hold(worker.id, "task", ended_task.id, "agent", supervisor.id)

        # Item 5: a stored card keeps its stored expiry.
        approval = TradeApprovalRow(
            id=str(uuid4()),
            owner_id=owner_id,
            agent_id=dino,
            call_id="stored",
            requests=[],
            status="pending",
            results=[],
            broker_snapshot={},
            expires_at=now + timedelta(minutes=20),
        )
        session.add(approval)

        # Item 7: Dino's journaled order opened one ticket; the owner opened the other.
        tickets = {}
        for name, agent_id in (("dino", dino), ("owner", None)):
            request = TradeRequest(
                account_id=account_id,
                operation_id="open-" + uuid4().hex,
                action="buy",
                symbol="XAUUSD",
                volume=Decimal("0.1"),
            )
            session.add(
                TradingJournalRow(
                    operation_id=request.operation_id,
                    owner_id=owner_id,
                    account_id=account_id,
                    request_hash=request_hash(request.model_dump(mode="json")),
                    request=request.model_dump(mode="json"),
                    status="confirmed",
                    result=TradeResult(
                        operation_id=request.operation_id,
                        status="confirmed",
                        broker_id=name + "-position",
                        details={
                            "position_id": name + "-position",
                            "execution": {"agent_id": agent_id},
                        },
                    ).model_dump(mode="json"),
                )
            )
            tickets[name] = request.operation_id
        await session.flush()
        refs = {
            "general": general.id,
            "unrecorded": unrecorded.id,
            "bounded": bounded.id,
            "bounded_grant": bounded_grant.id,
            "review": review.id,
            "expired": expired.id,
            "expired_grant": expired_grant.id,
            "pending": pending.id,
            "pending_grant": pending_grant.id,
            "revoked": revoked.id,
            "revoked_grant": revoked_grant.id,
            "orphan_grant": orphan_grant.id,
            "grant_card": grant_card.id,
            "stale_card": stale_card.id,
            "stranded": stranded.id,
            "routine_held": routine_held.id,
            "routine_hold": routine_hold.id,
            "lapsed_watch": lapsed_watch.id,
            "lapsed_hold": lapsed_hold.id,
            "task_watch_hold": task_watch_hold.id,
            "paused_task_hold": paused_task_hold.id,
            "wide": wide.id,
            "helper": helper.id,
            "parent": parent.id,
            "child": child.id,
            "child_thread": child_thread.id,
            "verified": verified.id,
            "stale": stale.id,
            "stale_account": stale_account.id,
            "grandchild": grandchild.id,
            "stray": stray.id,
            "supervisor": supervisor.id,
            "supervisor_thread": supervisor_thread.id,
            "worker": worker.id,
            "agent_hold": agent_hold.id,
            "pause_card": pause_card.id,
            "routine": routine.id,
            "asked_hold": asked_hold.id,
            "lonora_hold": lonora_hold.id,
            "lonora_watch": lonora_watch.id,
            "held_watch": held_watch.id,
            "watch_hold": watch_hold.id,
            "cancelled_watch": cancelled_watch.id,
            "cancelled_watch_hold": cancelled_watch_hold.id,
            "ended_task_hold": ended_task_hold.id,
            "approval": approval.id,
            "task_watch": task_watch.id,
            "live_task_watch": live_task_watch.id,
            "owner_task_watch": owner_task_watch.id,
            "owner_task_watch_hold": owner_task_watch_hold.id,
            "held_task_hold": held_task_hold.id,
            **{"task_watch:" + name: row.id for name, row in task_watches.items()},
            "own_watch": own_watch.id,
        }
    async with db.sessions() as session:
        revoked_row = await session.get(AccountAuthorityRow, refs["revoked_grant"])
        assert revoked_row is not None
        revoked_stamp = revoked_row.updated_at
        own_watch_before = await session.get(MarketWatchRow, refs["own_watch"])
        assert own_watch_before is not None
        own_watch_state = (own_watch_before.payload, own_watch_before.state)
        ended_watches: dict[str, tuple[Any, ...]] = {}
        for name in ("Cancelled", "Completing"):
            row = await session.get(MarketWatchRow, refs["task_watch:" + name])
            assert row is not None
            ended_watches[name] = (row.payload, row.state, row.version)
        expiry = approval.expires_at
        lonora_watch_row = await session.get(MarketWatchRow, refs["lonora_watch"])
        assert lonora_watch_row is not None
        lonora_watch_before = (lonora_watch_row.payload, lonora_watch_row.state)
    parent_digest = await digest(db, "SELECT * FROM ln_agents WHERE id = :id", id=refs["parent"])
    cursor = await last_cursor(db)

    await upgrade_from(db, BEFORE_MODE)

    async with db.sessions() as session:
        # Item 1: every agent in Ask, every stored level "Ask me" in the record's own shape.
        for agent in await session.scalars(select(AgentRow).where(AgentRow.owner_id == owner_id)):
            assert agent.trading_mode == "ask", agent.name
            record = await level_of(session, owner_id, agent.id)
            assert record.fallback_level == "supervised", agent.name
        assert (await level_of(session, owner_id, refs["general"])).revision == 1
        assert (await level_of(session, owner_id, refs["unrecorded"])).revision == 1

        # Item 3: every grant that was active or pending is revoked; the rest keep theirs.
        for name in ("bounded_grant", "expired_grant", "pending_grant", "orphan_grant"):
            row = await session.get(AccountAuthorityRow, refs[name], populate_existing=True)
            assert row is not None and row.status == "revoked", name
        row = await session.get(AccountAuthorityRow, refs["revoked_grant"])
        assert row is not None and row.updated_at == revoked_stamp
        expected = {
            "Running": ("cancelled", "cancelled"),
            "Failed": ("cancelled", "cancelled"),
            "Completing": ("completed", "completed"),
            "Cancelled": ("cancelled", "cancelled"),
            "Leased": ("cancelled", "cancelled"),
            "Paused": ("cancelled", "cancelled"),
            "Held": ("cancelled", "cancelled"),
        }
        for name, (_, _, task_id, run_id, _) in managers.items():
            ticket = await session.get(TicketRow, task_id, populate_existing=True)
            assert ticket is not None
            task = ticket.state["task"]
            assert (task["status"], ticket.payload["status"]) == expected[name], (name, task)
            assert task["control_requested"] is None, name
            if name != "Cancelled":
                assert ticket.version > 1, name
            run = await session.get(RunRow, run_id, populate_existing=True)
            assert run is not None
            if name == "Leased":
                # A worker holds it: it reads the stopped Task at its next checkpoint.
                assert run.status == "leased" and run.lease_owner == "worker-1", run.status
                continue
            waiting = name in {"Running", "Completing", "Paused", "Held"}
            assert run.status == ("cancelled" if waiting else "completed"), name
            if waiting:
                assert run.lease_owner is None and run.error_code == "mandate_migration"
        for run_id in unrelated_runs:
            run = await session.get(RunRow, run_id, populate_existing=True)
            assert run is not None and run.status in {"waiting_takeover", "queued"}, run_id
        approval = await session.get(TradeApprovalRow, refs["stranded"], populate_existing=True)
        assert approval is not None
        assert approval.status == "cancelled", "a card of a cancelled Run is not left pending"
        # Ending the Task never cancels its watches: each stays, without the Task (4.5.3).
        for name in ("live_task_watch", "task_watch", "owner_task_watch"):
            watch = await session.get(MarketWatchRow, refs[name], populate_existing=True)
            assert watch is not None and watch.version > 1, name
            assert not {"task_id", "task_run_id"} & set(watch.state), (name, watch.state)
        for name in ("Failed", "Leased", "Held", "Paused"):
            watch = await session.get(
                MarketWatchRow, refs["task_watch:" + name], populate_existing=True
            )
            assert watch is not None and watch.version > 1, name
            assert not {"task_id", "task_run_id"} & set(watch.state), (name, watch.state)
        for name in ("live_task_watch", "task_watch:Failed", "task_watch:Leased"):
            watch = await session.get(MarketWatchRow, refs[name], populate_existing=True)
            assert watch is not None and watch.payload["enabled"] is True, name
            assert watch.state == {"lifecycle": "pending"}, (name, watch.state)
        # A Task the owner had already ended keeps its settled watches exactly as they were.
        for name, before_watch in ended_watches.items():
            watch = await session.get(
                MarketWatchRow, refs["task_watch:" + name], populate_existing=True
            )
            assert watch is not None
            assert (watch.payload, watch.state, watch.version) == before_watch, name
        # The owner's pause of a Task holds its watches: each is paused by the owner, who
        # alone lifts it (4.7.2, 14.3.18.6).
        watch = await session.get(MarketWatchRow, refs["task_watch:Held"], populate_existing=True)
        assert watch is not None and watch.payload["enabled"] is False
        assert watch.state == {"lifecycle": "pending", "code": "watch_paused"}, watch.state
        watch_hold = await session.scalar(
            select(SupervisionHoldRow).where(
                SupervisionHoldRow.target_kind == "watch",
                SupervisionHoldRow.target_id == refs["task_watch:Held"],
                SupervisionHoldRow.released_at.is_(None),
            )
        )
        assert watch_hold is not None and watch_hold.source == "owner", watch_hold
        assert watch_hold.holder_agent_id is None and watch_hold.agent_id == managers["Held"][0]
        watch = await session.get(MarketWatchRow, refs["own_watch"], populate_existing=True)
        assert watch is not None and (watch.payload, watch.state) == own_watch_state
        review_run = await session.get(RunRow, refs["review"], populate_existing=True)
        assert review_run is not None and review_run.status == "cancelled"
        card = await session.get(OwnerActionRow, refs["grant_card"], populate_existing=True)
        assert card is not None
        assert card.status == "superseded", card.status
        card = await session.get(OwnerActionRow, refs["stale_card"], populate_existing=True)
        assert card is not None
        assert card.status == "expired", "a card past its expiry is settled as expired"

        # Item 2: a card for each agent whose grant was active and unexpired, and no other.
        for name in ("Running", "Failed", "Completing", "Cancelled"):
            assert len(await mandate_cards(session, managers[name][0])) == 1, name
        for name in ("general", "expired", "pending", "revoked"):
            assert not await mandate_cards(session, refs[name]), name
        assert not await session.scalar(
            select(OwnerActionRow).where(
                OwnerActionRow.kind == "trading_mode",
                OwnerActionRow.subject.not_in(
                    [
                        "trading_mode:" + agent
                        for agent in (
                            ids["lonora"],
                            ids["dino"],
                            refs["bounded"],
                            refs["wide"],
                            *(manager[0] for manager in managers.values()),
                        )
                    ]
                ),
            )
        )
        bounded_card = (await mandate_cards(session, refs["bounded"]))[0]
        assert bounded_card.payload["previous_grants"] == [
            {
                "account_id": account_id,
                "full_delegation": False,
                "symbol_scope": "selected",
                "symbols": ["XAUUSD", "EURUSD"],
            }
        ], bounded_card.payload
        # A Custom grant on the whole account is not Full delegation, and is named by scope.
        wide_card = (await mandate_cards(session, refs["wide"]))[0]
        assert wide_card.payload["previous_grants"][0]["full_delegation"] is False
        assert wide_card.payload["previous_grants"][0]["symbol_scope"] == "account"
        for agent in (ids["lonora"], ids["dino"]):
            assert len(await mandate_cards(session, agent)) == 1

        # Item 4: ordinary team agents; the binding is in the method, the parent is gone.
        for name in ("helper", "child", "verified", "stale", "grandchild", "stray", "supervisor"):
            agent = await session.get(AgentRow, refs[name], populate_existing=True)
            assert agent is not None
            assert (agent.role, agent.scope_mode, agent.parent_id) == ("general", "flexible", None)
            assert (agent.trading_account_id, agent.trading_symbol) == (None, None), name
            assert agent.scope_revision == 1, name
            assert agent.template != "supervisor", name
            assert_market_binding(agent)
            await require_financial_agent(session, owner_id, agent.id)
        # The account is named as the owner sees it, else by its provider and number: no
        # internal id and no JSON quoting in the method the owner reads (17).
        memory = await session.get(MemoryRow, refs["child"], populate_existing=True)
        assert memory is not None and memory.version == 5
        account = await session.get(BrokerSessionRow, account_id)
        assert account is not None
        note = (
            "Assigned market, moved here from your former fixed assignment: EURUSD on the"
            " simulation account " + account.payload["account_id"] + ". Work on this symbol on"
            " this account unless the owner or Lonora assigns another."
        )
        assert memory.content == (
            "# OPERATING.md\nScale in at most twice.\n" + note + "\n\n# USER.md\nOld preference.\n"
        ), memory.content
        assert account_id not in memory.content and '"' not in memory.content
        memory = await session.get(MemoryRow, refs["verified"], populate_existing=True)
        assert memory is not None and memory.version == 1
        assert memory.content == (
            "# OPERATING.md\nAssigned market, moved here from your former fixed assignment:"
            " XAUUSDm on the account Gold Broker Ltd · 5012345 · GoldBroker-Demo. Work on this"
            " symbol on this account unless the owner or Lonora assigns another.\n"
        ), memory.content
        # Behind the connection, the broker's identity names nothing (the live card shows
        # no label then): the account is named by its provider and number.
        stale_account = await session.get(BrokerSessionRow, refs["stale_account"])
        assert stale_account is not None
        assert account_facts(stale_account, stale_account.id)["label"] is None
        memory = await session.get(MemoryRow, refs["stale"], populate_existing=True)
        assert memory is not None and memory.version == 1
        assert memory.content == (
            "# OPERATING.md\nAssigned market, moved here from your former fixed assignment:"
            " XAGUSD on the simulation account " + stale_account.payload["account_id"] + "."
            " Work on this symbol on this account unless the owner or Lonora assigns another.\n"
        ), memory.content
        revision_row = await session.scalar(
            select(MemoryRevisionRow).where(MemoryRevisionRow.agent_id == refs["child"])
        )
        assert revision_row is not None and revision_row.author == "system"
        assert revision_row.version == 5 and note in revision_row.content
        assert "USER.md" not in revision_row.content
        memory = await session.get(MemoryRow, refs["supervisor"], populate_existing=True)
        assert memory is not None and SUPERVISOR_LINE not in memory.content
        assert "Report at noon." in memory.content and memory.version == 2
        origin = await session.get(SettingRow, origin_key(owner_id, refs["supervisor"]))
        assert origin is not None
        assert origin.payload["template"] == "general", origin.payload
        grants = {
            (row.supervisor_agent_id, row.supervised_agent_id): row.revoked_at
            for row in await session.scalars(
                select(SupervisionGrantRow).execution_options(populate_existing=True)
            )
        }
        assert grants[(refs["supervisor"], ids["dino"])] is not None
        assert grants[(refs["supervisor"], refs["worker"])] is not None
        assert grants[(ids["lonora"], ids["dino"])] is None
        assert grants[(ids["lonora"], refs["worker"])] is None

        # Item 6: a supervisor's own pauses end and the work resumes; pauses the owner
        # asked for or holds, and Lonora's, stay.

        async def hold(name: str) -> SupervisionHoldRow:
            row = await session.get(SupervisionHoldRow, refs[name], populate_existing=True)
            assert row is not None
            return row

        for name in (
            "agent_hold",
            "watch_hold",
            "cancelled_watch_hold",
            "ended_task_hold",
            "routine_hold",
            "lapsed_hold",
            "task_watch_hold",
            "paused_task_hold",
        ):
            row = await hold(name)
            assert row.released_at is not None and row.released_by == "owner", name
        worker = await session.get(AgentRow, refs["worker"], populate_existing=True)
        assert worker is not None and worker.paused is False
        card = await session.get(OwnerActionRow, refs["pause_card"], populate_existing=True)
        assert card is not None and card.status == "superseded"
        watch = await session.get(MarketWatchRow, refs["held_watch"], populate_existing=True)
        assert watch is not None
        assert watch.payload["enabled"] is True, watch.payload
        assert "code" not in watch.state and watch.state.get("lifecycle") == "pending"
        watch = await session.get(MarketWatchRow, refs["cancelled_watch"], populate_existing=True)
        assert watch is not None and watch.payload["enabled"] is False
        routine_row = await session.get(RoutineRow, refs["routine_held"], populate_existing=True)
        assert routine_row is not None and routine_row.enabled is True
        watch = await session.get(MarketWatchRow, refs["lapsed_watch"], populate_existing=True)
        assert watch is not None and watch.payload["enabled"] is False, "past its expiry"
        # The supervisor's pause of a Task watch ends, and the watch, now the agent's
        # own, resumes.
        watch = await session.get(MarketWatchRow, refs["task_watch"], populate_existing=True)
        assert watch is not None and watch.payload["enabled"] is True, "resumed"
        assert "code" not in watch.state, watch.state
        assert (await hold("held_task_hold")).released_at is None, "the owner's pause stays"
        # A supervisor's pause of a whole Task ends for its watch too.
        watch = await session.get(MarketWatchRow, refs["task_watch:Paused"], populate_existing=True)
        assert watch is not None and watch.payload["enabled"] is True, "resumed"
        assert "code" not in watch.state and "task_id" not in watch.state, watch.state
        # The owner's pause of a Task watch stays, and the owner can lift it afterwards.
        owner_hold = await hold("owner_task_watch_hold")
        assert owner_hold.released_at is None and owner_hold.source == "owner"
        watch = await session.get(MarketWatchRow, refs["owner_task_watch"], populate_existing=True)
        assert watch is not None and watch.payload["enabled"] is False
        assert watch.state["code"] == "watch_paused", watch.state
        asked = await hold("asked_hold")
        assert asked.released_at is None and asked.source == "owner"
        routine_row = await session.get(RoutineRow, refs["routine"], populate_existing=True)
        assert routine_row is not None and routine_row.enabled is False
        assert (await hold("lonora_hold")).released_at is None
        watch = await session.get(MarketWatchRow, refs["lonora_watch"], populate_existing=True)
        assert watch is not None and (watch.payload, watch.state) == lonora_watch_before

        # Item 5: the stored expiry stays.
        stored = await session.get(TradeApprovalRow, refs["approval"], populate_existing=True)
        assert stored is not None and stored.status == "pending" and stored.expires_at == expiry

        # Item 7: positions belong to whoever's journaled order opened them.
        for name, owner in (("dino", ids["dino"]), ("owner", None)):
            close = TradeRequest(
                account_id=account_id,
                operation_id="close-" + uuid4().hex,
                action="close_position",
                symbol="XAUUSD",
                position_id=name + "-position",
            )
            position = Position(
                id=name + "-position",
                symbol="XAUUSD",
                side="buy",
                volume=Decimal("0.1"),
                open_price=Decimal("2000"),
            )
            assert await ticket_agent(session, owner_id, close, position) == owner, name
    assert await digest(db, "SELECT * FROM ln_agents WHERE id = :id", id=refs["parent"]) == (
        parent_digest
    ), "a root agent's own binding is not item 4"
    assert len(await events_since(db, cursor, "task.updated")) == 6
    approvals = await events_since(db, cursor, "trading.approval.updated")
    assert [event.payload["id"] for event in approvals] == [refs["stranded"]]
    assert approvals[0].payload["status"] == "cancelled"
    # Each revoked supervision grant is recorded for both of its agents.
    assert len(await events_since(db, cursor, "supervision.revoked")) == 4
    assert len(await events_since(db, cursor, "memory.updated")) == 4
    # Each agent flattened (item 4) or unpaused (item 6) is shown with the live payload.
    updated = await events_since(db, cursor, "agent.updated")
    async with db.sessions() as session:
        shown_agents: dict[str, Any] = {}
        for name in (
            "helper",
            "child",
            "verified",
            "stale",
            "grandchild",
            "stray",
            "supervisor",
            "worker",
        ):
            agent = await session.get(AgentRow, refs[name])
            assert agent is not None
            shown_agents[agent.id] = agent_data(agent)
    assert len(updated) == len(shown_agents), [event.agent_id for event in updated]
    assert {event.agent_id: event.payload for event in updated} == shown_agents, updated
    kept = {
        event.payload["id"] for event in await events_since(db, cursor, "market_watches.updated")
    }
    assert {refs["live_task_watch"], refs["owner_task_watch"]} <= kept, kept
    # The owner's Resume on the kept pause works: the watch no longer names an ended Task.
    async with db.sessions() as session, session.begin():
        assert await owner_resumes(session, owner_id, refs["owner_task_watch_hold"])
        held = await session.scalar(
            select(SupervisionHoldRow.id).where(
                SupervisionHoldRow.target_id == refs["task_watch:Held"],
                SupervisionHoldRow.released_at.is_(None),
            )
        )
        assert held is not None
        assert await owner_resumes(session, owner_id, held)
    async with db.sessions() as session:
        for name in ("owner_task_watch", "task_watch:Held"):
            watch = await session.get(MarketWatchRow, refs[name])
            assert watch is not None and watch.payload["enabled"] is True, name
    print(
        "PASS the general cases: every agent in Ask at 'Ask me'; active, expired, pending and"
        " orphaned grants revoked, their Tasks stopped (failed→cancelled, complete→completed),"
        " the Task's watches kept as the agent's own (the owner's pause on one stays and"
        " lifts), its Run and activation review cancelled; cards only for"
        " active unexpired grants; delegated, child and supervisor agents flattened with their"
        " market in OPERATING.md under the account's own name (its provider and number when"
        " the broker's identity is behind the connection); a"
        " supervisor's own pauses ended with the work resumed, the owner's and Lonora's kept;"
        " each flattened or unpaused agent shown with agent.updated; stored approval expiry"
        " and journal attribution unchanged"
    )


async def dev_path(db: Database, ids: dict[str, str]) -> None:
    """Pass 3: a database already at 0061, with an agent in Full and older Mandate cards."""
    owner_id = ids["owner"]
    async with db.sessions() as session, session.begin():
        seed = Seed(session, owner_id, ids["account"])
        seed.device_id = ids["device"]
        late = await seed.agent("Late", role="specialist", scope_mode="flexible")
        late_thread = await seed.conversation(late.id)
        await seed.grant(late.id, late_thread.id)
        await set_trading_mode(session, owner_id, late.id, "full", by="owner_tap")
        own = await seed.card(
            late.id,
            late_thread.id,
            "trading_mode",
            "trading_mode:" + late.id,
            {"agent_id": late.id},
        )
        shown = await seed.card(
            ids["lonora"],
            ids["lonora_thread"],
            "trading_mode",
            "trading_mode:" + late.id,
            {"agent_id": late.id},
        )
        refs = {"late": late.id, "own": own.id, "shown": shown.id}
    cursor = await last_cursor(db)

    await upgrade_from(db, BEFORE)

    async with db.sessions() as session:
        assert await trading_mode(session, owner_id, refs["late"]) == "ask"
        new_id = migration_card_id(owner_id, refs["late"])
        for name in ("own", "shown"):
            card = await session.get(OwnerActionRow, refs[name], populate_existing=True)
            assert card is not None and card.status == "superseded", name
            assert card.superseded_by == new_id, name
        new = await session.get(OwnerActionRow, new_id)
        assert new is not None and new.status == "pending" and new.agent_id == ids["lonora"]
    changed = await events_since(db, cursor, "agent.trading_mode.updated")
    assert [event.payload for event in changed] == [
        {"agent_id": refs["late"], "trading_mode": "ask", "by": "system"}
    ], changed
    print(
        "PASS a database already at 0061: an agent in Full becomes Ask with the mode event, and"
        " the migration's Mandate card replaces the older pending ones for that agent"
    )


def resumed_shape(ticket: TicketRow, run: RunRow) -> tuple[Any, ...]:
    """What a resume leaves on a Task and its Run, without the ids a twin has of its own."""
    task: dict[str, Any] = {**ticket.state["task"], "origin_thread_id": None}
    if task.get("failure"):
        task["failure"] = {**task["failure"], "run_id": None}
    return (
        task,
        ticket.payload,
        ticket.version,
        run.status,
        run.lease_expires_at,
        run.execution_state,
    )


async def task_guard(db: Database, ids: dict[str, str]) -> None:
    """Pass 4: a supervisor's pause on a Task ends like any other (14.3.18.6). The Task
    resumes exactly as the live resume (control_task) resumes the same Task no one holds;
    a Task the live retry resumes (resume_failure) is released as it is, and its agent is
    woken once to resume it."""
    owner_id = ids["owner"]
    now = utcnow()
    question = {"id": "question-1", "kind": "owner_attention", "status": "pending"}
    shapes: dict[str, tuple[str, str, str]] = {}
    twins: dict[str, tuple[str, str]] = {}
    async with db.sessions() as session, session.begin():
        seed = Seed(session, owner_id, ids["account"])
        seed.device_id = ids["device"]
        held = await seed.agent("Held", role="general", scope_mode="flexible")
        boss = await seed.agent("Boss", role="general", scope_mode="flexible")
        trusted = await seed.agent("Trusted", role="specialist", scope_mode="flexible")
        trusted_thread = await seed.conversation(trusted.id)
        grant = await seed.grant(trusted.id, trusted_thread.id)
        await set_trading_mode(session, owner_id, trusted.id, "full", by="owner_tap")
        refs = {"held": held.id, "trusted": trusted.id, "grant": grant.id}

        async def shape(
            name: str, status: str, control: str | None, run_status: str, agent_id: str = held.id
        ) -> tuple[TicketRow, RunRow]:
            thread = await seed.conversation(agent_id)
            working = run_status == "running"
            attention = name == "attention"
            run = RunRow(
                thread_id=thread.id,
                agent_id=agent_id,
                trigger="tickets",
                status=run_status,
                lease_owner="worker-1" if working else None,
                lease_fence=1,
                # A lease left on a Run held for the owner's question ends on resume.
                lease_expires_at=now + timedelta(minutes=5) if working or attention else None,
                execution_state={"pending_input_request": question, "input_requests": [question]}
                if attention
                else {},
            )
            session.add(run)
            await session.flush()
            task = await seed.task(
                agent_id, thread.id, str(uuid4()), status=status, control_requested=control
            )
            failure = TaskFailure(
                run_id=run.id, lease_fence=1, code="broker_down", attempt=1, recovery="owner"
            ).model_dump(mode="json")
            changed = {
                # It failed once, the owner resumed it, and later it was paused normally.
                "stale": {"failure": failure},
                "attention": {"waiting_reason": "owner_attention"},
                "retry": {"phase": "retry_paused", "failure": failure},
            }.get(name)
            if changed:
                task.state = {"task": {**task.state["task"], **changed}}
            return task, run

        for name, status, control, run_status in (
            ("asked", "running", "pause", "running"),  # a worker holds its Run
            ("paused", "paused", None, "waiting_takeover"),
            ("stale", "paused", None, "waiting_takeover"),  # with an older failure
            ("attention", "paused", None, "waiting_takeover"),  # holds the owner's question
            ("retry", "paused", None, "failed"),  # paused after a failure
        ):
            task, run = await shape(name, status, control, run_status)
            if name == "retry":
                # A newer Run of the agent waits in that conversation: not the failed work.
                waiting = RunRow(
                    thread_id=task.thread_id,
                    agent_id=held.id,
                    status="waiting_takeover",
                    created_at=now + timedelta(seconds=1),
                )
                session.add(waiting)
                await session.flush()
                refs["waiting"] = waiting.id
            hold = await seed.hold(held.id, "task", task.id, "agent", boss.id)
            shapes[name] = (task.id, run.id, hold.id)
            if name in {"paused", "stale", "attention"}:
                # The same Task no one holds: the live resume resumes it after the update.
                twin, twin_run = await shape(name, status, control, run_status)
                twins[name] = (twin.id, twin_run.id)
        # The same Task of an agent the owner paused: create_run wakes no paused agent.
        resting = await seed.agent("Resting", role="general", scope_mode="flexible", paused=True)
        await seed.hold(resting.id, "agent", resting.id, "owner", None)
        rest_task, _ = await shape("retry", "paused", None, "failed", resting.id)
        rest_hold = await seed.hold(resting.id, "task", rest_task.id, "agent", boss.id)
        refs.update(rest_task=rest_task.id, rest_hold=rest_hold.id)
    before: dict[str, tuple[Any, ...]] = {}
    async with db.sessions() as session:
        for name, (task_id, run_id, _) in shapes.items():
            ticket, run = await session.get(TicketRow, task_id), await session.get(RunRow, run_id)
            assert ticket is not None and run is not None
            before[name] = (ticket.state, ticket.payload, ticket.version, run.status)
            before[name] += (run.execution_state, run.lease_owner)
    cursor = await last_cursor(db)

    await upgrade_from(db, BEFORE)

    assert await revision(db) == REVISION, "the update completes"
    resumed = await events_since(db, cursor, "task.updated")
    queued = await events_since(db, cursor, "run.queued")
    tasks: dict[str, TicketRow] = {}
    runs: dict[str, RunRow] = {}
    async with db.sessions() as session:
        assert await trading_mode(session, owner_id, refs["trusted"]) == "ask"
        row = await session.get(AccountAuthorityRow, refs["grant"])
        assert row is not None and row.status == "revoked"
        for name, (task_id, run_id, hold_id) in shapes.items():
            hold = await session.get(SupervisionHoldRow, hold_id)
            assert hold is not None and hold.released_at is not None, name
            assert hold.released_by == "owner", name
            ticket, run = await session.get(TicketRow, task_id), await session.get(RunRow, run_id)
            assert ticket is not None and run is not None
            tasks[name], runs[name] = ticket, run
        waiting_run = await session.get(RunRow, refs["waiting"])
        assert waiting_run is not None and waiting_run.status == "waiting_takeover"
        retry_thread = await session.get(ThreadRow, tasks["retry"].thread_id)
        assert retry_thread is not None
        wakes = list(
            await session.scalars(
                select(RunRow).where(
                    RunRow.thread_id == retry_thread.id,
                    RunRow.id.not_in([runs["retry"].id, refs["waiting"]]),
                )
            )
        )
    # A pause asked of a Task a worker holds is withdrawn: the Run reads it at its next
    # checkpoint and goes on working.
    task = tasks["asked"].state["task"]
    assert (task["status"], task["control_requested"]) == ("running", None), task
    assert tasks["asked"].version == before["asked"][2] + 1
    assert (runs["asked"].status, runs["asked"].lease_owner) == ("running", "worker-1")
    # A paused Task waiting for takeover is queued again, as the owner's resume does.
    task = tasks["paused"].state["task"]
    assert (task["status"], task["phase"], task["control_requested"]) == (
        "queued",
        "queued",
        None,
    ), task
    assert tasks["paused"].payload["status"] == "todo"
    assert tasks["paused"].version == before["paused"][2] + 1
    assert runs["paused"].status == "queued"
    # An older failure does not make a Task paused normally the retry's: only a failure
    # still being retried is (live retry_control), so it is queued like any paused Task.
    task = tasks["stale"].state["task"]
    assert (task["status"], task["phase"]) == ("queued", "queued"), task
    assert task["failure"] == before["stale"][0]["task"]["failure"]
    assert runs["stale"].status == "queued"
    # Paused while its Run held the owner's question, it resumes the work, not the
    # question: the question is cancelled and the Run queued (release_attention).
    task = tasks["attention"].state["task"]
    assert (task["status"], task["phase"], task["waiting_reason"]) == ("queued", "queued", None)
    assert (runs["attention"].status, runs["attention"].lease_expires_at) == ("queued", None)
    assert runs["attention"].execution_state == {
        "input_requests": [{**question, "status": "cancelled"}],
        ATTENTION_RESUMED: {"action": "resume", "question_id": question["id"]},
    }, runs["attention"].execution_state
    assert {event.payload["id"]: event.payload for event in resumed} == {
        tasks[name].id: {
            "id": tasks[name].id,
            "version": before[name][2] + 1,
            "status": tasks[name].state["task"]["status"],
            "waiting_reason": None,
        }
        for name in ("asked", "paused", "stale", "attention")
    }, [event.payload for event in resumed]
    assert len(resumed) == 4
    # Exactly as the live resume resumes the same Task no one holds.
    async with db.sessions() as session, session.begin():
        for twin_id, _ in twins.values():
            twin = await get_task(session, owner_id, twin_id)
            await control_task(
                session,
                owner_id,
                TaskControl(task_id=twin_id, action="resume", expected_version=twin.version),
            )
    async with db.sessions() as session:
        for name, (twin_id, twin_run_id) in twins.items():
            twin = await session.get(TicketRow, twin_id)
            twin_run = await session.get(RunRow, twin_run_id)
            assert twin is not None and twin_run is not None
            assert resumed_shape(twin, twin_run) == resumed_shape(tasks[name], runs[name]), name
    # Paused after a failure, it is the live retry's to resume (resume_failure, which reads
    # the journal): released as it is, its Runs as they were...
    after = (tasks["retry"].state, tasks["retry"].payload, tasks["retry"].version)
    after += (runs["retry"].status, runs["retry"].execution_state, runs["retry"].lease_owner)
    assert after == before["retry"]
    # ...and its agent is woken once in the Task's thread, with fixed server text read as
    # the server's own, to resume it itself.
    prompt = (
        "Your Task (task_id=" + tasks["retry"].id + ") is no longer held: the pause a"
        " supervising agent put on it has ended, and nothing else about it changed. Read it"
        " with task_inspect; if the work should go on, resume it with task_control (action"
        " resume), otherwise tell the owner in one line why not."
    )
    assert len(wakes) == 1, [(wake.trigger, wake.prompt) for wake in wakes]
    wake = wakes[0]
    assert (wake.agent_id, wake.status, wake.parent_run_id) == (refs["held"], "queued", None)
    assert wake.input_seq == retry_thread.next_seq - 1
    assert wake_context(wake) == "<wake trigger='owner_card'>\n" + prompt + "\n</wake>"
    assert [(event.run_id, event.thread_id, event.agent_id, event.payload) for event in queued] == [
        (wake.id, retry_thread.id, refs["held"], {"run": run_data(wake)})
    ], [event.payload for event in queued]
    # An agent the owner paused is not woken: its Task, released, waits for it as it is.
    async with db.sessions() as session:
        hold = await session.get(SupervisionHoldRow, refs["rest_hold"])
        assert hold is not None and hold.released_at is not None
        rest_task = await session.get(TicketRow, refs["rest_task"])
        assert rest_task is not None and rest_task.version == 1
        assert rest_task.state["task"]["phase"] == "retry_paused"
        count = select(func.count()).select_from(RunRow)
        assert await session.scalar(count.where(RunRow.thread_id == rest_task.thread_id)) == 1
    # Once: the same update over the same pause wakes no one twice (a stable id).
    async with db.sessions() as session, session.begin():
        hold = await session.get(SupervisionHoldRow, shapes["retry"][2])
        assert hold is not None
        hold.released_at, hold.released_by = None, None
    cursor = await last_cursor(db)
    await upgrade_from(db, BEFORE)
    async with db.sessions() as session:
        hold = await session.get(SupervisionHoldRow, shapes["retry"][2])
        assert hold is not None and hold.released_at is not None
        count = select(func.count()).select_from(RunRow)
        assert await session.scalar(count.where(RunRow.thread_id == retry_thread.id)) == 3
    assert await events_since(db, cursor, "run.queued") == []
    # Released, the Task is the agent's own to resume, as the wake says.
    async with db.sessions() as session, session.begin():
        resumed_task = await control_task(
            session,
            owner_id,
            TaskControl(
                task_id=tasks["retry"].id, action="resume", expected_version=tasks["retry"].version
            ),
            agent_id=refs["held"],
        )
        assert resumed_task.state["task"]["status"] == "queued"
    print(
        "PASS a supervisor's pause on a Task ends and the update completes: a pause asked of"
        " a Task a worker holds is withdrawn; a paused Task waiting for takeover, one with an"
        " older failure and one held for the owner's question resume exactly as the live"
        " resume does; a Task paused after a failure is released as it is and its agent is"
        " woken once, with fixed server text, to resume it (an agent the owner paused is not)"
    )


async def main() -> None:
    db = database()
    async with db.sessions() as session:
        assert await session.scalar(select(OwnerRow)) is None, "run on a fresh database"
    ids: dict[str, str] = {}
    await production_shape(db, ids)
    await general_cases(db, ids)
    await dev_path(db, ids)
    await task_guard(db, ids)
    # The downgrade restores nothing and never raises; a second upgrade adds nothing.
    await db.engine.dispose()
    alembic("downgrade", BEFORE_MODE)
    alembic("upgrade", "head")
    async with db.sessions() as session:
        active = await session.scalar(
            select(func.count())
            .select_from(AccountAuthorityRow)
            .where(AccountAuthorityRow.status.in_(["pending", "active"]))
        )
        assert active == 0
        for agent in (ids["lonora"], ids["dino"]):
            assert len(await mandate_cards(session, agent)) == 1
    await db.engine.dispose()
    print("PASS the downgrade restores no authority and the upgrade runs again cleanly")


if __name__ == "__main__":
    asyncio.run(main())
