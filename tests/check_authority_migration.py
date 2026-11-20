"""Migration 0128: existing grants, levels, team roles and pauses move to the mode (14.3.18).

On a disposable PostgreSQL at head, each pass steps down to 0127, seeds rows the way the
release before 0128 left them, and steps up again:

1. Production's shape (3 agents in Ask, 3 revoked grants, 3 confirmed grant cards, no
   position, 3 owner-held pauses): every grant card is deleted, with its event; no Mandate
   card is raised, no Run is cancelled, the agents stay in Ask and the owner's pauses stay.
2. The other shapes: an active grant (its Task stopped, its waiting Run and Trade Approval
   cancelled, its watch kept in the agent's conversation, one Mandate card naming the
   grant), a Full delegation whose paused Task's watch stays paused under the owner's
   hold, a pending grant, an activation review, an agent in Full with its own Task, "No
   trading" stored and by default, delegated, child and supervisor agents, a team agent's
   pause next to the owner's and Lonora's, and an ``ambiguous`` operation, which then
   reconciles without a resend (14.3.9).
3. A second upgrade over a grant signed again in between: no second Mandate card, and an
   agent bound since gets its method line in the owner's language, English now.
"""

import asyncio
import json
import subprocess
import sys
from datetime import timedelta
from decimal import Decimal
from typing import Any, cast
from uuid import uuid4

from check_trading import ScriptedBroker, ScriptedManager, database
from lonora_adapters.brokers.base import BrokerManager
from lonora_contracts.domain import AgentCreate, utcnow
from lonora_contracts.tasks import TaskCreate
from lonora_contracts.trading import TradeRequest, TradeResult
from lonora_db.agent_permissions import permission_key
from lonora_db.agents import create_agent
from lonora_db.broker_sessions import BrokerSessionRepository
from lonora_db.client import Database
from lonora_db.management_task import ensure_management_task, live_management_task
from lonora_db.owner_actions import owner_action_data, payload_hash
from lonora_db.personal_agent import ensure_personal_agent
from lonora_db.schema import (
    AccountAuthorityRow,
    AgentRow,
    EventRow,
    MarketWatchRow,
    MemoryRow,
    OwnerActionRow,
    OwnerRow,
    RoutineRow,
    RunRow,
    SettingRow,
    SupervisionHoldRow,
    TicketRow,
    TradeApprovalRow,
    TradingJournalRow,
)
from lonora_db.tasks import create_task, save_task, task_state
from lonora_db.threads import conversation_thread
from lonora_session.idempotency import stable_id
from lonora_trading.execution import ExecutionService
from lonora_trading.idempotency import trade_fingerprint
from lonora_trading.reconciliation import reconcile_ambiguous
from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

ALEMBIC = [sys.executable, "-m", "alembic", "-c", "packages/db/alembic.ini"]
REVISION = "0128_authority_migration"
BEFORE = "0127_no_supervision_grants"
SUPERVISOR_LINE = (
    "Supervisor: you review the work of the agents the owner named and message them;"
    " you never trade for them."
)


def alembic(*arguments: str) -> str:
    done = subprocess.run([*ALEMBIC, *arguments], check=True, capture_output=True, text=True)
    return done.stdout


async def upgrade(db: Database) -> int:
    """The newest event cursor before the step up."""
    async with db.sessions() as session:
        cursor = int(await session.scalar(select(func.max(EventRow.cursor))) or 0)
    await db.engine.dispose()
    alembic("upgrade", "head")
    return cursor


async def step_down(db: Database) -> None:
    await db.engine.dispose()
    alembic("downgrade", BEFORE)


async def events(db: Database, after: int, kind: str) -> list[EventRow]:
    async with db.sessions() as session:
        return list(
            await session.scalars(
                select(EventRow).where(EventRow.cursor > after, EventRow.kind == kind)
            )
        )


async def runs_digest(db: Database) -> str:
    async with db.sessions() as session:
        return str(
            await session.scalar(
                text("SELECT md5(string_agg(r::text, ',' ORDER BY id)) FROM ln_runs r")
            )
        )


async def mandate_cards(session: AsyncSession, agent_id: str) -> list[OwnerActionRow]:
    return list(
        await session.scalars(
            select(OwnerActionRow).where(
                OwnerActionRow.kind == "trading_mode",
                OwnerActionRow.subject == "trading_mode:" + agent_id,
            )
        )
    )


async def level(session: AsyncSession, owner_id: str, agent_id: str) -> dict[str, Any] | None:
    row = await session.get(SettingRow, permission_key(owner_id, agent_id), populate_existing=True)
    return row.payload if row else None


def grant(owner_id: str, agent_id: str, account_id: str, thread_id: str, **fields: Any):
    envelope = fields.pop("envelope", {"symbol_scope": "selected", "symbols": ["XAUUSD"]})
    return AccountAuthorityRow(
        owner_id=owner_id,
        agent_id=agent_id,
        thread_id=thread_id,
        account_id=account_id,
        envelope={"account_id": account_id, **envelope},
        envelope_hash="hash",
        activation_expires_at=utcnow() + timedelta(minutes=5),
        **fields,
    )


def grant_card(owner_id: str, agent_id: str, thread_id: str, status: str) -> OwnerActionRow:
    return OwnerActionRow(
        owner_id=owner_id,
        agent_id=agent_id,
        thread_id=thread_id,
        source="agent",
        kind="grant_authority",
        subject="grant:" + agent_id + ":" + uuid4().hex,
        payload={"agent_id": agent_id},
        payload_hash=uuid4().hex,
        status=status,
        expires_at=utcnow() + timedelta(days=1),
    )


def watch(owner_id: str, agent_id: str, thread_id: str, **state: Any) -> MarketWatchRow:
    return MarketWatchRow(
        owner_id=owner_id,
        agent_id=agent_id,
        thread_id=thread_id,
        payload={
            "kind": "price",
            "symbol": "XAUUSD",
            "condition": "above",
            "level": "1",
            "prompt": "level",
            "enabled": True,
        },
        state=state,
    )


async def production_shape(db: Database, owner_id: str, account_id: str) -> None:
    async with db.sessions() as session, session.begin():
        lonora = await ensure_personal_agent(session, owner_id)
        agents = [lonora] + [
            await create_agent(session, owner_id, AgentCreate(name="Agent " + uuid4().hex[:6]))
            for _ in range(2)
        ]
        for agent in agents:
            thread = await conversation_thread(session, owner_id, agent.id)
            revoked = grant(owner_id, agent.id, account_id, thread.id, status="revoked")
            session.add(revoked)
            session.add(grant_card(owner_id, agent.id, thread.id, "confirmed"))
            await session.flush()
            # A conversation's waiting Run, and one left by a grant revoked long ago.
            for metadata in ({}, {"account_management_id": revoked.id}):
                session.add(
                    RunRow(
                        thread_id=thread.id,
                        agent_id=agent.id,
                        status="waiting_takeover",
                        model_metadata=metadata,
                    )
                )
            held = watch(owner_id, lonora.id, thread.id)
            session.add(held)
            await session.flush()
            held.payload = {**held.payload, "enabled": False}
            session.add(
                SupervisionHoldRow(
                    owner_id=owner_id,
                    agent_id=lonora.id,
                    target_kind="watch",
                    target_id=held.id,
                    source="owner",
                    created_at=utcnow(),
                )
            )
        ids = [agent.id for agent in agents]
        cards = {agent.id: len(await mandate_cards(session, agent.id)) for agent in agents}
    runs = await runs_digest(db)
    assert runs != "None"
    cursor = await upgrade(db)
    async with db.sessions() as session:
        assert not await session.scalar(
            select(func.count())
            .select_from(OwnerActionRow)
            .where(OwnerActionRow.kind == "grant_authority")
        )
        for agent_id in ids:
            assert len(await mandate_cards(session, agent_id)) == cards[agent_id], "no card"
            agent = await session.get(AgentRow, agent_id)
            assert agent is not None and agent.trading_mode == "ask"
        statuses = await session.scalars(
            select(AccountAuthorityRow.status).where(AccountAuthorityRow.owner_id == owner_id)
        )
        assert sorted(statuses) == ["revoked"] * 3
        holds = list(await session.scalars(select(SupervisionHoldRow)))
        assert len(holds) == 3 and all(h.released_at is None and h.source == "owner" for h in holds)
    assert await runs_digest(db) == runs, "no Run is cancelled"
    deleted = await events(db, cursor, "owner_action.updated")
    assert sorted(e.payload["kind"] for e in deleted) == ["grant_authority"] * 3, deleted
    assert not await events(db, cursor, "account_authority.updated")
    print("PASS production's shape: grant cards deleted, no card, no Run cancelled, Ask kept")


async def general_shapes(db: Database, owner_id: str, account_id: str) -> dict[str, str]:
    ids: dict[str, str] = {}
    request = TradeRequest(
        account_id=account_id,
        operation_id="migration-" + uuid4().hex,
        action="buy",
        symbol="XAUUSD",
        volume=Decimal("0.1"),
    )
    ids["operation"] = request.operation_id
    async with db.sessions() as session, session.begin():
        lonora = await ensure_personal_agent(session, owner_id)

        async def new_agent(name: str, **fields: Any) -> AgentRow:
            row = await create_agent(session, owner_id, AgentCreate(name=name + uuid4().hex[:6]))
            for key, value in fields.items():
                setattr(row, key, value)
            await session.flush()
            ids[name] = row.id
            return row

        gold, full_one, paused_one = (
            await new_agent("gold"),
            await new_agent("full"),
            await new_agent("held"),
        )
        # An agent in Full with its own continuous task (4.5).
        full_one.trading_mode = "full"
        await session.flush()
        assert await ensure_management_task(session, owner_id, full_one.id) is not None
        # An active grant whose Task waits on its own wait, with a card and a watch.
        conversation = await conversation_thread(session, owner_id, gold.id)
        active = grant(owner_id, gold.id, account_id, conversation.id, status="active")
        session.add(active)
        session.add(grant(owner_id, full_one.id, account_id, conversation.id, status="pending"))
        await session.flush()
        ids["grant"] = active.id
        task = await create_task(
            session,
            owner_id,
            gold.id,
            conversation.id,
            TaskCreate(title="Manage", completion_mode="continuous"),
            stable_id(active.id, "account-management-task"),
        )
        run = await session.get(RunRow, task.payload["run_id"])
        assert run is not None
        run.status = "waiting_takeover"
        run.model_metadata = {**run.model_metadata, "account_management_id": active.id}
        session.add(
            TradeApprovalRow(
                id=str(uuid4()),
                owner_id=owner_id,
                run_id=run.id,
                thread_id=run.thread_id,
                agent_id=gold.id,
                call_id="call",
                requests=[request.model_dump(mode="json")],
            )
        )
        kept = watch(owner_id, gold.id, task.thread_id or "", task_id=task.id)
        session.add(kept)
        await session.flush()
        ids.update(task=task.id, run=run.id, watch=kept.id, conversation=conversation.id)
        # A Full delegation whose Task the owner paused.
        held_thread = await conversation_thread(session, owner_id, paused_one.id)
        full_envelope = {
            "management_mode": "full",
            "symbol_scope": "account",
            "actions": [
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
            ],
            "valid_until": None,
            "allow_manual_positions": True,
        }
        delegation = grant(
            owner_id,
            paused_one.id,
            account_id,
            held_thread.id,
            status="active",
            envelope=full_envelope,
        )
        session.add(delegation)
        await session.flush()
        paused_task = await create_task(
            session,
            owner_id,
            paused_one.id,
            held_thread.id,
            TaskCreate(title="Manage", completion_mode="continuous"),
            stable_id(delegation.id, "account-management-task"),
        )
        state = task_state(paused_task)
        state.status = state.phase = "paused"
        save_task(session, paused_task, state)
        session.add(
            SupervisionHoldRow(
                owner_id=owner_id,
                agent_id=paused_one.id,
                target_kind="task",
                target_id=paused_task.id,
                source="owner",
                created_at=utcnow(),
            )
        )
        paused_watch = watch(
            owner_id, paused_one.id, paused_task.thread_id or "", task_id=paused_task.id
        )
        session.add(paused_watch)
        # An activation review and an unrelated waiting Run.
        for trigger in ("activation", "user"):
            other = RunRow(
                thread_id=conversation.id,
                agent_id=gold.id,
                trigger=trigger,
                status="queued",
                model_metadata={"account_authority_id": "old"},
            )
            session.add(other)
            await session.flush()
            ids[trigger] = other.id
        await session.flush()
        ids["paused_watch"] = paused_watch.id
        # Levels: "No trading" by default, and stored with a draft.
        await new_agent("unset")
        stored = await new_agent("stored")
        session.add(
            SettingRow(
                key=permission_key(owner_id, stored.id),
                payload={
                    "owner_id": owner_id,
                    "agent_id": stored.id,
                    "revision": 3,
                    "fallback_level": "analysis",
                    "customization": {"symbols": ["EURUSD"]},
                },
            )
        )
        # Delegated, child and supervisor agents.
        await new_agent("delegated", role="delegated", parent_id=gold.id, template=None)
        await new_agent(
            "child",
            role="specialist",
            parent_id=gold.id,
            trading_account_id=account_id,
            trading_symbol="XAUUSD",
        )
        supervisor = await new_agent(
            "supervisor", role="general", scope_mode="flexible", template="supervisor"
        )
        memory = await session.get(MemoryRow, supervisor.id)
        assert memory is not None
        memory.content = "# OPERATING.md\nKeep notes short.\n" + SUPERVISOR_LINE + "\n"
        # A team agent's pause, the owner's and Lonora's.
        for name, holder, source in (
            ("team", supervisor.id, "agent"),
            ("owner", None, "owner"),
            ("lonora", lonora.id, "agent"),
        ):
            routine = RoutineRow(
                owner_id=owner_id,
                agent_id=gold.id,
                thread_id=conversation.id,
                prompt="check",
                interval_seconds=3600,
                enabled=False,
                next_run_at=utcnow(),
            )
            session.add(routine)
            await session.flush()
            session.add(
                SupervisionHoldRow(
                    owner_id=owner_id,
                    holder_agent_id=holder,
                    agent_id=gold.id,
                    target_kind="routine",
                    target_id=routine.id,
                    source=source,
                    created_at=utcnow(),
                )
            )
            ids["routine_" + name] = routine.id
        ids["lonora"] = lonora.id
    async with db.engine.begin() as connection:
        await connection.execute(
            text(
                "INSERT INTO ln_trading_journal (operation_id, owner_id, account_id,"
                " request_hash, request, status, result, submitted_at, updated_at)"
                " VALUES (:id, :owner, :account, :hash, :request, 'ambiguous', :result,"
                " :at, :at)"
            ),
            {
                "id": request.operation_id,
                "owner": owner_id,
                "account": account_id,
                "hash": trade_fingerprint(request),
                "request": json.dumps(request.model_dump(mode="json")),
                "result": json.dumps(
                    TradeResult(
                        operation_id=request.operation_id,
                        status="ambiguous",
                        code="broker_result_ambiguous",
                    ).model_dump(mode="json")
                ),
                "at": utcnow() - timedelta(minutes=5),
            },
        )
    cursor = await upgrade(db)
    async with db.sessions() as session:
        # Items 2 and 3: the grant revoked, its Task stopped, its Run and card cancelled.
        row = await session.get(AccountAuthorityRow, ids["grant"])
        assert row is not None and row.status == "revoked"
        assert not await session.scalar(
            select(func.count())
            .select_from(AccountAuthorityRow)
            .where(AccountAuthorityRow.status.in_(["pending", "active"]))
        )
        ticket = await session.get(TicketRow, ids["task"])
        assert ticket is not None and task_state(ticket).status == "cancelled"
        for key, status in (("run", "cancelled"), ("activation", "cancelled"), ("user", "queued")):
            run = await session.get(RunRow, ids[key])
            assert run is not None and run.status == status, (key, run and run.status)
        approval = await session.scalar(
            select(TradeApprovalRow).where(TradeApprovalRow.run_id == ids["run"])
        )
        assert approval is not None and approval.status == "cancelled"
        kept = await session.get(MarketWatchRow, ids["watch"])
        assert kept is not None and kept.payload["enabled"] and "task_id" not in kept.state
        assert kept.thread_id == ids["conversation"], "the watch moves to the conversation"
        paused = await session.get(MarketWatchRow, ids["paused_watch"])
        assert paused is not None and not paused.payload["enabled"]
        assert paused.state.get("code") == "watch_paused"
        hold = await session.scalar(
            select(SupervisionHoldRow).where(SupervisionHoldRow.target_id == paused.id)
        )
        assert hold is not None and hold.source == "owner" and hold.released_at is None
        # One Mandate card each for the two agents that held an active grant.
        for name in ("gold", "held"):
            [card] = await mandate_cards(session, ids[name])
            assert card.agent_id == ids["lonora"] and card.status == "pending"
            assert card.payload_hash == payload_hash("trading_mode", card.payload)
            facts = (await owner_action_data(session, card))["facts"]
            [previous] = facts["previous_grants"]
            assert previous["account"]["id"] == account_id, previous
            if name == "gold":
                assert not previous["full_delegation"] and previous["symbols"] == ["XAUUSD"]
            else:
                assert previous["full_delegation"] and previous["symbol_scope"] == "account"
        assert not await mandate_cards(session, ids["full"]), "a pending grant shows no card"
        # An agent in Full stays in Full with its own Task.
        full_one = await session.get(AgentRow, ids["full"])
        assert full_one is not None and full_one.trading_mode == "full"
        assert await live_management_task(session, owner_id, ids["full"]) is not None
        # Item 1: "No trading" becomes "Ask me"; a revoked grant bumps the revision.
        unset = await level(session, owner_id, ids["unset"])
        assert unset is not None and unset["fallback_level"] == "supervised"
        assert unset["revision"] == 1
        stored = await level(session, owner_id, ids["stored"])
        assert stored == {
            "owner_id": owner_id,
            "agent_id": ids["stored"],
            "revision": 4,
            "fallback_level": "supervised",
            "customization": {"symbols": ["EURUSD"]},
        }, stored
        assert await level(session, owner_id, ids["lonora"]) is None, "Lonora untouched"
        gold_level = await level(session, owner_id, ids["gold"])
        assert gold_level is not None and gold_level["fallback_level"] == "supervised"
        # Item 4: specialists with no parent; the bound market is in the method.
        for name in ("delegated", "child", "supervisor"):
            agent = await session.get(AgentRow, ids[name])
            assert agent is not None and agent.role == "specialist" and agent.parent_id is None
            assert agent.scope_mode == "flexible" and agent.trading_account_id is None
            assert agent.template != "supervisor"
        child = await session.get(MemoryRow, ids["child"])
        assert child is not None and "السوق المُسنَد إليك" in child.content, child
        assert "XAUUSD على حساب المحاكاة" in child.content, child.content
        supervisor = await session.get(MemoryRow, ids["supervisor"])
        assert supervisor is not None and SUPERVISOR_LINE not in supervisor.content
        assert "Keep notes short." in supervisor.content
        # Item 6: the team agent's pause is stale and its routine runs; the others stay.
        for name, released, enabled in (
            ("team", "stale", True),
            ("owner", None, False),
            ("lonora", None, False),
        ):
            hold = await session.scalar(
                select(SupervisionHoldRow).where(
                    SupervisionHoldRow.target_id == ids["routine_" + name]
                )
            )
            routine = await session.get(RoutineRow, ids["routine_" + name])
            assert hold is not None and hold.released_by == released, (name, hold)
            assert routine is not None and routine.enabled is enabled, name
    assert len(await events(db, cursor, "run.cancelled")) == 2
    revoked = await events(db, cursor, "account_authority.updated")
    assert sorted(e.payload["status"] for e in revoked) == ["revoked"] * 3
    print("PASS one active grant: revoked, Task stopped, watch kept, one Mandate card each")
    print("PASS Full stays Full with its Task; No trading becomes Ask me")
    print("PASS delegated, child and supervisor agents become specialists with the method line")
    print("PASS a team agent's pause is stale and its work resumes; owner and Lonora pauses stay")

    # 14.3.9: the operation left ambiguous reconciles without a resend.
    broker = ScriptedBroker()
    broker.account_id = account_id
    broker.receipts[ids["operation"]] = TradeResult(
        operation_id=ids["operation"], status="confirmed", broker_id="migration-deal"
    )
    manager = cast(BrokerManager, ScriptedManager(broker))
    assert await reconcile_ambiguous(db, manager) == 1
    assert broker.sent == 0, "An uncertain operation was resent"
    async with db.sessions() as session:
        operation = await session.get(TradingJournalRow, ids["operation"])
        assert operation is not None and operation.status == "confirmed"
        again = TradeRequest.model_validate(operation.request)
    result = await ExecutionService(db, manager).execute(owner_id, again)
    assert result.status == "confirmed" and broker.sent == 0, result
    print("PASS an ambiguous operation reconciles after the migration with no resend")
    return ids


async def second_upgrade(db: Database, owner_id: str, account_id: str, ids: dict[str, str]):
    await step_down(db)
    async with db.sessions() as session, session.begin():
        # A grant signed again under the older code, and an agent bound since.
        row = await session.get(AccountAuthorityRow, ids["grant"])
        assert row is not None
        row.status = "active"
        bound = await create_agent(session, owner_id, AgentCreate(name="Bound " + uuid4().hex[:6]))
        bound.role, bound.parent_id = "specialist", ids["gold"]
        bound.trading_account_id, bound.trading_symbol = account_id, "EURUSD"
        bound_id = bound.id
        await session.execute(
            text(
                "INSERT INTO ln_owner_profile (owner_id, content, version, reply_language,"
                " updated_at) VALUES (:owner, '', 1, 'en', now()) ON CONFLICT (owner_id)"
                " DO UPDATE SET reply_language = 'en'"
            ),
            {"owner": owner_id},
        )
        child = await session.get(MemoryRow, ids["child"])
        assert child is not None
        child_before = child.content
    await upgrade(db)
    async with db.sessions() as session:
        assert len(await mandate_cards(session, ids["gold"])) == 1, "shown once"
        row = await session.get(AccountAuthorityRow, ids["grant"])
        assert row is not None and row.status == "revoked"
        memory = await session.get(MemoryRow, bound_id)
        assert memory is not None and "Your assigned market" in memory.content, memory
        assert "EURUSD on the simulation account" in memory.content, memory.content
        child = await session.get(MemoryRow, ids["child"])
        assert child is not None and child.content == child_before, "no second line"
        stored = await level(session, owner_id, ids["stored"])
        assert stored is not None and stored["revision"] == 4
    heads = alembic("heads").strip().splitlines()
    assert heads == [REVISION + " (head)"], heads
    print(
        "PASS a second upgrade shows no second card; the method line follows the owner's language"
    )


async def main() -> None:
    db = database()
    async with db.sessions() as session, session.begin():
        owner = await session.scalar(select(OwnerRow))
        if owner is None:
            owner = OwnerRow(email="authority-migration@example.test", password_hash="x")
            session.add(owner)
            await session.flush()
        owner_id = owner.id
        account = await BrokerSessionRepository().create(
            session,
            owner_id,
            {"provider": "simulation", "account_id": "mig-" + uuid4().hex[:8], "enabled": True},
        )
        account_id = account.id
    await step_down(db)
    await production_shape(db, owner_id, account_id)
    await step_down(db)
    ids = await general_shapes(db, owner_id, account_id)
    await second_upgrade(db, owner_id, account_id, ids)
    await db.engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
