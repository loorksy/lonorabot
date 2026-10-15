"""Simulation-only owner intervention, durable dedup and read-only wake boundary."""

import asyncio
from decimal import Decimal
from typing import Any, cast
from unittest.mock import AsyncMock, patch
from uuid import uuid4

from check_streaming import Fixture
from lonora_adapter_kit.types import ToolCall
from lonora_agent.collaboration.outcome_return import return_outcome
from lonora_contracts.account import Position
from lonora_contracts.domain import utcnow
from lonora_contracts.trading import TradeRequest
from lonora_core.user_error import LonoraError
from lonora_db.runs import run_data
from lonora_db.schema import AgentRow, EventRow, RunRow, ThreadRow, TradingAccountRow
from lonora_tools.loader import load_tools
from lonora_trading.broker_recovery import reconcile_broker_account
from sqlalchemy import select


async def main() -> None:
    f = await Fixture().open()
    connection_id = ""
    try:
        connection_id = (
            await f.request(
                "POST",
                "/trading/connections",
                {"provider": "simulation", "account_id": uuid4().hex, "enabled": True},
            )
        )["id"]
        await f.request(
            "POST",
            f"/trading/connections/{connection_id}/simulation",
            {
                "snapshot": {
                    "currency": "USD",
                    "balance": "10000",
                    "instruments": [
                        {
                            "symbol": "XAUUSDm",
                            "digits": 2,
                            "tick_size": "0.01",
                            "volume_min": "0.1",
                            "volume_max": "100",
                            "volume_step": "0.1",
                        }
                    ],
                    "quotes": {
                        "XAUUSDm": {
                            "symbol": "XAUUSDm",
                            "bid": "100",
                            "ask": "101",
                            "observed_at": utcnow().isoformat(),
                            "source": "explicit-recovery-fixture",
                        }
                    },
                }
            },
        )
        service = f.runtime.services(f.owner)
        first = await reconcile_broker_account(
            f.runtime.db, service.brokers, f.owner, connection_id
        )
        assert first and first.status == "connected" and first.external_revision == 0

        async def manual(positions: list[Position]) -> None:
            async with f.runtime.db.sessions() as session, session.begin():
                account = await session.get(TradingAccountRow, connection_id, with_for_update=True)
                assert account
                account.payload = {
                    **account.payload,
                    "positions": [p.model_dump(mode="json") for p in positions],
                }

        position = Position(
            id="manual-ticket-125",
            symbol="XAUUSDm",
            side="buy",
            volume=Decimal("0.2"),
            open_price=Decimal(99),
            stop_loss=Decimal(95),
        )
        await manual([position])
        second = await reconcile_broker_account(
            f.runtime.db, service.brokers, f.owner, connection_id
        )
        assert second and second.external_revision == 1 and second.positions[0].id == position.id
        third = await reconcile_broker_account(
            f.runtime.db, service.brokers, f.owner, connection_id
        )
        assert third and third.external_revision == 1
        async with f.runtime.db.sessions() as session:
            events = list(
                await session.scalars(
                    select(EventRow).where(
                        EventRow.kind == "broker.external_activity",
                        EventRow.payload["account_id"].as_string() == connection_id,
                    )
                )
            )
            assert len(events) == 1 and events[0].payload["origin"] == "external"
            personal = await session.get(AgentRow, events[0].agent_id)
            assert personal and personal.role == "personal"
            wake = await session.scalar(
                select(RunRow).where(
                    RunRow.agent_id == personal.id,
                    RunRow.model_metadata["account_id"].as_string() == connection_id,
                )
            )
            assert wake and wake.model_metadata["authority"] == "observe_only"
            work_thread = await session.get(ThreadRow, wake.thread_id)
            assert work_thread and work_thread.purpose == "work"
            assert wake.thread_id != events[0].thread_id
            origin_id = events[0].thread_id
            wake_data = run_data(wake)
        context = await f.lease(wake_data)
        observations = await load_tools().execute(
            ToolCall(
                id="activity-read", name="account_activity", arguments={"account_id": connection_id}
            ),
            context,
        )
        assert len(observations["activities"]) == 1
        assert observations["activities"][0]["ticket"] == position.id
        assert observations["owner_rationale"] is None
        try:
            await context.trading.execute(
                f.owner,
                TradeRequest(
                    account_id=connection_id,
                    operation_id=uuid4().hex,
                    action="close_position",
                    symbol=position.symbol,
                    position_id=position.id,
                ),
                context.lease,
            )
        except LonoraError as error:
            assert error.code == "observe_only_execution_forbidden"
        else:
            raise AssertionError("Read-only event gained execution authority")
        print(
            "PASS broker reconciliation precedes ready; one external change belongs to Personal and cannot execute"
        )

        result_text = "Observed manual broker position " + connection_id
        async with f.runtime.db.sessions() as session, session.begin():
            completed = await session.get(RunRow, context.lease.run_id)
            assert completed
            completed.status = "completed"
            completed.result = result_text
        await return_outcome(f.runtime.db, context.lease.run_id)
        await return_outcome(f.runtime.db, context.lease.run_id)
        visible = cast(
            list[dict[str, Any]], await f.request("GET", f"/threads/{origin_id}/messages")
        )
        assert sum(m["content"] == result_text for m in visible) == 1
        print(
            "PASS broker observations use internal work lane and return one real result to the original conversation"
        )

        await f.request("PUT", "/trading/controls", {"enabled": True, "emergency_stop": False})
        agent = await f.agent("Manual management")
        thread = await f.conversation(agent)
        manager = await f.lease(await f.run(agent, thread))
        registry = load_tools()
        proposal = ToolCall(
            id="pending-modification",
            name="trade_execute",
            arguments={
                "account_id": connection_id,
                "symbol": position.symbol,
                "position_id": position.id,
                "action": "modify_position",
                "stop_loss": "94",
            },
        )
        card = await registry.execute(proposal, manager)
        assert card["_runtime_wait"]
        changed = position.model_copy(update={"stop_loss": Decimal(97)})
        await manual([changed])
        await f.request(
            "POST", f"/trading/approvals/{card['approval_id']}/decision", {"decision": "approve"}
        )
        result = await registry.execute(proposal, manager)
        assert result["results"][0]["status"] == "failed"
        assert result["results"][0]["code"] == "trade_approval_broker_state_changed"
        broker = await service.brokers.get(f.owner, connection_id)
        assert (await broker.positions())[0].stop_loss == Decimal(97)
        fourth = await reconcile_broker_account(
            f.runtime.db, service.brokers, f.owner, connection_id
        )
        assert fourth and fourth.external_revision == 2
        print(
            "PASS owner SL intervention invalidates old approved mutation; exact broker ticket/state retained"
        )

        await manual([])
        closed = await reconcile_broker_account(
            f.runtime.db, service.brokers, f.owner, connection_id
        )
        assert closed and closed.external_revision == 3 and not closed.positions
        # A closed manager represents an actual unavailable session, not invented state.
        await broker.close()
        with patch.object(
            service.brokers,
            "get",
            AsyncMock(side_effect=LonoraError("broker_connection_unavailable", 503)),
        ):
            degraded = await reconcile_broker_account(
                f.runtime.db, service.brokers, f.owner, connection_id
            )
            assert degraded and degraded.status == "disconnected"
        # Manager itself evicts the closed adapter, preserving one shared account slot.
        restored = await reconcile_broker_account(
            f.runtime.db, service.brokers, f.owner, connection_id
        )
        assert restored and restored.status == "connected" and not restored.positions
        assert restored.external_revision == 3
        print(
            "PASS manual close is not reopened; outage/reconnect restores current broker state without duplicate activity"
        )
    finally:
        if connection_id:
            await f.client.delete(f"/api/trading/connections/{connection_id}")
        await f.request("PUT", "/trading/controls", {"enabled": False, "emergency_stop": False})
        await f.close()


if __name__ == "__main__":
    asyncio.run(main())
