"""«اختبار الاتصال» dry runs (WP-H): one real read-only round trip, nothing stored."""

import os
from typing import Any
from uuid import uuid4

import pytest


def database() -> None:
    if not os.environ.get("LONORA_DATABASE_URL"):
        pytest.skip("The dry-run routes are exercised through the owner API.")


class FakeAdapter:
    def __init__(self, key: str):
        self.key, self.closed = key, False

    async def discover(self) -> list[Any]:
        from types import SimpleNamespace

        if self.key != "sk-good-key-123":
            from lonora_core.user_error import LonoraError

            raise LonoraError("provider_authentication_failed", 401)
        return [SimpleNamespace(id="gpt-test")]

    async def close(self) -> None:
        self.closed = True


def fake_adapter(provider: str, key: str) -> FakeAdapter:
    return FakeAdapter(key)


@pytest.mark.asyncio
async def test_provider_test_lists_models_without_storing_the_key(monkeypatch: pytest.MonkeyPatch):
    database()
    from check_streaming import Fixture
    from lonora_api.routes import connection_tests
    from lonora_db.schema import SecretRow
    from sqlalchemy import func, select

    monkeypatch.setattr(connection_tests, "model_adapter", fake_adapter)
    fixture = await Fixture().open()
    try:
        async with fixture.runtime.db.sessions() as session:
            before = await session.scalar(select(func.count()).select_from(SecretRow))
        good = await fixture.client.post(
            "/api/providers/openai/test", json={"api_key": "sk-good-key-123"}
        )
        assert good.status_code == 200, good.text
        assert good.json() == {"ok": True, "models": ["gpt-test"]}
        bad = await fixture.client.post(
            "/api/providers/openai/test", json={"api_key": "sk-wrong-key-1"}
        )
        assert bad.status_code == 401
        async with fixture.runtime.db.sessions() as session:
            after = await session.scalar(select(func.count()).select_from(SecretRow))
        assert before == after
    finally:
        await fixture.close()


@pytest.mark.asyncio
async def test_dry_runs_are_owner_only_and_bounded(monkeypatch: pytest.MonkeyPatch):
    database()
    import asyncio

    import httpx
    from check_streaming import Fixture
    from lonora_api.routes import connection_tests

    class Slow(FakeAdapter):
        async def discover(self) -> list[Any]:
            await asyncio.sleep(5)
            return []

    monkeypatch.setattr(connection_tests, "TIMEOUT_SECONDS", 0.2)

    def slow_adapter(provider: str, key: str) -> FakeAdapter:
        return Slow(key)

    monkeypatch.setattr(connection_tests, "model_adapter", slow_adapter)
    fixture = await Fixture().open()
    try:
        anonymous = httpx.AsyncClient(
            transport=httpx.ASGITransport(app=fixture.app), base_url="http://localhost"
        )
        for path, body in (
            ("/api/providers/openai/test", {"api_key": "sk-good-key-123"}),
            ("/api/mcp/test", {"url": "https://mcp.example.com/mcp"}),
            ("/api/trading/connections/test", {"provider": "simulation", "account_id": "x"}),
        ):
            refused = await anonymous.post(path, json=body)
            assert refused.status_code in {401, 403}, (path, refused.status_code)
        await anonymous.aclose()
        slow = await fixture.client.post(
            "/api/providers/openai/test", json={"api_key": "sk-good-key-123"}
        )
        assert slow.status_code == 504 and slow.json()["code"] == "connection_test_timeout"
        assert "sk-good-key-123" not in slow.text
    finally:
        await fixture.close()


@pytest.mark.asyncio
async def test_mcp_test_is_remote_only_and_broker_test_refuses_a_linked_account():
    database()
    from check_streaming import Fixture

    fixture = await Fixture().open()
    try:
        local = await fixture.client.post("/api/mcp/test", json={"url": "stdio://server"})
        assert local.status_code == 422
        plain = await fixture.client.post(
            "/api/mcp/test", json={"url": "http://mcp.example.com/mcp"}
        )
        assert plain.status_code == 422, plain.text
        private = await fixture.client.post(
            "/api/mcp/test", json={"url": "https://127.0.0.1:9/mcp"}
        )
        assert private.status_code >= 400 and private.status_code != 500, private.text
        stored = await fixture.client.post(
            "/api/mcp",
            json={"payload": {"name": "plain", "transport": "http", "url": "http://a.example/mcp"}},
        )
        assert stored.status_code == 422, stored.text
        simulation = await fixture.client.post(
            "/api/trading/connections/test",
            json={"provider": "simulation", "account_id": "sim-" + uuid4().hex[:8]},
        )
        assert simulation.status_code == 200, simulation.text
        assert simulation.json() == {"ok": True, "provider": "simulation"}
        # The token is never echoed back, also when the account is rejected.
        token = "secret-token-" + uuid4().hex
        rejected = await fixture.client.post(
            "/api/trading/connections/test",
            json={"provider": "simulation", "account_id": "sim-x", "api_key": token},
        )
        assert token not in rejected.text
        # A MetaApi account is connected from chat (9.2), never tested or linked by its id.
        by_id = await fixture.client.post(
            "/api/trading/connections/test",
            json={"provider": "metaapi", "account_id": "acct-" + uuid4().hex[:8], "api_key": token},
        )
        assert by_id.status_code == 409
        assert by_id.json()["code"] == "broker_connect_from_chat"
        assert token not in by_id.text
    finally:
        await fixture.close()


@pytest.mark.asyncio
async def test_a_snapshot_imports_only_into_a_demo_connection():
    database()
    from check_streaming import Fixture
    from lonora_db.broker_sessions import BrokerSessionRepository

    fixture = await Fixture().open()
    try:
        async with fixture.runtime.db.sessions() as session, session.begin():
            broker = await BrokerSessionRepository().create(
                session,
                fixture.owner,
                {"provider": "metaapi", "account_id": "mt-" + uuid4().hex[:8], "enabled": False},
                broker_identity={
                    "login": str(uuid4().int % 10**8),
                    "server": "Fixture-Server",
                    "platform": "mt5",
                },
            )
        snapshot = {"snapshot": {"balance": "1000", "currency": "USD"}}
        refused = await fixture.client.post(
            f"/api/trading/connections/{broker.id}/simulation", json=snapshot
        )
        assert refused.status_code == 409, refused.text
        assert refused.json()["code"] == "simulation_provider_required"
        missing = await fixture.client.post(
            f"/api/trading/connections/{uuid4()}/simulation", json=snapshot
        )
        assert missing.status_code == 404
        demo = await fixture.request(
            "POST",
            "/trading/connections",
            {"provider": "simulation", "account_id": "sim-" + uuid4().hex[:8], "enabled": True},
        )
        imported = await fixture.client.post(
            f"/api/trading/connections/{demo['id']}/simulation", json=snapshot
        )
        assert imported.status_code == 200, imported.text
        await fixture.request("DELETE", f"/trading/connections/{demo['id']}")
        await fixture.request("DELETE", f"/trading/connections/{broker.id}")
    finally:
        await fixture.close()
