"""Cross-stack permissions acceptance using disposable PostgreSQL and simulation.

The scripted authenticator produces real WebAuthn signatures accepted by the
production verifier. This does not claim physical-device signing coverage.
"""

import asyncio
from decimal import Decimal
from typing import Any, cast
from unittest.mock import patch
from uuid import uuid4

import httpx
from check_streaming import Fixture
from device_fixture import Device
from lonora_adapter_kit.types import ToolCall
from lonora_adapters.brokers.simulation import SimulationBroker
from lonora_contracts.domain import utcnow
from lonora_contracts.trading import TradeRequest, TradeResult, TradingControl
from lonora_core.user_error import LonoraError
from lonora_db.agent_permissions import permission_key, permission_state
from lonora_db.schema import SettingRow, TicketRow, TradingJournalRow
from lonora_session.idempotency import stable_id
from lonora_tools.loader import load_tools
from lonora_trading.controls import read_controls, save_controls
from lonora_trading.goals import wake_goal
from sqlalchemy import func, select


async def main() -> None:
    f = await Fixture().open()
    controls = await read_controls(f.runtime.db)
    try:
        connection = await f.request(
            "POST",
            "/trading/connections",
            {"provider": "simulation", "account_id": "permissions-" + uuid4().hex, "enabled": True},
        )
        account = connection["id"]
        symbol = "EURUSD.exact"
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
                            "symbol": symbol,
                            "digits": 2,
                            "tick_size": "0.01",
                            "volume_min": "0.1",
                            "volume_max": "10",
                            "volume_step": "0.1",
                        }
                    ],
                    "quotes": {
                        symbol: {
                            "symbol": symbol,
                            "bid": "100",
                            "ask": "101",
                            "observed_at": utcnow().isoformat(),
                            "source": "explicit-simulation-fixture",
                        }
                    },
                }
            },
        )
        # Exercise actual new-Agent API creation and immutable specialist binding.
        agent = await f.request(
            "POST",
            "/agents",
            {
                "name": "Unified permissions A",
                "trading_account_id": account,
                "trading_symbol": symbol,
            },
        )
        other = await f.request(
            "POST",
            "/agents",
            {
                "name": "Unified permissions B",
                "trading_account_id": account,
                "trading_symbol": symbol,
            },
        )
        f.agents.extend([agent["id"], other["id"]])
        thread = await f.conversation(agent)
        await f.conversation(other)
        context = await f.lease(await f.run(agent, thread))
        broker = cast(SimulationBroker, await context.brokers.get(f.owner, account))
        registry = load_tools()
        device = await Device.enroll(f)
        path = f"/agents/{agent['id']}/permissions"

        async def state():
            return await f.request("GET", path)

        async def change(level: str):
            previous = await state()
            return await f.request(
                "PUT", path, {"level": level, "expected_revision": previous["revision"]}
            )

        def call(action: str = "buy", **params: Any):
            return ToolCall(
                id=uuid4().hex,
                name="trade_execute",
                arguments={"account_id": account, "symbol": symbol, "action": action, **params},
            )

        async def execute(intent: ToolCall) -> dict[str, Any]:
            try:
                return await registry.execute(intent, context)
            except LonoraError as error:
                return {"status": "failed", "code": error.code}

        proposal_body: dict[str, Any] = {
            "thread_id": thread["id"],
            "account_id": account,
            "management_mode": "full",
            "symbol_scope": "selected",
            "symbols": [symbol],
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
                "POST", f"/agents/{agent['id']}/account-authorities", {**proposal_body, **changes}
            )

        async def sign(proposal: dict[str, Any]):
            challenge = await f.request(
                "POST", f"/account-authorities/{proposal['id']}/challenge", {}
            )
            proof = device.assertion(challenge, f.settings.allowed_origin)
            return await f.request("POST", "/account-authorities/verify", proof), proof

        initial = await state()
        assert initial["effective_level"] == "analysis" and not initial["active_authorities"]
        async with f.runtime.db.sessions() as session:
            try:
                await permission_state(session, str(uuid4()), agent["id"])
            except LonoraError as error:
                assert error.code == "agent_not_found" and error.status == 404
            else:
                raise AssertionError("A foreign owner could read another Agent's permission state")
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(f.app), base_url="https://streaming.test"
        ) as anonymous:
            assert (await anonymous.get("/api" + path)).status_code == 401
        missing = await f.client.get("/api/agents/" + str(uuid4()) + "/permissions")
        assert missing.status_code == 404
        csrf = f.client.headers.pop("X-CSRF-Token")
        try:
            denied = await f.client.put(
                "/api" + path,
                json={"level": "supervised", "expected_revision": initial["revision"]},
            )
            assert denied.status_code == 403
        finally:
            f.client.headers["X-CSRF-Token"] = csrf
        unsigned = await f.client.put(
            "/api" + path, json={"level": "autonomous", "expected_revision": initial["revision"]}
        )
        assert unsigned.status_code in {403, 409, 422}
        assert (await state())["effective_level"] == "analysis"
        await save_controls(f.runtime.db, TradingControl(enabled=True))
        before = await broker.snapshot()
        denied = await execute(call(volume="0.1", stop_loss="90"))
        assert denied.get("code") == "agent_analysis_only", denied
        assert await broker.snapshot() == before
        try:
            await context.trading.execute(
                f.owner,
                TradeRequest(
                    account_id=account,
                    symbol=symbol,
                    action="buy",
                    volume=Decimal("0.1"),
                    stop_loss=Decimal("90"),
                ),
                context.lease,
            )
        except LonoraError as error:
            assert error.code == "agent_analysis_only", error.code
        else:
            raise AssertionError("Direct executor bypassed Analysis Only")
        assert await broker.snapshot() == before
        print(
            "PASS newly created Agent defaults to Analysis Only; auth/CSRF and unsigned autonomy cannot bypass server enforcement"
        )

        # The very same financial intent is proposed, not submitted, in supervised mode.
        supervised = await change("supervised")
        assert supervised["effective_level"] == "supervised"
        supervised_intent = call(volume="0.1", stop_loss="90")
        requested = await execute(supervised_intent)
        assert requested.get("_runtime_wait") and await broker.snapshot() == before, requested
        await f.request(
            "POST",
            f"/trading/approvals/{requested['approval_id']}/decision",
            {"decision": "approve"},
        )
        opened = await execute(supervised_intent)
        assert opened.get("status") == "confirmed", opened
        assert opened["details"]["verification"]["status"] == "verified"
        print(
            "PASS supervised selection needs no management signature and exact existing operation approval gates simulated execution"
        )

        draft = {
            "account_id": account,
            "symbol_scope": "selected",
            "symbols": [symbol],
            "actions": ["buy", "close_position"],
            "limits": {
                "maximum_order_volume": "0.3",
                "maximum_symbol_volume": "",
                "maximum_positions": "",
                "maximum_pending_orders": "0",
                "maximum_actions": "",
                "minimum_equity": "",
            },
            "duration": "24h",
            "allow_manual_positions": False,
        }
        previous = await state()
        saved = await f.request(
            "PUT",
            path + "/customization",
            {"expected_revision": previous["revision"], "customization": draft},
        )
        assert saved["customization"] == draft
        assert saved["effective_level"] == "supervised"
        pending = await propose(maximum_order_volume="0.3")
        assert (await state())["effective_level"] == "supervised"
        assert (await state())["pending_authority"]["id"] == pending["id"]
        challenge = await f.request("POST", f"/account-authorities/{pending['id']}/challenge", {})
        forged = device.assertion(challenge, f.settings.allowed_origin)
        forged["credential"]["response"]["signature"] = "AAAA"
        assert (
            await f.client.post("/api/account-authorities/verify", json=forged)
        ).status_code in {400, 403, 409, 422}
        assert (await state())["effective_level"] == "supervised"
        grant, used_proof = await sign(pending)
        active = await state()
        assert active["effective_level"] == "autonomous"
        assert active["active_authorities"][0]["id"] == grant["id"]
        assert active["active_authorities"][0]["envelope"]["maximum_order_volume"] == "0.3"
        # A pre-feature signed grant remains effective without a preference row.
        key = permission_key(f.owner, agent["id"])
        async with f.runtime.db.sessions() as session, session.begin():
            preference = await session.get(SettingRow, key)
            assert preference is not None
            legacy_payload = dict(preference.payload)
            await session.delete(preference)
        migrated = await state()
        assert migrated["effective_level"] == "autonomous"
        assert migrated["active_authorities"][0]["id"] == grant["id"]
        async with f.runtime.db.sessions() as session, session.begin():
            session.add(SettingRow(key=key, payload=legacy_payload))
        assert (await f.request("GET", f"/agents/{other['id']}/permissions"))[
            "effective_level"
        ] == "analysis"
        positions_before_autonomy = len(await broker.positions())
        autonomous = await execute(call(volume="0.2", stop_loss="91"))
        assert autonomous["status"] == "confirmed", autonomous
        assert autonomous["authorization"] == "account_authority", autonomous
        assert len(await broker.positions()) == positions_before_autonomy + 1
        excessive = await execute(call(volume="0.4", stop_loss="91"))
        assert excessive.get("code") == "account_authority_volume_limit", excessive
        assert len(await broker.positions()) == positions_before_autonomy + 1
        delegated_run = await f.request(
            "POST",
            "/runs",
            {
                "agent_id": agent["id"],
                "thread_id": thread["id"],
                "trigger": "subagent",
                "prompt": "Research only",
            },
        )
        delegated_context = await f.lease(delegated_run)
        previous_positions = len(await broker.positions())
        try:
            delegated_result = await registry.execute(
                call(volume="0.1", stop_loss="90"), delegated_context
            )
        except LonoraError as error:
            assert error.code == "observe_only_execution_forbidden", error.code
        else:
            assert delegated_result.get("status") != "confirmed", delegated_result
        assert len(await broker.positions()) == previous_positions
        print(
            "PASS pending/forged signatures retain previous effective level; real WebAuthn signature activates customized autonomy only for its Agent"
        )

        # All pending proposals must be invalidated, not just the currently active grant.
        waiting = await propose(actions=["sell"])
        waiting_challenge = await f.request(
            "POST", f"/account-authorities/{waiting['id']}/challenge", {}
        )
        waiting_proof = device.assertion(waiting_challenge, f.settings.allowed_origin)
        position_ids = {row.id for row in await broker.positions()}
        async with f.runtime.db.sessions() as session:
            journal_count = await session.scalar(
                select(func.count()).select_from(TradingJournalRow)
            )
        reduced = await change("analysis")
        assert reduced["effective_level"] == "analysis" and not reduced["active_authorities"]
        assert reduced["customization"] == draft
        assert {row.id for row in await broker.positions()} == position_ids
        replay = await context.trading.execute(
            f.owner,
            TradeRequest.model_validate(
                {
                    "operation_id": opened["operation_id"],
                    "account_id": account,
                    "symbol": symbol,
                    "action": "buy",
                    "volume": "0.1",
                    "stop_loss": "90",
                }
            ),
            context.lease,
        )
        assert replay.status == "confirmed" and replay.operation_id == opened["operation_id"]
        tool_replay = await execute(supervised_intent)
        assert tool_replay["results"][0]["status"] == "confirmed", tool_replay
        assert tool_replay["results"][0]["operation_id"] == opened["operation_id"]
        assert {row.id for row in await broker.positions()} == position_ids
        stale = await f.client.post("/api/account-authorities/verify", json=waiting_proof)
        assert stale.status_code in {403, 409}, stale.status_code
        # A consumed proof cannot return a currently active authorization after revocation.
        consumed = await f.client.post("/api/account-authorities/verify", json=used_proof)
        assert consumed.status_code == 403, consumed.status_code
        assert (await state())["effective_level"] == "analysis"
        assert (await execute(call(volume="0.1", stop_loss="90"))).get(
            "code"
        ) == "agent_analysis_only"
        async with f.runtime.db.sessions() as session:
            task = await session.get(TicketRow, stable_id(grant["id"], "account-management-task"))
            assert task and task.state["task"]["status"] == "cancelled"
            assert (
                await session.scalar(select(func.count()).select_from(TradingJournalRow))
                == journal_count
            )
        print(
            "PASS downgrade revokes pending proofs and grant work; no old signature reactivation, position closure, journal deletion or draft loss"
        )

        # Stale client updates cannot race a restrictive update and silently win.
        current = await state()
        updates = await asyncio.gather(
            *[
                f.client.put(
                    "/api" + path, json={"level": level, "expected_revision": current["revision"]}
                )
                for level in ("supervised", "analysis")
            ]
        )
        assert sorted(result.status_code for result in updates) == [200, 409], [
            r.status_code for r in updates
        ]
        assert (await state())["revision"] > current["revision"]
        await change("supervised")
        stale_revision = (await state())["revision"]
        await change("supervised")
        stale_proposal = await f.client.post(
            f"/api/agents/{agent['id']}/account-authorities?permission_revision={stale_revision}",
            json=proposal_body,
        )
        assert stale_proposal.status_code == 409
        assert (await state())["pending_authority"] is None

        # Revocation while the actual broker adapter is waiting must win at before_send.
        await sign(await propose())
        old_execute = broker.execute
        entered = asyncio.Event()
        release = asyncio.Event()

        async def delayed(request: TradeRequest, before_send: Any = None) -> TradeResult:
            entered.set()
            await release.wait()
            return await old_execute(request, before_send)

        count = len(await broker.positions())
        with patch.object(broker, "execute", side_effect=delayed):
            attempt = asyncio.create_task(execute(call(volume="0.1", stop_loss="92")))
            try:
                await asyncio.wait_for(entered.wait(), 10)
                await change("analysis")
                release.set()
                result = await asyncio.wait_for(attempt, 10)
                assert result.get("status") != "confirmed", result
                assert result.get("code") == "agent_analysis_only", result
                assert len(await broker.positions()) == count
            finally:
                release.set()
                attempt.cancel()
                await asyncio.gather(attempt, return_exceptions=True)
        print(
            "PASS concurrent revision conflicts reject stale writes; downgrade before broker send prevents financial mutation"
        )

        async def goal_case(title: str, stop_loss: str):
            return await f.request(
                "POST",
                "/trading/goals",
                {
                    "agent_id": agent["id"],
                    "thread_id": thread["id"],
                    "title": title,
                    "objective": "Explicit simulated permission boundary acceptance",
                    "account_id": account,
                    "symbol": symbol,
                    "autonomous": False,
                    "maximum_volume": "0.1",
                    "max_trade_actions": 1,
                    "steps": [
                        {
                            "id": "entry",
                            "title": "Exact simulated entry",
                            "kind": "trade",
                            "trade": {
                                "account_id": account,
                                "symbol": symbol,
                                "action": "buy",
                                "volume": "0.1",
                                "stop_loss": stop_loss,
                            },
                        }
                    ],
                },
            )

        async def goal_context(goal: dict[str, Any]):
            return await f.lease(await wake_goal(f.runtime.db, f.owner, goal["id"], "entry"))

        async def goal_action(goal: dict[str, Any], run_context: Any, identifier: str):
            return await registry.execute(
                ToolCall(
                    id=identifier,
                    name="goal_step_execute",
                    arguments={
                        "goal_id": goal["id"],
                        "step_id": "entry",
                        "note": "Reviewed current simulated evidence",
                    },
                ),
                run_context,
            )

        # A real legacy Super Bot signature cannot upgrade the current Agent level.
        legacy = await goal_case("Legacy Goal signature cannot enable analysis Agent", "94")
        await device.authorize_goal_service(f, legacy)
        legacy = await f.request("GET", "/trading/goals/" + legacy["id"])
        assert legacy["state"]["autonomous"] is True
        assert (await state())["effective_level"] == "analysis"
        legacy_context = await goal_context(legacy)
        goal_count = len(await broker.positions())
        try:
            await goal_action(legacy, legacy_context, "legacy-entry")
        except LonoraError as error:
            assert error.code == "agent_analysis_only", error.code
        else:
            raise AssertionError("Legacy autonomous Goal signature bypassed Analysis Only")
        assert len(await broker.positions()) == goal_count
        await change("supervised")
        pending_goal = await goal_action(legacy, legacy_context, "legacy-entry")
        assert pending_goal.get("_runtime_wait"), pending_goal
        assert len(await broker.positions()) == goal_count
        await f.request(
            "POST",
            f"/trading/approvals/{pending_goal['approval_id']}/decision",
            {"decision": "approve"},
        )
        approved_goal = await goal_action(legacy, legacy_context, "legacy-entry")
        assert approved_goal["result"]["status"] == "confirmed", approved_goal
        assert approved_goal["result"]["details"]["verification"]["status"] == "verified"
        assert len(await broker.positions()) == goal_count + 1

        # The next Goal uses the same executor only after signing an actual Agent account grant.
        await sign(await propose())
        autonomous_goal = await goal_case("Signed Agent grant manages Goal", "95")
        autonomous_context = await goal_context(autonomous_goal)
        autonomous_goal_result = await goal_action(
            autonomous_goal, autonomous_context, "signed-entry"
        )
        assert autonomous_goal_result["result"]["status"] == "confirmed", autonomous_goal_result
        assert len(await broker.positions()) == goal_count + 2
        print(
            "PASS legacy autonomous Goal signature cannot grant Agent rights; same Goal intent needs exact supervised approval or signed account authority"
        )

        for control, code, stop_loss in (
            (TradingControl(enabled=False), "trading_disabled", "96"),
            (TradingControl(enabled=True, emergency_stop=True), "emergency_stop", "97"),
        ):
            await save_controls(f.runtime.db, control)
            blocked_control = await execute(call(volume="0.2", stop_loss=stop_loss))
            assert blocked_control.get("code") == code, blocked_control
            assert len(await broker.positions()) == goal_count + 2
        await save_controls(f.runtime.db, TradingControl(enabled=True))

        old_goal = await goal_case("Recheck authority on resumed and fresh wakes", "98")
        old_context = await goal_context(old_goal)
        await change("analysis")
        for run_context in (old_context, await goal_context(old_goal)):
            try:
                await goal_action(old_goal, run_context, uuid4().hex)
            except LonoraError as error:
                assert error.code == "agent_analysis_only", error.code
            else:
                raise AssertionError("Old or newly woken Goal lease bypassed current Analysis Only")
            assert len(await broker.positions()) == goal_count + 2
        print(
            "PASS global trading OFF/emergency stop block signed autonomy; old and newly woken Goal leases recheck the current permission"
        )
        print(
            "Unified permissions acceptance complete: simulation and scripted authenticator only; no real-money trading or physical signing claim"
        )
    finally:
        await save_controls(f.runtime.db, controls)
        await f.close()


if __name__ == "__main__":
    asyncio.run(main())
