"""A model provider's key, connected from chat (mandate 12.1, 7.2, P5; lead decision Q14 (b)).

The agent asks on a Secret card with target ``model_provider`` and the provider's id as
its name; the server sets the card's fields and its destination (workspace). For an
OpenAI-compatible endpoint the owner types the base URL with the key, as for any address
on a Secret card. Saving first asks the provider, with the typed key and no lock held,
whether it accepts the key: only the answer's status, never what it lists, since the
models are Lonora's list (VISION 12.4). The owner's endpoint is the exception: its URL is
checked and its catalog read. One transaction then saves the key under the provider's
usual name, records it for the router (with the endpoint's URL and catalog), settles the
card and wakes the asking agent to name the models that became available. The agent
never sees the key.
"""

import json
import os
import sys
from pathlib import Path
from typing import Any
from unittest.mock import patch
from uuid import uuid4

import httpx
import pytest
from lonora_contracts.model_catalog import ModelDescriptor
from lonora_contracts.model_routing import PROVIDER_KEY_NAMES
from lonora_contracts.owner_actions import OwnerActionProposal
from lonora_db.model_credentials import CONNECTION_SETTING
from lonora_db.schema import EventRow, MessageRow, RunRow, SecretRow, SettingRow
from lonora_db.transactions import SettingsRepository
from lonora_providers.credentials import ProviderCredentials
from pydantic import ValidationError
from sqlalchemy import select

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tests"))
from test_secret_card import call, thread_cards, workspace  # noqa: E402

ENDPOINT = "https://llm.example.test/v1"


def test_a_model_provider_card_takes_a_provider_id() -> None:
    for provider in PROVIDER_KEY_NAMES:
        OwnerActionProposal.model_validate(
            {"kind": "secret", "target": "model_provider", "name": provider}
        )
    for bad in (
        {},  # no provider
        {"name": "grok"},  # not a provider of 12.1
        {"name": "anthropic", "label": "x"},
        {"name": "anthropic", "metaapi_account_id": "a"},
        {"name": "anthropic", "service": "x"},
    ):
        with pytest.raises(ValidationError):
            OwnerActionProposal.model_validate(
                {"kind": "secret", "target": "model_provider", **bad}
            )


def test_an_agents_own_card_cannot_take_a_providers_key_name() -> None:
    # Only a model_provider card, which the owner reads as one, sets the router's key.
    for name in PROVIDER_KEY_NAMES.values():
        with pytest.raises(ValidationError):
            OwnerActionProposal.model_validate(
                {
                    "kind": "secret",
                    "label": "embeddings script",
                    "secret_fields": [{"key": name, "label": "key"}],
                }
            )


@pytest.mark.asyncio
async def test_an_older_own_card_under_a_providers_key_name_settles_stale() -> None:
    from typing import Any, cast

    from lonora_db.secret_cards import secret_stale_reason

    payload = {
        "connect": None,
        "fields": [{"key": "OPENAI_API_KEY", "label": "k"}],
        "destination": "workspace",
    }
    reason = await secret_stale_reason(cast(Any, None), "owner", payload)
    assert reason == "secret_name_reserved"


def test_an_endpoint_card_asks_for_its_url_and_a_fixed_provider_only_for_its_key() -> None:
    from lonora_db.secret_cards import secret_card_payload

    _, fixed = secret_card_payload(
        OwnerActionProposal(kind="secret", target="model_provider", name="anthropic")
    )
    assert fixed["details"] == {"provider": "anthropic", "name": "Anthropic"}
    assert [(f["key"], f["role"], f["secret"]) for f in fixed["fields"]] == [
        ("API_KEY", "api_key", True)
    ]
    assert fixed["destination"] == "workspace"
    _, endpoint = secret_card_payload(
        OwnerActionProposal(kind="secret", target="model_provider", name="openai_compatible")
    )
    assert endpoint["details"] == {"provider": "openai_compatible"}
    assert [(f["key"], f["role"], f["secret"]) for f in endpoint["fields"]] == [
        ("URL", "server_url", False),
        ("API_KEY", "api_key", True),
    ]


def descriptors(provider: str, count: int) -> list[ModelDescriptor]:
    return [
        ModelDescriptor(id=f"model-{index}", provider=provider, name=f"M{index}", source="fixture")  # type: ignore[arg-type]
        for index in range(count)
    ]


class Listing:
    """A provider answering the catalog read: its models, or a failure."""

    def __init__(self, models: list[ModelDescriptor] | None) -> None:
        self.models = models
        self.calls: list[tuple[str, str, str | None]] = []

    def __call__(self, provider: str, key: str, base_url: str | None = None) -> "Listing":
        self.calls.append((provider, key, base_url))
        return self

    async def discover(self) -> list[ModelDescriptor]:
        if self.models is None:
            raise ValueError("context_length 0")  # a listing the adapter cannot read
        return self.models

    async def close(self) -> None:
        return None


class KeyCheck:
    """Real adapters on a fake provider answering its model listing with ``status``."""

    def __init__(self, status: int) -> None:
        self.status = status
        self.seen: list[httpx.Request] = []

    def __call__(self, provider: str, key: str, base_url: str | None = None) -> Any:
        from lonora_providers.registry import PROVIDERS

        def answer(request: httpx.Request) -> httpx.Response:
            self.seen.append(request)
            listing = {"data": [{"id": "not-lonoras-list"}], "has_more": False}
            return httpx.Response(self.status, json=listing)

        return PROVIDERS[provider](key, httpx.AsyncClient(transport=httpx.MockTransport(answer)))


@pytest.mark.asyncio
async def test_a_fixed_providers_key_is_checked_and_its_list_is_never_read() -> None:
    if not os.environ.get("LONORA_DATABASE_URL"):
        pytest.skip("The Secret card uses the PostgreSQL test database.")
    from check_streaming import Fixture

    fixture = await Fixture().open()
    credentials = ProviderCredentials(
        fixture.runtime.db, fixture.runtime.services(fixture.owner).secrets
    )
    settings = SettingsRepository()
    async with fixture.runtime.db.sessions() as session:
        routing = await settings.get(session, "model_routing")
    # The default model's own key check, answered here: no request leaves the test.
    defaults: list[str] = []

    async def default_check(adapter: Any) -> None:
        defaults.append(type(adapter).__name__)

    try:
        agent = await fixture.agent("Claude")
        context = await fixture.lease(await fixture.run(agent, await fixture.conversation(agent)))
        outcomes: dict[int, tuple[str, str]] = {}
        chosen: dict[int, tuple[bool, int]] = {}
        for status in (200, 401, 503):
            # No routing yet: saving a usable key chooses the default model.
            async with fixture.runtime.db.sessions() as session, session.begin():
                await settings.put(session, "model_routing", {})
            checks = len(defaults)
            proposed = await call(
                context,
                "owner_action_propose",
                kind="secret",
                target="model_provider",
                name="anthropic",
            )
            card_id = proposed["owner_action"]["id"]
            key = "sk-ant-fixture-" + uuid4().hex
            check = KeyCheck(status)
            with (
                patch("lonora_api.routes.secret_cards.model_adapter", check),
                patch("lonora_providers.default_model.check_key", default_check),
            ):
                saved = await fixture.client.post(
                    f"/api/owner-actions/{card_id}/secret", json={"values": {"API_KEY": key}}
                )
            async with fixture.runtime.db.sessions() as session:
                unified = (await settings.get(session, "model_routing")).get("unified")
            chosen[status] = (unified is not None, len(defaults) - checks)
            assert saved.status_code == 200 and saved.json()["status"] == "confirmed"
            result = saved.json()["result"]
            assert result["saved"] == ["ANTHROPIC_API_KEY"] and "catalog" not in result
            # One request, its status the only thing read: the key in its own header.
            assert [(item.method, item.url.path, item.url.query) for item in check.seen] == [
                ("GET", "/v1/models", b"")
            ]
            assert check.seen[0].headers["x-api-key"] == key
            # The key is saved whatever the answer; the agent says what the provider said.
            assert await credentials.resolve("anthropic") == key
            outcomes[status] = (result["key"], card_id)
        assert {status: outcome[0] for status, outcome in outcomes.items()} == {
            200: "accepted",
            401: "rejected",
            503: "unchecked",
        }
        # A key the provider rejected chooses no default model; one it accepted, or that
        # could not be checked, does.
        assert not chosen[401][0] and chosen[401][1] == 0
        assert chosen[200][0] and chosen[503][0]
        async with fixture.runtime.db.sessions() as session:
            # Nothing the provider listed is stored: its models are Lonora's list.
            assert await session.get(SettingRow, "catalog:anthropic") is None
            runs = (
                await session.scalars(select(RunRow).where(RunRow.agent_id == agent["id"]))
            ).all()
        prompts = {
            status: next(
                run.prompt for run in runs if run.model_metadata.get("owner_action_id") == card
            )
            for status, (_, card) in outcomes.items()
        }
        assert "accepted the key" in prompts[200] and "model_list" in prompts[200]
        assert "rejected the key" in prompts[401] and "new Secret card" in prompts[401]
        assert "could not be checked" in prompts[503]
    finally:
        async with fixture.runtime.db.sessions() as session, session.begin():
            for row in (
                await session.scalars(
                    select(SecretRow).where(SecretRow.name == "ANTHROPIC_API_KEY")
                )
            ).all():
                await session.delete(row)
            setting = await session.get(SettingRow, CONNECTION_SETTING + "anthropic")
            if setting is not None:
                await session.delete(setting)
            await settings.put(session, "model_routing", routing)
        await fixture.close()


@pytest.mark.asyncio
async def test_the_owner_connects_a_model_provider_from_chat(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    if not os.environ.get("LONORA_DATABASE_URL"):
        pytest.skip("The Secret card uses the PostgreSQL test database.")
    from check_streaming import Fixture

    for provider in ("OPENAI", "OPENAI_COMPATIBLE"):
        monkeypatch.delenv(f"LONORA_{provider}_API_KEY", raising=False)
        monkeypatch.delenv(f"LONORA_{provider}_BASE_URL", raising=False)
    fixture = await Fixture().open()
    key, rotated = ("sk-fixture-" + uuid4().hex for _ in range(2))
    credentials = ProviderCredentials(
        fixture.runtime.db, fixture.runtime.services(fixture.owner).secrets
    )
    try:
        agent = await fixture.agent("Models")
        context = await fixture.lease(await fixture.run(agent, await fixture.conversation(agent)))

        async def propose() -> str:
            proposed = await call(
                context,
                "owner_action_propose",
                kind="secret",
                target="model_provider",
                name="openai_compatible",
            )
            return proposed["owner_action"]["id"]

        card_id = await propose()
        cards = await thread_cards(fixture, context.thread_id)
        facts = next(item for item in cards if item["id"] == card_id)["facts"]["secret"]
        # The server set the fields and the destination.
        assert facts["connect"] == "model_provider" and facts["destination"] == "workspace"
        assert facts["details"] == {"provider": "openai_compatible"}
        assert [field["key"] for field in facts["fields"]] == ["URL", "API_KEY"]
        assert facts["saves_as"] == ["OPENAI_COMPATIBLE_API_KEY"] and facts["replaces"] == []

        # An endpoint URL naming Lonora itself (here a metadata address) is refused before
        # any request; the card keeps waiting and nothing is saved.
        listing = Listing(descriptors("openai_compatible", 3))
        with patch("lonora_api.routes.secret_cards.model_adapter", listing):
            unsafe = await fixture.client.post(
                f"/api/owner-actions/{card_id}/secret",
                json={"values": {"URL": "http://169.254.169.254/v1", "API_KEY": key}},
            )
            assert unsafe.status_code == 422 and unsafe.json()["code"] == "unsafe_model_endpoint"
            assert listing.calls == []
            assert "OPENAI_COMPATIBLE_API_KEY" not in await workspace(fixture)

            saved = await fixture.client.post(
                f"/api/owner-actions/{card_id}/secret",
                json={"values": {"URL": ENDPOINT + "/", "API_KEY": key}},
            )
        assert saved.status_code == 200 and saved.json()["status"] == "confirmed"
        assert saved.json()["result"] == {
            "target": "model_provider",
            "provider": "openai_compatible",
            "configured": True,
            "saved": ["OPENAI_COMPATIBLE_API_KEY"],
            "catalog": 3,
        }
        # The catalog was read with the key and URL the owner typed, before saving.
        assert listing.calls == [("openai_compatible", key, ENDPOINT)]

        # The key is the owner's workspace secret by its usual name, and the router's.
        assert (await workspace(fixture))["OPENAI_COMPATIBLE_API_KEY"] == key
        assert await credentials.resolve("openai_compatible") == key
        assert await credentials.endpoint("openai_compatible") == ENDPOINT
        async with fixture.runtime.db.sessions() as session:
            stored = await session.get(SettingRow, "catalog:openai_compatible")
            assert stored is not None and len(stored.payload["models"]) == 3

        # The agent is woken to name the models; it never sees the key.
        async with fixture.runtime.db.sessions() as session:
            runs = (
                await session.scalars(select(RunRow).where(RunRow.agent_id == agent["id"]))
            ).all()
            events = (
                await session.scalars(select(EventRow).where(EventRow.owner_id == fixture.owner))
            ).all()
            messages = (
                await session.scalars(
                    select(MessageRow).where(MessageRow.thread_id == context.thread_id)
                )
            ).all()
        follow = [run for run in runs if run.model_metadata.get("owner_action_id") == card_id]
        assert len(follow) == 1
        assert "model_list" in follow[0].prompt and "3 models" in follow[0].prompt
        haystack = json.dumps(
            [
                [run.prompt for run in runs],
                [event.payload for event in events],
                [message.content for message in messages],
            ],
            default=str,
        )
        assert key not in haystack

        # A second card for the same provider says it replaces the saved key; a catalog
        # that cannot be read is said, not hidden, and the key is saved all the same.
        again_id = await propose()
        listed = await thread_cards(fixture, context.thread_id)
        rotate = next(item for item in listed if item["id"] == again_id)["facts"]["secret"]
        assert rotate["replaces"] == ["OPENAI_COMPATIBLE_API_KEY"]
        with patch("lonora_api.routes.secret_cards.model_adapter", Listing(None)):
            done = await fixture.client.post(
                f"/api/owner-actions/{again_id}/secret",
                json={"values": {"URL": ENDPOINT, "API_KEY": rotated}},
            )
        assert done.json()["status"] == "confirmed" and done.json()["result"]["catalog"] is None
        assert await credentials.resolve("openai_compatible") == rotated
        async with fixture.runtime.db.sessions() as session:
            # The catalog of the key it replaced is not offered as this key's.
            stored = await session.get(SettingRow, "catalog:openai_compatible")
            assert stored is not None and stored.payload["models"] == []
            runs = (
                await session.scalars(select(RunRow).where(RunRow.agent_id == agent["id"]))
            ).all()
        second = [run for run in runs if run.model_metadata.get("owner_action_id") == again_id]
        assert len(second) == 1 and "could not be read" in second[0].prompt

        # A key saved before Secret cards (scope provider) and one saved on a card: the
        # router uses the one the owner saved last, whichever path saved it, each with
        # its own URL (a settings-era key with the deployment's).
        deployment = "https://deployment.example.test/v1"
        monkeypatch.setenv("LONORA_OPENAI_COMPATIBLE_BASE_URL", deployment)
        store = fixture.runtime.services(fixture.owner).secrets
        await store.write("openai_compatible", "older-settings-key", "provider")
        assert await credentials.resolve("openai_compatible") == "older-settings-key"
        assert await credentials.endpoint("openai_compatible") == deployment
        third_id = await propose()
        with patch("lonora_api.routes.secret_cards.model_adapter", Listing([])):
            await fixture.client.post(
                f"/api/owner-actions/{third_id}/secret",
                json={"values": {"URL": ENDPOINT, "API_KEY": key}},
            )
        assert await credentials.resolve("openai_compatible") == key
        assert await credentials.endpoint("openai_compatible") == ENDPOINT

        # The card's key and its URL go together: once that key is gone, its URL is not
        # used with another key.
        async with fixture.runtime.db.sessions() as session, session.begin():
            for row in (
                await session.scalars(
                    select(SecretRow).where(
                        SecretRow.name.in_(["OPENAI_COMPATIBLE_API_KEY", "openai_compatible"])
                    )
                )
            ).all():
                await session.delete(row)
        monkeypatch.setenv("LONORA_OPENAI_COMPATIBLE_API_KEY", "deployment-key")
        assert await credentials.resolve("openai_compatible") == "deployment-key"
        assert await credentials.endpoint("openai_compatible") == deployment

        # A workspace secret under a provider's usual name that no card saved (a script's
        # key, or one migrated from an agent) is not the router's key.
        await store.write("OPENAI_API_KEY", "a-scripts-key", "workspace")
        assert not await credentials.configured("openai")
    finally:
        async with fixture.runtime.db.sessions() as session, session.begin():
            for row in (
                await session.scalars(
                    select(SecretRow).where(
                        SecretRow.name.in_(
                            ["OPENAI_COMPATIBLE_API_KEY", "openai_compatible", "OPENAI_API_KEY"]
                        )
                    )
                )
            ).all():
                await session.delete(row)
            for key_name in (CONNECTION_SETTING + "openai_compatible", "catalog:openai_compatible"):
                setting = await session.get(SettingRow, key_name)
                if setting is not None:
                    await session.delete(setting)
        await fixture.close()
