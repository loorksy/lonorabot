"""Model access uses API keys only, through the adapters and the router (mandate 12.1).

Each of the six provider paths (Anthropic, OpenAI, DeepSeek, OpenRouter, Z.ai and an
OpenAI-compatible endpoint the owner names by its base URL) connects with an API key,
lists its catalog and runs a turn. Fake transports stand in for the providers; no
request leaves the process. The key travels only in the header each provider documents
for API keys, and nothing in a request depends on the plan behind the key.
"""

import json
from typing import Any, cast

import httpx
import pytest
from lonora_adapter_kit.types import ModelMessage
from lonora_contracts.model_routing import Capability, ModelSelection, ProviderId, RoutingPolicy
from lonora_core.user_error import LonoraError
from lonora_db.client import Database
from lonora_db.transactions import SettingsRepository
from lonora_providers.credentials import ProviderCredentials
from lonora_providers.default_model import choose_default_model
from lonora_providers.registry import PROVIDERS, model_adapter
from lonora_providers.router import GlobalModelRouter
from lonora_security.network import compatible_endpoint
from test_model_context import router_db as router_db

KEY = "fixture-not-a-real-key"
ENDPOINT = "https://llm.example.test/v1"
USER = [ModelMessage(role="user", content="مرحبا")]

# provider -> (base URL it calls, header carrying the key, that header's value)
PATHS: dict[str, tuple[str, str, str]] = {
    "anthropic": ("https://api.anthropic.com/v1", "x-api-key", KEY),
    "openai": ("https://api.openai.com/v1", "authorization", "Bearer " + KEY),
    "deepseek": ("https://api.deepseek.com/v1", "authorization", "Bearer " + KEY),
    "openrouter": ("https://openrouter.ai/api/v1", "authorization", "Bearer " + KEY),
    "zai": ("https://api.z.ai/api/paas/v4", "authorization", "Bearer " + KEY),
    "openai_compatible": (ENDPOINT, "authorization", "Bearer " + KEY),
}
# Headers a request may carry. Anything else (a beta flag, a client id, a session or
# subscription marker) would be an assumption the key does not make.
ALLOWED_HEADERS = {
    "accept",
    "accept-encoding",
    "connection",
    "content-length",
    "content-type",
    "host",
    "user-agent",
    "authorization",
    "x-api-key",
    "anthropic-version",
}


def provider_answer(request: httpx.Request) -> httpx.Response:
    path = request.url.path
    if request.method == "GET" and path.endswith("/models"):
        return httpx.Response(
            200, json={"data": [{"id": "model-a", "display_name": "Model A"}], "has_more": False}
        )
    if path.endswith("/messages"):
        return httpx.Response(
            200,
            json={
                "id": "msg_1",
                "content": [{"type": "text", "text": "أهلاً"}],
                "stop_reason": "end_turn",
                "usage": {"input_tokens": 3, "output_tokens": 2},
            },
        )
    if path.endswith("/chat/completions"):
        return httpx.Response(
            200,
            json={
                "id": "chatcmpl_1",
                "choices": [{"message": {"content": "أهلاً"}, "finish_reason": "stop"}],
                "usage": {"prompt_tokens": 3, "completion_tokens": 2},
            },
        )
    return httpx.Response(404, json={"error": {"message": "not found"}})


def recording() -> tuple[httpx.AsyncClient, list[httpx.Request]]:
    seen: list[httpx.Request] = []

    def handle(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return provider_answer(request)

    return httpx.AsyncClient(transport=httpx.MockTransport(handle)), seen


def adapter_with(provider: str, client: httpx.AsyncClient) -> Any:
    if provider == "openai_compatible":
        return PROVIDERS[provider](KEY, ENDPOINT, client)
    return PROVIDERS[provider](KEY, client)


def test_the_registry_has_exactly_the_six_paths_of_12_1() -> None:
    assert set(PROVIDERS) == set(PATHS)
    assert set(ProviderId.__args__) == set(PATHS)  # type: ignore[attr-defined]


@pytest.mark.asyncio
@pytest.mark.parametrize("provider", sorted(PATHS))
async def test_each_provider_lists_its_catalog_and_runs_a_turn_with_an_api_key(
    provider: str,
) -> None:
    base, header, value = PATHS[provider]
    client, seen = recording()
    adapter = adapter_with(provider, client)
    try:
        catalog = await adapter.discover()
        reply = await adapter.complete("model-a", USER, [])
    finally:
        await client.aclose()
    assert [item.id for item in catalog] == ["model-a"]
    assert {item.provider for item in catalog} == {provider}
    assert reply.text == "أهلاً"
    assert len(seen) == 2
    for request in seen:
        assert str(request.url).startswith(base + "/")
        assert request.headers[header] == value
        assert set(request.headers) <= ALLOWED_HEADERS, set(request.headers) - ALLOWED_HEADERS
        if header == "x-api-key":
            # An API key is never sent as a bearer token, the form OAuth tokens take.
            assert "authorization" not in request.headers
    body = json.loads(seen[1].content)
    assert body["model"] == "model-a"


@pytest.mark.parametrize(
    "url",
    [
        "https://llm.example.test/v1",
        "https://llm.example.test:8443/v1/",
        "http://10.0.0.5:8000/v1",
        "http://192.168.1.20:11434/v1",
        "http://llmhost:11434/v1",
        "http://lonora-ollama-1:11434/v1",
        "http://ollama:11434/v1",
    ],
)
def test_an_owner_endpoint_is_accepted_over_https_or_on_the_owners_network(url: str) -> None:
    assert compatible_endpoint(url) == url.rstrip("/")


@pytest.mark.parametrize(
    "url",
    [
        "http://llm.example.test/v1",
        "http://8.8.8.8/v1",
        "http://134744072/v1",  # 8.8.8.8 as one integer
        "http://0x8080808/v1",  # and in hex
        "http://0/v1",
        # Lonora itself: this container, a cloud metadata address, Lonora's services.
        "http://localhost:11434/v1",
        "https://localhost/v1",
        "http://127.0.0.1:8000/v1",
        "http://[::1]:8000/v1",
        "http://[::ffff:127.0.0.1]:8000/v1",
        "http://169.254.169.254/latest",
        "https://169.254.169.254/v1",
        "http://postgres:5432/v1",
        "http://db:5432/v1",
        "http://api:8000/v1",
        "http://gateway/v1",
        # The same, spelled another way: numeric loopback, a trailing dot, metadata names.
        "https://127.1/v1",
        "https://2130706433/v1",
        "https://0x7f.1/v1",
        "https://localhost./v1",
        "https://api./v1",
        "http://instance-data/latest",
        # A Lonora service by its Docker container name.
        "http://lonora-api-1/v1",
        "http://lonora-db-1:5432/v1",
        "http://lonora-gateway-1/v1",
        "http://myproject-api-2:8000/v1",
        "https://metadata.google.internal/v1",
        "ftp://llm.example.test/v1",
        "https://user:pass@llm.example.test/v1",
        "https://llm.example.test/v1?key=x",
        "https://llm.example.test/v1#x",
        "https:///v1",
        "llm.example.test/v1",
    ],
)
def test_an_unsafe_owner_endpoint_is_refused_before_any_request(url: str) -> None:
    with pytest.raises(LonoraError) as caught:
        compatible_endpoint(url)
    assert caught.value.code == "unsafe_model_endpoint"


def test_the_owner_endpoint_needs_its_base_url() -> None:
    with pytest.raises(LonoraError) as caught:
        model_adapter("openai_compatible", KEY)
    assert caught.value.code == "model_not_configured"


class Store:
    async def read(self, secret_id: str) -> str:
        raise AssertionError("no stored key in this test")


@pytest.mark.asyncio
async def test_an_owner_endpoint_connects_from_the_deployment_and_answers_through_the_router(
    router_db: Database, monkeypatch: pytest.MonkeyPatch, tmp_path: Any
) -> None:
    for provider in PATHS:
        monkeypatch.delenv("LONORA_" + provider.upper() + "_API_KEY", raising=False)
    monkeypatch.delenv("LONORA_OPENAI_COMPATIBLE_BASE_URL", raising=False)
    monkeypatch.chdir(tmp_path)  # no .env is read
    credentials = ProviderCredentials(router_db, Store())  # type: ignore[arg-type]
    # A key without its URL connects nothing, and the reverse.
    monkeypatch.setenv("LONORA_OPENAI_COMPATIBLE_API_KEY", KEY)
    assert not await credentials.configured("openai_compatible")
    monkeypatch.delenv("LONORA_OPENAI_COMPATIBLE_API_KEY")
    monkeypatch.setenv("LONORA_OPENAI_COMPATIBLE_BASE_URL", ENDPOINT + "/")
    assert not await credentials.configured("openai_compatible")
    monkeypatch.setenv("LONORA_OPENAI_COMPATIBLE_API_KEY", KEY)
    assert await credentials.configured("openai_compatible")
    assert await credentials.endpoint("openai_compatible") == ENDPOINT
    assert await credentials.endpoint("openai") is None
    # A URL that fails the check connects nothing; routing passes over it.
    monkeypatch.setenv("LONORA_OPENAI_COMPATIBLE_BASE_URL", "http://134744072/v1")
    assert await credentials.endpoint("openai_compatible") is None
    with pytest.raises(LonoraError) as caught:
        await credentials.resolve("openai_compatible")
    assert caught.value.code == "model_not_configured"
    monkeypatch.setenv("LONORA_OPENAI_COMPATIBLE_BASE_URL", ENDPOINT)

    client, seen = recording()

    def factory(provider: str, secret: str, base_url: str | None = None) -> Any:
        assert provider == "openai_compatible" and secret == KEY and base_url == ENDPOINT
        return PROVIDERS[provider](secret, base_url, client)

    try:
        # The only connected provider: its first listed model becomes the default.
        chosen = await choose_default_model(router_db, credentials, factory)
        assert chosen == ModelSelection(provider="openai_compatible", model="model-a")
        async with router_db.sessions() as session:
            stored = await SettingsRepository().get(session, "model_routing")
        policy = RoutingPolicy.model_validate(stored)
        assert policy.unified == chosen
        reply, selection = await GlobalModelRouter(router_db, credentials, factory).complete(
            Capability.CONVERSATION, USER, []
        )
    finally:
        await client.aclose()
    assert reply.text == "أهلاً"
    assert selection == chosen
    assert all(str(request.url).startswith(ENDPOINT + "/") for request in seen)


@pytest.mark.asyncio
async def test_the_legacy_settings_routes_stay_as_they_were(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The settings screens outside chat are removed (P5) and are not extended (0.4):
    their routes neither list nor take the owner's endpoint, so no screen shows its raw
    id or a page that cannot open it. The router and the agent's tools still see it."""
    import os

    if not os.environ.get("LONORA_DATABASE_URL"):
        pytest.skip("The settings routes are exercised through the owner API.")
    from check_streaming import Fixture

    monkeypatch.setenv("LONORA_OPENAI_COMPATIBLE_BASE_URL", ENDPOINT)
    monkeypatch.setenv("LONORA_OPENAI_COMPATIBLE_API_KEY", KEY)
    fixture = await Fixture().open()
    try:
        listed = await fixture.client.get("/api/providers")
        assert listed.status_code == 200
        assert [item["id"] for item in listed.json()] == [
            "openai",
            "anthropic",
            "deepseek",
            "zai",
            "openrouter",
        ]
        for method, path, body in (
            ("PUT", "/api/providers/openai_compatible/credential", {"api_key": KEY}),
            ("GET", "/api/providers/openai_compatible/models", None),
            ("POST", "/api/providers/openai_compatible/discover", None),
            ("POST", "/api/providers/openai_compatible/test", {"api_key": KEY}),
        ):
            answer = await fixture.client.request(method, path, json=body)
            assert answer.status_code == 404, path
            assert answer.json()["code"] == "provider_not_supported", path
    finally:
        await fixture.close()


def test_lonoras_own_services_are_never_an_owner_endpoint() -> None:
    """Every service in the repository's Compose files is refused as an endpoint host."""
    from pathlib import Path

    import yaml
    from lonora_security.network import LONORA_SERVICES

    root = Path(__file__).resolve().parents[1]
    services: set[str] = set()
    for path in [root / "docker-compose.yml", *root.glob("infra/**/*compose*.yml")]:
        document: dict[str, Any] = yaml.safe_load(path.read_text()) or {}
        services |= set(cast(dict[str, Any], document.get("services") or {}))
    assert services and services <= LONORA_SERVICES


@pytest.mark.asyncio
async def test_a_rotation_while_the_key_is_read_never_pairs_a_key_with_another_url(
    router_db: Database,
) -> None:
    """R-SEC M1 on #174: a card saved between reading the record and decrypting the key
    keeps the secret's id. The record is read again after the key; the pair is used only
    when nothing changed, so the new key never goes to the replaced address."""
    from datetime import UTC, datetime, timedelta

    from lonora_db.model_credentials import CONNECTION_SETTING
    from lonora_db.schema import SecretRow
    from lonora_db.transactions import SettingsRepository

    setting = CONNECTION_SETTING + "openai_compatible"
    first = datetime(2026, 11, 12, tzinfo=UTC)
    async with router_db.sessions() as session, session.begin():
        session.add(
            SecretRow(
                id="card-key",
                owner_id="owner",
                scope="workspace",
                name="OPENAI_COMPATIBLE_API_KEY",
                ciphertext="old",
                updated_at=first,
            )
        )
        await SettingsRepository().put(
            session, setting, {"secret_id": "card-key", "url": "https://old.example/v1"}
        )

    class Rotating:
        """The owner saves a new card (same secret id) while the old key is decrypted."""

        reads = 0

        async def read(self, secret_id: str) -> str:
            self.reads += 1
            if self.reads == 1:
                async with router_db.sessions() as session, session.begin():
                    row = await session.get(SecretRow, secret_id)
                    assert row is not None
                    row.updated_at = first + timedelta(seconds=1)
                    await SettingsRepository().put(
                        session, setting, {"secret_id": secret_id, "url": "https://new.example/v1"}
                    )
            return "sk-new-key-2222"

    credentials = ProviderCredentials(router_db, Rotating())  # type: ignore[arg-type]
    assert await credentials.connection("openai_compatible") == (
        "sk-new-key-2222",
        "https://new.example/v1",
    )
