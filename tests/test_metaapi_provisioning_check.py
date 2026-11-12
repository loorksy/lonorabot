"""The live provisioning check the lead runs on the owner's server, run here against the
provisioning fake: it finds the connection's account again, reads its state, gets the two
refusals it probes for, and prints no secret, login, server or account id."""

import importlib.util
import sys
from pathlib import Path
from typing import Any
from unittest.mock import patch
from uuid import uuid4

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tests"))
sys.path.insert(0, str(ROOT))
from test_supervision import database  # noqa: E402

from scripts.agent_eval.broker import FakeMetaApiProvisioning, FakeProvisioningApi  # noqa: E402


def script() -> Any:
    path = ROOT / "scripts/metaapi_provisioning_check.py"
    spec = importlib.util.spec_from_file_location("metaapi_provisioning_check", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.mark.asyncio
async def test_the_live_check_reads_finds_and_probes_without_printing_identifiers(
    capsys: pytest.CaptureFixture[str],
) -> None:
    database()
    from check_streaming import Fixture
    from lonora_adapters.storage.broker_secrets import BrokerSecrets
    from lonora_db.broker_sessions import BrokerSessionRepository
    from lonora_db.schema import BrokerSessionRow, SecretRow
    from lonora_db.secrets import METAAPI_TOKEN
    from sqlalchemy import delete, select

    fixture = await Fixture().open()
    login, server = str(70000000 + uuid4().int % 9999999), "Fixture-MT5Demo"
    password, token = "fixture-master-" + uuid4().hex, "fixture.metaapi." + uuid4().hex
    api = FakeProvisioningApi(servers={server: {login: password}})
    metaapi_id = api.link(login, server)
    check = script()
    secrets = BrokerSecrets(
        fixture.runtime.db,
        fixture.runtime.settings.encryption_key.get_secret_value(),
        fixture.owner,
    )
    row: Any = None
    try:
        async with fixture.runtime.db.sessions() as session, session.begin():
            await session.execute(
                delete(SecretRow).where(
                    SecretRow.owner_id == fixture.owner, SecretRow.name == METAAPI_TOKEN
                )
            )
            token_id = await secrets.write_in_session(session, METAAPI_TOKEN, token)
            row = await BrokerSessionRepository().create(
                session,
                fixture.owner,
                {
                    "provider": "metaapi",
                    "account_id": metaapi_id,
                    "secret_id": token_id,
                    "enabled": True,
                },
                broker_identity={"login": login, "server": server, "platform": "mt5"},
            )
        others = []
        async with fixture.runtime.db.sessions() as session:
            others = [
                r.id
                for r in await session.scalars(
                    select(BrokerSessionRow).where(BrokerSessionRow.owner_id == fixture.owner)
                )
                if r.payload.get("provider") == "metaapi" and r.id != row.id
            ]

        def client(value: str) -> FakeMetaApiProvisioning:
            return FakeMetaApiProvisioning(api, value)

        with patch.object(check, "MetaApiProvisioning", client):
            await check.check(False, owner=fixture.owner)
            quiet = capsys.readouterr().out
            calls = list(api.calls)
            code = await check.check(True, owner=fixture.owner)
        out = capsys.readouterr().out
        # Without --probe-refusals it only reads: no create, update, deploy or remove.
        assert "probe" not in quiet and not {"create_account", "update", "deploy", "remove"} & set(
            calls
        )
        assert "found again by login and server: yes" in quiet
        if not others:  # other tests' connections in a shared database fail their own line
            assert code == 0, out
        assert "found again by login and server: yes; the same MetaApi account: yes" in out
        assert "state DEPLOYED; broker link CONNECTED" in out
        assert "refused with broker_password_rejected" in out
        assert "refused with broker_server_not_found" in out
        assert len(api.accounts) == 1  # the probes created nothing
        for value in (login, server, metaapi_id, token, password, token_id):
            assert value not in out
    finally:
        async with fixture.runtime.db.sessions() as session, session.begin():
            if row is not None:
                await session.execute(delete(BrokerSessionRow).where(BrokerSessionRow.id == row.id))
            await session.execute(
                delete(SecretRow).where(
                    SecretRow.owner_id == fixture.owner, SecretRow.name == METAAPI_TOKEN
                )
            )
        await fixture.close()
