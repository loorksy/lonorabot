"""The models each provider offers: Lonora's fixed list, the one reader of it (VISION 12.4).

Every provider's models are the shipped list (``models.json``, ``lonora_core.model_list``),
except the owner's own OpenAI-compatible endpoint: its models are the owner's, read from
the endpoint and stored as ``catalog:openai_compatible``. No other provider is asked for
its models, and nothing else is stored. A listed model is ``verified``: it serves text
with tools (Rakazo runs every listed model with agent tools), images when its entry takes
them, and reasoning when its entry reasons, within the window and output the entry states.
A model is available to an agent when its provider is connected and its catalog lists it.
"""

from collections.abc import Iterable
from typing import Any, cast

from lonora_contracts.model_catalog import ModelDescriptor
from lonora_contracts.model_routing import ModelSelection
from lonora_core.model_list import list_package, listed_entries
from lonora_core.user_error import LonoraError
from lonora_db.client import Database
from lonora_db.transactions import SettingsRepository
from pydantic import ValidationError
from sqlalchemy.ext.asyncio import AsyncSession

from .registry import OWNER_ENDPOINT


def list_source() -> str:
    """The ``source`` of a listed model: ``lonora_model_list:pi-ai@1.6.0``."""
    return "lonora_model_list:" + list_package().rsplit("/", 1)[-1]


def listed_models(provider: str) -> list[ModelDescriptor]:
    """The shipped models of one provider, sorted by id; none for the owner's endpoint."""
    source = list_source()
    # Built without validation: the import and its test check the data, and a provider
    # is listed before its connection exists (openai_chatgpt is not a ProviderId yet).
    return [
        ModelDescriptor.model_construct(
            id=entry["id"],
            provider=provider,
            name=entry["name"],
            capabilities=[
                "text",
                "tools",
                *(["vision"] if "image" in entry["input"] else []),
                *(["reasoning"] if entry["reasoning"] else []),
            ],
            verified=True,
            context_window=entry["context_window"],
            maximum_output_tokens=entry["maximum_output_tokens"],
            source=source,
        )
        for entry in listed_entries(provider)
    ]


async def provider_catalog(session: AsyncSession, provider: str) -> list[ModelDescriptor]:
    """The models of one provider: the shipped list, or the owner endpoint's stored one."""
    if provider not in OWNER_ENDPOINT:
        return listed_models(provider)
    payload = await SettingsRepository().get(session, "catalog:" + provider)
    models: list[ModelDescriptor] = []
    for item in cast(list[Any], payload.get("models", [])):
        try:
            models.append(ModelDescriptor.model_validate(item))
        except ValidationError:
            continue
    return models


async def read_catalog(db: Database, provider: str) -> list[ModelDescriptor]:
    async with db.sessions() as session:
        return await provider_catalog(session, provider)


async def store_catalog(db: Database, provider: str, models: list[ModelDescriptor]) -> None:
    """The owner endpoint's models as it listed them; no other provider's list is stored."""
    if provider not in OWNER_ENDPOINT:
        raise LonoraError("provider_not_supported", 404)
    async with db.sessions() as session, session.begin():
        await SettingsRepository().put(
            session,
            "catalog:" + provider,
            {"models": [item.model_dump(mode="json") for item in models]},
        )


async def catalog_models(session: AsyncSession, providers: Iterable[str]) -> list[dict[str, str]]:
    """Text models the providers' catalogs list, as provider, id and name."""
    found: list[dict[str, str]] = []
    for provider in providers:
        for descriptor in await provider_catalog(session, provider):
            # A model the catalog verifies without text is not an agent's model.
            if descriptor.verified and "text" not in descriptor.capabilities:
                continue
            found.append({"provider": provider, "model": descriptor.id, "name": descriptor.name})
    return found


async def catalog_has(session: AsyncSession, selection: ModelSelection) -> bool:
    """Whether the provider's catalog lists this model."""
    return any(
        item.id == selection.model for item in await provider_catalog(session, selection.provider)
    )


async def model_label(session: AsyncSession, selection: ModelSelection | None) -> dict[str, Any]:
    """The model as the owner recognizes it: its catalog name when known."""
    if selection is None:
        return {"provider": None, "model": None, "name": None}
    name = next(
        (
            item.name
            for item in await provider_catalog(session, selection.provider)
            if item.id == selection.model
        ),
        None,
    )
    return {
        "provider": selection.provider,
        "model": selection.model,
        "name": name if name and name != selection.model else None,
    }
