"""Sign in with ChatGPT (VISION Amendment 4; proposal section 4) against a fake OpenAI.

The fake answers OpenAI's official sign-in paths (token, JWKS with a key this test
generates, discovery, revocation), the account's model list and the Responses API; no
request leaves the process and no real account or token exists. The owner's journey runs
through the Secret card's routes: start gives the authorization address, the owner pastes
the address the browser landed on, and the card settles as a saved key does. Then the
plan's tokens are renewed under the lock, refused models leave the list, sign-out revokes,
and no token ever reaches the workspace, the agent or a log.
"""

import asyncio
import base64
import hashlib
import json
import logging
import os
import time
from collections.abc import AsyncIterator
from dataclasses import replace
from typing import Any
from unittest.mock import patch
from urllib.parse import parse_qs, urlencode, urlsplit
from uuid import uuid4

import httpx
import jwt
import pytest
import pytest_asyncio
from cryptography.hazmat.primitives.asymmetric import rsa
from jwt.algorithms import RSAAlgorithm
from lonora_adapter_kit.model_errors import FailureReason, ModelProviderError
from lonora_adapter_kit.types import ModelMessage, ModelReply
from lonora_contracts.model_routing import Capability, ModelSelection
from lonora_contracts.usage import TokenUsage
from lonora_core.user_error import LonoraError
from lonora_db.model_credentials import CONNECTION_SETTING
from lonora_db.schema import EventRow, MessageRow, RunRow, SecretRow, SettingRow
from lonora_db.transactions import SettingsRepository
from lonora_providers import chatgpt_sign_in as signin
from lonora_providers.catalog import PLAN_MODELS, listed_models, read_catalog
from lonora_providers.chatgpt_sign_in import ChatGptSignIn
from lonora_providers.credentials import ProviderCredentials
from lonora_providers.registry import PROVIDERS
from lonora_providers.router import GlobalModelRouter
from sqlalchemy import select
from test_secret_card import call, thread_cards

pytestmark = pytest.mark.asyncio
CLIENT = "oaiapp_fixture_" + uuid4().hex[:8]
REVOKE_URL = signin.ISSUER + "/oauth/revoke"
LISTED = {item.id for item in listed_models("openai_chatgpt")}


class FakeOpenAI:
    """OpenAI's sign-in, model list and Responses API, answering as its documentation says."""

    def __init__(self) -> None:
        self.key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        self.stranger = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        jwk = json.loads(RSAAlgorithm.to_jwk(self.key.public_key()))
        self.jwks = {"keys": [{**jwk, "kid": "fixture", "alg": "RS256", "use": "sig"}]}
        self.calls: list[httpx.Request] = []
        self.subject, self.email = "user-" + uuid4().hex[:8], "owner@example.test"
        self.scope = signin.SCOPES
        self.nonce: str | None = None
        self.issued: list[tuple[str, str]] = []
        self.models = [
            {"slug": "gpt-6.1-sol", "display_name": "GPT-6.1 Sol", "visibility": "list"},
            {"slug": "gpt-6.2-sol", "display_name": "GPT-6.2 Sol", "visibility": "list"},
            {"slug": "gpt-6-sol", "display_name": "Hidden", "visibility": "hide"},
            {"slug": "gpt-not-in-lonoras-list", "display_name": "Other", "visibility": "list"},
        ]
        # Failure switches: each names the answer that changes.
        self.mode: set[str] = set()
        self.refresh_answer: tuple[int, dict[str, Any]] | None = None
        self.revoke_status = 200

    def id_token(self, *, nonce: str | None, sub: str | None = None, **claims: Any) -> str:
        now = int(time.time())
        payload = {
            "iss": signin.ISSUER,
            "aud": CLIENT,
            "sub": sub or self.subject,
            "email": self.email,
            "iat": now,
            "exp": now + 3600,
            **({"nonce": nonce} if nonce is not None else {}),
            **claims,
        }
        key = self.stranger if "bad_signature" in self.mode else self.key
        return jwt.encode(payload, key, algorithm="RS256", headers={"kid": "fixture"})

    def token_set(self, *, nonce: str | None, rotated: bool) -> dict[str, Any]:
        access, refresh = "access-" + uuid4().hex, "refresh-" + uuid4().hex
        self.issued.append((access, refresh))
        body: dict[str, Any] = {
            "access_token": access,
            "refresh_token": refresh,
            "token_type": "Bearer",
            "expires_in": 3600,
        }
        if not rotated:
            body["scope"] = self.scope
            sub = "user-other" if "other_account" in self.mode else None
            claims = {"aud": "another-client"} if "bad_audience" in self.mode else {}
            token_nonce = "not-this-attempt" if "bad_nonce" in self.mode else nonce
            body["id_token"] = self.id_token(nonce=token_nonce, sub=sub, **claims)
            if self.scope != signin.SCOPES:
                body.pop("refresh_token")
        return body

    async def handle(self, request: httpx.Request) -> httpx.Response:
        self.calls.append(request)
        url = str(request.url.copy_with(query=None))
        form = parse_qs(request.content.decode()) if request.method == "POST" else {}
        if url == signin.JWKS_URL:
            return httpx.Response(200, json=self.jwks)
        if url == signin.DISCOVERY_URL:
            return httpx.Response(
                200, json={"issuer": signin.ISSUER, "revocation_endpoint": REVOKE_URL}
            )
        if url == REVOKE_URL:
            return httpx.Response(self.revoke_status)
        if url == signin.MODELS_URL:
            return httpx.Response(200, json={"models": self.models})
        if url == signin.TOKEN_URL:
            grant = form["grant_type"][0]
            if grant == "refresh_token":
                await asyncio.sleep(0.05)  # long enough for a second caller to queue
                if self.refresh_answer is not None:
                    status, body = self.refresh_answer
                    return httpx.Response(status, json=body)
                return httpx.Response(200, json=self.token_set(nonce=None, rotated=True))
            if "used_code" in self.mode:
                return httpx.Response(400, json={"error": "invalid_grant"})
            return httpx.Response(200, json=self.token_set(nonce=self.nonce, rotated=False))
        if url == signin.RESOURCE + "/responses":
            return self.responses(request)
        return httpx.Response(404, json={"error": "not_found"})

    def responses(self, request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        assert body["store"] is False and body["stream"] is True
        if self.response_error is not None:
            status, payload = self.response_error
            return httpx.Response(status, json=payload)
        events = [
            {"type": "response.output_text.delta", "delta": "Hello"},
            {"type": "response.completed", "response": {"id": "r1", "usage": {}}},
        ]
        return httpx.Response(200, text="".join(f"data: {json.dumps(e)}\n\n" for e in events))

    response_error: tuple[int, dict[str, Any]] | None = None

    def http(self) -> httpx.AsyncClient:
        return httpx.AsyncClient(transport=httpx.MockTransport(self.handle))

    def tokens(self) -> list[str]:
        return [token for pair in self.issued for token in pair]


def callback(authorization: str, **override: str) -> str:
    query = parse_qs(urlsplit(authorization).query)
    params = {"code": "fixture-code", "state": query["state"][0], "client_id": CLIENT}
    params.update(override)
    return signin.REDIRECT_URI + "?" + urlencode({k: v for k, v in params.items() if v})


@pytest_asyncio.fixture
async def world(monkeypatch: pytest.MonkeyPatch) -> AsyncIterator[dict[str, Any]]:
    if not os.environ.get("LONORA_DATABASE_URL"):
        pytest.skip("The sign-in uses the PostgreSQL test database.")
    from check_streaming import Fixture

    monkeypatch.delenv(signin.FLAG, raising=False)
    fake = FakeOpenAI()
    fixture = await Fixture().open()
    store = fixture.runtime.services(fixture.owner).secrets
    settings = SettingsRepository()
    async with fixture.runtime.db.sessions() as session, session.begin():
        routing = await settings.get(session, "model_routing")
        # No model chosen yet: the sign-in chooses the plan's default (M4).
        await settings.put(session, "model_routing", {})
    with patch.object(signin, "http_client", fake.http):
        try:
            agent = await fixture.agent("Plan")
            context = await fixture.lease(
                await fixture.run(agent, await fixture.conversation(agent))
            )
            yield {
                "fixture": fixture,
                "fake": fake,
                "store": store,
                "agent": agent,
                "context": context,
                "sign_in": ChatGptSignIn(store),
            }
        finally:
            async with fixture.runtime.db.sessions() as session, session.begin():
                for row in (
                    await session.scalars(
                        select(SecretRow).where(
                            SecretRow.name.in_([signin.PROVIDER, signin.PENDING])
                        )
                    )
                ).all():
                    await session.delete(row)
                for key in (CONNECTION_SETTING + signin.PROVIDER, PLAN_MODELS):
                    row = await session.get(SettingRow, key)
                    if row is not None:
                        await session.delete(row)
                await settings.put(session, "model_routing", routing)
            await fixture.close()


async def card(world: dict[str, Any]) -> str:
    proposed = await call(
        world["context"],
        "owner_action_propose",
        kind="secret",
        target="model_provider",
        name="openai_chatgpt",
    )
    return proposed["owner_action"]["id"]


async def start(world: dict[str, Any], card_id: str) -> str:
    started = await world["fixture"].client.post(f"/api/owner-actions/{card_id}/chatgpt/start")
    assert started.status_code == 200, started.text
    authorization = started.json()["authorization_url"]
    world["fake"].nonce = parse_qs(urlsplit(authorization).query)["nonce"][0]
    return authorization


async def finish(world: dict[str, Any], card_id: str, address: str) -> httpx.Response:
    return await world["fixture"].client.post(
        f"/api/owner-actions/{card_id}/chatgpt/finish", json={"address": address}
    )


async def sign_in(world: dict[str, Any]) -> str:
    card_id = await card(world)
    done = await finish(world, card_id, callback(await start(world, card_id)))
    assert done.status_code == 200 and done.json()["status"] == "confirmed", done.text
    return card_id


async def expire(world: dict[str, Any]) -> None:
    """The access token in its last minute."""
    async with world["fixture"].runtime.db.sessions() as session, session.begin():
        saved = await world["sign_in"]._saved(session)
        await world["sign_in"]._save(session, replace(saved, expires_at=time.time() + 30))


async def test_first_registration_connects_the_plan_from_the_card(
    world: dict[str, Any], caplog: pytest.LogCaptureFixture
) -> None:
    caplog.set_level(logging.DEBUG)
    fixture, fake = world["fixture"], world["fake"]
    card_id = await card(world)
    facts = next(
        i for i in await thread_cards(fixture, world["context"].thread_id) if i["id"] == card_id
    )
    secret = facts["facts"]["secret"]
    # The Secret card, with a sign-in in place of the key field: nothing is saved by name.
    assert secret["details"] == {"provider": "openai_chatgpt", "name": "ChatGPT"}
    assert secret["fields"] == [] and secret["saves_as"] == [] and secret["replaces"] == []
    refused = await fixture.client.post(f"/api/owner-actions/{card_id}/secret", json={"values": {}})
    assert refused.status_code == 409 and refused.json()["code"] == "chatgpt_sign_in_required"

    authorization = await start(world, card_id)
    parts = urlsplit(authorization)
    assert f"{parts.scheme}://{parts.netloc}{parts.path}" == signin.AUTHORIZE_URL
    query = {key: value[0] for key, value in parse_qs(parts.query).items()}
    assert query["client_id"] == "dynamic_agent_client" and query["agent_name_hint"] == "Lonora"
    assert query["ext_agent_host_id"].startswith("urn:uuid:")
    assert query["redirect_uri"] == "http://127.0.0.1:1455/auth/callback"
    assert query["scope"].split() == [
        "openid",
        "profile",
        "email",
        "offline_access",
        "resource.invoke",
        "chatgpt.tokens.use.direct",
    ]
    assert query["resource"] == "https://api.openai.com/v1"
    assert query["response_type"] == "code" and query["code_challenge_method"] == "S256"
    assert {"state", "nonce", "code_challenge"} <= set(query)
    assert not {"id_token_hint", "login_hint", "prompt"} & set(query)

    done = await finish(world, card_id, callback(authorization))
    assert done.status_code == 200 and done.json()["status"] == "confirmed"
    result = done.json()["result"]
    assert result["account"] == fake.email and result["saved"] == []
    # Two of the account's slugs are in Lonora's list; the hidden one and a slug the list
    # does not hold are not offered.
    assert result["models"] == 2
    exchange = next(c for c in fake.calls if str(c.url) == signin.TOKEN_URL)
    form = {key: value[0] for key, value in parse_qs(exchange.content.decode()).items()}
    assert form["grant_type"] == "authorization_code" and form["client_id"] == CLIENT
    assert form["redirect_uri"] == query["redirect_uri"] and form["resource"] == query["resource"]
    assert "client_secret" not in form
    digest = hashlib.sha256(form["code_verifier"].encode()).digest()
    assert base64.urlsafe_b64encode(digest).decode().rstrip("=") == query["code_challenge"]
    models_read = next(c for c in fake.calls if str(c.url) == signin.MODELS_URL)
    access, refresh = fake.issued[0]
    assert models_read.headers["authorization"] == "Bearer " + access
    assert {item.id for item in await read_catalog(fixture.runtime.db, "openai_chatgpt")} == {
        "gpt-6.1-sol",
        "gpt-6.2-sol",
    }

    credentials = ProviderCredentials(fixture.runtime.db, world["store"])
    assert await credentials.configured("openai_chatgpt")
    assert await credentials.connection("openai_chatgpt") == (access, "https://api.openai.com/v1")
    async with fixture.runtime.db.sessions() as session:
        routing = await SettingsRepository().get(session, "model_routing")
        record = await SettingsRepository().get(session, CONNECTION_SETTING + "openai_chatgpt")
        row = await session.scalar(select(SecretRow).where(SecretRow.name == "openai_chatgpt"))
        runs = (
            await session.scalars(select(RunRow).where(RunRow.agent_id == world["agent"]["id"]))
        ).all()
        events = (
            await session.scalars(select(EventRow).where(EventRow.owner_id == fixture.owner))
        ).all()
        messages = (
            await session.scalars(
                select(MessageRow).where(MessageRow.thread_id == world["context"].thread_id)
            )
        ).all()
    # The router's record and the M4 default, as a saved key gets.
    assert row is not None and row.scope == "provider" and record["secret_id"] == row.id
    assert routing["unified"] == {"provider": "openai_chatgpt", "model": "gpt-6.1-sol"}
    follow = [run for run in runs if run.model_metadata.get("owner_action_id") == card_id]
    assert len(follow) == 1 and "model_list" in follow[0].prompt and "2 of" in follow[0].prompt

    # No token reaches the workspace, the agent, the conversation, an event or a log; the
    # scan of workspace output knows each token as a value of its own.
    workspace = await world["store"].workspace_values()
    scanned = await world["store"].scanned_values()
    id_token = json.loads(world["store"].cipher.decrypt(row.ciphertext))["id_token"]
    assert scanned["openai_chatgpt:access_token"] == access
    assert scanned["openai_chatgpt:refresh_token"] == refresh
    assert scanned["openai_chatgpt:id_token"] == id_token
    haystack = json.dumps(
        [
            workspace,
            [run.prompt for run in runs],
            [event.payload for event in events],
            [message.content for message in messages],
            done.json(),
            caplog.text,
        ],
        default=str,
    )
    for token in (access, refresh, id_token):
        assert token not in haystack


async def test_a_returning_sign_in_reuses_its_client_and_never_takes_another_account(
    world: dict[str, Any],
) -> None:
    fake = world["fake"]
    await sign_in(world)
    stored = await world["sign_in"].credential()
    card_id = await card(world)
    authorization = await start(world, card_id)
    query = {key: value[0] for key, value in parse_qs(urlsplit(authorization).query).items()}
    assert query["client_id"] == CLIENT and "agent_name_hint" not in query
    assert query["login_hint"] == fake.email and query["id_token_hint"] == stored.id_token
    assert query["ext_agent_host_id"] == stored.host_id

    # Another registration's id on the callback is refused, and so is another account.
    other = await finish(world, card_id, callback(authorization, client_id="oaiapp_someone_else"))
    assert other.status_code == 409 and other.json()["code"] == "chatgpt_client_mismatch"
    authorization = await start(world, card_id)
    fake.mode.add("other_account")
    stranger = await finish(world, card_id, callback(authorization, client_id=""))
    assert stranger.status_code == 409 and stranger.json()["code"] == "chatgpt_other_account"
    assert await world["sign_in"].credential() == stored
    fake.mode.clear()
    # The callback of a returning sign-in may omit the client id: the one it started with.
    authorization = await start(world, card_id)
    done = await finish(world, card_id, callback(authorization, client_id=""))
    assert done.json()["status"] == "confirmed"


@pytest.mark.parametrize("failure", ["bad_nonce", "bad_audience", "bad_signature"])
async def test_an_unverified_identity_saves_nothing(world: dict[str, Any], failure: str) -> None:
    world["fake"].mode.add(failure)
    card_id = await card(world)
    answer = await finish(world, card_id, callback(await start(world, card_id)))
    assert answer.status_code == 502 and answer.json()["code"] == "chatgpt_identity_invalid"
    assert await world["sign_in"].credential() is None


async def test_the_pasted_address_must_be_this_attempts_callback(world: dict[str, Any]) -> None:
    card_id = await card(world)
    authorization = await start(world, card_id)
    good = callback(authorization)
    for bad in (
        good.replace("127.0.0.1", "localhost"),
        good.replace(":1455", ":1456"),
        good.replace("/auth/callback", "/callback"),
        good + "&state=again",
        "https://example.test/?" + urlsplit(good).query,
        "not an address",
    ):
        answer = await finish(world, card_id, bad)
        assert answer.status_code == 422 and answer.json()["code"] == "chatgpt_address_invalid"
    # Another attempt's state leaves this one waiting; the right address then works once.
    wrong = await finish(world, card_id, callback(authorization, state="another-attempt"))
    assert wrong.status_code == 422 and wrong.json()["code"] == "chatgpt_state_mismatch"
    assert not [c for c in world["fake"].calls if str(c.url) == signin.TOKEN_URL]
    assert (await finish(world, card_id, good)).json()["status"] == "confirmed"
    again = await finish(world, card_id, good)
    assert again.status_code == 409 and again.json()["code"] == "chatgpt_sign_in_expired"
    exchanges = [c for c in world["fake"].calls if str(c.url) == signin.TOKEN_URL]
    assert len(exchanges) == 1


async def test_a_declined_or_incomplete_registration_is_not_exchanged(
    world: dict[str, Any],
) -> None:
    card_id = await card(world)
    declined = await finish(
        world, card_id, callback(await start(world, card_id), error="access_denied", code="")
    )
    assert declined.status_code == 409 and declined.json()["code"] == "chatgpt_sign_in_declined"
    dynamic = await finish(
        world, card_id, callback(await start(world, card_id), client_id="dynamic_agent_client")
    )
    assert dynamic.status_code == 409 and dynamic.json()["code"] == "chatgpt_client_mismatch"
    assert not [c for c in world["fake"].calls if str(c.url) == signin.TOKEN_URL]
    # A used code keeps the issued id: the next attempt registers no second client.
    world["fake"].mode.add("used_code")
    used = await finish(world, card_id, callback(await start(world, card_id)))
    assert used.status_code == 409 and used.json()["code"] == "chatgpt_sign_in_code_expired"
    query = parse_qs(urlsplit(await start(world, card_id)).query)
    assert query["client_id"] == [CLIENT] and "agent_name_hint" not in query


async def test_declined_plan_use_keeps_the_sign_in_and_asks_for_consent_again(
    world: dict[str, Any],
) -> None:
    fake = world["fake"]
    fake.scope = "openid profile email"
    card_id = await card(world)
    answer = await finish(world, card_id, callback(await start(world, card_id)))
    assert answer.status_code == 409 and answer.json()["code"] == "chatgpt_plan_use_declined"
    saved = await world["sign_in"].credential()
    assert saved is not None and saved.subject == fake.subject and not saved.plan
    credentials = ProviderCredentials(world["fixture"].runtime.db, world["store"])
    assert not await credentials.configured("openai_chatgpt")
    with pytest.raises(LonoraError) as refused:
        await credentials.connection("openai_chatgpt")
    assert refused.value.code == "model_not_configured"
    cards = await thread_cards(world["fixture"], world["context"].thread_id)
    assert next(item for item in cards if item["id"] == card_id)["status"] == "pending"
    query = parse_qs(urlsplit(await start(world, card_id)).query)
    assert query["prompt"] == ["consent"] and query["client_id"] == [CLIENT]
    assert query["scope"] == [signin.SCOPES]
    fake.scope = signin.SCOPES
    authorization = await start(world, card_id)
    assert (await finish(world, card_id, callback(authorization))).json()["status"] == "confirmed"


async def test_two_callers_renew_once_and_the_rotated_set_replaces_the_old(
    world: dict[str, Any],
) -> None:
    fake = world["fake"]
    await sign_in(world)
    await expire(world)
    first, second = ChatGptSignIn(world["store"]), ChatGptSignIn(world["store"])
    tokens = await asyncio.gather(first.access_token(), second.access_token())
    refreshes = [
        parse_qs(c.content.decode())
        for c in fake.calls
        if str(c.url) == signin.TOKEN_URL and b"refresh_token" in c.content
    ]
    assert len(refreshes) == 1
    assert refreshes[0]["client_id"] == [CLIENT] and "scope" not in refreshes[0]
    assert refreshes[0]["refresh_token"] == [fake.issued[0][1]]
    access, refresh = fake.issued[1]
    assert tokens == [access, access]
    saved = await world["sign_in"].credential()
    assert saved.refresh_token == refresh and saved.plan and saved.expires_at > 0


async def test_a_refused_refresh_clears_the_tokens_and_a_failed_one_keeps_them(
    world: dict[str, Any],
) -> None:
    fake = world["fake"]
    await sign_in(world)
    await expire(world)
    before = await world["sign_in"].credential()
    fake.refresh_answer = (503, {"error": "temporarily_unavailable"})
    with pytest.raises(ModelProviderError) as transient:
        await world["sign_in"].access_token()
    assert transient.value.reason is FailureReason.OVERLOADED
    assert await world["sign_in"].credential() == before
    fake.refresh_answer = (400, {"error": "refresh_token_reused", "error_description": "secret"})
    with pytest.raises(ModelProviderError) as terminal:
        await world["sign_in"].access_token()
    assert terminal.value.code == "model_credentials_rejected"
    after = await world["sign_in"].credential()
    assert after.client_id == CLIENT and after.host_id == before.host_id
    assert after.access_token is None and after.refresh_token is None and after.sign_in_again
    credentials = ProviderCredentials(world["fixture"].runtime.db, world["store"])
    assert not await credentials.configured("openai_chatgpt")
    with pytest.raises(ModelProviderError) as again:
        await credentials.connection("openai_chatgpt")
    assert again.value.code == "model_credentials_rejected"
    refreshes = [c for c in fake.calls if b"grant_type=refresh_token" in c.content]
    assert len(refreshes) == 2


@pytest.mark.parametrize("confirmed", [True, False])
async def test_sign_out_revokes_and_clears_the_tokens_either_way(
    world: dict[str, Any], confirmed: bool
) -> None:
    fake = world["fake"]
    await sign_in(world)
    fake.revoke_status = 200 if confirmed else 503
    out = await world["fixture"].client.post("/api/providers/openai_chatgpt/sign-out")
    assert out.status_code == 200 and out.json() == {"signed_out": True, "revoked": confirmed}
    revokes = [c for c in fake.calls if str(c.url) == REVOKE_URL]
    assert len(revokes) == (1 if confirmed else 2)
    form = parse_qs(revokes[0].content.decode())
    assert form == {
        "token": [fake.issued[0][1]],
        "token_type_hint": ["refresh_token"],
        "client_id": [CLIENT],
    }
    saved = await world["sign_in"].credential()
    assert saved.access_token is None and saved.refresh_token is None and saved.id_token is None
    assert saved.client_id == CLIENT and not saved.sign_in_again
    async with world["fixture"].runtime.db.sessions() as session:
        assert await session.get(SettingRow, CONNECTION_SETTING + "openai_chatgpt") is None
    listed = await world["fixture"].request("GET", "/providers")
    chatgpt = next(item for item in listed if item["id"] == "openai_chatgpt")
    assert chatgpt["configured"] is False and chatgpt["sign_in"]["plan"] is False
    # The next sign-in reuses the registration, without the cleared ID token as a hint.
    query = parse_qs(urlsplit(await start(world, await card(world))).query)
    assert query["client_id"] == [CLIENT] and "id_token_hint" not in query


# Each answer of the plan (4.8) and its Lonora code; every one lets the next model answer.
PLAN_ANSWERS = [
    (429, "subscription_sharing_usage_limit_exceeded", "model_billing_exhausted"),
    (403, "subscription_sharing_user_not_eligible", "model_access_denied"),
    (403, "subscription_sharing_route_not_supported", "model_access_denied"),
    (403, "chatpass_v2_scope_not_authorized", "model_access_denied"),
    (401, "subscription_sharing_invalid_user", "model_credentials_rejected"),
    (400, "subscription_sharing_unsupported_capability", "model_request_rejected"),
    (503, "subscription_sharing_usage_unavailable", "model_provider_unavailable"),
    (503, "subscription_sharing_user_unavailable", "model_provider_unavailable"),
]


class PlanCredentials(ProviderCredentials):
    """The signed-in plan's token, and a second provider's key to fall back to."""

    async def connection(self, provider: str) -> tuple[str, str | None]:
        if provider == "openai_chatgpt":
            return await super().connection(provider)
        return "fixture-not-a-real-key", None


@pytest.mark.parametrize(("status", "code", "lonora"), PLAN_ANSWERS)
async def test_each_plan_error_is_classified_and_never_shown(
    world: dict[str, Any], caplog: pytest.LogCaptureFixture, status: int, code: str, lonora: str
) -> None:
    caplog.set_level(logging.DEBUG)
    fake = world["fake"]
    await sign_in(world)
    secret_text = "provider-text-" + uuid4().hex
    fake.response_error = (
        status,
        {"error": {"code": code, "message": secret_text, "param": "tools"}},
    )

    def factory(provider: str, key: str, base_url: str | None = None) -> Any:
        if provider == "openai_chatgpt":
            return PROVIDERS[provider](key, fake.http())
        return Fallback()

    router = GlobalModelRouter(
        world["fixture"].runtime.db,
        PlanCredentials(world["fixture"].runtime.db, world["store"]),
        factory,
        sleep=lambda _: asyncio.sleep(0),
    )
    plan = ModelSelection(provider="openai_chatgpt", model="gpt-6.1-sol")
    backup = ModelSelection(provider="anthropic", model="claude-sonnet-5-5")
    reply, used = await router.complete(
        Capability.CONVERSATION,
        [ModelMessage(role="user", content="hi")],
        [],
        choices=[plan, backup],
    )
    assert used == backup and reply.text == "fallback"
    failure = reply.provider_metadata["route_failures"][0]
    assert failure["provider"] == "openai_chatgpt"
    assert ModelProviderError(FailureReason(failure["reason"])).code == lonora
    assert secret_text not in caplog.text and secret_text not in json.dumps(reply.provider_metadata)
    if code == "subscription_sharing_unsupported_capability":
        assert "param=tools" in caplog.text

    # Alone, the plan's failure is the run's, named as the plan's.
    with pytest.raises(ModelProviderError) as alone:
        await router.complete(
            Capability.CONVERSATION,
            [ModelMessage(role="user", content="hi")],
            [],
            choices=[ModelSelection(provider="openai_chatgpt", model="gpt-6.2-sol")],
        )
    assert alone.value.code == lonora and alone.value.provider == "openai_chatgpt"


class Fallback:
    """The next provider in the chain, answering at once."""

    async def complete(self, *args: Any, **kwargs: Any) -> ModelReply:
        return ModelReply(text="fallback", tool_calls=[], usage=TokenUsage(), provider_metadata={})

    async def close(self) -> None:
        return None


async def test_a_model_the_plan_refuses_leaves_the_accounts_list(world: dict[str, Any]) -> None:
    fake = world["fake"]
    await sign_in(world)
    fake.response_error = (
        400,
        {"error": {"code": "subscription_sharing_unsupported_capability", "param": "model"}},
    )
    router = GlobalModelRouter(
        world["fixture"].runtime.db,
        ProviderCredentials(world["fixture"].runtime.db, world["store"]),
        lambda provider, key, base_url=None: PROVIDERS[provider](key, fake.http()),
    )
    with pytest.raises(ModelProviderError):
        await router.complete(
            Capability.CONVERSATION,
            [ModelMessage(role="user", content="hi")],
            [],
            choices=[ModelSelection(provider="openai_chatgpt", model="gpt-6.2-sol")],
        )
    offered = {
        item.id for item in await read_catalog(world["fixture"].runtime.db, "openai_chatgpt")
    }
    assert offered == {"gpt-6.1-sol"}
    # The next sign-in starts the account's list afresh.
    await sign_in(world)
    offered = {
        item.id for item in await read_catalog(world["fixture"].runtime.db, "openai_chatgpt")
    }
    assert offered == {"gpt-6.1-sol", "gpt-6.2-sol"} <= LISTED


async def test_with_the_flag_off_nothing_offers_or_uses_the_sign_in(
    world: dict[str, Any], monkeypatch: pytest.MonkeyPatch
) -> None:
    card_id = await card(world)
    monkeypatch.setenv(signin.FLAG, "off")
    fixture = world["fixture"]
    for path in (
        f"/api/owner-actions/{card_id}/chatgpt/start",
        "/api/providers/openai_chatgpt/sign-out",
    ):
        answer = await fixture.client.post(path)
        assert answer.status_code == 409 and answer.json()["code"] == "chatgpt_sign_in_unavailable"
    answer = await finish(world, card_id, signin.REDIRECT_URI + "?state=x&code=y")
    assert answer.json()["code"] == "chatgpt_sign_in_unavailable"
    with pytest.raises(LonoraError) as refused:
        await card(world)
    assert refused.value.code == "chatgpt_sign_in_unavailable"
    assert "openai_chatgpt" not in {
        item["id"] for item in await fixture.request("GET", "/providers")
    }
    credentials = ProviderCredentials(fixture.runtime.db, world["store"])
    assert not await credentials.configured("openai_chatgpt")
    with pytest.raises(LonoraError) as unused:
        await credentials.connection("openai_chatgpt")
    assert unused.value.code == "model_not_configured"
    assert world["fake"].calls == []
