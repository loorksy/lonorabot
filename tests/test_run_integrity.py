"""Run integrity at the execution door (mandate 6.9, 14.3.4).

The door keeps the run lease, the run's Task authority, the refusal of research subagent
runs and of observe-only broker-activity wakes, and walks every ancestor run with the same
checks. A paused Task still lets risk-reducing requests through (4.7). Runs on the real
migrated PostgreSQL schema (skipped without ``LONORA_DATABASE_URL``).
"""

from decimal import Decimal
from typing import Any

import pytest
from lonora_contracts.runs import Lease
from lonora_core.user_error import LonoraError
from test_proactive_wakes import database


async def check(fixture: Any, lease: Lease, *, reducing: bool = False) -> str | None:
    """The door's run-integrity check for ``lease``: None, or the refusal code."""
    from lonora_trading.execution import require_goal_lineage

    async with fixture.runtime.db.sessions() as session:
        try:
            await require_goal_lineage(session, lease, fixture.owner, reducing=reducing)
        except LonoraError as error:
            return error.code
    return None


async def change_run(fixture: Any, run_id: str, **fields: Any) -> None:
    from lonora_db.schema import RunRow

    async with fixture.runtime.db.sessions() as session, session.begin():
        row = await session.get(RunRow, run_id, with_for_update=True)
        assert row is not None
        for key, value in fields.items():
            setattr(row, key, value)


@pytest.mark.asyncio
async def test_the_door_keeps_lease_subagent_observe_only_and_ancestry_checks() -> None:
    database()
    from check_streaming import Fixture

    fixture = await Fixture().open()
    try:
        agent = await fixture.agent("Integrity")
        thread = await fixture.conversation(agent)
        parent = await fixture.lease(await fixture.run(agent, thread))
        child = await fixture.lease(await fixture.run(agent, thread))
        lease = child.lease
        assert await check(fixture, lease) is None
        # The lease: a stale fence is refused.
        assert await check(fixture, lease.model_copy(update={"fence": lease.fence + 1})) == (
            "stale_lease"
        )
        # A research subagent run and an observe-only wake never send.
        await change_run(fixture, lease.run_id, trigger="subagent")
        assert await check(fixture, lease) == "observe_only_execution_forbidden"
        await change_run(
            fixture, lease.run_id, trigger="user", model_metadata={"authority": "observe_only"}
        )
        assert await check(fixture, lease) == "observe_only_execution_forbidden"
        await change_run(fixture, lease.run_id, model_metadata={})
        # Every ancestor is checked the same way.
        await change_run(fixture, lease.run_id, parent_run_id=parent.lease.run_id)
        assert await check(fixture, lease) is None
        await change_run(fixture, parent.lease.run_id, model_metadata={"authority": "observe_only"})
        assert await check(fixture, lease) == "observe_only_execution_forbidden"
        await change_run(fixture, parent.lease.run_id, model_metadata={}, trigger="subagent")
        assert await check(fixture, lease) == "observe_only_execution_forbidden"
        # A cycle in the ancestry is refused.
        await change_run(fixture, parent.lease.run_id, trigger="user", parent_run_id=lease.run_id)
        assert await check(fixture, lease) == "goal_run_ancestry_invalid"
    finally:
        await fixture.close()


@pytest.mark.asyncio
async def test_task_authority_refuses_stopped_work_and_lets_a_paused_task_reduce_risk() -> None:
    database()
    from check_streaming import Fixture
    from lonora_contracts.tasks import TaskControl, TaskCreate
    from lonora_db.tasks import control_task, create_task, get_task

    fixture = await Fixture().open()
    try:
        agent = await fixture.agent("Task integrity")
        thread = await fixture.conversation(agent)
        other = await fixture.conversation(await fixture.agent("Other"))
        context = await fixture.lease(await fixture.run(agent, thread))
        lease = context.lease
        async with fixture.runtime.db.sessions() as session, session.begin():
            task = await create_task(
                session, fixture.owner, agent["id"], thread["id"], TaskCreate(title="Manage")
            )
            task_id, task_thread = task.id, task.thread_id
        await change_run(
            fixture, lease.run_id, thread_id=task_thread, model_metadata={"task_id": task_id}
        )
        assert await check(fixture, lease) is None
        # A run must belong to its Task's agent and conversation.
        await change_run(fixture, lease.run_id, thread_id=other["id"])
        assert await check(fixture, lease) == "task_run_mismatch"
        await change_run(fixture, lease.run_id, thread_id=task_thread)
        # A paused Task sends no new risk, and still reduces its risk.
        async with fixture.runtime.db.sessions() as session, session.begin():
            row = await get_task(session, fixture.owner, task_id)
            await control_task(
                session,
                fixture.owner,
                TaskControl(task_id=task_id, action="pause", expected_version=row.version),
            )
        assert await check(fixture, lease) == "task_execution_stopped"
        assert await check(fixture, lease, reducing=True) is None
        # A cancelled Task sends nothing.
        async with fixture.runtime.db.sessions() as session, session.begin():
            row = await get_task(session, fixture.owner, task_id)
            await control_task(
                session,
                fixture.owner,
                TaskControl(task_id=task_id, action="cancel", expected_version=row.version),
            )
        assert await check(fixture, lease, reducing=True) == "task_execution_stopped"
        # Shadow runs never send.
        await change_run(fixture, lease.run_id, model_metadata={"execution_mode": "shadow"})
        assert await check(fixture, lease, reducing=True) == "shadow_execution_forbidden"
    finally:
        await fixture.close()


@pytest.mark.asyncio
async def test_a_paused_tasks_run_tightens_a_stop_but_never_widens_it() -> None:
    """The final send check classifies against the broker's ticket (4.0): a stop moved
    away passes the first, static check and is refused at send, unsent; a stop moved
    toward the market is sent while the Task is paused (4.7, 6.9)."""
    database()
    from check_streaming import Fixture
    from lonora_contracts.tasks import TaskControl, TaskCreate
    from lonora_contracts.trading import TradingControl
    from lonora_db.tasks import control_task, create_task, get_task
    from lonora_db.trading_mode import set_trading_mode
    from lonora_trading.controls import read_controls, save_controls
    from test_proactive_wakes import call, retire, simulation

    fixture = await Fixture().open()
    original = await read_controls(fixture.runtime.db)
    connection = ""
    try:
        connection = await simulation(fixture, [])
        await save_controls(fixture.runtime.db, TradingControl(enabled=True))
        agent = await fixture.agent("Paused task stops", supervised=True)
        thread = await fixture.conversation(agent)
        async with fixture.runtime.db.sessions() as session, session.begin():
            await set_trading_mode(session, fixture.owner, agent["id"], "full", by="owner_tap")
            task = await create_task(
                session, fixture.owner, agent["id"], thread["id"], TaskCreate(title="Manage")
            )
            task_id, task_thread = task.id, task.thread_id
        opener = await fixture.lease(await fixture.run(agent, thread))
        opened = await call(
            opener,
            "trade_execute",
            action="buy",
            account_id=connection,
            symbol="XAUUSD",
            volume="0.1",
            stop_loss="95",
        )
        assert opened.get("status") == "confirmed", opened
        run = await fixture.run(agent, thread)
        await change_run(
            fixture, run["id"], thread_id=task_thread, model_metadata={"task_id": task_id}
        )
        context = await fixture.lease({**run, "thread_id": task_thread})
        async with fixture.runtime.db.sessions() as session, session.begin():
            row = await get_task(session, fixture.owner, task_id)
            await control_task(
                session,
                fixture.owner,
                TaskControl(task_id=task_id, action="pause", expected_version=row.version),
            )
        modify = {
            "action": "modify_position",
            "account_id": connection,
            "symbol": "XAUUSD",
            "position_id": opened["broker_id"],
        }
        widened = None
        try:
            widened = await call(context, "trade_execute", **modify, stop_loss="90")
        except LonoraError as error:
            assert error.code == "task_execution_stopped", error.code
        else:
            assert widened.get("code") == "task_execution_stopped", widened
            assert widened["details"]["send_state"] == "not_sent", widened
        tightened = await call(context, "trade_execute", **modify, stop_loss="97")
        assert tightened.get("status") == "confirmed", tightened
        broker = await fixture.runtime.services(fixture.owner).brokers.get(
            fixture.owner, connection
        )
        (position,) = await broker.positions()
        assert position.stop_loss == Decimal("97")
    finally:
        await save_controls(fixture.runtime.db, original)
        await retire(fixture, connection)
        await fixture.close()


@pytest.mark.asyncio
async def test_a_bound_agents_replayed_order_is_the_same_operation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Risk 4 of the phase 6 map: dropping the binding refusal keeps the argument fill,
    so a bound agent's replayed call hashes the same arguments, derives the same
    operation id, answers from the journal and never sends twice (6.2, 6.3)."""
    database()
    from check_streaming import Fixture
    from lonora_contracts.trading import TradingControl
    from lonora_db.schema import AgentRow, TradingJournalRow
    from lonora_db.trading_mode import set_trading_mode
    from lonora_trading.controls import read_controls, save_controls
    from sqlalchemy import func, select
    from test_proactive_wakes import retire, simulation
    from test_trading_mode_tools import same_call

    fixture = await Fixture().open()
    original = await read_controls(fixture.runtime.db)
    connection = ""
    try:
        connection = await simulation(fixture, [])
        await save_controls(fixture.runtime.db, TradingControl(enabled=True))
        agent = await fixture.agent("Bound replay", supervised=True)
        async with fixture.runtime.db.sessions() as session, session.begin():
            row = await session.get(AgentRow, agent["id"])
            assert row is not None
            row.role = "specialist"
            row.trading_account_id, row.trading_symbol = connection, "XAUUSD"
            await set_trading_mode(session, fixture.owner, agent["id"], "full", by="owner_tap")
        context = await fixture.lease(await fixture.run(agent, await fixture.conversation(agent)))
        from lonora_session.idempotency import request_hash, stable_id
        from lonora_tools import trade

        hashed: list[dict[str, Any]] = []
        derive = trade.operation_id

        def spy(run_id: str, agent_id: str, args: dict[str, Any], key: str | None) -> str:
            hashed.append(dict(args))
            return derive(run_id, agent_id, args, key)

        monkeypatch.setattr(trade, "operation_id", spy)
        # Account and symbol are omitted: the focus pair fills them before the id is hashed.
        first = await same_call(
            context, "bound-buy", "trade_execute", action="buy", volume="0.1", stop_loss="95"
        )
        again = await same_call(
            context, "bound-buy", "trade_execute", action="buy", volume="0.1", stop_loss="95"
        )
        assert first.get("status") == "confirmed", first
        assert again["operation_id"] == first["operation_id"]
        # The derivation 6.2 pins: the run's id over the arguments with the pair filled in,
        # as before this change, so a row journaled before it replays to the same id.
        assert hashed[0]["account_id"] == connection and hashed[0]["symbol"] == "XAUUSD"
        assert first["operation_id"] == stable_id(
            context.lease.run_id, "trade:" + request_hash(hashed[0])
        )
        broker = await fixture.runtime.services(fixture.owner).brokers.get(
            fixture.owner, connection
        )
        assert len(await broker.positions()) == 1
        async with fixture.runtime.db.sessions() as session:
            journaled = await session.scalar(
                select(func.count())
                .select_from(TradingJournalRow)
                .where(TradingJournalRow.operation_id == first["operation_id"])
            )
        assert journaled == 1
    finally:
        await save_controls(fixture.runtime.db, original)
        await retire(fixture, connection)
        await fixture.close()


class FakeSession:
    """``session.get`` over in-memory rows: enough for the door's run-integrity walk."""

    def __init__(self, *rows: Any) -> None:
        self.rows: dict[tuple[type, str], Any] = {(type(row), row.id): row for row in rows}

    async def get(self, model: Any, identifier: str, **_: Any) -> Any:
        return self.rows.get((model, identifier))


def task_rows(status: str, control: str | None, *, run_id: str = "run", parent: str | None = None):
    from lonora_contracts.tasks import TaskState
    from lonora_db.schema import RunRow, TicketRow

    state = TaskState(
        origin_thread_id="thread",
        status=status,  # type: ignore[arg-type]
        control_requested=control,  # type: ignore[arg-type]
    )
    task = TicketRow(
        id="task-" + run_id,
        agent_id="agent",
        thread_id="thread",
        state={"task": state.model_dump()},
    )
    run = RunRow(
        id=run_id,
        agent_id="agent",
        thread_id="thread",
        trigger="user",
        parent_run_id=parent,
        model_metadata={"task_id": task.id},
    )
    return run, task


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("status", "control", "reducing_passes"),
    [
        ("paused", None, True),
        ("running", "pause", True),
        ("queued", None, True),
        ("cancelled", "pause", False),
        ("completed", "pause", False),
        ("failed", "pause", False),
        ("paused", "cancel", False),
        ("paused", "complete", False),
        ("cancelled", None, False),
    ],
)
async def test_only_paused_work_lets_a_risk_reducing_request_through(
    status: str, control: str | None, reducing_passes: bool
) -> None:
    """6.9: paused work reduces its risk; cancelled, completed or failed work, or work
    asked to cancel or complete, sends nothing at all."""
    from lonora_trading.execution import require_task_authority

    run, task = task_rows(status, control)
    session: Any = FakeSession(run, task)
    running = status in {"queued", "running"} and control is None
    if not running:
        with pytest.raises(LonoraError, match="task_execution_stopped"):
            await require_task_authority(session, run)
    if reducing_passes:
        await require_task_authority(session, run, reducing=True)
    else:
        with pytest.raises(LonoraError, match="task_execution_stopped"):
            await require_task_authority(session, run, reducing=True)


@pytest.mark.asyncio
async def test_the_ancestry_walk_checks_every_ancestors_task(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """6.9: a parent run's paused Task refuses new risk and lets risk reduction through;
    a cancelled parent Task refuses both; a missing parent is refused."""
    from unittest.mock import AsyncMock

    from lonora_trading import execution

    child_task = task_rows("running", None, run_id="child")[1]
    for status, reducing, refused in (
        ("paused", False, "task_execution_stopped"),
        ("paused", True, None),
        ("cancelled", True, "task_execution_stopped"),
    ):
        parent, parent_task = task_rows(status, None, run_id="parent")
        child, _ = task_rows("running", None, run_id="child", parent="parent")
        session: Any = FakeSession(child, child_task, parent, parent_task)
        monkeypatch.setattr(execution, "require_lease", AsyncMock(return_value=child))
        for check in ("acting_agent", "require_financial_agent"):
            if hasattr(execution, check):  # The agent's ownership check, here a no-op.
                monkeypatch.setattr(execution, check, AsyncMock())
        lease = Lease(run_id="child", owner="worker", fence=1)
        if refused is None:
            await execution.require_goal_lineage(session, lease, "owner", reducing=reducing)
        else:
            with pytest.raises(LonoraError, match=refused):
                await execution.require_goal_lineage(session, lease, "owner", reducing=reducing)
    orphan, _ = task_rows("running", None, run_id="child", parent="gone")
    monkeypatch.setattr(execution, "require_lease", AsyncMock(return_value=orphan))
    with pytest.raises(LonoraError, match="goal_run_ancestry_invalid"):
        await execution.require_goal_lineage(
            FakeSession(orphan, child_task),  # type: ignore[arg-type]
            Lease(run_id="child", owner="worker", fence=1),
            "owner",
        )
