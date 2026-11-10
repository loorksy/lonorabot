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


@pytest.mark.asyncio
async def test_provider_test_lists_models_without_storing_the_key(monkeypatch):
    database()
    from check_streaming import Fixture
    from lonora_api.routes import connection_tests
    from lonora_db.schema import SecretRow
    from sqlalchemy import func, select

    monkeypatch.setattr(connection_tests, "model_adapter", lambda provider, key: FakeAdapter(key))
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
async def test_mcp_test_is_remote_only_and_broker_test_refuses_a_linked_account():
    database()
    from check_streaming import Fixture

    fixture = await Fixture().open()
    try:
        local = await fixture.client.post("/api/mcp/test", json={"url": "stdio://server"})
        assert local.status_code == 422
        private = await fixture.client.post("/api/mcp/test", json={"url": "http://127.0.0.1:9/mcp"})
        assert private.status_code >= 400 and private.status_code != 500, private.text
        simulation = await fixture.client.post(
            "/api/trading/connections/test",
            json={"provider": "simulation", "account_id": "sim-" + uuid4().hex[:8]},
        )
        assert simulation.status_code == 200, simulation.text
        assert simulation.json() == {"ok": True, "provider": "simulation"}
        missing = await fixture.client.post(
            "/api/trading/connections/test",
            json={"provider": "metaapi", "account_id": "acct-" + uuid4().hex[:8]},
        )
        assert missing.status_code == 409
        assert missing.json()["code"] == "broker_secret_required"
    finally:
        await fixture.close()
