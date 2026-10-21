"""Real PG, authenticated approval API, exact simulation broker receipts; no live trades."""

import asyncio
import json
from collections.abc import Awaitable, Callable
from dataclasses import replace
from datetime import timedelta
from typing import Any, cast
from unittest.mock import patch
from uuid import uuid4

from check_streaming import Fixture, ScriptedRouter
from lonora_adapter_kit.types import ModelMessage, ModelReply, ToolCall, ToolDefinition
from lonora_adapters.brokers.simulation import SimulationBroker
from lonora_agent.executor import execute_run
from lonora_contracts.domain import utcnow
from lonora_contracts.model_routing import Capability, ModelSelection
from lonora_contracts.trading import TradeRequest, TradeResult, TradingControl
from lonora_db.schema import TradingAccountRow
from lonora_providers.router import GlobalModelRouter
from lonora_tools.loader import load_tools
from lonora_trading.controls import read_controls, save_controls


async def main():
    fixture = await Fixture().open()
    controls = await read_controls(fixture.runtime.db)
    connection_id = None
    try:
        agent = await fixture.agent("Financial approval")
        thread = await fixture.conversation(agent)
        context = await fixture.lease(await fixture.run(agent, thread))
        registry = load_tools()
        await save_controls(fixture.runtime.db, TradingControl(enabled=True))
        connection = await fixture.request(
            "POST",
            "/trading/connections",
            {"provider": "simulation", "account_id": "approval-" + uuid4().hex, "enabled": True},
        )
        connection_id = connection["id"]
        symbol = "EURUSD.demo"
        await fixture.request(
            "POST",
            f"/trading/connections/{connection_id}/simulation",
            {
                "snapshot": {
                    "currency": "USD",
                    "balance": "10000",
                    "instruments": [
                        {
                            "symbol": symbol,
                            "digits": 2,
                            "tick_size": "0.01",
                            "volume_min": "0.1",
                            "volume_max": "10",
                            "volume_step": "0.1",
                            "stops_level": 2,
                            "point_size": "0.01",
                        }
                    ],
                    "quotes": {
                        symbol: {
                            "symbol": symbol,
                            "bid": "100",
                            "ask": "101",
                            "observed_at": utcnow().isoformat(),
                            "source": "explicit-fixture",
                        }
                    },
                    "positions": [
                        {
                            "id": "manual-mt5-ticket",
                            "symbol": symbol,
                            "side": "buy",
                            "volume": "1",
                            "open_price": "95",
                        }
                    ],
                }
            },
        )
        broker = cast(SimulationBroker, await context.brokers.get(context.owner_id, connection_id))
        # Inject an external MT5-style ticket into authoritative broker state,
        # without a Lonora execution journal or operation marker.
        async with fixture.runtime.db.sessions() as session, session.begin():
            account = await session.get(TradingAccountRow, connection_id, with_for_update=True)
            assert account is not None
            account.payload = {
                **account.payload,
                "positions": [
                    {
                        "id": "manual-mt5-ticket",
                        "symbol": symbol,
                        "side": "buy",
                        "volume": "1",
                        "open_price": "95",
                    }
                ],
            }

        async def operation(action: str, **params: Any) -> dict[str, Any]:
            call = ToolCall(
                id=uuid4().hex,
                name="trade_execute",
                arguments={
                    "account_id": connection_id,
                    "symbol": symbol,
                    "action": action,
                    **params,
                },
            )
            before = await broker.snapshot()
            wait = await registry.execute(call, context)
            assert wait["_runtime_retry"] and await broker.snapshot() == before
            approval = wait["approval_id"]
            clarification = await registry.execute(
                ToolCall(
                    id=uuid4().hex,
                    name="wait_for_input",
                    arguments={"question": "Would you like to approve again?"},
                ),
                context,
            )
            assert clarification["code"] == "trade_confirmation_already_pending"
            assert "_runtime_wait" not in clarification
            assert await broker.snapshot() == before
            await fixture.request(
                "POST", f"/trading/approvals/{approval}/decision", {"decision": "approve"}
            )
            await fixture.request(
                "POST", f"/trading/approvals/{approval}/decision", {"decision": "approve"}
            )
            result = await registry.execute(call, context)
            assert result["status"] == "confirmed", result
            assert result["details"]["verification"]["status"] == "verified", result
            assert result["details"]["verification"]["financial_retry_allowed"] is False
            assert await registry.execute(call, context) == {
                "approval_id": approval,
                "results": result["results"],
            }
            return result

        opened = await operation("buy", volume="0.2", stop_loss="90", take_profit="110")
        await operation("sell", volume="0.2")
        await operation("modify_position", position_id=opened["broker_id"], stop_loss="91")
        await operation("close_position", position_id="manual-mt5-ticket", volume="0.1")
        assert next(
            p for p in await broker.positions() if p.id == "manual-mt5-ticket"
        ).volume == __import__("decimal").Decimal("0.9")
        await operation("close_position", position_id="manual-mt5-ticket")
        for action, price in (
            ("buy_limit", "99"),
            ("sell_limit", "102"),
            ("buy_stop", "102"),
            ("sell_stop", "99"),
        ):
            order = await operation(action, price=price, volume="0.2")
            await operation(
                "modify_order",
                order_id=order["broker_id"],
                stop_loss="90" if action.startswith("buy") else "110",
            )
            await operation("cancel_order", order_id=order["broker_id"])
        print(
            "PASS market/pending/full+partial manual close/modifications/cancel and repeated approval"
        )
        rejected = ToolCall(
            id=uuid4().hex,
            name="trade_execute",
            arguments={
                "account_id": connection_id,
                "symbol": symbol,
                "action": "buy",
                "volume": "0.2",
            },
        )
        wait = await registry.execute(rejected, context)
        before = await broker.snapshot()
        await fixture.request(
            "POST", f"/trading/approvals/{wait['approval_id']}/decision", {"decision": "reject"}
        )
        assert (await registry.execute(rejected, context))["code"] == "trade_approval_rejected"
        assert await broker.snapshot() == before
        bulk = ToolCall(
            id=uuid4().hex,
            name="trade_close_positions",
            arguments={"account_id": connection_id, "symbol": symbol},
        )
        wait = await registry.execute(bulk, context)
        frozen = next(
            a
            for a in cast(
                list[dict[str, Any]],
                await fixture.request("GET", f"/trading/approvals?thread_id={thread['id']}"),
            )
            if a["id"] == wait["approval_id"]
        )
        assert len(frozen["requests"]) == 2
        await fixture.request(
            "POST", f"/trading/approvals/{wait['approval_id']}/decision", {"decision": "approve"}
        )
        new_ticket = await operation("buy", volume="0.4")
        result = await registry.execute(bulk, context)
        assert all(item["status"] == "confirmed" for item in result["results"]) and [
            p.id for p in await broker.positions()
        ] == [new_ticket["broker_id"]]
        all_call = ToolCall(
            id=uuid4().hex, name="trade_close_positions", arguments={"account_id": connection_id}
        )
        all_wait = await registry.execute(all_call, context)
        await fixture.request(
            "POST",
            f"/trading/approvals/{all_wait['approval_id']}/decision",
            {"decision": "approve"},
        )
        assert all(
            item["status"] == "confirmed"
            for item in (await registry.execute(all_call, context))["results"]
        )
        assert not await broker.positions()
        print("PASS rejected proposal no mutation and exact ticket-set bulk close")
        from lonora_db.schema import TradeApprovalRow
        from sqlalchemy import select

        async with fixture.runtime.db.sessions() as session:
            rows = list(
                await session.scalars(
                    select(TradeApprovalRow).where(TradeApprovalRow.thread_id == thread["id"])
                )
            )
            assert len(rows) >= 15 and all(r.status in {"completed", "rejected"} for r in rows)
        print("PASS durable approvals and real broker receipts survive service reads")

        class FinancialRouter(ScriptedRouter):
            def __init__(self):
                super().__init__([])
                self.proposed = False
                self.ticket = ""
                self.credentials = context.router.credentials

            async def complete(
                self,
                capability: Capability,
                messages: list[ModelMessage],
                tools: list[ToolDefinition],
                *,
                on_delta: Callable[[str], Awaitable[None]] | None = None,
                on_attempt: Callable[[ModelSelection], Awaitable[None]] | None = None,
            ) -> tuple[ModelReply, ModelSelection]:
                selection = ModelSelection(provider="openai", model="explicit-financial-fixture")
                if not self.proposed:
                    self.proposed = True
                    return ModelReply(
                        text="",
                        tool_calls=[
                            ToolCall(
                                id="durable-approval",
                                name="trade_execute",
                                arguments={
                                    "account_id": connection_id,
                                    "symbol": symbol,
                                    "action": "buy",
                                    "volume": "0.2",
                                },
                            )
                        ],
                    ), selection
                receipt = json.loads(
                    next(m.content for m in reversed(messages) if m.role == "tool")
                )
                assert receipt["status"] == "confirmed"
                self.ticket = receipt["broker_id"]
                return ModelReply(text="Confirmed broker ticket " + self.ticket), selection

        from lonora_db.runs import complete_run

        async with fixture.runtime.db.sessions() as session, session.begin():
            await complete_run(session, context.lease, "Fixture commands complete", {})
        runtime_run = await fixture.run(agent, thread)
        runtime_context = await fixture.lease(runtime_run)
        router = FinancialRouter()
        runtime_context = replace(runtime_context, router=cast(GlobalModelRouter, router))
        await execute_run(runtime_context, registry, 30, 12)
        stored = await fixture.request("GET", "/runs/" + runtime_run["id"])
        assert stored["status"] == "waiting_input" and not await broker.positions(), stored
        cards = cast(
            list[dict[str, Any]],
            await fixture.request("GET", f"/trading/approvals?thread_id={thread['id']}"),
        )
        card = next(item for item in cards if item["run_id"] == runtime_run["id"])
        await fixture.request(
            "POST", f"/trading/approvals/{card['id']}/decision", {"decision": "approve"}
        )
        assert not await broker.positions()
        runtime_context = replace(
            await fixture.lease(runtime_run), router=cast(GlobalModelRouter, router)
        )
        await execute_run(runtime_context, registry, 30, 12)
        final = await fixture.request("GET", "/runs/" + runtime_run["id"])
        assert final["status"] == "completed" and router.ticket in final["result"]
        assert len(await broker.positions()) == 1
        print(
            "PASS actual run wait/checkpoint -> owner button -> new lease -> broker -> confirmed chat"
        )

        # Broker accepted the operation, but transport lost the response.
        # Durable journal prevents any blind resend across new ToolCalls.
        financial_context = await fixture.lease(await fixture.run(agent, thread))

        class LostResponseBroker(SimulationBroker):
            async def execute(
                self,
                request: TradeRequest,
                before_send: Callable[[], Awaitable[None]] | None = None,
            ) -> TradeResult:
                await super().execute(request, before_send)
                raise TimeoutError("explicit lost response fixture")

        lost = LostResponseBroker(fixture.runtime.db, fixture.owner, connection_id)
        services = fixture.runtime.services(fixture.owner)
        cached = services.brokers.connections[connection_id]
        services.brokers.connections[connection_id] = (cached[0], lost)
        lost_call = ToolCall(
            id="lost-response",
            name="trade_execute",
            arguments={
                "account_id": connection_id,
                "symbol": symbol,
                "action": "sell",
                "volume": "0.3",
            },
        )
        proposal = await registry.execute(lost_call, financial_context)
        await fixture.request(
            "POST",
            f"/trading/approvals/{proposal['approval_id']}/decision",
            {"decision": "approve"},
        )
        receipt = await registry.execute(lost_call, financial_context)
        assert receipt["status"] == "ambiguous"
        count = len(await lost.positions())
        replay = await registry.execute(lost_call, financial_context)
        assert (
            replay["results"][0]["status"] == "ambiguous" and len(await lost.positions()) == count
        )
        services.brokers.connections[connection_id] = cached
        from lonora_trading.reconciliation import reconcile_ambiguous

        await reconcile_ambiguous(fixture.runtime.db, services.brokers)
        cards = cast(
            list[dict[str, Any]],
            await fixture.request("GET", f"/trading/approvals?thread_id={thread['id']}"),
        )
        card = next(item for item in cards if item["id"] == proposal["approval_id"])
        assert (
            card["results"][0]["status"] == "confirmed" and len(await broker.positions()) == count
        )
        print(
            "PASS lost broker response -> ambiguous receipt -> no resend -> reconciled exact ticket"
        )

        foreground = await fixture.lease(await fixture.run(agent, thread))
        goal = await fixture.request(
            "POST",
            "/trading/goals",
            {
                "agent_id": agent["id"],
                "thread_id": thread["id"],
                "title": "Owner approved foreground goal",
                "objective": "Explicit simulation command",
                "account_id": connection_id,
                "symbol": symbol,
                "steps": [
                    {
                        "id": "entry",
                        "title": "One approved entry",
                        "kind": "trade",
                        "trade": {
                            "account_id": connection_id,
                            "symbol": symbol,
                            "action": "buy",
                            "volume": "0.1",
                        },
                    }
                ],
            },
        )
        goal_call = ToolCall(
            id="goal-approval",
            name="goal_step_execute",
            arguments={
                "goal_id": goal["id"],
                "step_id": "entry",
                "note": "Explicit current broker fixture",
            },
        )
        before = len(await broker.positions())
        proposal = await registry.execute(goal_call, foreground)
        assert proposal["_runtime_retry"] and len(await broker.positions()) == before
        await fixture.request(
            "POST",
            f"/trading/approvals/{proposal['approval_id']}/decision",
            {"decision": "approve"},
        )
        result = await registry.execute(goal_call, foreground)
        assert (
            result["result"]["status"] == "confirmed"
            and len(await broker.positions()) == before + 1
        )
        current_goal = await fixture.request("GET", "/trading/goals/" + goal["id"])
        assert (
            current_goal["state"]["status"] == "completed"
            and not current_goal["state"]["autonomous"]
        )
        print(
            "PASS foreground goal uses same immutable approval without enabling autonomous trading"
        )

        # A later user message must prevent an approved but not-yet-sent command.
        steering_context = await fixture.lease(await fixture.run(agent, thread))
        steering_call = ToolCall(
            id="steered-intent",
            name="trade_execute",
            arguments={
                "account_id": connection_id,
                "symbol": symbol,
                "action": "buy",
                "volume": "0.6",
            },
        )
        proposal = await registry.execute(steering_call, steering_context)
        await fixture.request(
            "POST",
            f"/trading/approvals/{proposal['approval_id']}/decision",
            {"decision": "approve"},
        )
        from lonora_db.schema import MessageRow, SteeringRow, ThreadRow

        async with fixture.runtime.db.sessions() as session, session.begin():
            current_thread = await session.get(ThreadRow, thread["id"], with_for_update=True)
            assert current_thread is not None
            message = MessageRow(
                thread_id=thread["id"],
                seq=current_thread.next_seq,
                role="user",
                content="Do not execute the previous proposal",
            )
            current_thread.next_seq += 1
            session.add(message)
            await session.flush()
            session.add(SteeringRow(run_id=steering_context.lease.run_id, message_id=message.id))
        before = await broker.snapshot()
        outcome = await registry.execute(steering_call, steering_context)
        assert outcome["status"] == "failed" and outcome["code"] == "tool_call_superseded"
        assert await broker.snapshot() == before
        peer_context = await fixture.lease(await fixture.run(agent, thread))
        peer_call = ToolCall(
            id="peer-outcome-intent",
            name="trade_execute",
            arguments={
                "account_id": connection_id,
                "symbol": symbol,
                "action": "buy",
                "volume": "0.15",
            },
        )
        proposal = await registry.execute(peer_call, peer_context)
        await fixture.request(
            "POST",
            f"/trading/approvals/{proposal['approval_id']}/decision",
            {"decision": "approve"},
        )
        async with fixture.runtime.db.sessions() as session, session.begin():
            current_thread = await session.get(ThreadRow, thread["id"], with_for_update=True)
            assert current_thread is not None
            message = MessageRow(
                thread_id=thread["id"],
                seq=current_thread.next_seq,
                role="assistant",
                content="<peer_outcome>The research run finished.</peer_outcome>",
            )
            current_thread.next_seq += 1
            session.add(message)
            await session.flush()
            session.add(SteeringRow(run_id=peer_context.lease.run_id, message_id=message.id))
        outcome = await registry.execute(peer_call, peer_context)
        assert outcome["status"] == "failed" and outcome["code"] == "volume_step_mismatch"
        assert await broker.snapshot() == before
        invalid_call = ToolCall(
            id="invalid-volume",
            name="trade_execute",
            arguments={
                "account_id": connection_id,
                "symbol": symbol,
                "action": "buy",
                "volume": "0.15",
            },
        )
        isolated = await fixture.lease(await fixture.run(agent, thread))
        proposal = await registry.execute(invalid_call, isolated)
        await fixture.request(
            "POST",
            f"/trading/approvals/{proposal['approval_id']}/decision",
            {"decision": "approve"},
        )
        outcome = await registry.execute(invalid_call, isolated)
        assert outcome["status"] == "failed" and outcome["code"] == "volume_step_mismatch"
        assert await broker.snapshot() == before
        print("PASS owner steering and invalid volume fail before any broker mutation")
        for call_id, args, expected in (
            ("min-volume", {"volume": "0.01"}, "volume_out_of_range"),
            ("max-volume", {"volume": "11"}, "volume_out_of_range"),
            ("stops-level", {"volume": "0.2", "stop_loss": "99.99"}, "stop_loss_stops_level"),
            ("wrong-stops", {"volume": "0.2", "stop_loss": "102"}, "stop_loss_wrong_side"),
        ):
            financial_call = ToolCall(
                id=call_id,
                name="trade_execute",
                arguments={"account_id": connection_id, "symbol": symbol, "action": "buy", **args},
            )
            proposal = await registry.execute(financial_call, isolated)
            await fixture.request(
                "POST",
                f"/trading/approvals/{proposal['approval_id']}/decision",
                {"decision": "approve"},
            )
            outcome = await registry.execute(financial_call, isolated)
            assert outcome["status"] == "failed" and outcome["code"] == expected
        assert await broker.snapshot() == before
        history = await registry.execute(
            ToolCall(
                id="history",
                name="account_history",
                arguments={
                    "account_id": connection_id,
                    "start": (utcnow() - timedelta(hours=1)).isoformat(),
                    "end": utcnow().isoformat(),
                },
            ),
            isolated,
            read_only=True,
        )
        state = await registry.execute(
            ToolCall(id="account", name="account_read", arguments={"account_id": connection_id}),
            isolated,
            read_only=True,
        )
        assert (
            history["history"]
            and state["positions"]
            and "orders" in state
            and state["account"]["balance"] == "10000"
        )
        print(
            "PASS native account/position/order/history reads and exact generic min/max/step/stops errors"
        )

        class VerificationCrash(BaseException):
            pass

        crash_call = ToolCall(
            id="crash-after-ack",
            name="trade_execute",
            arguments={
                "account_id": connection_id,
                "symbol": symbol,
                "action": "buy",
                "volume": "0.2",
            },
        )
        proposal = await registry.execute(crash_call, isolated)
        await fixture.request(
            "POST",
            f"/trading/approvals/{proposal['approval_id']}/decision",
            {"decision": "approve"},
        )
        before_count = len((await broker.snapshot()).get("operations", {}))
        with patch("lonora_trading.execution.verify_effect", side_effect=VerificationCrash):
            try:
                await registry.execute(crash_call, isolated)
            except VerificationCrash:
                pass
            else:
                raise AssertionError(
                    "Expected interruption after the durable broker acknowledgment"
                )
        receipt = await registry.execute(crash_call, isolated)
        assert receipt["status"] == "confirmed" and "verification" not in receipt["details"]
        assert len((await broker.snapshot())["operations"]) == before_count + 1
        from lonora_agent.context.financial_result import unverified_financial_result

        assert unverified_financial_result(
            [
                ModelMessage(role="user", content="نفذ الطلب بعد الموافقة"),
                ModelMessage(role="assistant", content="", tool_calls=[crash_call]),
                ModelMessage(role="tool", tool_call_id=crash_call.id, content=json.dumps(receipt)),
            ]
        )
        print(
            "PASS crash during independent verification preserves acknowledgment, sends once and cannot claim verified completion"
        )

    finally:
        await save_controls(fixture.runtime.db, controls)
        if connection_id:
            await fixture.request("DELETE", "/trading/connections/" + connection_id)
        await fixture.close()


if __name__ == "__main__":
    asyncio.run(main())
