"""A model provider's key, connected from chat (mandate 12.1, 7.2, P5; lead decision Q14 (b)).

The agent asks on a Secret card with target ``model_provider``; the server sets its one
field and its destination (workspace). The owner's key is saved under the provider's
usual name, which the router reads on the server and a workspace tool finds by the same
name. An OpenAI-compatible endpoint's base URL comes from chat and is a setting, not a
secret. Saving reads the provider's catalog, then the asking agent is woken to name the
models that became available in one line. The agent never sees the key.
"""

import json
import os
import sys
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, patch
from uuid import uuid4

import pytest
from lonora_contracts.model_catalog import ModelDescriptor
from lonora_contracts.model_routing import PROVIDER_KEY_NAMES
from lonora_contracts.owner_actions import OwnerActionProposal
from lonora_core.user_error import LonoraError
from lonora_db.model_credentials import ENDPOINT_SETTING
from lonora_db.schema import EventRow, MessageRow, RunRow, SecretRow, SettingRow
from lonora_providers.credentials import ProviderCredentials
from pydantic import ValidationError
from sqlalchemy import select

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tests"))
from test_secret_card import call, thread_cards, workspace  # noqa: E402

ENDPOINT = "https://llm.example.test/v1"


def test_a_model_provider_card_takes_a_provider_id_and_a_url_only_for_an_endpoint() -> None:
    for provider in PROVIDER_KEY_NAMES:
        details: dict[str, Any] = {"name": provider}
        if provider == "openai_compatible":
            details["url"] = ENDPOINT
        OwnerActionProposal.model_validate(
            {"kind": "secret", "target": "model_provider", **details}
        )
    for bad in (
        {},  # no provider
        {"name": "grok"},  # not a provider of 12.1
        {"name": "openai", "url": ENDPOINT},  # a fixed provider has no URL to give
        {"name": "openai_compatible"},  # an endpoint needs its URL
        {"name": "anthropic", "label": "x"},
        {"name": "anthropic", "metaapi_account_id": "a"},
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


def test_an_unsafe_endpoint_never_becomes_a_card() -> None:
    from lonora_db.secret_cards import secret_card_payload

    with pytest.raises(LonoraError) as caught:
        secret_card_payload(
            OwnerActionProposal(
                kind="secret",
                target="model_provider",
                name="openai_compatible",
                url="http://134744072/v1",
            )
        )
    assert caught.value.code == "unsafe_model_endpoint"


def descriptors(provider: str, count: int) -> list[ModelDescriptor]:
    return [
        ModelDescriptor(id=f"model-{index}", provider=provider, name=f"M{index}", source="fixture")  # type: ignore[arg-type]
        for index in range(count)
    ]


@pytest.mark.asyncio
async def test_the_owner_connects_a_model_provider_from_chat() -> None:
    if not os.environ.get("LONORA_DATABASE_URL"):
        pytest.skip("The Secret card uses the PostgreSQL test database.")
    from check_streaming import Fixture

    fixture = await Fixture().open()
    key, rotated = ("sk-fixture-" + uuid4().hex for _ in range(2))
    try:
        agent = await fixture.agent("Models")
        context = await fixture.lease(await fixture.run(agent, await fixture.conversation(agent)))
        proposed = await call(
            context,
            "owner_action_propose",
            kind="secret",
            target="model_provider",
            name="openai_compatible",
            url=ENDPOINT + "/",
        )
        card_id = proposed["owner_action"]["id"]
        cards = await thread_cards(fixture, context.thread_id)
        facts = next(item for item in cards if item["id"] == card_id)["facts"]["secret"]
        # The server set the field and the destination; the details are the owner's words.
        assert facts["connect"] == "model_provider" and facts["destination"] == "workspace"
        assert facts["details"] == {
            "name": "llm.example.test",
            "provider": "openai_compatible",
            "url": ENDPOINT,
        }
        assert [field["key"] for field in facts["fields"]] == ["API_KEY"]
        assert facts["saves_as"] == ["OPENAI_COMPATIBLE_API_KEY"] and facts["replaces"] == []

        discovered = AsyncMock(return_value=descriptors("openai_compatible", 3))
        with patch("lonora_api.routes.secret_cards.discover_models", discovered):
            saved = await fixture.client.post(
                f"/api/owner-actions/{card_id}/secret", json={"values": {"API_KEY": key}}
            )
        assert saved.status_code == 200 and saved.json()["status"] == "confirmed"
        assert saved.json()["result"] == {
            "target": "model_provider",
            "provider": "openai_compatible",
            "configured": True,
            "saved": ["OPENAI_COMPATIBLE_API_KEY"],
            "catalog": 3,
        }
        assert discovered.await_args is not None
        assert discovered.await_args.args[2] == "openai_compatible"

        # The key is the owner's workspace secret by its usual name, and the router's.
        assert (await workspace(fixture))["OPENAI_COMPATIBLE_API_KEY"] == key
        credentials = ProviderCredentials(
            fixture.runtime.db, fixture.runtime.services(fixture.owner).secrets
        )
        assert await credentials.resolve("openai_compatible") == key
        assert await credentials.endpoint("openai_compatible") == ENDPOINT

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
        # that cannot be read is said, not hidden.
        again = await call(
            context,
            "owner_action_propose",
            kind="secret",
            target="model_provider",
            name="openai_compatible",
            url=ENDPOINT,
        )
        again_id = again["owner_action"]["id"]
        listed = await thread_cards(fixture, context.thread_id)
        rotate = next(item for item in listed if item["id"] == again_id)["facts"]["secret"]
        assert rotate["replaces"] == ["OPENAI_COMPATIBLE_API_KEY"]
        # An endpoint answering a listing the adapter cannot read (any error) is the same.
        failing = AsyncMock(side_effect=ValueError("context_length 0"))
        with patch("lonora_api.routes.secret_cards.discover_models", failing):
            done = await fixture.client.post(
                f"/api/owner-actions/{again_id}/secret", json={"values": {"API_KEY": rotated}}
            )
        assert done.json()["status"] == "confirmed" and done.json()["result"]["catalog"] is None
        assert await credentials.resolve("openai_compatible") == rotated
        async with fixture.runtime.db.sessions() as session:
            runs = (
                await session.scalars(select(RunRow).where(RunRow.agent_id == agent["id"]))
            ).all()
        second = [run for run in runs if run.model_metadata.get("owner_action_id") == again_id]
        assert len(second) == 1 and "could not be read" in second[0].prompt

        # A key saved before Secret cards (scope provider) and one saved on a card: the
        # router uses the one the owner saved last, whichever path saved it.
        store = fixture.runtime.services(fixture.owner).secrets
        await store.write("openai_compatible", "older-settings-key", "provider")
        assert await credentials.resolve("openai_compatible") == "older-settings-key"
        third = await call(
            context,
            "owner_action_propose",
            kind="secret",
            target="model_provider",
            name="openai_compatible",
            url=ENDPOINT,
        )
        with patch("lonora_api.routes.secret_cards.discover_models", discovered):
            await fixture.client.post(
                f"/api/owner-actions/{third['owner_action']['id']}/secret",
                json={"values": {"API_KEY": key}},
            )
        assert await credentials.resolve("openai_compatible") == key
    finally:
        async with fixture.runtime.db.sessions() as session, session.begin():
            for row in (
                await session.scalars(
                    select(SecretRow).where(
                        SecretRow.name.in_(["OPENAI_COMPATIBLE_API_KEY", "openai_compatible"])
                    )
                )
            ).all():
                await session.delete(row)
            setting = await session.get(SettingRow, ENDPOINT_SETTING + "openai_compatible")
            if setting is not None:
                await session.delete(setting)
        await fixture.close()
