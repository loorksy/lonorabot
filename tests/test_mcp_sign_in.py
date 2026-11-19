"""Signing in to an MCP server from the Secret card (VISION.md 13.1, 7.2, 10.3).

The owner types the server's address into the card and leaves the token empty. When the
server asks for a sign-in, saving answers with the server's sign-in page and the card
keeps waiting. The authorization server sends the owner's browser back to Lonora's
callback, which keeps the tokens as workspace secrets, connects the server and settles
the card in one transaction; the agent that asked is woken. The access token is renewed
with the refresh token before it expires.

No live server: a scripted MCP server and authorization server answer through httpx's
MockTransport; the API, the registry and PostgreSQL are real.
"""

import base64
import hashlib
import json
import os
from collections.abc import Generator
from contextlib import contextmanager
from datetime import UTC, datetime, timedelta
from typing import Any
from unittest.mock import patch
from urllib.parse import parse_qs, urlsplit
from uuid import uuid4

import httpx
import pytest
from lonora_adapter_kit.types import ToolCall
from lonora_adapters.mcp import oauth
from lonora_contracts.mcp import McpConnection
from lonora_core.user_error import LonoraError
from lonora_db.schema import (
    EventRow,
    McpConnectionRow,
    McpSignInRow,
    MessageRow,
    OwnerActionRow,
    RunRow,
    SecretRow,
)
from lonora_tools import mcp
from lonora_tools.loader import load_tools
from sqlalchemy import select

SERVER = "https://files.example.test/mcp"
PRM = "https://files.example.test/.well-known/oauth-protected-resource/mcp"
ISSUER = "https://auth.example.test"
SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {"query": {"type": "string"}},
    "required": ["query"],
    "additionalProperties": False,
}


def database() -> None:
    if not os.environ.get("LONORA_DATABASE_URL"):
        pytest.skip("Signing in uses the PostgreSQL test database.")


class Remote:
    """The MCP server's first answer (a sign-in), its metadata, and its authorization
    server: discovery, registration and the token endpoint, which answers ``tokens`` in
    order."""

    def __init__(self, *, needs_sign_in: bool = True, server: dict[str, Any] | None = None):
        self.needs_sign_in = needs_sign_in
        self.server = server or {}
        self.tokens: list[httpx.Response] = []
        self.requests: list[httpx.Request] = []

    def __call__(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        url = str(request.url.copy_with(query=None))
        if request.method == "POST" and url == SERVER:
            if not self.needs_sign_in:
                return httpx.Response(200, json={"jsonrpc": "2.0", "id": 1, "result": {}})
            challenge = f'Bearer resource_metadata="{PRM}"'
            return httpx.Response(401, headers={"WWW-Authenticate": challenge})
        if url == PRM:
            return httpx.Response(
                200,
                json={
                    "resource": SERVER,
                    "authorization_servers": [ISSUER],
                    "scopes_supported": ["files:read"],
                },
            )
        if url == ISSUER + "/.well-known/oauth-authorization-server":
            return httpx.Response(
                200,
                json={
                    "issuer": ISSUER,
                    "authorization_endpoint": ISSUER + "/authorize",
                    "token_endpoint": ISSUER + "/token",
                    "registration_endpoint": ISSUER + "/register",
                    "code_challenge_methods_supported": ["S256"],
                    "authorization_response_iss_parameter_supported": True,
                    **self.server,
                },
            )
        if url == ISSUER + "/register":
            return httpx.Response(201, json={"client_id": "lonora-client"})
        if url == ISSUER + "/token" and self.tokens:
            return self.tokens.pop(0)
        return httpx.Response(404)

    def sent(self, path: str) -> list[dict[str, list[str]]]:
        return [
            parse_qs(item.content.decode())
            for item in self.requests
            if str(item.url.copy_with(query=None)) == ISSUER + path
        ]


@contextmanager
def remote(script: Remote) -> Generator[Remote]:
    async def public(url: str) -> str:
        return url

    with (
        patch.object(oauth, "validate_public_url", public),
        patch.object(
            oauth,
            "http_client",
            lambda: httpx.AsyncClient(transport=httpx.MockTransport(script)),
        ),
    ):
        yield script


def tokens(access: str, refresh: str | None = None, expires_in: int | None = 3600) -> Any:
    body: dict[str, Any] = {"access_token": access, "token_type": "Bearer"}
    if refresh is not None:
        body["refresh_token"] = refresh
    if expires_in is not None:
        body["expires_in"] = expires_in
    return httpx.Response(200, json=body)


class Server:
    """The MCP server once signed in: it records the bearer token of each connection."""

    def __init__(self) -> None:
        self.tokens: list[str | None] = []

    def transport(self, url: str, token: str | None = None) -> Any:
        assert url == SERVER
        self.tokens.append(token)

        class Transport:
            async def request(self, payload: dict[str, Any]) -> dict[str, Any]:
                if payload["method"] == "notifications/initialized":
                    return {}
                result: dict[str, Any] = {"protocolVersion": "2025-06-18"}
                if payload["method"] == "tools/list":
                    result = {"tools": [{"name": "find_files", "inputSchema": SCHEMA}]}
                return {"jsonrpc": "2.0", "id": payload["id"], "result": result}

            async def close(self) -> None:
                pass

        return Transport()


async def call(context: Any, tool: str, /, **arguments: Any) -> dict[str, Any]:
    return await load_tools().execute(
        ToolCall(id="call-" + uuid4().hex, name=tool, arguments=arguments), context
    )


async def save(fixture: Any, card_id: str, values: dict[str, str], **extra: Any) -> Any:
    return await fixture.client.post(
        f"/api/owner-actions/{card_id}/secret", json={"values": values, **extra}
    )


async def come_back(fixture: Any, **query: str) -> httpx.Response:
    """The owner's browser, sent back by the authorization server: no Lonora session (on
    a phone it is the system browser)."""
    browser = httpx.AsyncClient(
        transport=httpx.ASGITransport(fixture.app), base_url="https://streaming.test"
    )
    try:
        return await browser.get("/api/mcp/oauth/callback", params=query)
    finally:
        await browser.aclose()


async def card(fixture: Any, card_id: str) -> dict[str, Any]:
    async with fixture.runtime.db.sessions() as session:
        row = await session.get(OwnerActionRow, card_id)
        assert row is not None
        thread_id = row.thread_id
    cards = await fixture.request("GET", f"/owner-actions?thread_id={thread_id}")
    return next(item for item in cards if item["id"] == card_id)


async def started(
    fixture: Any, script: Remote, name: str = "Files", **extra: Any
) -> tuple[dict[str, Any], str, str]:
    """An agent's Secret card for an MCP server, saved with its address only: the
    sign-in page it answers with, and the card."""
    agent = await fixture.agent("Files " + uuid4().hex[:6])
    thread = await fixture.conversation(agent)
    context = await fixture.lease(await fixture.run(agent, thread))
    proposed = await call(
        context, "owner_action_propose", kind="secret", target="mcp_server", name=name
    )
    card_id = proposed["owner_action"]["id"]
    with remote(script):
        answer = await save(fixture, card_id, {"URL": SERVER}, **extra)
    assert answer.status_code == 200, answer.text
    return agent, card_id, answer.json()["sign_in_url"]


async def connection(fixture: Any, connection_id: str) -> McpConnection:
    async with fixture.runtime.db.sessions() as session:
        row = await session.get(McpConnectionRow, connection_id)
        assert row is not None
        return McpConnection.model_validate(row.payload)


async def secret_value(fixture: Any, secret_id: str | None) -> str:
    assert secret_id is not None
    return await fixture.runtime.services(fixture.owner).secrets.read(secret_id)


@pytest.mark.asyncio
async def test_a_server_that_asks_for_a_sign_in_connects_when_the_owner_signs_in() -> None:
    database()
    from check_streaming import Fixture

    fixture = await Fixture().open()
    created: list[str] = []
    try:
        script = Remote()
        named = "Files " + uuid4().hex[:6]
        saved_as = "MCP_" + named.upper().replace(" ", "_")
        agent, card_id, page = await started(fixture, script, named)
        # The card waits; the answer is the authorization server's page, for this server.
        assert (await card(fixture, card_id))["status"] == "pending"
        address = urlsplit(page)
        query = {key: value[0] for key, value in parse_qs(address.query).items()}
        callback = fixture.settings.allowed_origin + "/api/mcp/oauth/callback"
        assert page.startswith(ISSUER + "/authorize?")
        assert query["client_id"] == "lonora-client" and query["redirect_uri"] == callback
        assert query["code_challenge_method"] == "S256" and query["resource"] == SERVER
        assert query["scope"] == "files:read"
        [registered] = [
            json.loads(item.content)
            for item in script.requests
            if str(item.url) == ISSUER + "/register"
        ]
        assert registered["redirect_uris"] == [callback]
        # Nothing is saved yet: no secret, no connection. The waiting sign-in keeps its
        # verifier and the address only encrypted, and its state only as a digest.
        async with fixture.runtime.db.sessions() as session:
            names = (await session.scalars(select(SecretRow.name))).all()
            assert not [name for name in names if name.startswith(saved_as)]
            [waiting] = (
                await session.scalars(select(McpSignInRow).where(McpSignInRow.card_id == card_id))
            ).all()
        assert waiting.state_sha256 == hashlib.sha256(query["state"].encode()).hexdigest()
        stored = json.dumps(waiting.plan) + waiting.ciphertext
        assert SERVER not in stored and query["state"] not in stored

        # The authorization server sends the browser back: the tokens are fetched with
        # the verifier, saved, and the server is connected. No Lonora session needed.
        script.tokens.append(tokens("access-1", "refresh-1"))
        with remote(script):
            back = await come_back(fixture, code="code-1", state=query["state"], iss=ISSUER)
        assert back.status_code == 303
        assert back.headers["location"] == fixture.settings.allowed_origin + "/app/" + agent["id"]
        [exchange] = script.sent("/token")
        assert exchange["grant_type"] == ["authorization_code"]
        assert exchange["code"] == ["code-1"] and exchange["resource"] == [SERVER]
        verifier = exchange["code_verifier"][0]
        digest = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest())
        assert digest.rstrip(b"=").decode() == query["code_challenge"]

        settled = await card(fixture, card_id)
        assert settled["status"] == "confirmed", settled
        result = settled["result"]
        created.append(result["connection_id"])
        assert result["saved"] == [
            saved_as + "_URL",
            saved_as + "_TOKEN",
            saved_as + "_REFRESH_TOKEN",
        ]
        config = await connection(fixture, result["connection_id"])
        assert config.oauth is not None and config.url is None
        assert await secret_value(fixture, config.url_secret_id) == SERVER
        assert await secret_value(fixture, config.secret_id) == "access-1"
        assert await secret_value(fixture, config.oauth.refresh_secret_id) == "refresh-1"
        # The address is kept only in the store, so the resource that is the address is too.
        assert config.oauth.client_id == "lonora-client" and config.oauth.resource is None
        assert config.oauth.token_endpoint == ISSUER + "/token"
        assert config.oauth.expires_at is not None
        assert config.oauth.expires_at > datetime.now(UTC) + timedelta(minutes=50)

        # The agent that asked is woken; no token, verifier or address reached a card, a
        # message, an event or a run.
        async with fixture.runtime.db.sessions() as session:
            woken = await session.scalar(
                select(RunRow).where(RunRow.agent_id == agent["id"], RunRow.trigger == "owner_card")
            )
            assert woken is not None and "mcp_trust" in woken.prompt
            for model in (MessageRow, EventRow, OwnerActionRow, RunRow):
                for row in await session.scalars(select(model)):
                    dumped = json.dumps({key: str(value) for key, value in vars(row).items()})
                    for value in ("access-1", "refresh-1", verifier, "code-1"):
                        assert value not in dumped, model.__name__

        # The same callback again changes nothing and asks for no token.
        with remote(script):
            again = await come_back(fixture, code="code-1", state=query["state"], iss=ISSUER)
        assert again.status_code == 303 and len(script.sent("/token")) == 1

        # The agent's tools reach the server with the access token.
        server = Server()
        context = await fixture.lease(await fixture.run(agent, {"id": settled["thread_id"]}))
        with patch.object(mcp, "HttpMcpTransport", server.transport):
            listed = await call(context, "mcp_tools", connection_id=result["connection_id"])
        assert [tool["name"] for tool in listed["tools"]] == ["find_files"]
        assert server.tokens == ["access-1"]
    finally:
        for connection_id in created:
            await fixture.request("DELETE", "/mcp/" + connection_id)
        await fixture.close()


@pytest.mark.asyncio
async def test_an_access_token_about_to_expire_is_renewed_with_the_refresh_token() -> None:
    database()
    from check_streaming import Fixture

    fixture = await Fixture().open()
    created: list[str] = []
    try:
        script = Remote()
        agent, card_id, page = await started(fixture, script)
        state = parse_qs(urlsplit(page).query)["state"][0]
        script.tokens.append(tokens("access-1", "refresh-1", expires_in=30))
        with remote(script):
            await come_back(fixture, code="code-1", state=state, iss=ISSUER)
        connection_id = (await card(fixture, card_id))["result"]["connection_id"]
        created.append(connection_id)
        context = await fixture.lease(
            await fixture.run(agent, {"id": (await card(fixture, card_id))["thread_id"]})
        )
        server = Server()
        # It expires within the minute: renewed before use, the new refresh token kept.
        script.tokens.append(tokens("access-2", "refresh-2"))
        with remote(script), patch.object(mcp, "HttpMcpTransport", server.transport):
            await call(context, "mcp_tools", connection_id=connection_id)
            await call(context, "mcp_tools", connection_id=connection_id)
        assert server.tokens == ["access-2", "access-2"]
        [_, renewal] = script.sent("/token")
        assert renewal["grant_type"] == ["refresh_token"]
        assert renewal["refresh_token"] == ["refresh-1"] and renewal["resource"] == [SERVER]
        config = await connection(fixture, connection_id)
        assert config.oauth is not None
        assert await secret_value(fixture, config.secret_id) == "access-2"
        assert await secret_value(fixture, config.oauth.refresh_secret_id) == "refresh-2"
        assert config.oauth.expires_at is not None
        assert config.oauth.expires_at > datetime.now(UTC) + timedelta(minutes=50)

        # A refused renewal: the sign-in has ended, and nothing reaches the server.
        async with fixture.runtime.db.sessions() as session, session.begin():
            row = await session.get(McpConnectionRow, connection_id, with_for_update=True)
            assert row is not None
            payload = dict(row.payload)
            payload["oauth"] = {**payload["oauth"], "expires_at": "2020-01-01T00:00:00+00:00"}
            row.payload = payload
        script.tokens.append(httpx.Response(400, json={"error": "invalid_grant"}))
        with remote(script), patch.object(mcp, "HttpMcpTransport", server.transport):
            with pytest.raises(LonoraError) as caught:
                await call(context, "mcp_tools", connection_id=connection_id)
        assert caught.value.code == "mcp_sign_in_expired"
        assert server.tokens == ["access-2", "access-2"]
        assert await secret_value(fixture, config.secret_id) == "access-2"
    finally:
        for connection_id in created:
            await fixture.request("DELETE", "/mcp/" + connection_id)
        await fixture.close()


@pytest.mark.asyncio
async def test_a_sign_in_that_does_not_finish_leaves_the_card_waiting_and_says_so() -> None:
    database()
    from check_streaming import Fixture

    fixture = await Fixture().open()
    try:
        script = Remote()
        _, card_id, page = await started(fixture, script, return_to="app")
        state = parse_qs(urlsplit(page).query)["state"][0]
        thread_id = (await card(fixture, card_id))["thread_id"]
        # The owner declined at the server: back to the app, the card still waiting.
        back = await come_back(fixture, error="access_denied", state=state)
        assert back.status_code == 303
        assert back.headers["location"] == f"lonora://thread?id={thread_id}"
        waiting = await card(fixture, card_id)
        assert waiting["status"] == "pending" and waiting["facts"]["secret"]["sign_in_failed"]
        # A used, unknown or late sign-in finishes nothing and asks for no token.
        for query in (
            {"code": "code-1", "state": state, "iss": ISSUER},
            {"code": "code-1", "state": "unknown"},
            {},
        ):
            with remote(script):
                late = await come_back(fixture, **query)
            assert late.status_code == 303
            assert late.headers["location"] == fixture.settings.allowed_origin + "/app"
        assert script.sent("/token") == []

        # Another attempt, answered by another issuer (a mix-up): refused, no token asked.
        _, other_id, page = await started(fixture, script)
        state = parse_qs(urlsplit(page).query)["state"][0]
        with remote(script):
            await come_back(fixture, code="code-2", state=state, iss="https://evil.example.test")
        assert script.sent("/token") == []
        assert (await card(fixture, other_id))["facts"]["secret"]["sign_in_failed"]
        async with fixture.runtime.db.sessions() as session, session.begin():
            row = await session.scalar(select(McpSignInRow).where(McpSignInRow.card_id == other_id))
            assert row is not None and row.used_at is not None
        # A sign-in older than its ten minutes finishes nothing.
        _, late_id, page = await started(fixture, script)
        state = parse_qs(urlsplit(page).query)["state"][0]
        async with fixture.runtime.db.sessions() as session, session.begin():
            row = await session.scalar(select(McpSignInRow).where(McpSignInRow.card_id == late_id))
            assert row is not None
            row.expires_at = datetime.now(UTC) - timedelta(seconds=1)
        script.tokens.append(tokens("access-3"))
        with remote(script):
            await come_back(fixture, code="code-3", state=state, iss=ISSUER)
        assert script.sent("/token") == [] and (await card(fixture, late_id))["status"] == "pending"
    finally:
        await fixture.close()


@pytest.mark.asyncio
async def test_a_server_that_needs_no_sign_in_or_cannot_offer_one() -> None:
    database()
    from check_streaming import Fixture

    fixture = await Fixture().open()
    created: list[str] = []
    try:
        agent = await fixture.agent("Plain " + uuid4().hex[:6])
        thread = await fixture.conversation(agent)
        context = await fixture.lease(await fixture.run(agent, thread))

        async def propose(name: str) -> str:
            proposed = await call(
                context, "owner_action_propose", kind="secret", target="mcp_server", name=name
            )
            return proposed["owner_action"]["id"]

        # It answers without credentials: saved as it always was, no sign-in.
        plain = Remote(needs_sign_in=False)
        open_id = await propose("Open")
        with remote(plain):
            answer = await save(fixture, open_id, {"URL": SERVER})
        assert answer.status_code == 200 and "sign_in_url" not in answer.json()
        assert answer.json()["status"] == "confirmed"
        created.append(answer.json()["result"]["connection_id"])
        assert (await connection(fixture, created[-1])).oauth is None
        assert [str(item.url) for item in plain.requests] == [SERVER]
        # A token typed into the card is used as it is: the server is not asked.
        typed = Remote()
        token_id = await propose("Typed")
        with remote(typed):
            answer = await save(fixture, token_id, {"URL": SERVER, "TOKEN": "static-token"})
        assert answer.json()["status"] == "confirmed" and typed.requests == []
        created.append(answer.json()["result"]["connection_id"])
        # Its metadata cannot be trusted (no S256): refused, nothing saved, the card waits.
        unsafe = Remote(server={"code_challenge_methods_supported": ["plain"]})
        unsafe_id = await propose("Unsafe")
        with remote(unsafe):
            answer = await save(fixture, unsafe_id, {"URL": SERVER})
        assert answer.status_code == 422
        assert answer.json()["code"] == "mcp_sign_in_unsupported"
        assert (await card(fixture, unsafe_id))["status"] == "pending"
        async with fixture.runtime.db.sessions() as session:
            assert (
                await session.scalar(select(McpSignInRow).where(McpSignInRow.card_id == unsafe_id))
                is None
            )
    finally:
        for connection_id in created:
            await fixture.request("DELETE", "/mcp/" + connection_id)
        await fixture.close()
