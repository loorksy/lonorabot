"""Real WebAuthn proofs and disposable PostgreSQL; no production grants or orders."""

import asyncio
from dataclasses import replace
from datetime import timedelta
from typing import Any, cast
from unittest.mock import patch
from uuid import uuid4

from check_streaming import Fixture
from device_fixture import Device
from lonora_adapter_kit.types import ToolCall
from lonora_adapters.brokers.simulation import SimulationBroker
from lonora_auth.account_authority import finish_activation
from lonora_auth.sessions import read_session
from lonora_contracts.domain import utcnow
from lonora_contracts.super_bot import DeviceProof
from lonora_contracts.trading import TradeResult, TradingControl
from lonora_core.user_error import LonoraError
from lonora_db.account_authority import authority_data, require_authority
from lonora_db.client import Database
from lonora_db.schema import (
    AccountAuthorityRow,
    DeviceChallengeRow,
    RunRow,
    TradingAccountRow,
    TradingJournalRow,
)
from lonora_tools.loader import load_tools
from lonora_trading.controls import read_controls, save_controls


async def main() -> None:
    f = await Fixture().open()
    controls = await read_controls(f.runtime.db)
    try:
        agent = await f.agent("Account authority")
        thread = await f.conversation(agent)
        context = await f.lease(await f.run(agent, thread))
        registry = load_tools()
        connection = await f.request(
            "POST",
            "/trading/connections",
            {
                "provider": "simulation",
                "account_id": "account-authority-" + uuid4().hex,
                "enabled": True,
            },
        )
        account = connection["id"]
        symbols = ["EURUSDm", "XAUUSDm", "US500.cash", "BTCUSD.pro"]
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
                        for symbol in symbols
                    ],
                    "quotes": {
                        symbol: {
                            "symbol": symbol,
                            "bid": "100",
                            "ask": "101",
                            "observed_at": utcnow().isoformat(),
                            "source": "explicit-fixture",
                        }
                        for symbol in symbols
                    },
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
            },
        )
        broker = cast(SimulationBroker, await context.brokers.get(f.owner, account))
        # Snapshot import deliberately initializes an empty trading ledger. Model
        # an external MT5 position by updating only this disposable fixture row.
        async with f.runtime.db.sessions() as session, session.begin():
            snapshot = await session.get(TradingAccountRow, account, with_for_update=True)
            assert snapshot
            snapshot.payload = {
                **snapshot.payload,
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
        await save_controls(f.runtime.db, TradingControl(enabled=True))

        def trade(action: str = "buy", symbol: str = symbols[0], **params: Any) -> ToolCall:
            return ToolCall(
                id=uuid4().hex,
                name="trade_execute",
                arguments={
                    "action": action,
                    "account_id": account,
                    "symbol": symbol,
                    **params,
                },
            )

        async def operation(
            action: str = "buy", symbol: str = symbols[0], **params: Any
        ) -> dict[str, Any]:
            return await registry.execute(trade(action, symbol, **params), context)

        before = await broker.snapshot()
        no_grant = await operation(volume="0.1", stop_loss="90")
        assert no_grant["_runtime_wait"] and await broker.snapshot() == before
        await f.request(
            "POST", f"/trading/approvals/{no_grant['approval_id']}/decision", {"decision": "reject"}
        )
        print("PASS no grant requires genuine per-request confirmation and sends nothing")

        proposal_body = {
            "thread_id": thread["id"],
            "account_id": account,
            "symbols": symbols,
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
            "maximum_order_volume": "0.5",
            "maximum_symbol_volume": "2",
            "maximum_positions": 10,
            "maximum_pending_orders": 5,
            "maximum_actions": 100,
            "minimum_equity": "9000",
            "valid_until": (utcnow() + timedelta(days=1)).isoformat(),
            "allow_manual_positions": False,
        }

        async def propose(**overrides: Any) -> dict[str, Any]:
            return await f.request(
                "POST", f"/agents/{agent['id']}/account-authorities", {**proposal_body, **overrides}
            )

        device = await Device.enroll(f)
        proposal = await propose()
        assert proposal["status"] == "pending"
        assert (await propose())["id"] == proposal["id"]
        assert proposal["monetary_stop_risk"] == "unavailable"
        before = await broker.snapshot()
        pending = await operation(volume="0.1", stop_loss="90")
        assert pending["_runtime_wait"] and await broker.snapshot() == before
        await f.request(
            "POST", f"/trading/approvals/{pending['approval_id']}/decision", {"decision": "reject"}
        )
        unknown = await f.client.post(
            f"/api/agents/{agent['id']}/account-authorities",
            json={**proposal_body, "symbols": ["UNKNOWNm"]},
        )
        assert unknown.status_code == 404 and unknown.json()["code"] == "symbol_not_found"
        print(
            "PASS immutable pending requests deduplicate and text/pending requests grant no authority"
        )

        challenge = await f.request("POST", f"/account-authorities/{proposal['id']}/challenge", {})
        async with f.runtime.db.sessions() as session:
            identity = await read_session(session, f.client.cookies.get("lonora_session"))

        async def denied(
            payload: dict[str, Any], code: str, *, other_session: bool = False
        ) -> None:
            try:
                async with f.runtime.db.sessions() as session, session.begin():
                    await finish_activation(
                        session,
                        replace(identity, token_hash="other-session")
                        if other_session
                        else identity,
                        DeviceProof.model_validate(payload),
                        f.settings.allowed_origin,
                    )
            except LonoraError as error:
                assert error.code == code, error.code
            else:
                raise AssertionError("invalid account authority activated")

        await denied(
            device.assertion(challenge, f.settings.allowed_origin, verified=False),
            "device_proof_invalid",
        )
        await denied(device.assertion(challenge, "https://wrong.example"), "device_proof_invalid")
        forged = device.assertion(challenge, f.settings.allowed_origin)
        forged["credential"]["response"]["signature"] = "AAAA"
        await denied(forged, "device_proof_invalid")
        await denied(
            device.assertion(challenge, f.settings.allowed_origin),
            "device_challenge_not_found",
            other_session=True,
        )
        proof = device.assertion(challenge, f.settings.allowed_origin)
        grant = await f.request("POST", "/account-authorities/verify", proof)
        assert grant["status"] == "active"
        assert (await f.request("POST", "/account-authorities/verify", proof))["id"] == grant["id"]
        print(
            "PASS real signed UV, origin/session isolation, forged proofs and idempotent activation"
        )

        buy_call = trade(volume="0.1", stop_loss="90", take_profit="110")
        opened = await registry.execute(buy_call, context)
        assert opened["status"] == "confirmed", opened
        assert opened["details"]["verification"]["status"] == "verified"
        repeat = await registry.execute(buy_call, context)
        assert repeat["broker_id"] == opened["broker_id"]
        assert len(await broker.positions()) == 2
        for symbol in symbols[1:]:
            result = await operation(symbol=symbol, volume="0.1", stop_loss="90")
            assert result["status"] == "confirmed", result
        modified = await operation(
            "modify_position", position_id=opened["broker_id"], stop_loss="91"
        )
        assert modified["status"] == "confirmed", modified
        for action, price in (
            ("buy_limit", "99"),
            ("sell_limit", "102"),
            ("buy_stop", "102"),
            ("sell_stop", "99"),
        ):
            pending_order = await operation(
                action,
                volume="0.1",
                price=price,
                stop_loss="90" if action.startswith("buy") else "110",
            )
            assert pending_order["status"] == "confirmed", pending_order
            edit = await operation(
                "modify_order",
                order_id=pending_order["broker_id"],
                stop_loss="91" if action.startswith("buy") else "109",
            )
            assert edit["status"] == "confirmed", edit
            cancelled = await operation("cancel_order", order_id=pending_order["broker_id"])
            assert cancelled["status"] == "confirmed", cancelled
        print(
            "PASS repeated signed account trades across exact forex/metal/index/crypto symbols; pending and management use one verified executor"
        )

        denied_manual = await operation("close_position", position_id="manual-ticket")
        assert denied_manual["code"] == "account_authority_manual_permission_required", (
            denied_manual
        )
        for params, code in (
            ({"volume": "0.6", "stop_loss": "90"}, "account_authority_volume_limit"),
            ({"volume": "0.1"}, "account_authority_stop_loss_required"),
        ):
            blocked = await operation(**params)
            assert blocked["code"] == code, blocked
        widened = await operation(
            "modify_position", position_id=opened["broker_id"], stop_loss="80"
        )
        assert widened["code"] == "account_authority_protection_expansion_forbidden", widened
        print("PASS scope volume/protection/manual ownership limits remain server authoritative")

        async with f.runtime.db.sessions() as session, session.begin():
            row = await session.get(RunRow, context.lease.run_id)
            assert row
            row.model_metadata = {**row.model_metadata, "voice_handoff": {"finalized": False}}
        partial = await operation(volume="0.1", stop_loss="90")
        assert partial["_runtime_wait"]
        await f.request(
            "POST", f"/trading/approvals/{partial['approval_id']}/decision", {"decision": "reject"}
        )
        async with f.runtime.db.sessions() as session, session.begin():
            row = await session.get(RunRow, context.lease.run_id)
            assert row
            row.model_metadata = {
                key: value for key, value in row.model_metadata.items() if key != "voice_handoff"
            }
        await save_controls(f.runtime.db, TradingControl(enabled=False))
        stopped = await operation(volume="0.1", stop_loss="90")
        assert stopped["status"] == "failed" and stopped["code"] == "trading_disabled", stopped
        await save_controls(f.runtime.db, TradingControl(enabled=True, emergency_stop=True))
        stopped = await operation(volume="0.1", stop_loss="90")
        assert stopped["status"] == "failed" and stopped["code"] == "emergency_stop", stopped
        await save_controls(f.runtime.db, TradingControl(enabled=True))
        print(
            "PASS provisional voice requires real confirmation; global OFF and Emergency Stop dominate grants"
        )

        async with f.runtime.db.sessions() as session, session.begin():
            row = await session.get(TradingAccountRow, account, with_for_update=True)
            assert row
            row.payload = {**row.payload, "equity": "8900"}
        floor = await operation(volume="0.1", stop_loss="90")
        assert floor["code"] == "account_authority_equity_floor", floor
        async with f.runtime.db.sessions() as session, session.begin():
            row = await session.get(TradingAccountRow, account, with_for_update=True)
            assert row
            row.payload = {**row.payload, "equity": "10000"}

        real_execute = broker.execute

        async def activate(**overrides: Any) -> dict[str, Any]:
            pending = await propose(**overrides)
            fresh_challenge = await f.request(
                "POST", f"/account-authorities/{pending['id']}/challenge", {}
            )
            return await f.request(
                "POST",
                "/account-authorities/verify",
                device.assertion(fresh_challenge, f.settings.allowed_origin),
            )

        # Replacement scope needs another genuine signature. Older signed
        # requests remain revoked and cannot enlarge the replacement.
        await activate(maximum_order_volume="0.3", maximum_symbol_volume="0.3")
        limited = await operation(volume="0.1", stop_loss="90")
        assert limited["code"] == "account_authority_symbol_volume_limit", limited
        await activate(maximum_positions=len(await broker.positions()))
        limited = await operation(volume="0.1", stop_loss="90")
        assert limited["code"] == "account_authority_position_limit", limited
        await activate(maximum_pending_orders=0)
        limited = await operation("buy_limit", volume="0.2", price="98", stop_loss="90")
        assert limited["code"] == "account_authority_pending_limit", limited

        limited_grant = await activate(maximum_actions=1)
        before_count = len(await broker.positions())
        attempts = await asyncio.gather(
            operation(volume="0.2", stop_loss="90"),
            operation(volume="0.3", stop_loss="90"),
        )
        assert sum(item.get("status") == "confirmed" for item in attempts) == 1, attempts
        assert len(await broker.positions()) == before_count + 1
        assert all(
            item.get("status") == "confirmed"
            or item.get("code")
            in {"account_authority_action_limit", "broker_reconciliation_required"}
            for item in attempts
        ), attempts
        limited = await operation(volume="0.4", stop_loss="90")
        assert limited["code"] == "account_authority_action_limit", limited
        fresh_db = Database.connect(f.settings.database_url)
        try:
            async with fresh_db.sessions() as session:
                restored, _ = await require_authority(
                    session, f.owner, agent["id"], limited_grant["id"]
                )
                assert restored.status == "active"
                try:
                    await require_authority(session, "different-owner", agent["id"], restored.id)
                except LonoraError as error:
                    assert error.code == "account_authority_not_found"
                else:
                    raise AssertionError("cross-owner grant exposed")
        finally:
            await fresh_db.close()
        print(
            "PASS signed scope/slot/budget limits serialize concurrent intents and survive fresh DB connections"
        )

        rejected_grant = await activate(maximum_actions=1)

        async def broker_reject(request: Any, before_send: Any = None) -> TradeResult:
            assert before_send
            await before_send()
            return TradeResult(
                operation_id=request.operation_id, status="failed", code="market_closed"
            )

        # Use a new Run to avoid reusing the intentionally terminal operation
        # identities from the previous lifetime-budget checks.
        context = await f.lease(await f.run(agent, thread))
        rejection_call = trade(volume="0.1", stop_loss="90")
        before_count = len(await broker.positions())
        with patch.object(broker, "execute", side_effect=broker_reject):
            rejected = await registry.execute(rejection_call, context)
        assert rejected["status"] == "failed" and rejected["code"] == "market_closed", rejected
        assert len(await broker.positions()) == before_count
        async with f.runtime.db.sessions() as session:
            journal = await session.get(TradingJournalRow, rejected["operation_id"])
            assert journal and journal.result["details"]["execution"]["send_authorized"] is True
            assert (
                journal.result["details"]["execution"]["account_authority_id"]
                == rejected_grant["id"]
            )
        limited = await operation(volume="0.2", stop_loss="90")
        assert limited["code"] == "account_authority_action_limit", limited
        print(
            "PASS broker rejection retains server submission attribution and cannot refund standing action budget"
        )

        grant = await activate(allow_manual_positions=True)
        context = await f.lease(await f.run(agent, thread))
        partial_close = await operation("close_position", position_id="manual-ticket", volume="0.1")
        assert partial_close["status"] == "confirmed", partial_close
        full_close = await operation("close_position", position_id="manual-ticket")
        assert full_close["status"] == "confirmed", full_close
        assert not any(p.id == "manual-ticket" for p in await broker.positions())

        async def owner_intervenes(request: Any, before_send: Any = None) -> TradeResult:
            async with f.runtime.db.sessions() as session, session.begin():
                state = await session.get(TradingAccountRow, account, with_for_update=True)
                assert state
                state.payload = {
                    **state.payload,
                    "positions": [
                        {**item, "stop_loss": "93"} if item["id"] == opened["broker_id"] else item
                        for item in state.payload["positions"]
                    ],
                }
            return await real_execute(request, before_send)

        with patch.object(broker, "execute", side_effect=owner_intervenes):
            changed_target = await operation(
                "modify_position", position_id=opened["broker_id"], stop_loss="92"
            )
        assert changed_target["code"] == "account_authority_broker_state_changed", changed_target
        assert (
            next(p for p in await broker.positions() if p.id == opened["broker_id"]).stop_loss == 93
        )
        print(
            "PASS manual position management requires signed permission; owner changes between observation and send win"
        )

        async with f.runtime.db.sessions() as session:
            row = await session.get(AccountAuthorityRow, grant["id"])
            assert row
            with patch(
                "lonora_db.account_authority.utcnow",
                return_value=row.valid_until + timedelta(seconds=1),
            ):
                assert authority_data(row)["status"] == "expired"
                try:
                    await require_authority(session, f.owner, agent["id"], row.id)
                except LonoraError as error:
                    assert error.code == "account_authority_unavailable"
                else:
                    raise AssertionError("expired grant authorized execution")
            row.status = "revoked"
            with patch(
                "lonora_db.account_authority.utcnow",
                return_value=row.valid_until + timedelta(seconds=1),
            ):
                assert authority_data(row)["status"] == "revoked"
        print("PASS expiry is enforced and terminal revoked state remains visible after expiry")

        context = await f.lease(await f.run(agent, thread))

        async def lose_ack(*args: Any, **kwargs: Any):
            await real_execute(*args, **kwargs)
            raise TimeoutError("scripted response loss")

        ambiguous_call = trade(volume="0.1", stop_loss="90")
        with patch.object(broker, "execute", side_effect=lose_ack):
            ambiguous = await registry.execute(ambiguous_call, context)
        assert ambiguous["status"] == "ambiguous", ambiguous
        count = len(await broker.positions())
        replayed = await registry.execute(ambiguous_call, context)
        assert replayed["status"] == "ambiguous" and len(await broker.positions()) == count
        # A different financial intent must be blocked; identical intent in this
        # Run correctly replays the original ambiguous receipt regardless of call ID.
        next_trade = await operation(volume="0.2", stop_loss="90")
        assert next_trade["code"] == "broker_reconciliation_required", next_trade
        async with f.runtime.db.sessions() as session:
            journal = await session.get(TradingJournalRow, ambiguous["operation_id"])
            assert (
                journal
                and journal.result["details"]["execution"]["account_authority_id"] == grant["id"]
            )
        print(
            "PASS lost acknowledgement persists grant provenance, replay never resends, unresolved account blocks subsequent autonomous operations"
        )

        revoked = await f.request("POST", f"/account-authorities/{grant['id']}/revoke", {})
        assert revoked["status"] == "revoked"
        assert (await f.request("POST", "/account-authorities/verify", proof))[
            "status"
        ] == "revoked"
        needs_approval = await operation(volume="0.1", stop_loss="90")
        assert needs_approval["_runtime_wait"]
        print(
            "PASS revocation and lost-response proof replay cannot restore grant; absent authority returns to explicit approval"
        )

        fresh = await propose()
        challenge = await f.request("POST", f"/account-authorities/{fresh['id']}/challenge", {})
        async with f.runtime.db.sessions() as session, session.begin():
            row = await session.get(AccountAuthorityRow, fresh["id"])
            assert row
            row.envelope = {**row.envelope, "maximum_order_volume": "5"}
        await denied(
            device.assertion(challenge, f.settings.allowed_origin),
            "account_authority_expired_or_changed",
        )
        async with f.runtime.db.sessions() as session, session.begin():
            row = await session.get(DeviceChallengeRow, challenge["challenge_id"])
            assert row
            row.expires_at = utcnow() - timedelta(seconds=1)
        await denied(
            device.assertion(challenge, f.settings.allowed_origin),
            "device_challenge_expired_or_used",
        )
        print("PASS persisted envelope tampering and expired challenges cannot activate authority")
    finally:
        await save_controls(f.runtime.db, controls)
        await f.close()


if __name__ == "__main__":
    asyncio.run(main())
