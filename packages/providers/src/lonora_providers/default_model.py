"""The model a fresh install answers with before the owner has chosen one.

No routing and a provider key is the state of every new installation, and of one
that only received its keys (an import, an environment variable). The owner should
not have to find a routing setting before the product speaks, so the router asks
here once: the connected providers are taken in registry order, each one's own
catalog is read, and the first preferred family that catalog lists becomes the
unified route. It is written to ``model_routing`` like the owner's own choice, so
Settings show it and the owner changes it there.

The preference only orders what a provider really lists; an id it does not list is
never chosen. No key, or no listed family, chooses nothing: the caller reports
``model_not_configured``, which is not an outage.
"""

import logging
from collections.abc import Callable

from lonora_adapter_kit.model import ModelAdapter
from lonora_contracts.model_routing import ModelSelection, RoutingPolicy
from lonora_core.user_error import LonoraError
from lonora_db.client import Database
from lonora_db.transactions import SettingsRepository

from .catalog import store_catalog
from .credentials import ProviderCredentials
from .registry import PROVIDERS, build_adapter, model_adapter

log = logging.getLogger("lonora.model_router")

# General tool-calling text models per provider, newest first. A family matches its
# exact id or a dated snapshot of it, never a different model sharing the prefix.
PREFERRED_FAMILIES: dict[str, tuple[str, ...]] = {
    "openai": ("gpt-5.4-mini", "gpt-5-mini", "gpt-5", "gpt-4.1-mini", "gpt-4o-mini"),
    "anthropic": ("claude-sonnet-5", "claude-sonnet-4-6", "claude-sonnet-4-5", "claude-sonnet-4"),
    # DeepSeek's catalog lists deepseek-v4-pro and deepseek-flash (2026-11); deepseek-chat
    # stays for an account whose catalog still lists it.
    "deepseek": ("deepseek-v4-pro", "deepseek-flash", "deepseek-chat"),
    "zai": ("glm-5", "glm-4.7", "glm-4.6", "glm-4.5"),
    "openrouter": ("openrouter/auto",),
    # The owner's own endpoint has no family Lonora could know: the first model it lists.
    "openai_compatible": (),
}


def preferred_model(listed: list[str], families: tuple[str, ...]) -> str | None:
    """The first preferred family the catalog lists: its exact id, else its newest
    dated snapshot (``claude-sonnet-4-5-20250929``, ``gpt-5-mini-2025-08-07``)."""
    for family in families:
        if family in listed:
            return family
        snapshots = [
            model
            for model in listed
            if model.startswith(family + "-")
            and model[len(family) + 1 :].replace("-", "").isdigit()
        ]
        if snapshots:
            return max(snapshots)
    return None


async def choose_default_model(
    db: Database,
    credentials: ProviderCredentials,
    factory: Callable[..., ModelAdapter] = model_adapter,
) -> ModelSelection | None:
    """Choose and record the unified model, or return ``None`` when nothing can be
    chosen. A provider that could not be asked is passed over; if no other provider
    gives a model, its failure is raised, so an outage reads as an outage."""
    async with db.sessions() as session:
        stored = await SettingsRepository().get(session, "model_routing")
    current = RoutingPolicy.model_validate(stored)
    if current.mode != "unified" or current.unified is not None:
        # The owner's own routing (a unified model, or custom routes) is never filled in.
        return None
    unreachable: LonoraError | None = None
    for provider in PROVIDERS:
        try:
            secret = await credentials.resolve(provider)
        except LonoraError as error:
            if error.code != "model_not_configured":
                raise
            continue
        adapter = build_adapter(factory, provider, secret, await credentials.endpoint(provider))
        try:
            models = await adapter.discover()
        except LonoraError as error:
            unreachable = unreachable or error
            continue
        finally:
            await adapter.close()
        await store_catalog(db, provider, models)
        listed = [item.id for item in models]
        families = PREFERRED_FAMILIES[provider]
        model = preferred_model(listed, families) if families else next(iter(listed), None)
        if model is None:
            continue
        selection = ModelSelection.model_validate({"provider": provider, "model": model})
        async with db.sessions() as session, session.begin():
            settings = SettingsRepository()
            policy = RoutingPolicy.model_validate(await settings.get(session, "model_routing"))
            if policy.unified is not None:
                # The owner chose meanwhile: theirs stands.
                return policy.unified
            policy = policy.model_copy(update={"unified": selection})
            await settings.put(session, "model_routing", policy.model_dump(mode="json"))
        log.info("default_model_chosen provider=%s model=%s", provider, model)
        return selection
    if unreachable is not None:
        raise unreachable
    return None
