"""Signed full-management scope over disposable PostgreSQL and simulation only."""

import asyncio
from typing import Any
from uuid import uuid4

from check_streaming import Fixture
from device_fixture import Device
from lonora_adapter_kit.types import ToolCall
from lonora_contracts.domain import utcnow
from lonora_contracts.trading import TradingControl
from lonora_core.user_error import LonoraError
from lonora_db.account_authority import require_authority
from lonora_db.schema import RunRow, TicketRow, TradeApprovalRow, TradingAccountRow
from lonora_session.idempotency import stable_id
from lonora_tools.loader import load_tools
from lonora_trading.controls import read_controls, save_controls
from sqlalchemy import func, select


async def main():
    f = await Fixture().open()
    controls = await read_controls(f.runtime.db)
    try:
        # Use the real default Personal Agent; the fixture database is disposable.
        agents = (await f.client.get("/api/agents")).json()
        agent = next(row for row in agents if row["role"] == "personal")
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
        broker = await context.brokers.get(f.owner, account)
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
                arguments={"account_id": account, "symbol": symbol, "action": action, **params},
            )

        async def trade(action: str = "buy", symbol: str = symbols[0], **params: Any):
            return await registry.execute(call(action, symbol, **params), context)

        proposal = await propose()
        assert proposal["valid_until"] is None
        assert proposal["envelope"]["schema_version"] == 2
        assert proposal["envelope"]["maximum_actions"] is None
        assert proposal["status"] == "pending"
        await save_controls(f.runtime.db, TradingControl(enabled=True))
        pending = await trade(volume="0.1")
        assert pending.get("_runtime_wait"), pending
        await f.request(
            "POST", f"/trading/approvals/{pending['approval_id']}/decision", {"decision": "reject"}
        )
        grant = await sign(proposal)
        assert grant["status"] == "active"
        async with f.runtime.db.sessions() as session:
            saved, envelope = await require_authority(session, f.owner, agent["id"], grant["id"])
            assert saved.valid_until is None and envelope.symbol_scope == "account"
        task_id = stable_id(grant["id"], "account-management-task")
        async with f.runtime.db.sessions() as session:
            task = await session.get(TicketRow, task_id)
            assert task and task.state["task"]["origin_thread_id"] == thread["id"]
            kickoff = await session.get(RunRow, task.payload["run_id"])
            assert kickoff and kickoff.model_metadata["account_management_id"] == grant["id"]
            assert (
                await session.scalar(
                    select(func.count())
                    .select_from(RunRow)
                    .where(
                        RunRow.model_metadata["account_management_id"].as_string() == grant["id"]
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
            "PASS signed full management atomically starts one durable same-Agent task, bound to this exact grant"
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

        # Optional explicit limits still apply; full mode never nulls them silently.
        management_context = context
        context = await f.lease(await f.run(agent, thread))
        limited = await sign(await propose(maximum_order_volume="0.2"))
        try:
            await registry.execute(call(volume="0.1"), management_context)
        except LonoraError as error:
            assert error.code == "account_authority_unavailable"
        else:
            raise AssertionError("old management task spent replacement authority")
        rejected = await trade(volume="0.3")
        assert rejected["code"] == "account_authority_volume_limit", rejected
        current = (await f.client.get(f"/api/agents/{agent['id']}/account-authorities")).json()
        assert next(r for r in current if r["id"] == grant["id"])["status"] == "revoked"
        await f.request("POST", f"/account-authorities/{limited['id']}/revoke", {})
        context = await f.lease(await f.run(agent, thread))
        after_revoke = await trade(volume="0.1")
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
        await save_controls(f.runtime.db, TradingControl(enabled=False, emergency_stop=True))
        blocked = await trade(volume="0.1")
        assert blocked["status"] == "failed" and blocked["code"] == "emergency_stop", blocked
        await save_controls(f.runtime.db, TradingControl(enabled=True))
        invalid = await trade(volume="0.15")
        assert invalid["status"] == "failed" and invalid["code"] == "volume_step_mismatch", invalid
        print("PASS full management preserves emergency control and broker volume validity")

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
    finally:
        await save_controls(f.runtime.db, controls)
        await f.close()


asyncio.run(main())
