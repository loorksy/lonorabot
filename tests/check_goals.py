"""Disposable PostgreSQL same-agent goal/watch/execution recovery; explicit simulation only."""

import asyncio
import json
import os
import sys
from collections.abc import Awaitable, Callable
from datetime import timedelta
from decimal import Decimal
from typing import Any
from uuid import uuid4

from check_streaming import Fixture
from lonora_adapter_kit.model import ModelAdapter
from lonora_adapter_kit.types import ModelMessage, ModelReply, ToolCall, ToolDefinition
from lonora_adapters.brokers.simulation import SimulationBroker
from lonora_agent.context.goals import MAX_GOAL_CONTEXT_CHARS, goal_context
from lonora_agent.runtime import AgentRuntime
from lonora_contracts.account import Position
from lonora_contracts.domain import utcnow
from lonora_contracts.market import Quote
from lonora_contracts.model_catalog import ModelDescriptor
from lonora_contracts.model_routing import ModelSelection, RoutingPolicy
from lonora_contracts.runs import Lease, RunRequest
from lonora_contracts.trading import TradeRequest, TradeResult, TradingControl
from lonora_contracts.trading_goal import GoalControl
from lonora_core.user_error import LonoraError
from lonora_db.routines import enqueue_due
from lonora_db.runs import claim_next, complete_run, create_run, run_data
from lonora_db.schema import (
    GoalDecisionRow,
    MarketWatchRow,
    MessageRow,
    RoutineRow,
    RunRow,
    SecretRow,
    TradingAccountRow,
    TradingGoalRow,
    TradingJournalRow,
)
from lonora_db.trading_goals import control_goal, owned_goal
from lonora_gateway.run_dispatch import dispatch_one
from lonora_market.watchers import check_watches
from lonora_providers.routing_policy import read_policy, save_policy
from lonora_session.idempotency import stable_id
from lonora_tools.context import ToolContext
from lonora_tools.loader import load_tools
from lonora_trading.controls import read_controls, save_controls
from lonora_trading.goals import execute_goal_step, recover_goals
from lonora_trading.reconciliation import reconcile_ambiguous
from sqlalchemy import delete, select


class GateBroker(SimulationBroker):
    def __init__(self, *args: Any):
        super().__init__(*args)
        self.before: Callable[[], Awaitable[None]] | None = None
        self.sent = 0
        self.mode = "confirmed"

    async def execute(
        self, request: TradeRequest, before_send: Callable[[], Awaitable[None]] | None = None
    ) -> TradeResult:
        if self.before:
            await self.before()
        result = await super().execute(request, before_send)
        self.sent += 1
        if self.mode == "crash":
            os._exit(24)
        if self.mode == "ambiguous":
            return TradeResult(
                operation_id=request.operation_id,
                status="ambiguous",
                code="explicit_fixture_response_lost",
            )
        return result


async def checks() -> None:
    fixture = await Fixture().open()
    db = fixture.runtime.db
    services = fixture.runtime.services(fixture.owner)
    original_policy = await read_policy(db)
    original_factory = None
    fixture_secret_id: str | None = None
    old_ciphertext: str | None = None
    original_controls = await read_controls(db)
    await save_controls(db, TradingControl(enabled=True))
    goals: list[str] = []
    accounts: list[str] = []
    operations: list[str] = []
    watches: list[str] = []
    try:
        agent = await fixture.agent("Goal fixture specialist")
        thread = await fixture.conversation(agent)
        connection = await fixture.request(
            "POST",
            "/trading/connections",
            {"provider": "simulation", "account_id": "explicit-goal-fixture", "enabled": True},
        )
        account_id = connection["id"]
        accounts.append(account_id)
        now = utcnow()
        await fixture.request(
            "POST",
            f"/trading/connections/{account_id}/simulation",
            {
                "snapshot": {
                    "currency": "USD",
                    "balance": "1000",
                    "instruments": [
                        {
                            "symbol": "FIXTURE",
                            "digits": 2,
                            "tick_size": "0.01",
                            "volume_min": "0.1",
                            "volume_max": "10",
                            "volume_step": "0.1",
                        }
                    ],
                    "quotes": {
                        "FIXTURE": {
                            "symbol": "FIXTURE",
                            "bid": "11",
                            "ask": "11.01",
                            "observed_at": now.isoformat(),
                            "source": "explicit simulation fixture",
                        }
                    },
                    "positions": [],
                    "orders": [],
                }
            },
        )
        services = fixture.runtime.services(fixture.owner)
        brokers, executor = services.brokers, services.trading
        registry = load_tools()
        origin = await fixture.run(agent, thread)
        origin_context = await fixture.lease(origin)
        trade = {"account_id": account_id, "symbol": "FIXTURE", "action": "buy", "volume": "0.1"}
        payload = {
            "title": "Explicit fixture goal",
            "objective": "Scripted lifecycle, no promised return",
            "account_id": account_id,
            "symbol": "FIXTURE",
            "autonomous": True,
            "maximum_volume": "0.1",
            "max_trade_actions": 3,
            "steps": [
                {"id": "analysis", "title": "Inspect evidence", "kind": "analysis"},
                {
                    "id": "entry",
                    "title": "Wait for condition then entry",
                    "kind": "trade",
                    "trade": trade,
                    "condition": {
                        "kind": "price",
                        "account_id": account_id,
                        "symbol": "FIXTURE",
                        "condition": "above",
                        "level": "10",
                        "prompt": "Revalidate entry",
                    },
                },
                {
                    "id": "monitor",
                    "title": "Watch actual entry position profit",
                    "kind": "watch",
                    "condition": {
                        "kind": "position",
                        "account_id": account_id,
                        "symbol": "FIXTURE",
                        "target_step_id": "entry",
                        "condition": "above",
                        "metric": "profit",
                        "level": "1",
                        "prompt": "Recheck position",
                    },
                },
                {
                    "id": "protect",
                    "title": "Modify actual entry protection",
                    "kind": "trade",
                    "trade": {
                        "account_id": account_id,
                        "symbol": "FIXTURE",
                        "action": "modify_position",
                        "target_step_id": "entry",
                        "stop_loss": "10.50",
                    },
                },
                {
                    "id": "exit",
                    "title": "Close confirmed position",
                    "kind": "trade",
                    "trade": {
                        "account_id": account_id,
                        "symbol": "FIXTURE",
                        "action": "close_position",
                        "target_step_id": "entry",
                    },
                },
            ],
        }
        created = await registry.execute(
            __import__("lonora_adapter_kit.types", fromlist=["ToolCall"]).ToolCall(
                id="create-goal", name="goal_create", arguments=payload
            ),
            origin_context,
        )
        goal_id = created["id"]
        goals.append(goal_id)
        assert created["state"]["autonomous"] is False  # model cannot self-enable
        assert created["thread_id"] == thread["id"] and created["agent_id"] == agent["id"]

        async def tool(context: ToolContext, name: str, args: dict[str, Any]) -> dict[str, Any]:
            from lonora_adapter_kit.types import ToolCall

            return await registry.execute(
                ToolCall(id=uuid4().hex, name=name, arguments=args), context
            )

        await tool(
            origin_context,
            "goal_step_complete",
            {
                "goal_id": goal_id,
                "step_id": "analysis",
                "note": "Explicit inspected fixture evidence",
            },
        )
        waiting = await tool(origin_context, "goal_wait", {"goal_id": goal_id, "step_id": "entry"})
        watches.append(waiting["wake_source"]["id"])
        assert waiting["goal"]["state"]["status"] == "waiting"
        async with db.sessions() as session, session.begin():
            await complete_run(session, origin_context.lease, "Waiting on saved fixture goal", {})
        assert (
            await check_watches(
                db,
                brokers,
                price_update=Quote(
                    symbol="FIXTURE",
                    bid=Decimal("11"),
                    ask=Decimal("11.01"),
                    observed_at=now,
                    source="explicit fixture",
                ),
                connection_id=account_id,
                owner_id=fixture.owner,
            )
            == 1
        )

        async def newest_context() -> ToolContext:
            async with db.sessions() as session:
                row = await session.scalar(
                    select(RunRow)
                    .where(RunRow.thread_id == thread["id"], RunRow.status == "queued")
                    .order_by(RunRow.created_at.desc())
                    .limit(1)
                )
                assert row is not None
                assert row.model_metadata["goal_id"] == goal_id
                data = run_data(row)
            return await fixture.lease(data)

        entry_context = await newest_context()
        try:
            await execute_goal_step(
                db, brokers, executor, fixture.owner, goal_id, "entry", entry_context.lease
            )
            raise AssertionError("Background autonomy bypass")
        except LonoraError as error:
            assert error.code == "goal_autonomy_required"
        async with db.sessions() as session, session.begin():
            goal = await owned_goal(session, fixture.owner, goal_id)
            await control_goal(
                session,
                fixture.owner,
                goal_id,
                GoalControl(version=goal.version, action="resume", autonomous=True),
            )
        try:
            await executor.execute(
                fixture.owner, TradeRequest.model_validate(trade), entry_context.lease
            )
            raise AssertionError("Ordinary trade bypassed goal")
        except LonoraError as error:
            assert error.code == "goal_step_required"
        result = await execute_goal_step(
            db,
            brokers,
            executor,
            fixture.owner,
            goal_id,
            "entry",
            entry_context.lease,
            "Actual fixture condition satisfied",
        )
        operations.append(result["operation_id"])
        assert result["result"]["status"] == "confirmed"
        replay = await execute_goal_step(
            db, brokers, executor, fixture.owner, goal_id, "entry", entry_context.lease
        )
        assert replay["deduplicated"] and replay["operation_id"] == result["operation_id"]
        position_id = result["result"]["broker_id"]
        assert len(await (await brokers.get(fixture.owner, account_id)).positions()) == 1
        waiting = await tool(entry_context, "goal_wait", {"goal_id": goal_id, "step_id": "monitor"})
        watches.append(waiting["wake_source"]["id"])
        assert waiting["wake_source"]["payload"]["position_id"] == position_id
        async with db.sessions() as session, session.begin():
            await complete_run(
                session, entry_context.lease, "Entry confirmed; waiting for actual position", {}
            )
            snapshot = await session.get(TradingAccountRow, account_id, with_for_update=True)
            assert snapshot is not None
            positions = [{**item, "profit": "2"} for item in snapshot.payload["positions"]]
            snapshot.payload = {**snapshot.payload, "positions": positions}
        assert await check_watches(db, brokers, owner_id=fixture.owner) == 1
        monitor_context = await newest_context()
        async with db.sessions() as session:
            block = await goal_context(session, fixture.owner, agent["id"], thread["id"], goal_id)
            assert "target_step_id" in block and position_id in block and "autonomy" in block
        requested_step = await tool(
            monitor_context, "goal_read", {"goal_id": goal_id, "step_id": "protect"}
        )
        assert requested_step["step"]["trade"]["action"] == "modify_position"
        await tool(
            monitor_context,
            "goal_step_complete",
            {
                "goal_id": goal_id,
                "step_id": "monitor",
                "note": "Fresh actual fixture position profit confirmed",
            },
        )
        modified = await execute_goal_step(
            db, brokers, executor, fixture.owner, goal_id, "protect", monitor_context.lease
        )
        operations.append(modified["operation_id"])
        actual = await (await brokers.get(fixture.owner, account_id)).positions()
        assert actual[0].id == position_id and str(actual[0].stop_loss) == "10.50"
        exited = await execute_goal_step(
            db, brokers, executor, fixture.owner, goal_id, "exit", monitor_context.lease
        )
        operations.append(exited["operation_id"])
        assert (
            exited["result"]["status"] == "confirmed"
            and not await (await brokers.get(fixture.owner, account_id)).positions()
        )
        final = await fixture.request("GET", f"/trading/goals/{goal_id}")
        assert final["state"]["status"] == "completed"
        assert len(await fixture.request("GET", f"/trading/goals/{goal_id}/decisions")) == 3
        async with db.sessions() as session, session.begin():
            await complete_run(session, monitor_context.lease, "Fixture closed loop completed", {})
        gate = GateBroker(db, fixture.owner, account_id)
        brokers.connections[account_id] = (1, gate)

        async def make_goal(steps: list[dict[str, Any]] | None = None) -> dict[str, Any]:
            row = await fixture.request(
                "POST",
                "/trading/goals",
                {
                    "agent_id": agent["id"],
                    "thread_id": thread["id"],
                    "title": "Safety fixture",
                    "objective": "Explicit scripted goal safety",
                    "account_id": account_id,
                    "symbol": "FIXTURE",
                    "autonomous": True,
                    "maximum_volume": "0.1",
                    "max_trade_actions": 3,
                    "steps": steps
                    or [
                        {
                            "id": "entry",
                            "title": "Exact declared fixture entry",
                            "kind": "trade",
                            "trade": trade,
                        }
                    ],
                },
            )
            goals.append(row["id"])
            return row

        async def goal_lease(row: dict[str, Any]) -> ToolContext:
            async with db.sessions() as session, session.begin():
                run = await create_run(
                    session,
                    fixture.owner,
                    RunRequest(
                        agent_id=agent["id"],
                        thread_id=thread["id"],
                        trigger="goal",
                        metadata={"goal_id": row["id"]},
                    ),
                )
                data = run_data(run)
            return await fixture.lease(data)

        async def finish(context: ToolContext) -> None:
            async with db.sessions() as session, session.begin():
                await complete_run(session, context.lease, "Explicit fixture turn ended", {})

        # Pause and cancel arriving after preflight but before send block the exact operation.
        for action in ("pause", "cancel"):
            row = await make_goal()
            context = await goal_lease(row)

            async def stop_goal(goal_id: str = row["id"], control_action: str = action) -> None:
                async with db.sessions() as session, session.begin():
                    current = await owned_goal(session, fixture.owner, goal_id)
                    await control_goal(
                        session,
                        fixture.owner,
                        goal_id,
                        GoalControl.model_validate(
                            {"version": current.version, "action": control_action}
                        ),
                    )

            gate.before = stop_goal
            sent = gate.sent
            result = await execute_goal_step(
                db, brokers, executor, fixture.owner, row["id"], "entry", context.lease
            )
            assert result["result"]["status"] == "failed" and gate.sent == sent
            actual_goal = await fixture.request("GET", f"/trading/goals/{row['id']}")
            assert actual_goal["state"]["status"] == (
                "paused" if action == "pause" else "cancelled"
            )
            if action == "pause":
                previous_operation = result["operation_id"]
                resumed = await fixture.request(
                    "POST",
                    f"/trading/goals/{row['id']}/control",
                    {"version": actual_goal["version"], "action": "resume"},
                )
                assert resumed["state"]["steps"]["entry"]["attempt"] == 2
                gate.before = None
                result = await execute_goal_step(
                    db, brokers, executor, fixture.owner, row["id"], "entry", context.lease
                )
                assert (
                    result["result"]["status"] == "confirmed"
                    and result["operation_id"] != previous_operation
                )
            gate.before = None
            await finish(context)

        # Emergency stop is independent of per-goal owner autonomy.
        row = await make_goal()
        context = await goal_lease(row)

        async def emergency() -> None:
            await save_controls(db, TradingControl(emergency_stop=True))

        gate.before = emergency
        sent = gate.sent
        result = await execute_goal_step(
            db, brokers, executor, fixture.owner, row["id"], "entry", context.lease
        )
        assert result["result"]["code"] == "emergency_stop" and gate.sent == sent
        gate.before = None
        await save_controls(db, TradingControl(enabled=True))
        await finish(context)

        # A lost response blocks the same step, survives recovery, never blindly resends.
        row = await make_goal()
        context = await goal_lease(row)
        gate.mode = "ambiguous"
        sent = gate.sent
        result = await execute_goal_step(
            db, brokers, executor, fixture.owner, row["id"], "entry", context.lease
        )
        assert result["result"]["status"] == "ambiguous" and gate.sent == sent + 1
        assert (await fixture.request("GET", f"/trading/goals/{row['id']}"))["state"][
            "status"
        ] == "blocked"
        replay = await execute_goal_step(
            db, brokers, executor, fixture.owner, row["id"], "entry", context.lease
        )
        assert replay["deduplicated"] and gate.sent == sent + 1
        assert await recover_goals(db) == 0
        assert await reconcile_ambiguous(db, brokers) >= 1
        assert await recover_goals(db) >= 1
        actual_goal = await fixture.request("GET", f"/trading/goals/{row['id']}")
        assert actual_goal["state"]["status"] == "completed" and gate.sent == sent + 1
        gate.mode = "confirmed"
        await finish(context)

        # Goal ancestry cannot escape the plan by delegating financial execution.
        child_agent = await fixture.agent("Research-only goal peer")
        child_thread = await fixture.conversation(child_agent)
        async with db.sessions() as session, session.begin():
            child = await create_run(
                session,
                fixture.owner,
                RunRequest(
                    agent_id=child_agent["id"],
                    thread_id=child_thread["id"],
                    trigger="peer",
                    parent_run_id=context.lease.run_id,
                ),
            )
            child_data = run_data(child)
        child_context = await fixture.lease(child_data)
        sent = gate.sent
        try:
            await executor.execute(
                fixture.owner, TradeRequest.model_validate(trade), child_context.lease
            )
            raise AssertionError("Peer escaped goal authority")
        except LonoraError as error:
            assert error.code == "goal_delegated_trade_forbidden" and gate.sent == sent
        await finish(child_context)

        # Real worker process death AFTER simulation receipt but BEFORE journal completion.
        row = await make_goal()
        context = await goal_lease(row)
        child = await asyncio.create_subprocess_exec(
            sys.executable, __file__, "crash-goal", row["id"], context.lease.model_dump_json()
        )
        assert await asyncio.wait_for(child.wait(), 20) == 24
        operation_id = stable_id(row["id"], "step:entry:attempt:1")
        async with db.sessions() as session, session.begin():
            journal = await session.get(TradingJournalRow, operation_id)
            assert journal is not None and journal.status == "submitted"
            running = await session.get(RunRow, context.lease.run_id)
            assert running is not None
            running.lease_expires_at = utcnow() - timedelta(seconds=1)
            journal.submitted_at = utcnow() - timedelta(minutes=2)
        async with db.sessions() as session, session.begin():
            recovered = await claim_next(session, "actual-fixture-restart", 300)
            assert recovered is not None and recovered.id == context.lease.run_id
            recovered.status = "running"  # same admission transition used by the resident executor
            recovered_lease = Lease(
                run_id=recovered.id, owner=recovered.lease_owner or "", fence=recovered.lease_fence
            )
        sent = gate.sent
        replay = await execute_goal_step(
            db, brokers, executor, fixture.owner, row["id"], "entry", recovered_lease
        )
        assert replay["result"]["status"] == "ambiguous" and gate.sent == sent
        assert await reconcile_ambiguous(db, brokers) >= 1
        await recover_goals(db)
        assert (await fixture.request("GET", f"/trading/goals/{row['id']}"))["state"][
            "status"
        ] == "completed"
        async with db.sessions() as session, session.begin():
            await complete_run(
                session, recovered_lease, "Restart recovered exact broker receipt", {}
            )

        # Pending acceptance is an order, not an invented position; wait across restart.
        row = await make_goal(
            [
                {
                    "id": "entry",
                    "title": "Pending entry",
                    "kind": "trade",
                    "trade": {**trade, "action": "buy_limit", "price": "10"},
                },
                {
                    "id": "monitor",
                    "title": "Wait for actual fill",
                    "kind": "watch",
                    "condition": {
                        "kind": "position",
                        "account_id": account_id,
                        "symbol": "FIXTURE",
                        "target_step_id": "entry",
                        "condition": "opened",
                        "prompt": "Observe actual position",
                    },
                },
                {
                    "id": "exit",
                    "title": "Close actual filled position",
                    "kind": "trade",
                    "trade": {
                        "account_id": account_id,
                        "symbol": "FIXTURE",
                        "action": "close_position",
                        "target_step_id": "entry",
                    },
                },
            ]
        )
        context = await goal_lease(row)
        accepted = await execute_goal_step(
            db, brokers, executor, fixture.owner, row["id"], "entry", context.lease
        )
        pending_order_id = accepted["result"]["broker_id"]
        waiting = await tool(context, "goal_wait", {"goal_id": row["id"], "step_id": "monitor"})
        assert waiting["waiting"] and waiting["code"] == "goal_target_pending"
        review_id = waiting["wake_source"]["id"]
        await finish(context)
        assert await recover_goals(db) == 0  # durable existing review is retained
        filled_position_id = uuid4().hex
        async with db.sessions() as session, session.begin():
            snapshot = await session.get(TradingAccountRow, account_id, with_for_update=True)
            assert snapshot is not None
            snapshot.payload = {
                **snapshot.payload,
                "orders": [
                    item for item in snapshot.payload["orders"] if item["id"] != pending_order_id
                ],
                "positions": [
                    *snapshot.payload["positions"],
                    Position(
                        id=filled_position_id,
                        symbol="FIXTURE",
                        side="buy",
                        volume=Decimal("0.1"),
                        open_price=Decimal("10"),
                        operation_id=accepted["operation_id"],
                    ).model_dump(mode="json"),
                ],
            }
            routine = await session.get(RoutineRow, review_id)
            assert routine is not None
            routine.next_run_at = utcnow() - timedelta(seconds=1)
        async with db.sessions() as session, session.begin():
            assert await enqueue_due(session) == 1
            review_run = await session.scalar(
                select(RunRow)
                .where(RunRow.thread_id == thread["id"], RunRow.status == "queued")
                .order_by(RunRow.created_at.desc())
                .limit(1)
            )
            assert review_run is not None and review_run.model_metadata["goal_id"] == row["id"]
            review_data = run_data(review_run)
        review_context = await fixture.lease(review_data)
        actual_watch = await tool(
            review_context, "goal_wait", {"goal_id": row["id"], "step_id": "monitor"}
        )
        watches.append(actual_watch["wake_source"]["id"])
        assert actual_watch["wake_source"]["payload"]["position_id"] == filled_position_id
        await finish(review_context)
        assert await check_watches(db, brokers, owner_id=fixture.owner) == 1
        async with db.sessions() as session:
            opened_run = await session.scalar(
                select(RunRow)
                .where(RunRow.thread_id == thread["id"], RunRow.status == "queued")
                .order_by(RunRow.created_at.desc())
                .limit(1)
            )
            assert opened_run is not None and opened_run.model_metadata["goal_id"] == row["id"]
            opened_data = run_data(opened_run)
        opened_context = await fixture.lease(opened_data)
        await tool(
            opened_context,
            "goal_step_complete",
            {
                "goal_id": row["id"],
                "step_id": "monitor",
                "note": "Actual pending order filled into verified position",
            },
        )
        closed = await execute_goal_step(
            db, brokers, executor, fixture.owner, row["id"], "exit", opened_context.lease
        )
        assert (
            closed["result"]["status"] == "confirmed"
            and closed["result"]["broker_id"] == filled_position_id
        )
        assert (await fixture.request("GET", f"/trading/goals/{row['id']}"))["state"][
            "status"
        ] == "completed"
        await finish(opened_context)
        # A crossing needs an actual durable watch receipt and must still hold at send time.
        row = await make_goal(
            [
                {
                    "id": "entry",
                    "title": "Verified crossing entry",
                    "kind": "trade",
                    "trade": trade,
                    "condition": {
                        "kind": "price",
                        "account_id": account_id,
                        "symbol": "FIXTURE",
                        "condition": "cross_above",
                        "level": "10",
                        "prompt": "Recheck actual crossing",
                    },
                }
            ]
        )
        context = await goal_lease(row)
        sent = gate.sent
        try:
            await execute_goal_step(
                db, brokers, executor, fixture.owner, row["id"], "entry", context.lease
            )
            raise AssertionError("Unobserved crossing authorized trade")
        except LonoraError as error:
            assert error.code == "goal_watch_evidence_required" and gate.sent == sent
        cross_wait = await tool(context, "goal_wait", {"goal_id": row["id"], "step_id": "entry"})
        watches.append(cross_wait["wake_source"]["id"])
        await finish(context)
        low = Quote(
            symbol="FIXTURE",
            bid=Decimal("9"),
            ask=Decimal("9.01"),
            observed_at=utcnow(),
            source="explicit crossing fixture",
        )
        assert (
            await check_watches(
                db, brokers, price_update=low, connection_id=account_id, owner_id=fixture.owner
            )
            == 0
        )
        high = Quote(
            symbol="FIXTURE",
            bid=Decimal("11"),
            ask=Decimal("11.01"),
            observed_at=utcnow(),
            source="explicit crossing fixture",
        )
        assert (
            await check_watches(
                db, brokers, price_update=high, connection_id=account_id, owner_id=fixture.owner
            )
            == 1
        )
        async with db.sessions() as session:
            crossing_run = await session.scalar(
                select(RunRow)
                .where(RunRow.thread_id == thread["id"], RunRow.status == "queued")
                .order_by(RunRow.created_at.desc())
                .limit(1)
            )
            assert crossing_run is not None and crossing_run.model_metadata.get("wake_receipt_id")
            crossing_data = run_data(crossing_run)
        crossing_context = await fixture.lease(crossing_data)

        async def actual_quote(value: Quote) -> None:
            async with db.sessions() as session, session.begin():
                snapshot = await session.get(TradingAccountRow, account_id, with_for_update=True)
                assert snapshot is not None
                snapshot.payload = {
                    **snapshot.payload,
                    "quotes": {"FIXTURE": value.model_dump(mode="json")},
                }

        await actual_quote(low.model_copy(update={"observed_at": utcnow()}))
        try:
            await execute_goal_step(
                db, brokers, executor, fixture.owner, row["id"], "entry", crossing_context.lease
            )
            raise AssertionError("Old crossing quote bypassed fresh broker condition")
        except LonoraError as error:
            assert error.code == "goal_condition_unmet" and gate.sent == sent
        await actual_quote(high.model_copy(update={"observed_at": utcnow()}))
        matched = await execute_goal_step(
            db, brokers, executor, fixture.owner, row["id"], "entry", crossing_context.lease
        )
        assert matched["result"]["status"] == "confirmed" and gate.sent == sent + 1
        await finish(crossing_context)
        # Versioned plan changes retire old watches/reviews instead of waking new intent.
        old_steps = [
            {
                "id": "entry",
                "title": "Old plan watch",
                "kind": "trade",
                "trade": trade,
                "condition": {
                    "kind": "price",
                    "account_id": account_id,
                    "symbol": "FIXTURE",
                    "condition": "above",
                    "level": "10",
                    "prompt": "Observe declared plan",
                },
            }
        ]
        changed_goal = await make_goal(old_steps)
        changed_context = await goal_lease(changed_goal)
        old_wait = await tool(
            changed_context, "goal_wait", {"goal_id": changed_goal["id"], "step_id": "entry"}
        )
        watches.append(old_wait["wake_source"]["id"])
        await finish(changed_context)
        revised = await fixture.request(
            "PUT",
            f"/trading/goals/{changed_goal['id']}/plan",
            {
                "version": old_wait["goal"]["version"],
                "steps": [{**old_steps[0], "title": "Revised plan"}],
            },
        )
        assert revised["state"]["plan_version"] == 2 and not revised["state"]["autonomous"]
        assert (
            await check_watches(
                db,
                brokers,
                price_update=high.model_copy(update={"observed_at": utcnow()}),
                connection_id=account_id,
                owner_id=fixture.owner,
            )
            == 0
        )
        async with db.sessions() as session:
            stale_watch = await session.get(MarketWatchRow, old_wait["wake_source"]["id"])
            assert stale_watch is not None and not stale_watch.payload["enabled"]
        review_goal = await make_goal(
            [
                {
                    "id": "review",
                    "title": "Old scheduled review",
                    "kind": "review",
                    "review_interval_seconds": 60,
                }
            ]
        )
        review_context = await goal_lease(review_goal)
        old_review = await tool(
            review_context, "goal_wait", {"goal_id": review_goal["id"], "step_id": "review"}
        )
        await finish(review_context)
        await fixture.request(
            "PUT",
            f"/trading/goals/{review_goal['id']}/plan",
            {
                "version": old_review["goal"]["version"],
                "steps": [
                    {
                        "id": "review",
                        "title": "Revised review",
                        "kind": "review",
                        "review_interval_seconds": 60,
                    }
                ],
            },
        )
        async with db.sessions() as session, session.begin():
            stale_review = await session.get(RoutineRow, old_review["wake_source"]["id"])
            assert stale_review is not None
            stale_review.next_run_at = utcnow() - timedelta(seconds=1)
        async with db.sessions() as session, session.begin():
            assert await enqueue_due(session) == 0
            stale_review = await session.get(RoutineRow, old_review["wake_source"]["id"])
            assert stale_review is not None and not stale_review.enabled

        # Ten maximum-length goals cannot exhaust model context or corrupt persisted plans.
        large_ids: list[str] = []
        for _ in range(10):
            large = await fixture.request(
                "POST",
                "/trading/goals",
                {
                    "agent_id": agent["id"],
                    "thread_id": thread["id"],
                    "title": "Large context fixture",
                    "objective": "x" * 8000,
                    "account_id": account_id,
                    "symbol": "FIXTURE",
                    "steps": [
                        {"id": f"step_{index}", "title": "y" * 300, "kind": "analysis"}
                        for index in range(40)
                    ],
                },
            )
            goals.append(large["id"])
            large_ids.append(large["id"])
        async with db.sessions() as session, session.begin():
            selected = await session.get(TradingGoalRow, large_ids[-1])
            assert selected is not None
            selected.state = {**selected.state, "current_step": "step_39"}
        async with db.sessions() as session:
            selected = await session.get(TradingGoalRow, large_ids[-1])
            assert selected is not None
            before = json.dumps(
                {"payload": selected.payload, "state": selected.state}, sort_keys=True
            )
            bounded = await goal_context(session, fixture.owner, agent["id"], thread["id"])
            seed = bounded.split("<saved_goals>", 1)[1].split("</saved_goals>", 1)[0]
            decoded = json.loads(seed)
            assert len(seed) <= MAX_GOAL_CONTEXT_CHARS and decoded["goals"]
            exact = await goal_context(
                session, fixture.owner, agent["id"], thread["id"], large_ids[-1]
            )
            selected_json = json.loads(
                exact.split("<saved_goals>", 1)[1].split("</saved_goals>", 1)[0]
            )
            assert selected_json["goals"][0]["current_step"]["id"] == "step_39"
            assert (
                json.dumps({"payload": selected.payload, "state": selected.state}, sort_keys=True)
                == before
            )
        # Actual owner message -> resident dispatcher -> AgentRuntime -> typed goal tools -> reply.
        async with db.sessions() as session:
            prior_secret = await session.scalar(
                select(SecretRow).where(
                    SecretRow.owner_id == fixture.owner,
                    SecretRow.scope == "provider",
                    SecretRow.name == "openai",
                )
            )
            if prior_secret:
                old_ciphertext = prior_secret.ciphertext
        fixture_secret_id = await services.secrets.write(
            "openai", "explicit-local-scripted-fixture-not-a-real-key", "provider"
        )
        await save_policy(
            db,
            RoutingPolicy(
                unified=ModelSelection(provider="openai", model="explicit-scripted-goal-model")
            ),
        )
        proposal = {
            "title": "Gateway message goal",
            "objective": "Persist this goal through the actual resident executor",
            "account_id": account_id,
            "symbol": "FIXTURE",
            "steps": [
                {
                    "id": "research",
                    "title": "Inspect real broker evidence later",
                    "kind": "analysis",
                }
            ],
        }
        adapter_rounds = 0
        gateway_goal: str | None = None

        class ScriptedModel:
            async def complete(
                self,
                model: str,
                messages: list[ModelMessage],
                tools: list[ToolDefinition],
                *,
                on_delta: Callable[[str], Awaitable[None]] | None = None,
            ) -> ModelReply:
                nonlocal adapter_rounds, gateway_goal
                adapter_rounds += 1
                assert model == "explicit-scripted-goal-model"
                if adapter_rounds == 1:
                    assert any(tool.name == "goal_create" for tool in tools)
                    return ModelReply(
                        tool_calls=[
                            ToolCall(
                                id="gateway-goal-create", name="goal_create", arguments=proposal
                            )
                        ]
                    )
                if adapter_rounds == 2:
                    result = json.loads(
                        next(
                            message.content
                            for message in reversed(messages)
                            if message.role == "tool"
                        )
                    )
                    assert result["ok"] and result["state"]["autonomous"] is False
                    identifier = str(result["id"])
                    gateway_goal = identifier
                    goals.append(identifier)
                    return ModelReply(
                        tool_calls=[
                            ToolCall(
                                id="gateway-goal-read",
                                name="goal_read",
                                arguments={"goal_id": gateway_goal},
                            )
                        ]
                    )
                assert adapter_rounds == 3
                answer = "Saved the goal in this same chat; financial autonomy remains off."
                if on_delta:
                    await on_delta(answer)
                return ModelReply(text=answer)

            async def discover(self) -> list[ModelDescriptor]:
                return []

            async def close(self) -> None:
                pass

        def factory(provider: str, key: str) -> ModelAdapter:
            assert provider == "openai" and key == "explicit-local-scripted-fixture-not-a-real-key"
            return ScriptedModel()

        original_factory = services.router.factory
        services.router.factory = factory
        admitted = await fixture.request(
            "POST",
            f"/threads/{thread['id']}/messages",
            {"content": "Save an ongoing analysis goal in this chat", "client_nonce": uuid4().hex},
        )
        assert len(admitted["run_ids"]) == 1
        assert await dispatch_one(
            db,
            "actual-goal-gateway-fixture",
            AgentRuntime(load_tools(), 300, 8),
            {fixture.owner: services},
            fixture.settings.encryption_key.get_secret_value(),
            fixture.settings.artifact_root,
            300,
            4,
        )
        async with db.sessions() as session:
            run = await session.get(RunRow, admitted["run_ids"][0])
            assert run is not None and run.status == "completed" and gateway_goal
            assert run.model_metadata["goal_id"] == gateway_goal
            goal = await session.get(TradingGoalRow, gateway_goal)
            assert (
                goal is not None and goal.thread_id == thread["id"] and not goal.state["autonomous"]
            )
            answer = await session.scalar(
                select(MessageRow)
                .where(MessageRow.thread_id == thread["id"], MessageRow.role == "assistant")
                .order_by(MessageRow.seq.desc())
                .limit(1)
            )
            assert (
                answer is not None
                and answer.content == run.result
                and "autonomy remains off" in answer.content
            )
        assert adapter_rounds == 3
        print(
            "Goals: actual message/Gateway/AgentRuntime/tool/reply, closed loop, pending fill/restart, worker death, fixed identities, ambiguity, stop controls, peer ancestry, verified fresh crossings and bounded context passed; local scripted/simulation fixtures only"
        )
    finally:
        await save_policy(db, original_policy)
        if original_factory is not None:
            services.router.factory = original_factory
        if fixture_secret_id:
            async with db.sessions() as session, session.begin():
                secret = await session.get(SecretRow, fixture_secret_id)
                if secret is not None:
                    if old_ciphertext is not None:
                        secret.ciphertext = old_ciphertext
                    else:
                        await session.delete(secret)
        await save_controls(db, original_controls)
        async with db.sessions() as session, session.begin():
            operations.extend(
                await session.scalars(
                    select(GoalDecisionRow.operation_id).where(GoalDecisionRow.goal_id.in_(goals))
                )
            )
            watches.extend(
                await session.scalars(
                    select(MarketWatchRow.id).where(
                        MarketWatchRow.payload["goal_id"].as_string().in_(goals)
                    )
                )
            )
            await session.execute(delete(MarketWatchRow).where(MarketWatchRow.id.in_(watches)))
            await session.execute(
                delete(TradingJournalRow).where(TradingJournalRow.operation_id.in_(operations))
            )
            await session.execute(delete(TradingGoalRow).where(TradingGoalRow.id.in_(goals)))
        for account_id in accounts:
            await fixture.request("DELETE", "/trading/connections/" + account_id)
        await fixture.close()


async def crash_goal() -> None:
    fixture = await Fixture().open()
    goal_id, lease = sys.argv[2], Lease.model_validate_json(sys.argv[3])
    async with fixture.runtime.db.sessions() as session:
        goal = await owned_goal(session, fixture.owner, goal_id)
        account_id = str(goal.payload["account_id"])
    services = fixture.runtime.services(fixture.owner)
    gate = GateBroker(fixture.runtime.db, fixture.owner, account_id)
    gate.mode = "crash"
    services.brokers.connections[account_id] = (1, gate)
    await execute_goal_step(
        fixture.runtime.db,
        services.brokers,
        services.trading,
        fixture.owner,
        goal_id,
        "entry",
        lease,
    )
    raise AssertionError("Scripted worker did not die after broker commit")


if __name__ == "__main__":
    asyncio.run(crash_goal() if len(sys.argv) > 1 else checks())
