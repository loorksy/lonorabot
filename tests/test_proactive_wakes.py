"""Proactive wakes that can act, and reading without walls (W15-7).

The pure cases run everywhere. The PostgreSQL cases (LONORA_DATABASE_URL) use the
real registry, the simulation broker and the reconciliation lane: an observe-only
wake keeps every non-financial ability, a stop-loss hit on an Agent's own position
wakes that Agent with its normal authority while the owner's manual position wakes
the Personal Agent, a repeated wake duplicates nothing, a fixed-market Agent reads
every owned account but trades only its pair, and owner_notify follows the owner's
reach-me rules.
"""

import os
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Any
from uuid import uuid4

import pytest
from lonora_adapter_kit.types import ToolCall
from lonora_contracts.account import Position
from lonora_contracts.attention import OwnerNotifyRequest
from lonora_contracts.broker_activity import BrokerRecoverySnapshot
from lonora_contracts.domain import utcnow
from lonora_contracts.incoming_calls import IncomingCallPolicy
from lonora_core.user_error import LonoraError
from lonora_db.schema import TradingJournalRow
from lonora_tools.base import HELPER_EFFECTS, Tool, run_scope
from lonora_tools.loader import load_tools
from lonora_trading.manual_activity import attributed_agent, detect_activity, journal_agent
from pydantic import BaseModel, ValidationError

NOW = datetime(2026, 11, 8, 12, 0, tzinfo=UTC)


class Empty(BaseModel):
    pass


async def handler(_: Any, __: dict[str, Any]) -> dict[str, Any]:
    return {}


def journal(
    operation_id: str,
    request: dict[str, Any],
    *,
    agent_id: str | None,
    status: str = "confirmed",
    broker_id: str | None = None,
    updated_at: datetime = NOW,
) -> TradingJournalRow:
    execution = {"run_id": "run-" + operation_id, "agent_id": agent_id} if agent_id else None
    return TradingJournalRow(
        operation_id=operation_id,
        owner_id="owner",
        account_id="acc",
        request_hash="h",
        request={"account_id": "acc", **request},
        status=status,
        result={
            "status": status,
            "broker_id": broker_id,
            "details": {"execution": execution} if execution else {},
        },
        updated_at=updated_at,
    )


def position(ticket: str, *, operation_id: str | None = None, stop: str = "95") -> Position:
    return Position(
        id=ticket,
        symbol="XAUUSD",
        side="buy",
        volume=Decimal("0.1"),
        open_price=Decimal(100),
        stop_loss=Decimal(stop),
        operation_id=operation_id,
    )


# --- Scope: observe-only means no financial effects ---------------------------------


def test_scopes_follow_the_run_not_the_tool_list():
    assert run_scope("subagent", {"authority": "observe_only"}) == "helper"
    assert run_scope("broker_event", {"authority": "observe_only"}) == "observe_only"
    assert run_scope("broker_event", {}) == "full"
    trade = Tool("fixture_trade", "Trade", Empty, handler, financial=True)
    write = Tool("fixture_write", "Write", Empty, handler)
    read = Tool("fixture_read", "Read", Empty, handler, True)
    assert trade.permitted("full") and not trade.permitted("observe_only")
    assert not trade.permitted("helper")
    assert write.permitted("observe_only") and not write.permitted("helper")
    assert read.permitted("helper") and read.permitted("observe_only")
    catalog = load_tools()
    wake = catalog.names("observe_only")
    assert {"memory_write", "watch_create", "peer_send", "owner_notify", "routine_create"} <= wake
    assert {"artifact_create", "workspace_update", "trade_restriction_create"} <= wake
    assert not {name for name, tool in catalog.tools.items() if tool.financial} & wake
    helper = catalog.names("helper")
    assert HELPER_EFFECTS <= helper
    assert not {"memory_write", "peer_send", "child_agent_create", "owner_notify"} & helper


# --- Attribution: the journal says whose position it is -----------------------------


def test_the_journal_attributes_tickets_to_the_agent_that_opened_or_manages_them():
    opened = journal(
        "op-open", {"action": "buy", "symbol": "XAUUSD"}, agent_id="gold", broker_id="T1"
    )
    assert journal_agent(opened) == "gold"
    # The opening operation decides, by broker id or by the operation id it carries.
    assert attributed_agent(position("T1"), None, [opened]) == "gold"
    assert attributed_agent(position("T9", operation_id="op-open"), None, [opened]) == "gold"
    # The owner's manual position, and the owner's own order through Lonora, are nobody's.
    owner_order = journal(
        "op-owner", {"action": "buy", "symbol": "XAUUSD"}, agent_id=None, broker_id="T2"
    )
    assert attributed_agent(position("T2"), None, [owner_order]) is None
    assert attributed_agent(position("manual"), None, [opened, owner_order]) is None
    # An Agent that manages a manual ticket (grant with manual positions) owns its events.
    managed = journal(
        "op-sl",
        {"action": "modify_position", "symbol": "XAUUSD", "position_id": "T2", "stop_loss": "97"},
        agent_id="lonora",
    )
    assert attributed_agent(position("T2"), None, [managed, owner_order]) == "lonora"
    # A reservation never reached the broker and attributes nothing.
    reserved = journal(
        "op-res", {"action": "buy", "symbol": "XAUUSD"}, agent_id="gold", status="reserved"
    )
    reserved.result["broker_id"] = "T3"
    assert attributed_agent(position("T3"), None, [reserved]) is None


def test_a_stop_loss_hit_is_external_activity_attributed_to_its_agent():
    opened = journal(
        "op-open",
        {"action": "buy", "symbol": "XAUUSD"},
        agent_id="gold",
        broker_id="T1",
        updated_at=NOW - timedelta(hours=1),
    )
    previous = BrokerRecoverySnapshot(
        status="connected",
        reason_code="broker_reconciled",
        since=NOW - timedelta(hours=1),
        observed_at=NOW - timedelta(minutes=1),
        revision=4,
        positions=[position("T1"), position("manual-7")],
    )
    changes = detect_activity("acc", previous, [], [], [opened], revision=5, now=NOW)
    by_ticket = {change.ticket: change for change in changes}
    assert by_ticket["T1"].change == "closed" and by_ticket["T1"].origin == "external"
    assert by_ticket["T1"].agent_id == "gold"
    assert by_ticket["manual-7"].agent_id is None
    # The fact itself still grants nothing.
    assert by_ticket["T1"].authority == "observe_only"


# --- Owner notify contract and quiet hours ------------------------------------------


def test_quiet_hours_end_in_the_owner_timezone():
    policy = IncomingCallPolicy(timezone="Asia/Riyadh", quiet_start_hour=22, quiet_end_hour=7)
    late = datetime(2026, 11, 8, 20, 30, tzinfo=UTC)  # 23:30 in Riyadh
    assert policy.quiet(late)
    assert policy.quiet_until(late) == datetime(2026, 11, 9, 4, 0, tzinfo=UTC)
    assert policy.quiet_until(datetime(2026, 11, 8, 9, 0, tzinfo=UTC)) is None
    assert IncomingCallPolicy().quiet_until(late) is None


def test_owner_notify_input_is_bounded():
    valid = {"importance": "important_change", "summary": "Gold stop was hit", "dedupe_key": "k"}
    assert OwnerNotifyRequest.model_validate(valid).evidence_refs == []
    for invalid in (
        {**valid, "importance": "opportunity"},
        {**valid, "summary": "short"},
        {**valid, "evidence_refs": [""]},
        {**valid, "evidence_refs": ["x"] * 9},
        {**valid, "expires_at": "2026-11-08T12:00:00"},
    ):
        with pytest.raises(ValidationError):
            OwnerNotifyRequest.model_validate(invalid)


# --- PostgreSQL: wakes act, broker events reach the responsible agent -----------------


def database() -> None:
    if not os.environ.get("LONORA_DATABASE_URL"):
        pytest.skip("The wake cases use the real migrated PostgreSQL schema.")


async def call(context: Any, name: str, **arguments: Any) -> dict[str, Any]:
    return await load_tools().execute(
        ToolCall(id=name + "-" + uuid4().hex, name=name, arguments=arguments), context
    )


async def simulation(fixture: Any, positions: list[Position] | None = None) -> str:
    connection = (
        await fixture.request(
            "POST",
            "/trading/connections",
            {"provider": "simulation", "account_id": uuid4().hex, "enabled": True},
        )
    )["id"]
    await fixture.request(
        "POST",
        f"/trading/connections/{connection}/simulation",
        {
            "snapshot": {
                "currency": "USD",
                "balance": "10000",
                "instruments": [
                    {
                        "symbol": "XAUUSD",
                        "digits": 2,
                        "tick_size": "0.01",
                        "volume_min": "0.1",
                        "volume_max": "100",
                        "volume_step": "0.1",
                    }
                ],
                "quotes": {
                    "XAUUSD": {
                        "symbol": "XAUUSD",
                        "bid": "100",
                        "ask": "101",
                        "observed_at": utcnow().isoformat(),
                        "source": "wake-fixture",
                    }
                },
            }
        },
    )
    if positions is not None:
        await set_positions(fixture, connection, positions)
    return connection


async def set_positions(fixture: Any, connection: str, positions: list[Position]) -> None:
    from lonora_db.schema import TradingAccountRow

    async with fixture.runtime.db.sessions() as session, session.begin():
        account = await session.get(TradingAccountRow, connection, with_for_update=True)
        assert account is not None
        account.payload = {
            **account.payload,
            "positions": [item.model_dump(mode="json") for item in positions],
        }


async def retire(fixture: Any, *connections: str) -> None:
    """Remove the fixture accounts and settle the wakes they queued.

    The Personal Agent outlives the fixture, so its queued wakes would otherwise be
    claimed by later tests sharing this database.
    """
    from lonora_db.schema import RunRow
    from sqlalchemy import select

    accounts = [connection for connection in connections if connection]
    if accounts:
        async with fixture.runtime.db.sessions() as session, session.begin():
            for row in await session.scalars(
                select(RunRow).where(
                    RunRow.model_metadata["account_id"].as_string().in_(accounts),
                    RunRow.status.in_(["queued", "leased", "running", "waiting_input"]),
                )
            ):
                row.status = "cancelled"
    for connection in accounts:
        await fixture.client.delete(f"/api/trading/connections/{connection}")


async def wake_run(
    fixture: Any,
    agent: dict[str, Any],
    *,
    observe_only: bool,
    trigger: str = "broker_event",
    metadata: dict[str, Any] | None = None,
) -> Any:
    """A server-style wake: the Agent's work lane, reporting to its conversation."""
    from lonora_contracts.domain import ThreadCreate
    from lonora_contracts.runs import RunRequest
    from lonora_db.runs import create_run, run_data
    from lonora_db.threads import conversation_thread, create_thread

    async with fixture.runtime.db.sessions() as session, session.begin():
        origin = await conversation_thread(session, fixture.owner, agent["id"])
        work = await create_thread(
            session, fixture.owner, ThreadCreate(agent_id=agent["id"]), purpose="work"
        )
        run = await create_run(
            session,
            fixture.owner,
            RunRequest(
                thread_id=work.id,
                agent_id=agent["id"],
                trigger=trigger,
                prompt="Wake fixture",
                metadata={
                    "origin_thread_id": origin.id,
                    **({"authority": "observe_only"} if observe_only else {}),
                    **(metadata or {}),
                },
            ),
        )
        data, origin_id = run_data(run), origin.id
    return await fixture.lease(data), origin_id


@pytest.mark.asyncio
async def test_an_observe_only_wake_acts_but_never_trades():
    database()
    from check_streaming import Fixture
    from lonora_db.schema import MarketWatchRow
    from sqlalchemy import func, select

    fixture = await Fixture().open()
    connection = ""
    try:
        connection = await simulation(fixture)
        agent = await fixture.agent("Wake", supervised=True)
        colleague = await fixture.agent("Colleague")
        context, origin = await wake_run(fixture, agent, observe_only=True)
        read = await call(context, "memory_read")
        saved = await call(
            context,
            "memory_write",
            version=read["version"],
            operations=[
                {"action": "add", "section": "MEMORY.md", "content": "- Gold stop hit at 95"}
            ],
        )
        assert saved["version"] == read["version"] + 1, saved
        watch = {
            "account_id": connection,
            "symbol": "XAUUSD",
            "kind": "price",
            "condition": "below",
            "level": "90",
            "prompt": "Re-check gold below 90",
            "dedupe_key": "gold-below-90",
        }
        first = await call(context, "watch_create", **watch)
        # A watch set up in a wake belongs to the Agent's conversation, like one from chat.
        assert first["thread_id"] == origin
        # The same wake twice, or a later wake re-arming it, keeps one live watch.
        again, _ = await wake_run(fixture, agent, observe_only=True)
        repeated = await call(again, "watch_create", **watch)
        assert repeated["id"] == first["id"] and repeated["deduplicated"] is True
        moved = await call(again, "watch_create", **{**watch, "level": "88"})
        assert moved["id"] != first["id"]
        async with fixture.runtime.db.sessions() as session:
            live = await session.scalar(
                select(func.count())
                .select_from(MarketWatchRow)
                .where(
                    MarketWatchRow.agent_id == agent["id"],
                    MarketWatchRow.payload["dedupe_key"].as_string() == "gold-below-90",
                    MarketWatchRow.payload["enabled"].as_boolean().is_(True),
                )
            )
            replaced = await session.get(MarketWatchRow, first["id"])
            assert live == 1 and replaced is not None
            assert replaced.payload["enabled"] is False
            assert replaced.state["code"] == "watch_replaced"
        peer = await call(
            context, "peer_send", agent_id=colleague["id"], task="Gold stop was hit; check DXY."
        )
        assert peer.get("status") or peer.get("id"), peer
        for name, arguments in (
            (
                "trade_execute",
                {"account_id": connection, "symbol": "XAUUSD", "action": "buy", "volume": "0.1"},
            ),
            ("trade_close_positions", {"account_id": connection}),
        ):
            with pytest.raises(LonoraError, match="observe_only_execution_forbidden"):
                await call(context, name, **arguments)
    finally:
        await retire(fixture, connection)
        await fixture.close()


@pytest.mark.asyncio
async def test_tasks_and_tickets_an_observe_only_wake_starts_never_trade():
    database()
    from check_streaming import Fixture
    from lonora_db.schema import RunRow, TicketRow
    from lonora_trading.execution import require_goal_lineage

    fixture = await Fixture().open()
    connection = ""
    try:
        connection = await simulation(fixture)
        agent = await fixture.agent("Wake delegator", supervised=True)
        context, _ = await wake_run(fixture, agent, observe_only=True)
        task = await call(context, "task_start", title="Watch gold after the stop")
        board = await call(context, "board_create", title="Wake follow-ups")
        ticket = await call(
            context, "ticket_create", board_id=board["id"], title="Review gold exposure"
        )
        started = await call(context, "ticket_start", ticket_id=ticket["id"])
        async with fixture.runtime.db.sessions() as session:
            row = await session.get(TicketRow, task["id"])
            assert row is not None
            task_run = await session.get(RunRow, row.payload["run_id"])
            ticket_run = await session.get(RunRow, started["id"])
        assert task_run is not None and ticket_run is not None
        for run in (task_run, ticket_run):
            # No parent link, so the narrowing travels in the Run itself.
            assert run.parent_run_id is None
            assert run.model_metadata["authority"] == "observe_only"
            assert run.model_metadata["authority_run_id"] == context.lease.run_id
            assert run_scope(run.trigger, run.model_metadata) == "observe_only"
        # A full Run's Task keeps the Agent's normal authority.
        chat = await fixture.lease(await fixture.run(agent, await fixture.conversation(agent)))
        normal = await call(chat, "task_start", title="Ordinary background work")
        async with fixture.runtime.db.sessions() as session:
            row = await session.get(TicketRow, normal["id"])
            assert row is not None
            normal_run = await session.get(RunRow, row.payload["run_id"])
            assert normal_run is not None and "authority" not in normal_run.model_metadata
        for run in (task_run, ticket_run):
            delegated = await fixture.lease(
                {"id": run.id, "agent_id": run.agent_id, "thread_id": run.thread_id}
            )
            # The Task keeps every non-financial ability ...
            assert (await call(delegated, "memory_read"))["version"] >= 0
            # ... and neither the registry nor the executor lets it reach the broker.
            for name, arguments in (
                (
                    "trade_execute",
                    {
                        "account_id": connection,
                        "symbol": "XAUUSD",
                        "action": "buy",
                        "volume": "0.1",
                    },
                ),
                ("trade_close_positions", {"account_id": connection}),
            ):
                with pytest.raises(LonoraError, match="observe_only_execution_forbidden"):
                    await call(delegated, name, **arguments)
            async with fixture.runtime.db.sessions() as session:
                with pytest.raises(LonoraError, match="observe_only_execution_forbidden"):
                    await require_goal_lineage(session, delegated.lease, None)
    finally:
        await retire(fixture, connection)
        await fixture.close()


@pytest.mark.asyncio
async def test_a_follow_up_to_an_observe_only_request_stays_observe_only():
    """A peer's answer after the requester's Run ended starts a follow-up Run that keeps
    the requester's narrowing: it never asks the owner to approve a trade the executor
    would refuse."""
    database()
    from check_streaming import Fixture
    from lonora_agent.collaboration.outcome_return import return_outcome
    from lonora_db.schema import RunRow
    from sqlalchemy import select

    fixture = await Fixture().open()
    try:
        requester = await fixture.agent("Wake requester", supervised=True)
        peer = await fixture.agent("Wake helper peer")
        context, _ = await wake_run(fixture, requester, observe_only=True)
        sent = await call(context, "peer_send", agent_id=peer["id"], task="Check gold news")
        async with fixture.runtime.db.sessions() as session, session.begin():
            parent = await session.get(RunRow, context.lease.run_id)
            child = await session.scalar(
                select(RunRow).where(RunRow.parent_run_id == context.lease.run_id)
            )
            assert parent is not None and child is not None, sent
            parent.status, parent.result = "completed", "Asked the helper"
            child.status, child.result = "completed", "Nothing material"
            child_id = child.id
        await return_outcome(fixture.runtime.db, child_id)
        async with fixture.runtime.db.sessions() as session:
            follow_up = await session.scalar(
                select(RunRow).where(
                    RunRow.parent_run_id == context.lease.run_id, RunRow.trigger == "follow_up"
                )
            )
        assert follow_up is not None
        assert follow_up.model_metadata["authority"] == "observe_only"
        assert run_scope(follow_up.trigger, follow_up.model_metadata) == "observe_only"
    finally:
        await fixture.close()


async def gold_goal(context: Any, connection: str) -> dict[str, Any]:
    return await call(
        context,
        "goal_create",
        title="Gold swing",
        objective="Hold gold while the weekly trend holds",
        account_id=connection,
        symbol="XAUUSD",
        steps=[{"id": "review", "title": "Review the position", "kind": "analysis"}],
    )


@pytest.mark.asyncio
async def test_re_arming_an_identical_goal_watch_keeps_it():
    database()
    from check_streaming import Fixture
    from lonora_db.schema import MarketWatchRow

    fixture = await Fixture().open()
    connection = ""
    try:
        connection = await simulation(fixture)
        agent = await fixture.agent("Goal watcher", supervised=True)
        chat = await fixture.lease(await fixture.run(agent, await fixture.conversation(agent)))
        goal = await gold_goal(chat, connection)
        watch = {
            "account_id": connection,
            "symbol": "XAUUSD",
            "kind": "price",
            "condition": "below",
            "level": "90",
            "prompt": "Review the swing below 90",
            "goal_id": goal["id"],
            "step_id": "review",
            "dedupe_key": "swing-below-90-" + uuid4().hex[:6],
        }
        first = await call(chat, "watch_create", **watch)
        # The server adds the Goal's plan version; an identical re-arm still matches.
        assert first["payload"]["goal_plan_version"] == 1
        again = await call(chat, "watch_create", **watch)
        assert again["id"] == first["id"] and again["deduplicated"] is True
        async with fixture.runtime.db.sessions() as session:
            row = await session.get(MarketWatchRow, first["id"])
            assert row is not None and row.payload["enabled"] is True
            assert "code" not in row.state or row.state["code"] != "watch_replaced"
    finally:
        await retire(fixture, connection)
        await fixture.close()


@pytest.mark.asyncio
async def test_an_identical_watch_request_without_a_key_keeps_the_one_live_watch():
    """A model that asks again for the same watch (after a worker restart, or a later wake
    re-arming it) gets the live watch back; a changed condition or a cancelled watch is a
    new one, and another agent's identical watch is its own."""
    database()
    from check_streaming import Fixture
    from lonora_db.schema import MarketWatchRow
    from sqlalchemy import func, select

    fixture = await Fixture().open()
    connection = ""
    try:
        connection = await simulation(fixture)
        agent = await fixture.agent("Watcher")
        other = await fixture.agent("Other watcher")
        chat = await fixture.lease(await fixture.run(agent, await fixture.conversation(agent)))
        watch = {
            "account_id": connection,
            "symbol": "XAUUSD",
            "kind": "price",
            "condition": "above",
            "level": "110",
            "prompt": "Gold above 110",
            "expires_at": (utcnow() + timedelta(hours=4)).isoformat(),
        }
        first = await call(chat, "watch_create", **watch)
        again = await call(chat, "watch_create", **watch)
        assert again["id"] == first["id"] and again["deduplicated"] is True
        moved = await call(chat, "watch_create", **{**watch, "level": "120"})
        assert moved["id"] != first["id"] and "deduplicated" not in moved
        theirs = await fixture.lease(await fixture.run(other, await fixture.conversation(other)))
        separate = await call(theirs, "watch_create", **watch)
        assert separate["id"] != first["id"]
        await call(chat, "watch_cancel", watch_id=first["id"])
        rearmed = await call(chat, "watch_create", **watch)
        assert rearmed["id"] != first["id"] and "deduplicated" not in rearmed
        async with fixture.runtime.db.sessions() as session:
            live = await session.scalar(
                select(func.count())
                .select_from(MarketWatchRow)
                .where(
                    MarketWatchRow.agent_id == agent["id"],
                    MarketWatchRow.payload["enabled"].as_boolean().is_(True),
                )
            )
        assert live == 2, live  # The re-armed watch and the moved one; never a duplicate.
    finally:
        await retire(fixture, connection)
        await fixture.close()


@pytest.mark.asyncio
async def test_every_work_lane_wake_reads_the_goals_of_its_conversation():
    database()
    from check_streaming import Fixture
    from lonora_agent.context.goals import goal_context_blocks
    from lonora_db.runs import require_lease
    from lonora_db.threads import origin_read_threads

    fixture = await Fixture().open()
    connection = ""
    try:
        connection = await simulation(fixture)
        agent = await fixture.agent("Goal keeper", supervised=True)
        chat = await fixture.lease(await fixture.run(agent, await fixture.conversation(agent)))
        goal = await gold_goal(chat, connection)
        wakes = {
            "observe-only": (await wake_run(fixture, agent, observe_only=True))[0],
            "attributed broker event": (await wake_run(fixture, agent, observe_only=False))[0],
            "opportunity": (
                await wake_run(
                    fixture,
                    agent,
                    observe_only=False,
                    trigger="watch",
                    metadata={"opportunity_id": "opportunity-fixture", "opportunity_version": 2},
                )
            )[0],
        }
        for label, context in wakes.items():
            listed = await call(context, "goal_list")
            assert [item["id"] for item in listed["goals"]] == [goal["id"]], label
            read = await call(context, "goal_read", goal_id=goal["id"])
            assert read["scope"]["account_id"] == connection, label
            # A goal's size is plan data: nothing presents it to the model as a limit.
            assert "limits" not in read and "planned_volume" in read, label
            assert "decisions" in await call(context, "goal_decisions", goal_id=goal["id"])
            async with fixture.runtime.db.sessions() as session:
                run = await require_lease(session, context.lease)
                core, _ = await goal_context_blocks(
                    session,
                    fixture.owner,
                    agent["id"],
                    await origin_read_threads(session, run),
                )
            # The Goal, its plan and limits are in the wake's own context.
            assert goal["id"] in core, label
        # Another Agent's lane never reads this conversation's Goals.
        stranger = await fixture.agent("Stranger")
        foreign, _ = await wake_run(fixture, stranger, observe_only=False)
        assert (await call(foreign, "goal_list"))["goals"] == []
        with pytest.raises(LonoraError, match="goal_run_mismatch"):
            await call(foreign, "goal_read", goal_id=goal["id"])
    finally:
        await retire(fixture, connection)
        await fixture.close()


@pytest.mark.asyncio
async def test_a_stop_loss_hit_wakes_the_agent_that_opened_the_position():
    database()
    from check_streaming import Fixture
    from lonora_db.schema import AgentRow, EventRow, RunRow
    from lonora_trading.broker_recovery import reconcile_broker_account
    from sqlalchemy import select

    fixture = await Fixture().open()
    connection = ""
    try:
        gold = await fixture.agent("Gold", supervised=True)
        opened = position("sim-gold-1", operation_id="gold-entry-" + uuid4().hex[:8])
        manual = position("manual-owner-1")
        connection = await simulation(fixture, [opened, manual])
        async with fixture.runtime.db.sessions() as session, session.begin():
            row = journal(
                str(opened.operation_id),
                {"action": "buy", "symbol": "XAUUSD", "volume": "0.1"},
                agent_id=gold["id"],
                broker_id=opened.id,
                updated_at=utcnow() - timedelta(minutes=5),
            )
            row.owner_id, row.account_id = fixture.owner, connection
            row.request = {**row.request, "account_id": connection}
            session.add(row)
        brokers = fixture.runtime.services(fixture.owner).brokers

        async def reconcile() -> BrokerRecoverySnapshot:
            snapshot = await reconcile_broker_account(
                fixture.runtime.db, brokers, fixture.owner, connection
            )
            assert snapshot is not None and snapshot.status == "connected", snapshot
            return snapshot

        async def wakes() -> list[RunRow]:
            async with fixture.runtime.db.sessions() as session:
                return list(
                    await session.scalars(
                        select(RunRow)
                        .where(
                            RunRow.trigger == "broker_event",
                            RunRow.model_metadata["account_id"].as_string() == connection,
                        )
                        .order_by(RunRow.created_at)
                    )
                )

        await reconcile()
        # Both tickets are discovered; the owner's manual one wakes the Personal Agent.
        first = await wakes()
        assert len(first) == 1 and first[0].model_metadata["authority"] == "observe_only"
        async with fixture.runtime.db.sessions() as session:
            personal = await session.get(AgentRow, first[0].agent_id)
            assert personal is not None and personal.role == "personal"
        # The broker closes the gold position at its stop loss.
        await set_positions(fixture, connection, [manual])
        await reconcile()
        current = await wakes()
        assert len(current) == 2
        woken = current[-1]
        assert woken.agent_id == gold["id"] and "authority" not in woken.model_metadata
        async with fixture.runtime.db.sessions() as session:
            events = list(
                await session.scalars(
                    select(EventRow).where(
                        EventRow.kind == "broker.external_activity",
                        EventRow.payload["account_id"].as_string() == connection,
                        EventRow.payload["ticket"].as_string() == opened.id,
                    )
                )
            )
            assert len(events) == 1 and events[0].agent_id == gold["id"]
            assert events[0].payload["agent_id"] == gold["id"]
            assert events[0].payload["change"] == "closed"
            assert woken.model_metadata["broker_event_ids"] == [events[0].payload["id"]]
            assert woken.model_metadata["origin_thread_id"] == events[0].thread_id
        # Reconciling again finds nothing new and wakes nobody twice.
        await reconcile()
        assert len(await wakes()) == 2
        # The owner moves the manual stop: still the Personal Agent's observe-only wake.
        await set_positions(fixture, connection, [position(manual.id, stop="97")])
        await reconcile()
        latest = await wakes()
        assert len(latest) == 3 and latest[-1].agent_id == personal.id
        assert latest[-1].model_metadata["authority"] == "observe_only"
        # The woken Agent reads the activity of its account; every owned account is readable.
        context = await fixture.lease(
            {"id": woken.id, "agent_id": woken.agent_id, "thread_id": woken.thread_id}
        )
        activity = await call(context, "account_activity", account_id=connection)
        tickets = {item["ticket"]: item["agent_id"] for item in activity["activities"]}
        assert tickets[opened.id] == gold["id"] and tickets[manual.id] is None
    finally:
        await retire(fixture, connection)
        await fixture.close()


@pytest.mark.asyncio
async def test_a_paused_agents_activity_falls_back_to_the_personal_agent():
    database()
    from check_streaming import Fixture
    from lonora_contracts.broker_activity import BrokerActivity
    from lonora_db.personal_agent import ensure_personal_agent
    from lonora_db.schema import AgentRow, RunRow
    from lonora_trading.broker_recovery import wake_for_activity
    from sqlalchemy import select

    fixture = await Fixture().open()
    connection = ""
    try:
        connection = await simulation(fixture)
        gold = await fixture.agent("Paused gold")
        async with fixture.runtime.db.sessions() as session, session.begin():
            row = await session.get(AgentRow, gold["id"])
            assert row is not None
            row.paused = True
            change = BrokerActivity(
                id=str(uuid4()),
                account_id=connection,
                symbol="XAUUSD",
                ticket="T-paused",
                resource="position",
                change="closed",
                origin="external",
                observed_at=utcnow(),
                previous=position("T-paused"),
                agent_id=gold["id"],
            )
            await wake_for_activity(session, fixture.owner, connection, 99, [change])
            # Delivered once: the same change again creates nothing.
            await wake_for_activity(session, fixture.owner, connection, 99, [change])
            personal = await ensure_personal_agent(session, fixture.owner)
        async with fixture.runtime.db.sessions() as session:
            runs = list(
                await session.scalars(
                    select(RunRow).where(
                        RunRow.model_metadata["account_id"].as_string() == connection
                    )
                )
            )
        assert len(runs) == 1 and runs[0].agent_id == personal.id
        assert runs[0].model_metadata["authority"] == "observe_only"
    finally:
        await retire(fixture, connection)
        await fixture.close()


async def other_symbol_records(fixture: Any, account_id: str) -> None:
    """A confirmed EURUSD operation and an EURUSD decision by a colleague on ``account_id``."""
    from lonora_contracts.trading_decision import DecisionEvidence, TradingDecision
    from lonora_db.trading_decisions import store_decision

    colleague = await fixture.agent("Euro desk")
    thread = await fixture.conversation(colleague)
    run = await fixture.run(colleague, thread)
    async with fixture.runtime.db.sessions() as session, session.begin():
        row = journal(
            "eur-" + uuid4().hex[:10],
            {"action": "buy", "symbol": "EURUSD", "volume": "0.1"},
            agent_id=colleague["id"],
            broker_id="EUR-1",
        )
        row.owner_id, row.account_id = fixture.owner, account_id
        row.request = {**row.request, "account_id": account_id}
        session.add(row)
        await store_decision(
            session,
            TradingDecision(
                id=str(uuid4()),
                owner_id=fixture.owner,
                agent_id=colleague["id"],
                run_id=run["id"],
                account_id=account_id,
                symbol="EURUSD",
                timeframe="H1",
                recorded_at=utcnow(),
                requested_action="WAIT",
                action="WAIT",
                summary="Euro range holds; wait for the break",
                gate_codes=[],
                evidence=DecisionEvidence(id=str(uuid4()), captured_at=utcnow()),
            ),
            thread_id=thread["id"],
            intent="eur-wait",
        )


@pytest.mark.asyncio
async def test_a_fixed_market_agent_reads_every_account_and_trades_only_its_pair():
    database()
    from check_streaming import Fixture
    from lonora_db.schema import AgentRow

    fixture = await Fixture().open()
    primary = secondary = ""
    try:
        primary, secondary = await simulation(fixture), await simulation(fixture)
        agent = await fixture.agent("Fixed gold", supervised=True)
        async with fixture.runtime.db.sessions() as session, session.begin():
            row = await session.get(AgentRow, agent["id"])
            assert row is not None
            row.role = "specialist"
            row.trading_account_id, row.trading_symbol = primary, "XAUUSD"
        context = await fixture.lease(await fixture.run(agent, await fixture.conversation(agent)))
        accounts = await call(context, "list_accounts")
        scope = {item["connection_id"]: item["in_execution_scope"] for item in accounts["accounts"]}
        assert scope[primary] is True and scope[secondary] is False
        other = await call(context, "account_read", account_id=secondary)
        assert "positions" in other and other["execution_scope"]["account_id"] == primary
        quote = await call(context, "market_quote", account_id=secondary, symbol="XAUUSD")
        assert quote["symbol"] == "XAUUSD"
        assert (await call(context, "account_activity", account_id=secondary))["activities"] == []
        # Another account's records are read whole, not filtered to the focus symbol.
        await other_symbol_records(fixture, secondary)
        records = await call(context, "trade_record_history", account_id=secondary)
        assert [item["symbol"] for item in records["records"]] == ["EURUSD"], records
        decisions = await call(context, "market_decision_history", account_id=secondary)
        assert [item["symbol"] for item in decisions["decisions"]] == ["EURUSD"], decisions
        assert decisions["decisions"][0]["recorded_by"]["you"] is False
        # The focus account still defaults to the focus symbol.
        assert (await call(context, "trade_record_history"))["records"] == []
        with pytest.raises(LonoraError, match="agent_trading_account_mismatch"):
            await call(
                context,
                "trade_execute",
                account_id=secondary,
                symbol="XAUUSD",
                action="buy",
                volume="0.1",
            )
        with pytest.raises(LonoraError, match="agent_trading_account_mismatch"):
            await call(
                context,
                "watch_create",
                account_id=secondary,
                symbol="XAUUSD",
                kind="price",
                condition="above",
                level="120",
                prompt="Another account's watch",
            )
    finally:
        await retire(fixture, primary, secondary)
        await fixture.close()


async def reach_me(fixture: Any, **policy: Any) -> None:
    from lonora_db.owner_profile import REACH_ME_KEY
    from lonora_db.transactions import SettingsRepository

    async with fixture.runtime.db.sessions() as session, session.begin():
        await SettingsRepository().put(
            session,
            REACH_ME_KEY + fixture.owner,
            IncomingCallPolicy.model_validate(policy).model_dump(mode="json"),
        )


@pytest.mark.asyncio
async def test_owner_notify_follows_dedupe_quiet_hours_rate_and_reach_me():
    database()
    from check_streaming import Fixture
    from lonora_db.attention import NOTIFY_LIMIT_PER_HOUR
    from lonora_db.owner_profile import REACH_ME_KEY
    from lonora_db.schema import AttentionRow, DeviceCredentialRow, SettingRow
    from sqlalchemy import delete

    fixture = await Fixture().open()
    device = "device-" + uuid4().hex[:12]
    try:
        from lonora_db.attention import NOTIFY_EVENT
        from lonora_db.schema import EventRow

        # The owner-wide critical cap counts this shared owner's earlier test alerts.
        async with fixture.runtime.db.sessions() as session, session.begin():
            await session.execute(
                delete(EventRow).where(
                    EventRow.owner_id == fixture.owner, EventRow.kind == NOTIFY_EVENT
                )
            )
        agent = await fixture.agent("Notifier")
        context, origin = await wake_run(fixture, agent, observe_only=True)
        await reach_me(fixture, channel="message")
        alert = {
            "importance": "critical",
            "summary": "توقف الذهب عند وقف الخسارة؛ الصفقة أغلقت",
            "evidence_refs": ["broker:sim-gold-1"],
            "dedupe_key": "gold-stop-" + uuid4().hex[:6],
        }
        first = await call(context, "owner_notify", **alert)
        assert first["status"] == "ready" and first["delivery"] == "in_app", first
        assert first["execution_authorized"] is False and "Off-app" in first["note"]
        item = first["attention"]
        # The wake reports in the Agent's conversation, where the owner opens it.
        assert item["thread_id"] == origin and item["code"] == "agent_notification"
        assert item["parameters"]["summary"] == alert["summary"]
        again = await call(context, "owner_notify", **alert)
        assert again["deduplicated"] is True and again["attention_id"] == first["attention_id"]
        # Quiet hours hold everything but critical alerts until they end.
        hour = utcnow().hour
        await reach_me(
            fixture,
            channel="message",
            quiet_start_hour=hour,
            quiet_end_hour=(hour + 2) % 24,
        )
        held = await call(
            context,
            "owner_notify",
            importance="important_change",
            summary="DXY broke the weekly high",
            dedupe_key="dxy-" + uuid4().hex[:6],
        )
        assert held["status"] == "held_for_quiet_hours", held
        async with fixture.runtime.db.sessions() as session:
            row = await session.get(AttentionRow, held["attention_id"])
            assert row is not None and row.status == "pending"
            assert row.due_at.isoformat() == held["held_until"]
        urgent = await call(
            context,
            "owner_notify",
            importance="critical",
            summary="Margin level is close to the stop-out",
            dedupe_key="margin-" + uuid4().hex[:6],
        )
        assert urgent["status"] == "ready"
        # "Activity only" keeps non-critical alerts out of the owner's notifications.
        await reach_me(fixture, channel="activity")
        quiet = await call(
            context,
            "owner_notify",
            importance="important_change",
            summary="Silver range is tightening",
            dedupe_key="silver-" + uuid4().hex[:6],
        )
        assert quiet["status"] == "activity_only" and quiet["attention_id"] is None
        # The Agent is told where the record goes instead of a notification.
        assert "your reply" in quiet["note"] and "Shown in" not in quiet["note"]
        # A bounded rate per Agent and hour.
        await reach_me(fixture, channel="message")
        sent = 4  # Every alert counts, the activity-only one too.
        while sent < NOTIFY_LIMIT_PER_HOUR:
            await call(
                context,
                "owner_notify",
                importance="important_change",
                summary="Another meaningful change " + str(sent),
                dedupe_key="burst-" + uuid4().hex[:8],
            )
            sent += 1
        with pytest.raises(LonoraError, match="owner_notify_rate_limited"):
            await call(
                context,
                "owner_notify",
                importance="important_change",
                summary="One alert too many this hour",
                dedupe_key="burst-" + uuid4().hex[:8],
            )
        # owner_call_request can target the Agent's own alert from the wake.
        async with fixture.runtime.db.sessions() as session, session.begin():
            session.add(
                DeviceCredentialRow(
                    id=device,
                    owner_id=fixture.owner,
                    name="Owner phone",
                    credential_id="notify-" + device,
                    public_key="fixture-not-authentication",
                    sign_count=0,
                    revoked=False,
                )
            )
        await reach_me(fixture, channel="call", device_id=device)
        ring = await call(
            context,
            "owner_call_request",
            attention_id=first["attention_id"],
            reason="The gold position closed at its stop loss",
        )
        assert ring["call"]["attention_id"] == first["attention_id"], ring
        assert ring["execution_authorized"] is False
    finally:
        async with fixture.runtime.db.sessions() as session, session.begin():
            await session.execute(
                delete(SettingRow).where(SettingRow.key == REACH_ME_KEY + fixture.owner)
            )
            row = await session.get(DeviceCredentialRow, device)
            if row is not None:
                await session.delete(row)
        await fixture.close()


@pytest.mark.asyncio
async def test_agent_declared_critical_alerts_are_capped_per_owner():
    database()
    from datetime import timedelta

    from check_streaming import Fixture
    from lonora_contracts.attention import OwnerNotifyRequest
    from lonora_contracts.domain import utcnow
    from lonora_db.attention import CRITICAL_LIMIT_PER_HOUR, NOTIFY_EVENT, notify_owner
    from lonora_db.schema import AttentionRow, EventRow
    from sqlalchemy import delete, func, select

    fixture = await Fixture().open()
    agents: list[str] = []
    try:
        async with fixture.runtime.db.sessions() as session:
            earlier = int(
                await session.scalar(
                    select(func.count())
                    .select_from(EventRow)
                    .where(
                        EventRow.owner_id == fixture.owner,
                        EventRow.kind == NOTIFY_EVENT,
                        EventRow.created_at > utcnow() - timedelta(hours=1),
                        EventRow.payload["importance"].as_string() == "critical",
                    )
                )
                or 0
            )
        allowed = max(CRITICAL_LIMIT_PER_HOUR - earlier, 0)
        results: list[dict[str, Any]] = []
        for index in range(allowed + 2):
            # One alert per agent: the per-agent rate never decides here.
            agent = await fixture.agent("Alert " + str(index))
            agents.append(agent["id"])
            thread = await fixture.conversation(agent)
            async with fixture.runtime.db.sessions() as session, session.begin():
                results.append(
                    await notify_owner(
                        session,
                        fixture.owner,
                        agent["id"],
                        thread["id"],
                        OwnerNotifyRequest(
                            importance="critical",
                            summary="Gold broke the level, act now " + str(index),
                            dedupe_key="critical-" + uuid4().hex,
                        ),
                    )
                )
        async with fixture.runtime.db.sessions() as session:
            importances = [
                (await session.get(AttentionRow, item["attention_id"])).importance  # type: ignore[union-attr]
                for item in results
                if item.get("attention_id")
            ]
        assert importances[:allowed] == ["critical"] * allowed, importances
        assert importances[allowed:] == ["important_change"] * 2, importances
    finally:
        # Other tests share this owner: their critical alerts must not meet this cap.
        async with fixture.runtime.db.sessions() as session, session.begin():
            await session.execute(
                delete(EventRow).where(EventRow.kind == NOTIFY_EVENT, EventRow.agent_id.in_(agents))
            )
        await fixture.close()
