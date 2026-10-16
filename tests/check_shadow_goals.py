"""Goal → real evidence → virtual journal → watch wake → management, never broker mutation."""

import asyncio
from datetime import timedelta
from typing import Any
from unittest.mock import AsyncMock, patch
from uuid import uuid4

from check_streaming import Fixture
from device_fixture import Device
from lonora_adapter_kit.types import ToolCall
from lonora_contracts.account import Position
from lonora_contracts.domain import utcnow
from lonora_core.user_error import LonoraError
from lonora_db.market_watches import MarketWatchRepository
from lonora_db.runs import complete_run
from lonora_db.schema import (
    GoalDecisionRow,
    MarketWatchRow,
    RunRow,
    ShadowTradeRow,
    TradingAccountRow,
    TradingJournalRow,
)
from lonora_db.trade_approvals import decide
from lonora_market.watchers import check_watches
from lonora_tools.loader import load_tools
from lonora_trading.goals import recover_goals
from lonora_trading.goals_market import fresh_goal_evidence
from lonora_trading.preflight import preflight as actual_preflight
from lonora_trading.shadow import advance_shadow
from sqlalchemy import select


async def main():
    f = await Fixture().open()
    try:
        account = (
            await f.request(
                "POST",
                "/trading/connections",
                {"provider": "simulation", "account_id": "shadow-goals", "enabled": True},
            )
        )["id"]
        symbols = ("EURUSDm", "XAUUSD.raw", "US30.cash", "BTCUSD.pro")
        now = utcnow()
        await f.request(
            "POST",
            f"/trading/connections/{account}/simulation",
            {
                "snapshot": {
                    "balance": "10000",
                    "currency": "USD",
                    "instruments": [
                        {
                            "symbol": symbol,
                            "digits": 2,
                            "tick_size": "0.01",
                            "volume_min": "0.01",
                            "volume_max": "10",
                            "volume_step": "0.01",
                        }
                        for symbol in symbols
                    ],
                    "quotes": {
                        symbol: {
                            "symbol": symbol,
                            "bid": "100",
                            "ask": "101",
                            "observed_at": now.isoformat(),
                            "source": "explicit-shadow-goal-fixture",
                        }
                        for symbol in symbols
                    },
                    "candles": {
                        symbol + ":1m": [
                            {
                                "symbol": symbol,
                                "timeframe": "1m",
                                "time": (now - timedelta(minutes=1)).isoformat(),
                                "open": "100",
                                "high": "103",
                                "low": "99",
                                "close": "101",
                            }
                        ]
                        for symbol in symbols
                    },
                    "positions": [
                        {
                            "id": "real-manual-ticket",
                            "symbol": symbols[0],
                            "side": "buy",
                            "volume": "0.5",
                            "open_price": "99",
                        }
                    ],
                }
            },
        )
        # Explicit broker-side fixture: initialization deliberately starts empty.
        # This position has no Lonora execution journal, like a manual external trade.
        async with f.runtime.db.sessions() as session, session.begin():
            snapshot = await session.get(TradingAccountRow, account)
            assert snapshot
            snapshot.payload = {
                **snapshot.payload,
                "positions": [
                    Position.model_validate(
                        {
                            "id": "real-manual-ticket",
                            "symbol": symbols[0],
                            "side": "buy",
                            "volume": "0.5",
                            "open_price": "99",
                        }
                    ).model_dump(mode="json")
                ],
            }
        agent = await f.agent("Persistent virtual goals")
        await f.request(
            "PUT", f"/agents/{agent['id']}/execution-mode", {"execution_mode": "shadow"}
        )
        thread = await f.conversation(agent)
        context = await f.lease(await f.run(agent, thread))
        registry = load_tools()
        broker = await context.brokers.get(f.owner, account)
        trap = AsyncMock(side_effect=AssertionError("Shadow Goal submitted a real broker mutation"))
        device = await Device.enroll(f)

        async def tool(name: str, args: dict[str, Any], key: str | None = None) -> dict[str, Any]:
            return await registry.execute(
                ToolCall(id=key or uuid4().hex, name=name, arguments=args), context
            )

        async def recorded(symbol: str, action: str):
            await tool(
                "market_decision_record",
                {
                    "account_id": account,
                    "symbol": symbol,
                    "timeframe": "1m",
                    "action": action,
                    "summary": "Actual explicit simulation evidence for a virtual Goal",
                },
            )

        async def step(goal: dict[str, Any], identifier: str, key: str | None = None):
            call = ToolCall(
                id=key or uuid4().hex,
                name="goal_step_execute",
                arguments={
                    "goal_id": goal["id"],
                    "step_id": identifier,
                    "note": "Use actual recorded evidence and virtual state",
                },
            )
            result = await registry.execute(call, context)
            if result.get("_runtime_wait"):
                approval = (
                    await f.client.get("/api/trading/approvals?thread_id=" + thread["id"])
                ).json()
                # Fixture helper's legacy return annotation is dict; the endpoint is a list.
                assert any(
                    row["id"] == result["approval_id"] and row["execution_mode"] == "shadow"
                    for row in list(approval)
                )
                async with f.runtime.db.sessions() as session, session.begin():
                    await decide(session, f.owner, result["approval_id"], "approve")
                result = await registry.execute(call, context)
            assert (
                result["result"]["status"] == "confirmed"
                and result["result"]["details"]["mode"] == "shadow"
            ), result
            return result

        trade = {
            "account_id": account,
            "symbol": symbols[0],
            "volume": "0.1",
            "action": "buy",
            "stop_loss": "90",
            "take_profit": "130",
        }
        with patch.object(broker, "execute", trap), patch.object(broker, "reconcile", trap):
            goal = await tool(
                "goal_create",
                {
                    "title": "Persistent virtual loop",
                    "objective": "Verify the same Goal runtime without real mutation",
                    "account_id": account,
                    "symbol": symbols[0],
                    "maximum_volume": "0.1",
                    "max_trade_actions": 4,
                    "steps": [
                        {"id": "entry", "title": "Virtual entry", "kind": "trade", "trade": trade},
                        {
                            "id": "observed",
                            "title": "Observe virtual position",
                            "kind": "watch",
                            "condition": {
                                "kind": "position",
                                "account_id": account,
                                "symbol": symbols[0],
                                "condition": "above",
                                "metric": "volume",
                                "level": "0.05",
                                "target_step_id": "entry",
                                "prompt": "Observe the persisted virtual position",
                            },
                        },
                        {
                            "id": "protect",
                            "title": "Virtual protection",
                            "kind": "trade",
                            "trade": {
                                "account_id": account,
                                "symbol": symbols[0],
                                "action": "modify_position",
                                "stop_loss": "95",
                                "take_profit": "140",
                                "target_step_id": "entry",
                            },
                        },
                        {
                            "id": "partial",
                            "title": "Virtual partial exit",
                            "kind": "trade",
                            "trade": {
                                "account_id": account,
                                "symbol": symbols[0],
                                "action": "close_position",
                                "volume": "0.04",
                                "target_step_id": "entry",
                            },
                        },
                        {
                            "id": "exit",
                            "title": "Virtual final exit",
                            "kind": "trade",
                            "trade": {
                                "account_id": account,
                                "symbol": symbols[0],
                                "action": "close_position",
                                "target_step_id": "entry",
                            },
                        },
                    ],
                },
            )
            assert (
                goal["state"]["execution_mode"] == "shadow" and goal["state"]["autonomous"] is False
            )
            await recorded(symbols[0], "BUY")
            try:
                await tool("trade_execute", trade)
            except LonoraError as error:
                assert error.code == "goal_step_required"
            else:
                raise AssertionError("Generic Shadow tool bypassed declared Goal steps")
            with patch(
                "lonora_trading.goals.sync_goal_decision", new=AsyncMock(return_value=False)
            ):
                entry = await step(goal, "entry", "fixed-entry")
            # Broker-independent virtual commit survives the worker/Goal-checkpoint gap.
            assert await recover_goals(f.runtime.db) == 1
            assert await recover_goals(f.runtime.db) == 0

            virtual_id = entry["result"]["broker_id"]
            profit_condition = {
                "kind": "position",
                "account_id": account,
                "symbol": symbols[0],
                "position_id": virtual_id,
                "metric": "profit",
                "condition": "above",
                "level": "10",
                "prompt": "Never infer monetary virtual profit",
            }
            profit_goal = await f.request(
                "POST",
                "/trading/goals",
                {
                    "agent_id": agent["id"],
                    "thread_id": thread["id"],
                    "title": "Unavailable virtual valuation",
                    "objective": "Suspend unavailable valuation rather than invent profit",
                    "account_id": account,
                    "symbol": symbols[0],
                    "steps": [
                        {
                            "id": "profit",
                            "title": "Unavailable monetary condition",
                            "kind": "watch",
                            "condition": profit_condition,
                        }
                    ],
                },
            )
            try:
                await fresh_goal_evidence(
                    f.runtime.db, context.brokers, f.owner, profit_goal["id"], "profit"
                )
            except LonoraError as error:
                assert error.code == "shadow_monetary_pnl_unavailable"
            else:
                raise AssertionError("Unavailable monetary valuation became zero profit")
            async with f.runtime.db.sessions() as session, session.begin():
                watch = await MarketWatchRepository().create(
                    session,
                    f.owner,
                    {**profit_condition, "goal_id": profit_goal["id"], "step_id": "profit"},
                    agent_id=agent["id"],
                    thread_id=thread["id"],
                )
                unavailable_watch = watch.id
            assert await check_watches(f.runtime.db, context.brokers) == 0
            async with f.runtime.db.sessions() as session:
                watch = await session.get(MarketWatchRow, unavailable_watch)
                assert (
                    watch
                    and watch.state["health"]["reason_code"] == "shadow_monetary_pnl_unavailable"
                )
            await f.request(
                "POST",
                f"/trading/goals/{profit_goal['id']}/control",
                {"version": profit_goal["version"], "action": "cancel"},
            )
            waiting = await tool("goal_wait", {"goal_id": goal["id"], "step_id": "observed"})
            assert waiting["goal"]["state"]["status"] == "waiting"
            async with f.runtime.db.sessions() as session, session.begin():
                await complete_run(
                    session, context.lease, "Waiting for the persisted virtual-position watch", {}
                )
            assert await check_watches(f.runtime.db, context.brokers) == 1
            async with f.runtime.db.sessions() as session:
                wake = await session.scalar(
                    select(RunRow).where(
                        RunRow.trigger == "watch",
                        RunRow.model_metadata["goal_id"].as_string() == goal["id"],
                    )
                )
                assert wake and wake.model_metadata["execution_mode"] == "shadow"
                wake_data = {"id": wake.id, "agent_id": wake.agent_id, "thread_id": wake.thread_id}
            context = await f.lease(wake_data)
            await tool(
                "goal_step_complete",
                {
                    "goal_id": goal["id"],
                    "step_id": "observed",
                    "note": "Observed the actual virtual position",
                },
            )
            await device.authorize_goal_service(f, goal)
            await step(goal, "protect")
            partial = await step(goal, "partial", "fixed-partial")
            await step(goal, "exit")
            replay = await step(goal, "partial", "fixed-partial")
            assert replay["operation_id"] == partial["operation_id"] and replay["deduplicated"]
            async with f.runtime.db.sessions() as session:
                virtual = await session.get(ShadowTradeRow, virtual_id)
                assert (
                    virtual
                    and virtual.status == "closed"
                    and virtual.state["remaining_volume"] == "0.00"
                )
                decisions = list(
                    await session.scalars(
                        select(GoalDecisionRow).where(GoalDecisionRow.goal_id == goal["id"])
                    )
                )
                assert len(decisions) == 4 and all(
                    row.evidence["execution_mode"] == "shadow" for row in decisions
                )
                for decision in decisions:
                    journal = await session.get(TradingJournalRow, decision.operation_id)
                    assert journal and journal.execution_mode == "shadow"
                    observed = journal.result["details"]["execution_evidence"]["before_send"]
                    assert observed["execution_mode"] == "shadow"
                    assert observed["goal"]["goal_id"] == goal["id"]
                    assert observed["target_source"] == "virtual_book"
                    assert all(p["profit"] is None for p in observed["snapshot"]["positions"])
                    assert all(
                        p["id"] != "real-manual-ticket" and p["profit"] is None
                        for p in decision.evidence["observation"]["positions"]
                    )
            assert (await f.request("GET", "/trading/goals/" + goal["id"]))["state"][
                "status"
            ] == "completed"
            assert [row.id for row in await broker.positions()] == [
                "real-manual-ticket"
            ] and trap.await_count == 0
            async with f.runtime.db.sessions() as session, session.begin():
                await complete_run(
                    session, context.lease, "Virtual Goal complete; real account unchanged", {}
                )
            print(
                "PASS same Goal/decision/journal path opens, wakes from a durable virtual-position watch, protects, partially closes and exits with fixed replay identities; real manual positions are excluded and real mutations are zero"
            )

            for index, (action, price, modified) in enumerate(
                (
                    ("buy_limit", "95", "94"),
                    ("sell_limit", "105", "106"),
                    ("buy_stop", "105", "106"),
                    ("sell_stop", "95", "94"),
                )
            ):
                context = await f.lease(await f.run(agent, thread))
                symbol = symbols[index]
                async with f.runtime.db.sessions() as session, session.begin():
                    account_row = await session.get(TradingAccountRow, account)
                    assert account_row
                    quotes = {
                        key: {**value, "observed_at": utcnow().isoformat()}
                        for key, value in account_row.payload["quotes"].items()
                    }
                    account_row.payload = {**account_row.payload, "quotes": quotes}
                await recorded(symbol, "BUY" if action.startswith("buy") else "SELL")
                pending_goal = await tool(
                    "goal_create",
                    {
                        "title": "Virtual pending " + action,
                        "objective": "Persistent virtual pending-order lifecycle",
                        "account_id": account,
                        "symbol": symbol,
                        "maximum_volume": "0.1",
                        "max_trade_actions": 3,
                        "steps": [
                            {
                                "id": "entry",
                                "title": "Virtual pending entry",
                                "kind": "trade",
                                "trade": {
                                    "account_id": account,
                                    "symbol": symbol,
                                    "action": action,
                                    "price": price,
                                    "volume": "0.1",
                                },
                            },
                            {
                                "id": "modify",
                                "title": "Modify virtual order",
                                "kind": "trade",
                                "trade": {
                                    "account_id": account,
                                    "symbol": symbol,
                                    "action": "modify_order",
                                    "price": modified,
                                    "target_step_id": "entry",
                                },
                            },
                            {
                                "id": "cancel",
                                "title": "Cancel virtual order",
                                "kind": "trade",
                                "trade": {
                                    "account_id": account,
                                    "symbol": symbol,
                                    "action": "cancel_order",
                                    "target_step_id": "modify",
                                },
                            },
                        ],
                    },
                )
                await step(pending_goal, "entry")
                await step(pending_goal, "modify")
                with (
                    patch.object(
                        broker,
                        "account",
                        AsyncMock(side_effect=LonoraError("broker_connection_unavailable", 503)),
                    ),
                    patch.object(
                        broker,
                        "quote",
                        AsyncMock(side_effect=LonoraError("broker_connection_unavailable", 503)),
                    ),
                ):
                    await step(pending_goal, "cancel")
                async with f.runtime.db.sessions() as session, session.begin():
                    await complete_run(
                        session, context.lease, "Virtual pending lifecycle completed", {}
                    )
            context = await f.lease(await f.run(agent, thread))
            symbol = symbols[3]
            await recorded(symbol, "BUY")
            fill_goal = await tool(
                "goal_create",
                {
                    "title": "Deferred virtual fill",
                    "objective": "Resolve the same virtual order after later source prices",
                    "account_id": account,
                    "symbol": symbol,
                    "maximum_volume": "0.1",
                    "max_trade_actions": 2,
                    "steps": [
                        {
                            "id": "entry",
                            "title": "Virtual stop",
                            "kind": "trade",
                            "trade": {
                                "account_id": account,
                                "symbol": symbol,
                                "action": "buy_stop",
                                "price": "105",
                                "volume": "0.1",
                            },
                        },
                        {
                            "id": "exit",
                            "title": "Resolve filled virtual position",
                            "kind": "trade",
                            "trade": {
                                "account_id": account,
                                "symbol": symbol,
                                "action": "close_position",
                                "target_step_id": "entry",
                            },
                        },
                    ],
                },
            )
            pending = await step(fill_goal, "entry")
            waiting = await tool(
                "goal_step_execute",
                {
                    "goal_id": fill_goal["id"],
                    "step_id": "exit",
                    "note": "Wait for the pending virtual target",
                },
            )
            assert waiting["waiting"] and waiting["goal"]["state"]["status"] == "waiting"
            await device.authorize_goal_service(f, fill_goal)
            async with f.runtime.db.sessions() as session, session.begin():
                snapshot = await session.get(TradingAccountRow, account)
                assert snapshot
                quotes = {
                    **snapshot.payload["quotes"],
                    symbol: {
                        **snapshot.payload["quotes"][symbol],
                        "bid": "106",
                        "ask": "107",
                        "observed_at": utcnow().isoformat(),
                    },
                }
                snapshot.payload = {**snapshot.payload, "quotes": quotes}
                await complete_run(session, context.lease, "Persisted wait for virtual fill", {})
            assert await advance_shadow(f.runtime.db, context.brokers, f.owner) == 1
            assert await advance_shadow(f.runtime.db, context.brokers, f.owner) == 0
            wake = await f.request("POST", f"/trading/goals/{fill_goal['id']}/wake", {})
            context = await f.lease(wake)
            filled_exit = await step(fill_goal, "exit")
            assert filled_exit["result"]["broker_id"] == pending["result"]["broker_id"]
            async with f.runtime.db.sessions() as session, session.begin():
                await complete_run(
                    session,
                    context.lease,
                    "Confirmed virtual fill resolved without recreating entry",
                    {},
                )
            print(
                "PASS target-review state persists before a pending fill; later real-source quote fills once, a fresh Run resolves the same virtual ticket, and broker outage does not block local virtual cancellation"
            )

            context = await f.lease(await f.run(agent, thread))
            invalid = await tool(
                "goal_create",
                {
                    "title": "No broker-ticket laundering",
                    "objective": "A broker position cannot be managed by the virtual book",
                    "account_id": account,
                    "symbol": symbols[0],
                    "max_trade_actions": 1,
                    "steps": [
                        {
                            "id": "close",
                            "title": "Reject real ticket in virtual scope",
                            "kind": "trade",
                            "trade": {
                                "account_id": account,
                                "symbol": symbols[0],
                                "action": "close_position",
                                "position_id": "real-manual-ticket",
                            },
                        }
                    ],
                },
            )
            call = ToolCall(
                id="reject-real-ticket",
                name="goal_step_execute",
                arguments={
                    "goal_id": invalid["id"],
                    "step_id": "close",
                    "note": "The virtual reader must not find a real broker ticket",
                },
            )
            pending = await registry.execute(call, context)
            assert pending["_runtime_wait"]
            async with f.runtime.db.sessions() as session, session.begin():
                await decide(session, f.owner, pending["approval_id"], "approve")
            try:
                await registry.execute(call, context)
            except LonoraError as error:
                assert error.code == "position_not_found"
            else:
                raise AssertionError("Virtual Goal managed a real manual position")
            approvals = (
                await f.client.get("/api/trading/approvals?thread_id=" + thread["id"])
            ).json()
            failed_card = next(row for row in approvals if row["id"] == pending["approval_id"])
            assert (
                failed_card["status"] == "completed"
                and failed_card["results"][0]["status"] == "failed"
                and failed_card["results"][0]["code"] == "position_not_found"
            )
            async with f.runtime.db.sessions() as session, session.begin():
                await complete_run(
                    session,
                    context.lease,
                    "Real ticket rejected and failure reflected in approval card",
                    {},
                )
            context = await f.lease(await f.run(agent, thread))
            fenced = await tool(
                "goal_create",
                {
                    "title": "Fenced virtual commit",
                    "objective": "An old worker cannot overwrite the new lease",
                    "account_id": account,
                    "symbol": symbol,
                    "maximum_volume": "0.1",
                    "max_trade_actions": 1,
                    "steps": [
                        {
                            "id": "entry",
                            "title": "Fenced entry",
                            "kind": "trade",
                            "trade": {
                                "account_id": account,
                                "symbol": symbol,
                                "action": "buy",
                                "volume": "0.1",
                            },
                        }
                    ],
                },
            )
            await recorded(symbol, "BUY")
            call = ToolCall(
                id="lease-window",
                name="goal_step_execute",
                arguments={
                    "goal_id": fenced["id"],
                    "step_id": "entry",
                    "note": "One fenced virtual operation",
                },
            )
            pending = await registry.execute(call, context)
            async with f.runtime.db.sessions() as session, session.begin():
                await decide(session, f.owner, pending["approval_id"], "approve")

            async def steal_lease(*args: Any, **kwargs: Any):
                observed = await actual_preflight(*args, **kwargs)
                async with f.runtime.db.sessions() as session, session.begin():
                    run = await session.get(RunRow, context.lease.run_id, with_for_update=True)
                    assert run
                    run.lease_fence += 1
                    run.lease_owner = "new-worker"
                return observed

            try:
                with patch("lonora_trading.shadow.preflight", steal_lease):
                    await registry.execute(call, context)
            except LonoraError as error:
                assert error.code == "stale_lease"
            else:
                raise AssertionError("Old worker completed after losing its fence")
            async with f.runtime.db.sessions() as session:
                decision = await session.scalar(
                    select(GoalDecisionRow).where(GoalDecisionRow.goal_id == fenced["id"])
                )
                assert decision and decision.status == "executing" and not decision.result
                assert await session.get(TradingJournalRow, decision.operation_id) is None
            context = await f.lease(
                {"id": context.lease.run_id, "agent_id": agent["id"], "thread_id": thread["id"]}
            )
            resumed = await registry.execute(call, context)
            assert resumed["result"]["status"] == "confirmed"
            async with f.runtime.db.sessions() as session, session.begin():
                await complete_run(
                    session,
                    context.lease,
                    "New fenced worker completed the same virtual operation",
                    {},
                )
            context = await f.lease(await f.run(agent, thread))
            paused_goal = await tool(
                "goal_create",
                {
                    "title": "Mode isolation",
                    "objective": "Never reinterpret a waiting virtual goal as live",
                    "account_id": account,
                    "symbol": symbol,
                    "maximum_volume": "0.1",
                    "max_trade_actions": 1,
                    "steps": [
                        {
                            "id": "wait",
                            "title": "Wait for actual price",
                            "kind": "watch",
                            "condition": {
                                "kind": "price",
                                "account_id": account,
                                "symbol": symbol,
                                "condition": "above",
                                "level": "999",
                                "prompt": "Inspect the saved virtual plan",
                            },
                        },
                    ],
                },
            )
            await device.authorize_goal_service(f, paused_goal)
            await tool("goal_wait", {"goal_id": paused_goal["id"], "step_id": "wait"})
            await f.request(
                "PUT", f"/agents/{agent['id']}/execution-mode", {"execution_mode": "live"}
            )
            saved = await f.request("GET", "/trading/goals/" + paused_goal["id"])
            assert (
                saved["state"]["status"] == "paused"
                and saved["state"]["autonomous"] is False
                and saved["state"]["execution_mode"] == "shadow"
            )
            denied = await f.client.post(
                f"/api/trading/goals/{paused_goal['id']}/control",
                json={"version": saved["version"], "action": "resume", "autonomous": True},
            )
            assert denied.status_code == 403 and denied.json()["code"] == "execution_mode_changed"
            assert await check_watches(f.runtime.db, context.brokers) == 0
            async with f.runtime.db.sessions() as session, session.begin():
                await complete_run(
                    session, context.lease, "Mode changed; virtual scope stays frozen", {}
                )
            assert trap.await_count == 0
            assert (await f.request("GET", "/trading/controls"))["enabled"] is False
            print(
                "PASS all four pending types across exact forex/metal/index/crypto symbols use virtual Goal targets, modifications and cancellation; approval cards label Shadow and live Trading stays OFF"
            )
    finally:
        await f.close()


if __name__ == "__main__":
    asyncio.run(main())
