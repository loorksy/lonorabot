"""Push device registration (VISION 11.4, map R7): owner session only, one row per device and
per token, encrypted at rest, removed on sign-out, and a revoked or expired session never
receives a push. Runs on in-memory SQLite, or on LONORA_TASK_TEST_DATABASE_URL."""

import logging
from collections.abc import AsyncGenerator
from datetime import timedelta
from types import SimpleNamespace
from typing import Any

import httpx
import pytest
import pytest_asyncio
from fastapi import FastAPI
from lonora_api.errors import install_errors
from lonora_api.routes import auth, push_devices
from lonora_auth.sessions import issue_session
from lonora_contracts.domain import utcnow
from lonora_contracts.push import PushDeviceRegistration
from lonora_db.client import Database
from lonora_db.push_devices import live_devices
from lonora_db.schema import OwnerRow, PushDeviceRow, SessionRow
from lonora_security.secrets import SecretCipher
from pydantic import SecretStr, ValidationError
from sqlalchemy import select
from test_task_runtime import task_db as task_db

KEY = "MDAwMDAwMDAwMDAwMDAwMDAwMDAwMDAwMDAwMDAwMDA="
TOKEN = "ExponentPushToken[abcdefghijklmnop0123]"
OTHER = "ExponentPushToken[qrstuvwxyz98765432]"
PHONE = "0f4c1b52-7c2e-4f53-9e64-1d1d6c0f4a21"
TABLET = "b5d0e9c4-2a8f-4c11-8e1b-77a6c3d2e910"
Fixture = tuple[Database, str, str, str]


@pytest_asyncio.fixture
async def api(task_db: Fixture) -> AsyncGenerator[tuple[FastAPI, Database, str]]:
    db, owner_id, _, _ = task_db
    app = FastAPI()
    settings = SimpleNamespace(encryption_key=SecretStr(KEY))
    app.state.runtime = SimpleNamespace(db=db, settings=settings)
    install_errors(app)
    app.include_router(auth.router, prefix="/api")
    app.include_router(push_devices.router, prefix="/api")
    yield app, db, owner_id


async def bearer(db: Database, owner_id: str) -> str:
    async with db.sessions() as session, session.begin():
        owner = await session.get(OwnerRow, owner_id)
        assert owner
        token, _ = await issue_session(session, owner, 3600)
    return token


def client(app: FastAPI, token: str | None) -> httpx.AsyncClient:
    headers = {"Authorization": "Bearer " + token} if token else {}
    return httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="https://t", headers=headers
    )


async def rows(db: Database) -> list[PushDeviceRow]:
    async with db.sessions() as session:
        return list(await session.scalars(select(PushDeviceRow)))


def body(token: str = TOKEN, platform: str = "android") -> dict[str, Any]:
    return {"token": token, "platform": platform}


@pytest.mark.asyncio
async def test_only_a_signed_in_owner_registers_a_device(api: Any) -> None:
    app, db, _ = api
    async with client(app, None) as anonymous:
        response = await anonymous.put(f"/api/push/devices/{PHONE}", json=body())
        assert response.status_code == 401
        assert (await anonymous.delete(f"/api/push/devices/{PHONE}")).status_code == 401
    async with client(app, "not-a-session") as forged:
        assert (await forged.put(f"/api/push/devices/{PHONE}", json=body())).status_code == 401
    assert await rows(db) == []


@pytest.mark.asyncio
async def test_a_device_is_stored_once_encrypted_and_bound_to_its_session(api: Any) -> None:
    app, db, owner_id = api
    token = await bearer(db, owner_id)
    async with client(app, token) as phone:
        first = await phone.put(f"/api/push/devices/{PHONE}", json=body())
        assert first.status_code == 200 and first.json() == {"registered": True}
        # A new token for the same install replaces the old one: still one row.
        again = await phone.put(f"/api/push/devices/{PHONE}", json=body(OTHER))
        assert again.status_code == 200
    stored = await rows(db)
    assert len(stored) == 1
    assert TOKEN not in stored[0].token_ciphertext and OTHER not in stored[0].token_ciphertext
    assert stored[0].platform == "android" and stored[0].device_id == PHONE
    async with db.sessions() as session:
        devices = await live_devices(session, owner_id, SecretCipher(KEY))
    assert [(device.device_id, device.token) for device in devices] == [(PHONE, OTHER)]


@pytest.mark.asyncio
async def test_a_token_moved_to_another_install_leaves_the_old_install(api: Any) -> None:
    app, db, owner_id = api
    token = await bearer(db, owner_id)
    async with client(app, token) as http:
        await http.put(f"/api/push/devices/{PHONE}", json=body())
        await http.put(f"/api/push/devices/{TABLET}", json=body(TOKEN, "ios"))
    stored = await rows(db)
    assert [(row.device_id, row.platform) for row in stored] == [(TABLET, "ios")]


@pytest.mark.asyncio
async def test_signing_out_removes_the_device_of_that_session_only(api: Any) -> None:
    app, db, owner_id = api
    phone_session, tablet_session = await bearer(db, owner_id), await bearer(db, owner_id)
    async with client(app, phone_session) as phone, client(app, tablet_session) as tablet:
        await phone.put(f"/api/push/devices/{PHONE}", json=body())
        await tablet.put(f"/api/push/devices/{TABLET}", json=body(OTHER, "ios"))
        assert (await phone.post("/api/auth/logout", json={})).status_code == 200
    assert [row.device_id for row in await rows(db)] == [TABLET]


@pytest.mark.asyncio
async def test_delete_removes_this_device_and_refuses_an_unknown_one(api: Any) -> None:
    app, db, owner_id = api
    async with client(app, await bearer(db, owner_id)) as phone:
        await phone.put(f"/api/push/devices/{PHONE}", json=body())
        removed = await phone.delete(f"/api/push/devices/{PHONE}")
        assert removed.status_code == 200 and removed.json() == {"removed": True}
        missing = await phone.delete(f"/api/push/devices/{PHONE}")
        assert missing.status_code == 404 and missing.json()["code"] == "push_device_not_found"
    assert await rows(db) == []


@pytest.mark.asyncio
async def test_a_revoked_or_expired_session_receives_no_push(api: Any) -> None:
    app, db, owner_id = api
    phone_session, tablet_session = await bearer(db, owner_id), await bearer(db, owner_id)
    async with client(app, phone_session) as phone, client(app, tablet_session) as tablet:
        await phone.put(f"/api/push/devices/{PHONE}", json=body())
        await tablet.put(f"/api/push/devices/{TABLET}", json=body(OTHER, "ios"))
    async with db.sessions() as session, session.begin():
        sessions = list(await session.scalars(select(SessionRow)))
        by_device = {row.device_id: row.session_hash for row in await rows(db)}
        for row in sessions:
            if row.token_hash == by_device[PHONE]:
                row.revoked = True
            else:
                row.expires_at = utcnow() - timedelta(seconds=1)
    async with db.sessions() as session:
        assert await live_devices(session, owner_id, SecretCipher(KEY)) == []


@pytest.mark.asyncio
async def test_bad_input_is_refused_without_echoing_the_token(
    api: Any, caplog: pytest.LogCaptureFixture
) -> None:
    app, db, owner_id = api
    caplog.set_level(logging.DEBUG)
    async with client(app, await bearer(db, owner_id)) as phone:
        wrong = await phone.put(f"/api/push/devices/{PHONE}", json=body("fcm:abcdefgh123456"))
        assert wrong.status_code == 422 and "fcm:abcdefgh" not in wrong.text
        extra = await phone.put(f"/api/push/devices/{PHONE}", json={**body(), "owner": "x"})
        assert extra.status_code == 422 and TOKEN not in extra.text
        platform = await phone.put(f"/api/push/devices/{PHONE}", json=body(TOKEN, "web"))
        assert platform.status_code == 422 and TOKEN not in platform.text
        short = await phone.put("/api/push/devices/abc", json=body())
        assert short.status_code == 422
        ok = await phone.put(f"/api/push/devices/{PHONE}", json=body())
        assert ok.status_code == 200
    assert TOKEN not in caplog.text and "abcdefgh" not in caplog.text
    assert TOKEN not in repr(PushDeviceRegistration(token=SecretStr(TOKEN), platform="ios"))
    with pytest.raises(ValidationError) as refused:
        PushDeviceRegistration.model_validate(body("ExponentPushToken[short]"))
    assert "push_token_invalid" in str(refused.value)
