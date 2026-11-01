"""Authenticated owner API, actual PostgreSQL and explicit simulation only."""

import asyncio
from typing import Any
from uuid import uuid4

from check_streaming import Fixture
from device_fixture import Device
from lonora_adapter_kit.types import ToolCall
from lonora_contracts.domain import AgentCreate, utcnow
from lonora_contracts.trading import TradingControl
from lonora_core.user_error import LonoraError
from lonora_db.account_authority import require_authority
from lonora_db.agent_binding import binding_context, require_financial_agent
from lonora_db.agents import agent_data, create_agent
from lonora_db.schema import AccountAuthorityRow, AgentRow
from lonora_tools.context import ToolContext
from lonora_tools.loader import load_tools
from lonora_trading.controls import read_controls, save_controls


async def main() -> None:
    f = await Fixture().open()
    controls = await read_controls(f.runtime.db)
    connections: list[str] = []
    try:
        general = await f.request(
            "POST",
            "/agents",
            {"name": "General", "scope_mode": "flexible", "instructions": "Research economic news"},
        )
        f.agents.append(general["id"])
        assert general["role"] == "general" and general["trading_symbol"] is None
        assert general["scope"]["visibility"] == "owner_accounts"
        assert general["instructions"] == "Research economic news"
        assert (await f.request("GET", f"/agents/{general['id']}/permissions"))[
            "effective_level"
        ] == "analysis"
        print("PASS general creation without a broker or default market; analysis-only authority")

        async def connection() -> str:
            value = await f.request(
                "POST",
                "/trading/connections",
                {"provider": "simulation", "account_id": uuid4().hex, "enabled": True},
            )
            account = value["id"]
            connections.append(account)
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
                            for symbol in ("EURUSDm", "XAUUSDm")
                        ],
                        "quotes": {
                            symbol: {
                                "symbol": symbol,
                                "bid": "100",
                                "ask": "101",
                                "observed_at": utcnow().isoformat(),
                                "source": "explicit-flexible-fixture",
                            }
                            for symbol in ("EURUSDm", "XAUUSDm")
                        },
                    }
                },
            )
            return account

        first, second = await connection(), await connection()

        async def create(mode: str) -> dict[str, Any]:
            value = await f.request(
                "POST",
                "/agents",
                {
                    "name": "Default market",
                    "scope_mode": mode,
                    "trading_account_id": first,
                    "trading_symbol": "EURUSDm",
                },
            )
            f.agents.append(value["id"])
            return value

        flexible, fixed = await create("flexible"), await create("fixed_market")
        renamed = await f.request("PATCH", f"/agents/{fixed['id']}", {"name": "Still fixed"})
        assert renamed["scope_mode"] == "fixed_market" and renamed["scope_revision"] == 0
        for data in (
            {"scope_mode": "flexible", "trading_account_id": first},
            {"scope_mode": "flexible", "trading_account_id": first, "trading_symbol": "UNKNOWN"},
        ):
            result = await f.client.post("/api/agents", json={"name": "Invalid", **data})
            assert result.status_code in (404, 422)
        incomplete = await f.client.patch(
            f"/api/agents/{fixed['id']}", json={"trading_symbol": "XAUUSDm"}
        )
        assert incomplete.status_code == 422
        print(
            "PASS exact symbol validation, incomplete binding rejection and legacy rename compatibility"
        )

        registry = load_tools()
        thread = await f.conversation(flexible)
        context = await f.lease(await f.run(flexible, thread))

        async def call(
            name: str, args: dict[str, Any], ctx: ToolContext = context
        ) -> dict[str, Any]:
            return await registry.execute(ToolCall(id=uuid4().hex, name=name, arguments=args), ctx)

        assert (await call("market_quote", {}))["symbol"] == "EURUSDm"
        assert (await call("market_quote", {"symbol": "XAUUSDm"}))["symbol"] == "XAUUSDm"
        assert (await call("market_quote", {"account_id": second, "symbol": "XAUUSDm"}))[
            "symbol"
        ] == "XAUUSDm"
        assert len((await call("market_symbols", {}))["symbols"]) == 2
        accounts = (await call("list_accounts", {}))["accounts"]
        assert {first, second}.issubset({item["connection_id"] for item in accounts})
        try:
            denied = await call(
                "trade_execute", {"action": "buy", "volume": "0.1", "stop_loss": "90"}
            )
            assert denied.get("code") == "agent_analysis_only", denied
        except LonoraError as error:
            assert error.code == "agent_analysis_only"
        chart = await call(
            "chart_open", {"account_id": second, "symbol": "XAUUSDm", "timeframe": "1h"}
        )
        assert chart
        fixed_thread = await f.conversation(fixed)
        fixed_context = await f.lease(await f.run(fixed, fixed_thread))
        try:
            await call("market_quote", {"account_id": first, "symbol": "XAUUSDm"}, fixed_context)
        except LonoraError as error:
            assert error.code == "agent_trading_symbol_mismatch"
        else:
            raise AssertionError("Legacy scope widened implicitly")
        print(
            "PASS default fill, explicit alternate market/account, full discovery, chart path and legacy rejection"
        )

        device = await Device.enroll(f)
        proposal = await f.request(
            "POST",
            f"/agents/{fixed['id']}/account-authorities",
            {
                "thread_id": fixed_thread["id"],
                "account_id": first,
                "symbols": ["EURUSDm"],
                "actions": ["buy"],
                "management_mode": "full",
            },
        )
        challenge = await f.request("POST", f"/account-authorities/{proposal['id']}/challenge", {})
        await f.request(
            "POST",
            "/account-authorities/verify",
            device.assertion(challenge, f.settings.allowed_origin),
        )
        async with f.runtime.db.sessions() as session:
            original = await session.get(AccountAuthorityRow, proposal["id"])
            assert original
            original_hash, original_envelope = original.envelope_hash, original.envelope

        converted = await f.request(
            "PATCH",
            f"/agents/{fixed['id']}",
            {
                "scope_mode": "flexible",
                "trading_account_id": first,
                "trading_symbol": "XAUUSDm",
                "expected_scope_revision": 0,
            },
        )
        assert converted["scope_revision"] == 1 and converted["trading_symbol"] == "XAUUSDm"
        async with f.runtime.db.sessions() as session:
            row, envelope = await require_authority(session, f.owner, fixed["id"], proposal["id"])
            assert row.envelope_hash == original_hash and row.envelope == original_envelope
            assert envelope.symbols == ["EURUSDm"]
        # The existing lease must use fresh identity; the old signature still permits
        # EURUSDm, while the newly preferred XAUUSDm is not authorized by that grant.
        await save_controls(f.runtime.db, TradingControl(enabled=True))
        opened = await call(
            "trade_execute",
            {
                "account_id": first,
                "symbol": "EURUSDm",
                "action": "buy",
                "volume": "0.1",
                "stop_loss": "90",
            },
            fixed_context,
        )
        assert opened["status"] == "confirmed", opened
        assert opened["details"]["verification"]["status"] == "verified"
        before = await (await context.brokers.get(f.owner, first)).positions()
        try:
            blocked = await call(
                "trade_execute",
                {
                    "account_id": first,
                    "symbol": "XAUUSDm",
                    "action": "buy",
                    "volume": "0.1",
                    "stop_loss": "90",
                },
                fixed_context,
            )
            assert blocked.get("code") == "account_authority_scope_mismatch", blocked
        except LonoraError as error:
            assert error.code == "account_authority_scope_mismatch"
        assert await (await context.brokers.get(f.owner, first)).positions() == before
        print(
            "PASS signed scope survives conversion unchanged; simulation confirms authorized execution and rejects default outside grant"
        )

        stale = await f.client.patch(
            f"/api/agents/{fixed['id']}",
            json={
                "scope_mode": "flexible",
                "trading_account_id": None,
                "trading_symbol": None,
                "expected_scope_revision": 0,
            },
        )
        assert stale.status_code == 409
        cleared = await f.request(
            "PATCH",
            f"/agents/{fixed['id']}",
            {
                "scope_mode": "flexible",
                "trading_account_id": None,
                "trading_symbol": None,
                "expected_scope_revision": 1,
            },
        )
        assert cleared["role"] == "general" and cleared["trading_symbol"] is None
        assert (await f.request("GET", f"/agents/{fixed['id']}"))["scope_revision"] == 2
        async with f.runtime.db.sessions() as session:
            persisted = await session.get(AgentRow, fixed["id"])
            assert persisted and "<flexible_agent_scope>" in binding_context(persisted)
            assert "<immutable_trading_market>" not in binding_context(persisted)
        async with f.runtime.db.sessions() as session, session.begin():
            child = await create_agent(
                session,
                f.owner,
                AgentCreate(name="Research child", scope_mode="flexible"),
                parent_id=general["id"],
            )
            child_data = agent_data(child)
            assert child.role == "delegated" and child.scope_mode == "fixed_market"
        f.agents.insert(0, child_data["id"])
        async with f.runtime.db.sessions() as session:
            try:
                await require_financial_agent(session, f.owner, child_data["id"])
            except LonoraError as error:
                assert error.code == "delegated_financial_authority_forbidden"
            else:
                raise AssertionError("General-agent child inherited financial authority")
        denied = await f.client.patch(
            f"/api/agents/{child_data['id']}",
            json={
                "scope_mode": "flexible",
                "trading_account_id": None,
                "trading_symbol": None,
                "expected_scope_revision": 0,
            },
        )
        assert denied.status_code == 403
        print(
            "PASS revision conflicts, clearing defaults, persisted identity, immutable child restrictions"
        )

        general_thread = await f.conversation(general)
        general_proposal = await f.request(
            "POST",
            f"/agents/{general['id']}/account-authorities",
            {
                "thread_id": general_thread["id"],
                "account_id": second,
                "symbols": [],
                "symbol_scope": "account",
                "actions": ["buy"],
                "management_mode": "full",
            },
        )
        assert general_proposal["status"] == "pending"
        assert (await f.request("GET", f"/agents/{general['id']}/permissions"))[
            "effective_level"
        ] == "analysis"
        print(
            "PASS general agent can propose account-wide scope without automatically activating it"
        )
    finally:
        await save_controls(f.runtime.db, controls)
        for account in connections:
            await f.request("DELETE", "/trading/connections/" + account)
        await f.close()


if __name__ == "__main__":
    asyncio.run(main())
