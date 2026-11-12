"""Removing a model provider's key: refused while anything still routes to the provider."""

import os
from typing import Any

import pytest

PROVIDER = "zai"
KEY = "sk-remove-me-123"
SELECTION = {"provider": PROVIDER, "model": "glm-test"}
GLOBAL = ("model_routing", "model_backups", "model_allowed")
IN_USE = {
    "the default model": ("model_routing", {"mode": "unified", "unified": SELECTION}),
    "a voice route": ("model_routing", {"mode": "unified", "routes": {"tts": SELECTION}}),
    "a backup": ("model_backups", {"choices": [SELECTION]}),
    "an allowed model": ("model_allowed", {"added": [SELECTION]}),
}


def database() -> None:
    if not os.environ.get("LONORA_DATABASE_URL"):
        pytest.skip("The provider routes are exercised through the owner API.")


async def setting(fixture: Any, key: str, payload: dict[str, Any] | None = None) -> dict[str, Any]:
    """Read one global setting, or write it when a payload is given."""
    from lonora_db.transactions import SettingsRepository

    async with fixture.runtime.db.sessions() as session, session.begin():
        if payload is None:
            return await SettingsRepository().get(session, key)
        await SettingsRepository().put(session, key, payload)
        return payload


async def stored_keys(fixture: Any) -> int:
    from lonora_db.schema import SecretRow
    from sqlalchemy import func, select

    async with fixture.runtime.db.sessions() as session:
        return await session.scalar(
            select(func.count())
            .select_from(SecretRow)
            .where(SecretRow.scope == "provider", SecretRow.name == PROVIDER)
        )


async def opened() -> tuple[Any, dict[str, dict[str, Any]]]:
    """A fixture with no global model choice, and the choices to put back afterwards."""
    from check_streaming import Fixture

    fixture = await Fixture().open()
    saved = {key: await setting(fixture, key) for key in GLOBAL}
    for key in GLOBAL:
        await setting(fixture, key, {})
    return fixture, saved


async def closed(fixture: Any, saved: dict[str, dict[str, Any]]) -> None:
    for key, payload in saved.items():
        await setting(fixture, key, payload)
    await fixture.close()


@pytest.mark.asyncio
async def test_an_unused_provider_key_is_removed_with_its_catalog(
    caplog: pytest.LogCaptureFixture,
) -> None:
    database()
    from lonora_db.schema import SettingRow

    fixture, saved = await opened()
    try:
        path = f"/api/providers/{PROVIDER}/credential"
        assert (await fixture.client.put(path, json={"api_key": KEY})).status_code == 200
        await setting(fixture, "catalog:" + PROVIDER, {"models": []})
        removed = await fixture.client.delete(path)
        assert removed.status_code == 200, removed.text
        assert removed.json() == {"configured": False}
        assert KEY not in removed.text and KEY not in caplog.text
        assert await stored_keys(fixture) == 0
        async with fixture.runtime.db.sessions() as session:
            assert await session.get(SettingRow, "catalog:" + PROVIDER) is None
        listed = {
            row["id"]: row["configured"]
            for row in (await fixture.client.get("/api/providers")).json()
        }
        assert listed[PROVIDER] is False
        again = await fixture.client.delete(path)
        assert again.status_code == 404
        assert again.json()["code"] == "provider_credential_not_stored"
    finally:
        await closed(fixture, saved)


@pytest.mark.asyncio
@pytest.mark.parametrize("use", list(IN_USE))
async def test_a_provider_in_use_keeps_its_key(use: str):
    database()
    fixture, saved = await opened()
    try:
        path = f"/api/providers/{PROVIDER}/credential"
        assert (await fixture.client.put(path, json={"api_key": KEY})).status_code == 200
        key, payload = IN_USE[use]
        await setting(fixture, key, payload)
        refused = await fixture.client.delete(path)
        assert refused.status_code == 409, (use, refused.text)
        assert refused.json()["code"] == "provider_in_use"
        assert await stored_keys(fixture) == 1
    finally:
        await setting(fixture, IN_USE[use][0], {})
        await fixture.client.delete(f"/api/providers/{PROVIDER}/credential")
        await closed(fixture, saved)


@pytest.mark.asyncio
async def test_an_agents_own_model_keeps_the_provider_key():
    database()
    from lonora_contracts.model_routing import AgentModelRecord
    from lonora_db.agent_models import agent_model_key
    from lonora_db.schema import SettingRow
    from sqlalchemy import delete

    fixture, saved = await opened()
    agent = await fixture.agent("m")
    record_key = agent_model_key(fixture.owner, agent["id"])
    try:
        path = f"/api/providers/{PROVIDER}/credential"
        assert (await fixture.client.put(path, json={"api_key": KEY})).status_code == 200
        record = AgentModelRecord.model_validate(
            {
                "owner_id": fixture.owner,
                "agent_id": agent["id"],
                "mode": "fixed",
                "preference": {"primary": SELECTION},
            }
        )
        await setting(fixture, record_key, record.model_dump(mode="json"))
        refused = await fixture.client.delete(path)
        assert refused.status_code == 409 and refused.json()["code"] == "provider_in_use"
        assert await stored_keys(fixture) == 1
    finally:
        async with fixture.runtime.db.sessions() as session, session.begin():
            await session.execute(delete(SettingRow).where(SettingRow.key == record_key))
        await fixture.client.delete(f"/api/providers/{PROVIDER}/credential")
        await closed(fixture, saved)


@pytest.mark.asyncio
async def test_only_the_owner_removes_a_provider_key():
    database()
    import httpx

    fixture, saved = await opened()
    try:
        path = f"/api/providers/{PROVIDER}/credential"
        assert (await fixture.client.put(path, json={"api_key": KEY})).status_code == 200
        anonymous = httpx.AsyncClient(
            transport=httpx.ASGITransport(app=fixture.app), base_url="http://localhost"
        )
        refused = await anonymous.delete(path)
        await anonymous.aclose()
        assert refused.status_code in {401, 403}
        assert await stored_keys(fixture) == 1
    finally:
        await fixture.client.delete(f"/api/providers/{PROVIDER}/credential")
        await closed(fixture, saved)
