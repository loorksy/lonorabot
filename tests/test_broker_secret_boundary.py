"""The broker destination (VISION.md 7.2.3, 14.3.11): the MetaApi token and broker passwords
are readable only by the broker adapter layer and provisioning, never by a tool context,
a workspace command or the general secret store; one a live connection uses is not deleted.
"""

import inspect
import os
import re
import sys
from pathlib import Path
from uuid import uuid4

import pytest
from lonora_core.user_error import LonoraError

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tests"))
# Code that may hold the broker reader; nothing under the tool or agent packages may.
BROKER_READERS = {
    "packages/adapters/src/lonora_adapters/storage/broker_secrets.py",
    "packages/adapters/src/lonora_adapters/brokers/base.py",
    "packages/trading/src/lonora_trading/connections.py",
    "packages/gateway/src/lonora_gateway/runtime.py",
    "apps/api/src/lonora_api/routes/trading.py",
    # Connect from chat: the card's save and the gateway's provisioning step.
    "apps/api/src/lonora_api/routes/secret_cards.py",
    "packages/trading/src/lonora_trading/broker_provisioning.py",
    "packages/gateway/src/lonora_gateway/service.py",
}


def test_only_the_broker_layer_constructs_the_broker_reader() -> None:
    holders = {
        str(path.relative_to(ROOT))
        for top in ("packages", "apps")
        for path in (ROOT / top).rglob("*.py")
        if any(
            use in path.read_text(encoding="utf-8")
            for use in ("import BrokerSecrets", "BrokerSecrets(", "class BrokerSecrets")
        )
    }
    assert holders == BROKER_READERS
    from lonora_adapters.brokers.base import BrokerManager

    manager = BrokerManager(None, None)  # type: ignore[arg-type]
    assert not hasattr(manager, "secrets")  # the reader is private to the adapter layer


def test_nothing_else_decrypts_or_reaches_into_the_broker_layer() -> None:
    """No module outside the stores decrypts a stored secret itself, and
    nothing reaches into ``BrokerManager``'s private reader."""
    stores = {
        "packages/adapters/src/lonora_adapters/storage/secret_store.py",
        "packages/adapters/src/lonora_adapters/storage/broker_secrets.py",
    }
    for top in ("packages", "apps"):
        for path in (ROOT / top).rglob("*.py"):
            name = str(path.relative_to(ROOT))
            if name.startswith("packages/security/") or "/migrations/" in name:
                continue
            text = path.read_text(encoding="utf-8")
            if name not in stores:
                # Encrypting is anyone's (a device token, say); reading a stored secret's
                # ciphertext back is only the stores'.
                assert not (
                    ".decrypt(" in text and re.search(r"SecretRow|ln_secrets|ciphertext", text)
                ), name
            if name != "packages/adapters/src/lonora_adapters/brokers/base.py":
                assert not re.search(r"\._secrets\b", text), name


def test_the_workspace_bridge_has_no_broker_reader() -> None:
    from lonora_agent import workspace, workspace_access, workspace_host

    # The workspace layer may hold the general store (to scan output for workspace
    # values), which refuses scope broker; never the broker reader or a raw decrypt.
    for module in (workspace, workspace_access, workspace_host):
        source = inspect.getsource(module)
        for name in ("BrokerSecrets", "SecretRow", "SecretCipher", "ciphertext"):
            assert name not in source


def test_the_token_has_one_fixed_name() -> None:
    import importlib.util

    from lonora_db.secrets import METAAPI_TOKEN, require_scope

    path = ROOT / "packages/db/migrations/versions/0145_metaapi_token.py"
    spec = importlib.util.spec_from_file_location("metaapi_token_migration", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    assert module.TOKEN == METAAPI_TOKEN == "metaapi_token"
    require_scope(METAAPI_TOKEN, "broker")


def database() -> None:
    if not os.environ.get("LONORA_DATABASE_URL"):
        pytest.skip("The broker secret boundary uses the PostgreSQL test database.")


@pytest.mark.asyncio
async def test_a_broker_value_never_leaves_the_broker_layer_and_a_used_one_is_kept() -> None:
    database()
    from check_streaming import Fixture
    from lonora_adapters.storage.broker_secrets import BrokerSecrets
    from lonora_db.schema import BrokerSessionRow

    fixture = await Fixture().open()
    try:
        key = fixture.runtime.settings.encryption_key.get_secret_value()
        broker = BrokerSecrets(fixture.runtime.db, key, fixture.owner)
        services = fixture.runtime.services(fixture.owner)
        value = "fixture.metaapi." + uuid4().hex
        async with fixture.runtime.db.sessions() as session, session.begin():
            token_id = await broker.write_in_session(session, "fixture_" + uuid4().hex, value)
        assert await broker.read(token_id) == value

        # The general store, which every tool context carries, refuses the scope.
        agent = await fixture.agent("Broker boundary")
        context = services.tool_context(
            agent["id"],
            agent["id"],
            None,  # pyright: ignore[reportArgumentType]  (the store is read, no run)
            Path("/tmp"),
        )
        for store in (services.secrets, context.secrets):
            with pytest.raises(LonoraError) as refused:
                await store.read(token_id)
            assert refused.value.code == "secret_scope_forbidden"
            with pytest.raises(LonoraError) as overwrite:
                await store.write("metaapi_token", "attacker.chosen.token", "broker")
            assert overwrite.value.code == "secret_scope_forbidden"
        assert await broker.read(token_id) == value

        # The broker reader reads nothing else.
        workspace_id = await services.secrets.write(
            "FIXTURE_" + uuid4().hex[:6].upper(), "w", "workspace"
        )
        with pytest.raises(LonoraError) as other:
            await broker.read(workspace_id)
        assert other.value.code == "secret_scope_forbidden"

        # DELETE /secrets/{id} stays (14.3.11) and refuses a broker secret a connection uses.
        async with fixture.runtime.db.sessions() as session, session.begin():
            connection = BrokerSessionRow(
                owner_id=fixture.owner,
                payload={
                    "provider": "metaapi",
                    "account_id": "fixture-" + uuid4().hex,
                    "secret_id": token_id,
                    "enabled": True,
                },
            )
            session.add(connection)
        refused = await fixture.client.delete("/api/secrets/" + token_id)
        assert refused.status_code == 409 and refused.json()["code"] == "secret_in_use"
        assert value not in refused.text
        assert await broker.read(token_id) == value
        async with fixture.runtime.db.sessions() as session, session.begin():
            row = await session.get(BrokerSessionRow, connection.id)
            assert row is not None
            await session.delete(row)
        assert (await fixture.client.delete("/api/secrets/" + token_id)).status_code == 200
        assert (await fixture.client.delete("/api/secrets/" + workspace_id)).status_code == 200
    finally:
        await fixture.close()
