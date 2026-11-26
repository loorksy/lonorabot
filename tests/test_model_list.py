"""Lonora's fixed model list (VISION 12.4, Amendment 4).

The list is Rakazo's: the chat models of ``@earendil-works/pi-ai`` 1.6.0 for the
providers Lonora supports, without OpenRouter's ``:batch`` ids, checked in as
``lonora_providers/models.json`` by ``scripts/import_model_catalog.py``. Every entry's
wire is one its provider's adapter speaks. No fixed provider is asked for its models on
any path that reads a catalog: the pickers, the agent's tools and gates, the router and
the default model all read the list; only the owner's endpoint lists its own.
"""

import importlib.util
import json
import os
from pathlib import Path
from typing import Any, get_args

import httpx
import pytest
from lonora_contracts.model_catalog import ModelDescriptor
from lonora_contracts.model_routing import Capability, ModelSelection, ProviderId
from lonora_core.user_error import LonoraError
from lonora_db.client import Database
from lonora_providers.catalog import (
    catalog_has,
    catalog_models,
    list_source,
    listed_models,
    model_label,
    read_catalog,
    store_catalog,
)
from lonora_providers.credentials import ProviderCredentials
from lonora_providers.default_model import DEFAULT_MODELS, choose_default_model
from lonora_providers.registry import OWNER_ENDPOINT, PROVIDERS
from lonora_providers.router import GlobalModelRouter
from lonora_providers.routing_policy import read_policy
from test_model_context import router_db as router_db
from test_model_context import settings

ROOT = Path(__file__).resolve().parents[1]
LIST = ROOT / "packages/providers/src/lonora_providers/models.json"
FIXED = sorted(set(PROVIDERS) - OWNER_ENDPOINT)
# The wires each provider's adapter speaks (pi-ai's ``api``).
WIRES = {
    "anthropic": {"anthropic-messages"},
    "openai": {"openai-responses"},
    "openai_chatgpt": {"openai-codex-responses"},
    "deepseek": {"openai-completions"},
    "zai": {"openai-completions"},
    "openrouter": {"openai-completions", "anthropic-messages"},
}
ENTRY = {
    "id",
    "name",
    "wire",
    "context_window",
    "maximum_output_tokens",
    "input",
    "reasoning",
    "cost",
}


def importer() -> Any:
    path = ROOT / "scripts/import_model_catalog.py"
    spec = importlib.util.spec_from_file_location("import_model_catalog", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def shipped() -> dict[str, Any]:
    return json.loads(LIST.read_text(encoding="utf-8"))


def test_the_list_has_its_shape_and_its_source() -> None:
    data = shipped()
    assert list(data) == ["source", "providers"]
    assert data["source"] == "@earendil-works/pi-ai@1.6.0 (the list Rakazo pins)"
    assert set(data["providers"]) == set(WIRES)
    for provider, entries in data["providers"].items():
        ids = [entry["id"] for entry in entries]
        assert ids == sorted(ids) and len(ids) == len(set(ids)), provider
        for entry in entries:
            assert set(entry) == ENTRY, entry["id"]
            assert entry["wire"] in WIRES[provider], (provider, entry["id"], entry["wire"])
            assert entry["input"][0] == "text" and set(entry["input"]) <= {"text", "image"}
            assert isinstance(entry["reasoning"], bool)
            assert entry["context_window"] > 0 and entry["maximum_output_tokens"] > 0
            assert set(entry["cost"]) == {"input", "output", "cache_read", "cache_write"}
            assert all(price >= 0 for price in entry["cost"].values())
    # Rakazo's agent filter: OpenRouter's batch ids are not agents' models.
    assert not [entry for entry in data["providers"]["openrouter"] if ":batch" in entry["id"]]
    # The file is exactly what the import writes, so a re-import is a reviewable diff.
    assert importer().rendered(data) == LIST.read_text(encoding="utf-8")


def test_each_provider_lists_the_models_rakazo_lists() -> None:
    data = shipped()
    listed = {
        provider: {e["id"] for e in entries} for provider, entries in data["providers"].items()
    }
    expected = {
        "anthropic": {
            "claude-sonnet-5-5",
            "claude-opus-5-5",
            "claude-haiku-4-5",
            "claude-fable-5-2",
        },
        "openai": {"gpt-6.2-sol", "gpt-5.4-mini", "gpt-4.1", "o3"},
        "openai_chatgpt": {"gpt-6.1-sol", "gpt-6.2-sol", "gpt-5.6-luna"},
        "deepseek": {"deepseek-v4-pro", "deepseek-flash"},
        "zai": {"glm-5.3", "glm-4.7", "glm-5-turbo"},
        "openrouter": {"anthropic/claude-sonnet-5.5", "~anthropic/claude-sonnet-latest"},
    }
    for provider, models in expected.items():
        assert models <= listed[provider], (provider, models - listed[provider])
    assert len(listed["deepseek"]) == 2 and len(listed["openai_chatgpt"]) == 10
    sonnet = next(e for e in data["providers"]["anthropic"] if e["id"] == "claude-sonnet-5-5")
    assert sonnet == {
        "id": "claude-sonnet-5-5",
        "name": "Claude Sonnet 5.5",
        "wire": "anthropic-messages",
        "context_window": 1000000,
        "maximum_output_tokens": 128000,
        "input": ["text", "image"],
        "reasoning": True,
        "cost": {"input": 2, "output": 10, "cache_read": 0.1, "cache_write": 2.5},
    }


def test_the_import_keeps_chat_models_maps_providers_and_refuses_another_wire(
    tmp_path: Path,
) -> None:
    script = importer()
    data = tmp_path / "dist" / "providers" / "data"
    data.mkdir(parents=True)
    (tmp_path / "package.json").write_text(
        json.dumps({"name": "@earendil-works/pi-ai", "version": "9.9.9"})
    )

    def chat(model: str, api: str, **extra: Any) -> dict[str, Any]:
        return {
            "type": "chat",
            "id": model,
            "name": model.upper(),
            "api": api,
            "reasoning": False,
            "input": ["image", "text"],
            "cost": {"input": 1, "output": 2, "cacheRead": 0.1, "cacheWrite": 0},
            "contextWindow": 1000,
            "maxTokens": 100,
            **extra,
        }

    wires = {
        "anthropic": "anthropic-messages",
        "openai": "openai-responses",
        "openai-codex": "openai-codex-responses",
        "deepseek": "openai-completions",
        "zai": "openai-completions",
        "openrouter": "openai-completions",
    }
    for name, api in wires.items():
        group = {"chat:b-model": chat("b-model", api), "chat:a-model": chat("a-model", api)}
        if name == "openrouter":
            group["chat:a-model:batch"] = chat("a-model:batch", api)
        if name == "openai":
            group["classifier:c"] = {**chat("classifier-model", api), "type": "classifier"}
        (data / (name + ".json")).write_text(json.dumps({api: group}))
    imported = script.model_list(tmp_path)
    assert imported["source"] == "@earendil-works/pi-ai@9.9.9 (the list Rakazo pins)"
    assert list(imported["providers"]) == sorted(WIRES)
    for provider, entries in imported["providers"].items():
        assert [entry["id"] for entry in entries] == ["a-model", "b-model"], provider
    first = imported["providers"]["openai_chatgpt"][0]
    assert first["wire"] == "openai-codex-responses" and first["input"] == ["text", "image"]
    assert first["cost"] == {"input": 1, "output": 2, "cache_read": 0.1, "cache_write": 0}
    assert script.rendered(imported) == script.rendered(script.model_list(tmp_path))
    # A wire its provider's adapter does not speak fails the whole import.
    (data / "deepseek.json").write_text(
        json.dumps({"x": {"chat:a": chat("a-model", "anthropic-messages")}})
    )
    with pytest.raises(SystemExit, match="does not speak"):
        script.model_list(tmp_path)


def test_listed_models_are_verified_descriptors_of_the_list() -> None:
    for provider in FIXED:
        models = listed_models(provider)
        assert models and all(item.verified for item in models)
        for item in models:
            # A registered provider's entries are valid descriptors.
            assert ModelDescriptor.model_validate(item.model_dump()) == item
            assert item.provider == provider and item.source == list_source()
            assert item.capabilities[:2] == ["text", "tools"]
            assert item.context_window and item.maximum_output_tokens
    assert list_source() == "lonora_model_list:pi-ai@1.6.0"
    glm = next(item for item in listed_models("zai") if item.id == "glm-4.7")
    assert glm.capabilities == ["text", "tools", "reasoning"]
    sonnet = next(item for item in listed_models("anthropic") if item.id == "claude-sonnet-5-5")
    assert sonnet.capabilities == ["text", "tools", "vision", "reasoning"]
    # The ChatGPT plan's list is there before its sign-in exists; the owner's endpoint
    # has none: its models are the owner's.
    assert "openai_chatgpt" not in get_args(ProviderId) and "openai_chatgpt" not in PROVIDERS
    assert "gpt-6.1-sol" in {item.id for item in listed_models("openai_chatgpt")}
    assert listed_models("openai_compatible") == []


def forbid_discovery(monkeypatch: pytest.MonkeyPatch) -> list[str]:
    """Every fixed provider's adapter refuses to list its models."""
    asked: list[str] = []
    for provider in FIXED:

        async def discover(self: Any, provider: str = provider) -> list[ModelDescriptor]:
            asked.append(provider)
            raise AssertionError(provider + " was asked for its models")

        monkeypatch.setattr(PROVIDERS[provider], "discover", discover)
    return asked


class Keys(ProviderCredentials):
    def __init__(self, *providers: str) -> None:
        self.providers = providers

    async def resolve(self, provider: str) -> str:
        if provider not in self.providers:
            raise LonoraError("model_not_configured", 409)
        return "fixture-not-a-real-key"


@pytest.mark.asyncio
async def test_no_fixed_provider_is_asked_for_its_models_on_the_catalog_path(
    router_db: Database, monkeypatch: pytest.MonkeyPatch
) -> None:
    asked = forbid_discovery(monkeypatch)
    for provider in FIXED:
        assert [item.id for item in await read_catalog(router_db, provider)] == [
            item.id for item in listed_models(provider)
        ]
        with pytest.raises(LonoraError):
            await store_catalog(router_db, provider, listed_models(provider))
    async with router_db.sessions() as session:
        # The pickers and the agent's tools and gates (model_list, model_request,
        # agent_create, subagent_spawn, consult_model).
        entries = await catalog_models(session, FIXED)
        assert len(entries) == sum(len(listed_models(provider)) for provider in FIXED)
        chosen = ModelSelection(provider="openrouter", model="anthropic/claude-sonnet-5.5")
        assert await catalog_has(session, chosen)
        assert not await catalog_has(session, ModelSelection(provider="openai", model="gpt-9"))
        assert (await model_label(session, chosen))["name"] == "Anthropic: Claude Sonnet 5.5"
    # The default model and the router's descriptors.
    keys = Keys(*FIXED)
    selection = await choose_default_model(router_db, keys)
    assert selection == ModelSelection(provider="openai", model=DEFAULT_MODELS["openai"])
    assert (await read_policy(router_db)).unified == selection
    await settings(
        router_db,
        {
            "model_backups": {
                "choices": [
                    {"provider": provider, "model": DEFAULT_MODELS[provider]} for provider in FIXED
                ]
            }
        },
    )
    route = await GlobalModelRouter(router_db, keys).route(Capability.CONVERSATION)
    for choice in route.choices:
        descriptor = route.descriptor(choice)
        assert descriptor is not None and descriptor.source == list_source(), choice
    assert asked == []


@pytest.mark.asyncio
async def test_the_settings_routes_serve_the_list_and_check_a_key_by_status(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    if not os.environ.get("LONORA_DATABASE_URL"):
        pytest.skip("The settings routes are exercised through the owner API.")
    from check_streaming import Fixture
    from lonora_api.routes import connection_tests

    asked = forbid_discovery(monkeypatch)
    seen: list[httpx.Request] = []

    def adapter(provider: str, key: str) -> Any:
        def answer(request: httpx.Request) -> httpx.Response:
            seen.append(request)
            return httpx.Response(200, json={"data": [{"id": "not-lonoras-list"}]})

        return PROVIDERS[provider](key, httpx.AsyncClient(transport=httpx.MockTransport(answer)))

    monkeypatch.setattr(connection_tests, "model_adapter", adapter)
    fixture = await Fixture().open()
    try:
        for provider in FIXED:
            listed = await fixture.client.get(f"/api/providers/{provider}/models")
            assert listed.status_code == 200, listed.text
            assert [item["id"] for item in listed.json()] == [
                item.id for item in listed_models(provider)
            ]
            tested = await fixture.client.post(
                f"/api/providers/{provider}/test", json={"api_key": "sk-fixture-key-1"}
            )
            assert tested.status_code == 200 and tested.json() == {"ok": True}
        # One status-only request per key: the listing's path, with no paging asked.
        assert [(item.method, item.url.query) for item in seen] == [("GET", b"")] * len(FIXED)
        assert all(item.url.path.endswith("/models") for item in seen)
        assert asked == []
    finally:
        await fixture.close()
