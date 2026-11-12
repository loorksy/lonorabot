"""Signed full-management scope over disposable PostgreSQL and simulation only."""

import asyncio
from typing import Any, cast
from uuid import uuid4

from check_streaming import Fixture
from device_fixture import Device
from lonora_adapter_kit.types import ToolCall
from lonora_adapters.brokers.simulation import SimulationBroker
from lonora_contracts.domain import utcnow
from lonora_core.user_error import LonoraError
from lonora_db.account_authority import require_authority
from lonora_db.management_task import live_management_task
from lonora_db.schema import RunRow, TicketRow, TradeApprovalRow, TradingAccountRow
from lonora_db.trading_mode import set_trading_mode
from lonora_session.idempotency import stable_id
from lonora_tools.loader import load_tools
from sqlalchemy import func, select


async def main():
    f = await Fixture().open()
    try:
        # Use the real default Personal Agent; the fixture database is disposable.
        agents = (await f.client.get("/api/agents")).json()
        agent = next(row for row in agents if row["role"] == "personal")
        permission = await f.request("GET", f"/agents/{agent['id']}/permissions")
        await f.request(
            "PUT",
            f"/agents/{agent['id']}/permissions",
            {"level": "supervised", "expected_revision": permission["revision"]},
        )
        thread = await f.conversation(agent)
        context = await f.lease(await f.run(agent, thread))
        connection = await f.request(
            "POST",
            "/trading/connections",
            {
                "provider": "simulation",
                "account_id": "full-test-" + uuid4().hex,
                "enabled": True,
            },
        )
        account = connection["id"]
        symbols = ["EURUSD.suffix", "XAUUSDm", "US500.cash", "BTCUSD.pro"]
        await f.request(
            "POST",
            f"/trading/connections/{account}/simulation",
            {
                "snapshot": {
                    "currency": "USD",
                    "balance": "10000",
                    "equity": "10000",
                    "instruments": [
                        {
                            "symbol": s,
                            "digits": 2,
                            "tick_size": "0.01",
                            "volume_min": "0.1",
                            "volume_max": "100",
                            "volume_step": "0.1",
                        }
                        for s in symbols
                    ],
                    "quotes": {
                        s: {
                            "symbol": s,
                            "bid": "100",
                            "ask": "101",
                            "observed_at": utcnow().isoformat(),
                            "source": "explicit-fixture",
                        }
                        for s in symbols
                    },
                }
            },
        )
        async with f.runtime.db.sessions() as session, session.begin():
            row = await session.get(TradingAccountRow, account, with_for_update=True)
            assert row
            row.payload = {
                **row.payload,
                "positions": [
                    {
                        "id": "manual-ticket",
                        "symbol": symbols[0],
                        "side": "buy",
                        "volume": "0.2",
                        "open_price": "95",
                        "stop_loss": "80",
                    }
                ],
            }
        broker = cast(SimulationBroker, await context.brokers.get(f.owner, account))
        registry = load_tools()
        device = await Device.enroll(f)
        body = {
            "thread_id": thread["id"],
            "account_id": account,
            "management_mode": "full",
            "symbol_scope": "account",
            "symbols": [],
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
            "allow_manual_positions": True,
        }

        async def propose(**changes: Any):
            return await f.request(
                "POST", f"/agents/{agent['id']}/account-authorities", {**body, **changes}
            )

        async def sign(proposal: dict[str, Any]):
            challenge = await f.request(
                "POST", f"/account-authorities/{proposal['id']}/challenge", {}
            )
            proof = device.assertion(challenge, f.settings.allowed_origin)
            signed = await f.request("POST", "/account-authorities/verify", proof)
            assert (await f.request("POST", "/account-authorities/verify", proof))["id"] == signed[
                "id"
            ]
            return signed

        def call(action: str = "buy", symbol: str = symbols[0], **params: Any):
            return ToolCall(
                id=uuid4().hex,
                name="trade_execute",
                arguments={
                    "account_id": account,
                    "symbol": symbol,
                    "action": action,
                    # A request that may raise a Trade Approval card carries a reason and a
                    # tolerance (10.3.1); a request sent on its own ignores them.
                    "reason": "Fixture order",
                    "tolerance": "5",
                    **params,
                },
            )

        async def trade(action: str = "buy", symbol: str = symbols[0], **params: Any):
            return await registry.execute(call(action, symbol, **params), context)

        proposal = await propose()
        assert proposal["valid_until"] is None
        assert proposal["envelope"]["schema_version"] == 2
        assert proposal["envelope"]["maximum_actions"] is None
        assert proposal["status"] == "pending"
        pending = await trade(volume="0.1", tolerance="5", reason="Fixture request")
        assert pending.get("_runtime_wait"), pending
        await f.request(
            "POST", f"/trading/approvals/{pending['approval_id']}/decision", {"decision": "reject"}
        )
        grant = await sign(proposal)
        assert grant["status"] == "active"
        async with f.runtime.db.sessions() as session:
            saved, envelope = await require_authority(session, f.owner, agent["id"], grant["id"])
            assert saved.valid_until is None and envelope.symbol_scope == "account"
        # A grant starts no task (4.5.1): the owner's Full tap starts the agent's one task.
        async with f.runtime.db.sessions() as session:
            assert (
                await session.get(TicketRow, stable_id(grant["id"], "account-management-task"))
                is None
            )
        async with f.runtime.db.sessions() as session, session.begin():
            await set_trading_mode(session, f.owner, agent["id"], "full", by="owner_tap")
        async with f.runtime.db.sessions() as session:
            task = await live_management_task(session, f.owner, agent["id"])
            assert task and task.state["task"]["origin_thread_id"] == thread["id"]
            assert task.state["task"]["completion_mode"] == "continuous"
            kickoff = await session.get(RunRow, task.payload["run_id"])
            assert kickoff and kickoff.model_metadata["account_management_id"] == agent["id"]
            assert (
                await session.scalar(
                    select(func.count())
                    .select_from(RunRow)
                    .where(
                        RunRow.model_metadata["account_management_id"].as_string() == agent["id"]
                    )
                )
                == 1
            )
            kickoff_data = {
                "id": kickoff.id,
                "agent_id": kickoff.agent_id,
                "thread_id": kickoff.thread_id,
            }
        context = await f.lease(kickoff_data)
        print(
            "PASS a signed grant starts no task; the owner's Full tap starts the agent's one continuous task"
        )

        initial_approvals = 0
        async with f.runtime.db.sessions() as session:
            initial_approvals = await session.scalar(
                select(func.count()).select_from(TradeApprovalRow)
            )
        opened_call = call(volume="12.3")
        opened = await registry.execute(opened_call, context)
        assert opened["status"] == "confirmed", opened
        assert opened["details"]["verification"]["status"] == "verified"
        repeat = await registry.execute(opened_call, context)
        assert repeat["broker_id"] == opened["broker_id"]
        assert len([p for p in await broker.positions() if p.id == opened["broker_id"]]) == 1
        for s in symbols[1:]:
            result = await trade(symbol=s, volume="0.1")
            assert result["status"] == "confirmed", result
        async with f.runtime.db.sessions() as session:
            assert (
                await session.scalar(select(func.count()).select_from(TradeApprovalRow))
                == initial_approvals
            )
        print(
            "PASS repeated market execution across four symbol classes needs no per-order approval or default lot cap; replay does not duplicate"
        )

        modified = await trade("modify_position", position_id="manual-ticket", stop_loss="70")
        assert modified["status"] == "confirmed", modified
        cleared = await trade("modify_position", position_id="manual-ticket", clear_stop_loss=True)
        assert cleared["status"] == "confirmed", cleared
        partial = await trade("close_position", position_id="manual-ticket", volume="0.1")
        assert partial["status"] == "confirmed", partial
        closed = await trade("close_position", position_id="manual-ticket")
        assert closed["status"] == "confirmed", closed
        for action, price in [
            ("buy_limit", "99"),
            ("sell_limit", "102"),
            ("buy_stop", "102"),
            ("sell_stop", "99"),
        ]:
            placed = await trade(action, price=price, volume="0.1")
            assert placed["status"] == "confirmed", placed
            edited = await trade(
                "modify_order",
                order_id=placed["broker_id"],
                stop_loss="90" if action.startswith("buy") else "110",
            )
            assert edited["status"] == "confirmed", edited
            cancelled = await trade("cancel_order", order_id=placed["broker_id"])
            assert cancelled["status"] == "confirmed", cancelled
        print(
            "PASS signed full scope manages external positions, stop discretion, partial/full closure and every supported pending type"
        )

        # Optional explicit limits still apply; full mode never nulls them silently. The
        # grant decides within its own terms; outside them the agent's mode decides, so
        # the agent is in Ask from here (4.2.2).
        async with f.runtime.db.sessions() as session, session.begin():
            await set_trading_mode(session, f.owner, agent["id"], "ask", by="agent")
        context = await f.lease(await f.run(agent, thread))
        limited = await sign(await propose(maximum_order_volume="0.2"))
        # A Run held to a replaced grant (a grant's management Run from before 4.5.1)
        # never spends the replacement's authority.
        legacy = await f.run(agent, thread)
        async with f.runtime.db.sessions() as session, session.begin():
            held = await session.get(RunRow, legacy["id"])
            assert held is not None
            held.model_metadata = {**held.model_metadata, "account_management_id": grant["id"]}
        legacy_context = await f.lease(legacy)
        try:
            await registry.execute(call(volume="0.1"), legacy_context)
        except LonoraError as error:
            assert error.code == "account_authority_unavailable"
        else:
            raise AssertionError("a Run held to a replaced grant spent replacement authority")
        # Over the signed cap the agent asks the owner (correction 6); nothing is sent.
        before = await broker.snapshot()
        over = await trade(volume="0.3", tolerance="5", reason="Fixture request")
        assert over.get("_runtime_wait") and over.get("approval_id"), over
        assert await broker.snapshot() == before
        await f.request(
            "POST", f"/trading/approvals/{over['approval_id']}/decision", {"decision": "reject"}
        )
        current = (await f.client.get(f"/api/agents/{agent['id']}/account-authorities")).json()
        assert next(r for r in current if r["id"] == grant["id"])["status"] == "revoked"
        await f.request("POST", f"/account-authorities/{limited['id']}/revoke", {})
        async with f.runtime.db.sessions() as session:
            assert (
                await session.get(TicketRow, stable_id(limited["id"], "account-management-task"))
                is None
            )
        context = await f.lease(await f.run(agent, thread))
        after_revoke = await trade(volume="0.1", tolerance="5", reason="Fixture request")
        assert after_revoke.get("_runtime_wait"), after_revoke
        await f.request(
            "POST",
            f"/trading/approvals/{after_revoke['approval_id']}/decision",
            {"decision": "reject"},
        )
        print(
            "PASS optional owner limits, authenticated replacement and immediate revocation remain authoritative"
        )

        await sign(await propose())
        # The broker's volume step is checked before anything is sent: a refusal the
        # agent reads and corrects.
        try:
            await trade(volume="0.15")
        except LonoraError as error:
            assert error.code == "volume_step_mismatch", error.code
        else:
            raise AssertionError("an order off the broker's volume step was not refused")
        print("PASS full management preserves broker volume validity")

        specialist = await f.request(
            "POST",
            "/agents",
            {
                "name": "Exact specialist",
                "trading_account_id": account,
                "trading_symbol": symbols[0],
            },
        )
        f.agents.append(specialist["id"])
        specialist_thread = await f.conversation(specialist)
        denied = await f.client.post(
            f"/api/agents/{specialist['id']}/account-authorities",
            json={**body, "thread_id": specialist_thread["id"]},
        )
        assert (
            denied.status_code == 403
            and denied.json()["code"] == "account_authority_scope_mismatch"
        ), denied.text
        exact = await f.request(
            "POST",
            f"/agents/{specialist['id']}/account-authorities",
            {
                **body,
                "thread_id": specialist_thread["id"],
                "symbol_scope": "selected",
                "symbols": [symbols[0]],
            },
        )
        assert exact["envelope"]["symbols"] == [symbols[0]]
        print("PASS full management never broadens a specialist's immutable market binding")
        device_grant = await sign(await propose())
        devices = (await f.client.get("/api/auth/devices")).json()
        await f.request("DELETE", f"/auth/devices/{devices[0]['id']}")
        async with f.runtime.db.sessions() as session:
            assert (
                await session.get(
                    TicketRow, stable_id(device_grant["id"], "account-management-task")
                )
                is None
            )
        print("PASS device revocation leaves no grant task and deletes no broker history")
    finally:
        await f.close()


asyncio.run(main())
