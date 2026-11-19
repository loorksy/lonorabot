"""Stored secrets by scope (VISION.md 7.2.3, 7.2.4, 14.3.11).

Workspace secrets are the owner's, named as environment variables; per-agent secrets
moved there; a secret a connection uses is not deleted; the scope set is closed.
"""

import importlib.util
import os
import re
import sys
from pathlib import Path
from uuid import uuid4

import pytest
from lonora_contracts.agent_secrets import WORKSPACE_SECRET_NAME
from lonora_core.user_error import LonoraError
from lonora_db.secrets import require_scope

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tests"))


def migration():
    path = ROOT / "packages/db/migrations/versions/0070_secret_scopes.py"
    spec = importlib.util.spec_from_file_location("secret_scopes_migration", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_workspace_names_are_environment_variable_names() -> None:
    for name in ("A", "OPENAI_API_KEY", "X1", "A" + "B" * 63):
        require_scope(name, "workspace")
        assert re.fullmatch(WORKSPACE_SECRET_NAME, name)
    for name in ("", "a", "1A", "_A", "A-B", "A B", "A" * 65, "openai"):
        with pytest.raises(LonoraError) as refused:
            require_scope(name, "workspace")
        assert refused.value.code == "secret_name_invalid"
        assert not re.fullmatch(WORKSPACE_SECRET_NAME, name)
    # Other scopes keep their own names (a broker account number, a provider name).
    require_scope("12345678", "broker")
    require_scope("openai", "provider")
    require_scope("Brave", "integration")


def test_the_scope_set_is_closed() -> None:
    for scope in ("agent:abc", "owner", "", "Workspace"):
        with pytest.raises(LonoraError) as refused:
            require_scope("NAME", scope)
        assert refused.value.code == "secret_scope_invalid"


def test_per_agent_secret_names_become_unique_workspace_names() -> None:
    name = migration().workspace_name
    taken: set[str] = {"TAKEN"}
    assert name("openai key", taken) == "OPENAI_KEY"
    assert name("taken", taken) == "TAKEN_2"
    assert name("Taken", taken) == "TAKEN_3"
    assert name("9lives", taken) == "S_9LIVES"
    assert name("_x", taken) == "S__X"
    assert name("مفتاح", taken) == "S______"
    long = name("k" * 80, taken)
    assert long == "K" * 64 and name("k" * 80, taken) == "K" * 62 + "_2"
    for item in taken:
        require_scope(item, "workspace")


def database() -> None:
    if not os.environ.get("LONORA_DATABASE_URL"):
        pytest.skip("Secret scopes use the PostgreSQL test database.")


@pytest.mark.asyncio
async def test_workspace_secrets_are_the_owners_and_a_used_secret_is_not_deleted() -> None:
    database()
    from check_streaming import Fixture
    from lonora_db.schema import IntegrationRow

    fixture = await Fixture().open()
    try:
        name = "FIXTURE_" + uuid4().hex[:8].upper()
        services = fixture.runtime.services(fixture.owner)
        workspace_id = await services.secrets.write(name, "s3cr3t", "workspace")
        # A secret is saved only through a Secret card; there is no other write route.
        assert (await fixture.client.post("/api/secrets", json={"name": name})).status_code == 405
        listed = (await fixture.client.get("/api/secrets")).json()
        entry = next(item for item in listed if item["name"] == name)
        assert set(entry) == {"id", "name", "updated_at"}  # never the value
        # The per-agent routes are gone: secrets belong to the owner (7.2.4).
        agent = await fixture.agent("Secrets")
        gone = await fixture.client.get(f"/api/agents/{agent['id']}/secrets")
        assert gone.status_code in {404, 405}

        # A connection names only a secret of its own scope (7.2.3): a workspace value
        # is never sent to a search service.
        crossed = await fixture.client.post(
            "/api/integrations",
            json={
                "payload": {
                    "type": "brave_search",
                    "name": "search",
                    "secret_id": workspace_id,
                }
            },
        )
        assert crossed.status_code == 403
        assert crossed.json()["code"] == "secret_scope_forbidden"

        used_id = await services.secrets.write("fixture-feed", uuid4().hex, "integration")
        async with fixture.runtime.db.sessions() as session, session.begin():
            connection = IntegrationRow(
                owner_id=fixture.owner,
                payload={"type": "news_feed", "name": "feed", "secret_id": used_id},
            )
            session.add(connection)
        refused = await fixture.client.delete("/api/secrets/" + used_id)
        assert refused.status_code == 409
        assert refused.json()["code"] == "secret_in_use"
        assert await services.secrets.read(used_id)
        async with fixture.runtime.db.sessions() as session, session.begin():
            row = await session.get(IntegrationRow, connection.id)
            assert row is not None
            await session.delete(row)
        assert (await fixture.client.delete("/api/secrets/" + used_id)).status_code == 200
        assert (await fixture.client.delete("/api/secrets/" + entry["id"])).status_code == 200
        with pytest.raises(LonoraError):
            await services.secrets.write("x", "y", "agent:" + agent["id"])
    finally:
        await fixture.close()
