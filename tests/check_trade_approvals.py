"""Real PG, authenticated approval API, exact simulation broker receipts; no live trades."""

import asyncio
import json
from collections.abc import Awaitable, Callable
from dataclasses import replace
from datetime import timedelta
from typing import Any, cast
from unittest.mock import AsyncMock, patch
from uuid import uuid4

from check_streaming import Fixture, ScriptedRouter
from lonora_adapter_kit.types import ModelMessage, ModelReply, ToolCall, ToolDefinition
from lonora_adapters.brokers.simulation import SimulationBroker
from lonora_agent.executor import execute_run
from lonora_contracts.domain import utcnow
from lonora_contracts.model_routing import Capability, ModelSelection
from lonora_contracts.trading import TradeRequest, TradeResult, TradingControl
from lonora_core.user_error import ToolRefusal
from lonora_db.schema import TradingAccountRow
from lonora_providers.router import GlobalModelRouter
from lonora_tools.loader import load_tools
from lonora_trading.controls import read_controls, save_controls


async def main():
    fixture = await Fixture().open()
    controls = await read_controls(fixture.runtime.db)
    connection_id = None
    try:
        agent = await fixture.agent("Financial approval", supervised=True)
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

        async def operation(action: str, *, card: bool = True, **params: Any) -> dict[str, Any]:
            """``card`` False: a risk-reducing request on the agent's own ticket (Ask)."""
            call = ToolCall(
                id=uuid4().hex,
                name="trade_execute",
                arguments={
                    "account_id": connection_id,
                    "symbol": symbol,
                    "action": action,
                    "tolerance": "5",
                    **params,
                },
            )
            before = await broker.snapshot()
            wait = await registry.execute(call, context)
            if not card:
                # Ask: a risk-reducing request on the agent's own ticket needs no card.
                assert "_runtime_wait" not in wait and "approval_id" not in wait, wait
                assert wait["status"] == "confirmed", wait
                assert wait["details"]["verification"]["financial_retry_allowed"] is False
                assert await registry.execute(call, context) == wait
                return wait
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
            # A replay answers from the completed approval, with the single result's
            # fields at the top level as on the first execution.
            assert await registry.execute(call, context) == {
                "approval_id": approval,
                "results": result["results"],
                **(result["results"][0] if len(result["results"]) == 1 else {}),
            }
            return result

        opened = await operation("buy", volume="0.2", stop_loss="90", take_profit="110")
        await operation("sell", volume="0.2")
        await operation(
            "modify_position", card=False, position_id=opened["broker_id"], stop_loss="91"
        )
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
            await operation("cancel_order", card=False, order_id=order["broker_id"])
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
                "tolerance": "5",
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
        # Both positions are the agent's own: in Ask a close-all reduces risk and executes
        # without a card, on the exact ticket set it read; a replay never adds a later one.
        result = await registry.execute(bulk, context)
        assert "approval_id" not in result, result
        assert len(result["results"]) == 2
        assert all(item["status"] == "confirmed" for item in result["results"])
        new_ticket = await operation("buy", volume="0.4")
        assert (await registry.execute(bulk, context))["results"] == result["results"]
        assert [p.id for p in await broker.positions()] == [new_ticket["broker_id"]]
        all_call = ToolCall(
            id=uuid4().hex, name="trade_close_positions", arguments={"account_id": connection_id}
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
            # Cards for every request that adds risk or touches the owner's own ticket:
            # 2 entries, 2 manual closes, 4 pending orders, 4 order changes, 1 rejected.
            # The agent's own stop tightening, cancels and closes executed without one.
            assert len(rows) >= 13 and all(r.status in {"completed", "rejected"} for r in rows)
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
                **_: Any,
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
                                    "tolerance": "5",
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
                "tolerance": "5",
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
            and "autonomous" not in current_goal["state"]
        )
        print(
            "PASS foreground goal uses same immutable approval; a goal carries no autonomy of its own"
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
                "tolerance": "5",
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
                "tolerance": "5",
            },
        )
        # The executor refuses a wrong size on its own, without the tool's early check.
        early_size_check = patch("lonora_tools.trade.require_order_size", AsyncMock())
        early_size_check.start()
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
                "tolerance": "5",
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
                arguments={
                    "account_id": connection_id,
                    "symbol": symbol,
                    "action": "buy",
                    "tolerance": "5",
                    **args,
                },
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
        early_size_check.stop()
        # With it, a size the contract cannot take is refused before any card, with the limits.
        listed = f"/trading/approvals?thread_id={thread['id']}"
        cards = len(await fixture.request("GET", listed))
        for volume, expected in (
            ("0.15", "volume_step_mismatch"),
            ("0.01", "volume_out_of_range"),
            ("11", "volume_out_of_range"),
        ):
            try:
                await registry.execute(
                    ToolCall(
                        id="early-" + volume,
                        name="trade_execute",
                        arguments={
                            "account_id": connection_id,
                            "symbol": symbol,
                            "action": "buy",
                            "volume": volume,
                            "tolerance": "5",
                        },
                    ),
                    isolated,
                )
            except ToolRefusal as refused:
                assert refused.code == expected and refused.details["retryable"] is False
                assert refused.details["limits"] == {
                    "volume_min": "0.1",
                    "volume_max": "10",
                    "volume_step": "0.1",
                }
            else:
                raise AssertionError("a size the contract cannot take raised a card")
        assert len(await fixture.request("GET", listed)) == cards
        assert await broker.snapshot() == before
        print("PASS a size the contract cannot take is refused before any card, with its limits")
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
            scope="helper",
        )
        state = await registry.execute(
            ToolCall(id="account", name="account_read", arguments={"account_id": connection_id}),
            isolated,
            scope="helper",
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
                "tolerance": "5",
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
