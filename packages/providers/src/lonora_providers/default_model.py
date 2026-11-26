"""The model a fresh install answers with before the owner has chosen one.

No routing and a provider key is the state of every new installation, and of one
that only received its keys (an import, an environment variable). The owner should
not have to find a routing setting before the product speaks, so the router asks
here once: the connected providers are taken in registry order, and the first one's
default model becomes the unified route. It is written to ``model_routing`` like the
owner's own choice, so Settings show it and the owner changes it there.

A provider's default (``DEFAULT_MODELS``) is a strong tool-calling model of Lonora's
list (VISION 12.4), and it is chosen only while the list holds it; for the ChatGPT plan,
only while the signed-in account offers it (else its latest offered model). No provider is
asked for its models: its key is checked by the status of its listing alone
(``key_check``), and a key it rejects (401, 403) is passed over, so a stale key never
takes the route from a working one; a key that could not be checked counts. Only the
owner's own endpoint, which has no model Lonora could know, is read for the first
model it lists. No key, or nothing to choose, chooses nothing: the caller reports
``model_not_configured``, which is not an outage.
"""

import logging
from collections.abc import Callable

from lonora_adapter_kit.model import ModelAdapter
from lonora_adapter_kit.model_errors import ModelProviderError
from lonora_contracts.model_routing import ModelSelection, RoutingPolicy
from lonora_core.user_error import LonoraError
from lonora_db.client import Database
from lonora_db.transactions import SettingsRepository

from .catalog import listed_models, read_catalog
from .credentials import ProviderCredentials
from .discovery import discover_models
from .key_check import REJECTED, check_key
from .registry import OWNER_ENDPOINT, PROVIDERS, SIGN_IN, build_adapter, model_adapter

log = logging.getLogger("lonora.model_router")

# A trading agent needs a strong model: each provider's default when the owner chose none.
DEFAULT_MODELS: dict[str, str] = {
    "openai": "gpt-6.2-sol",
    # Rakazo's subscription default.
    "openai_chatgpt": "gpt-6.1-sol",
    "anthropic": "claude-sonnet-5-5",
    "deepseek": "deepseek-v4-pro",
    "zai": "glm-5.3",
    "openrouter": "anthropic/claude-sonnet-5.5",
}


async def choose_default_model(
    db: Database,
    credentials: ProviderCredentials,
    factory: Callable[..., ModelAdapter] = model_adapter,
) -> ModelSelection | None:
    """Choose and record the unified model, or return ``None`` when nothing can be
    chosen. A rejected key, or the owner's endpoint when it cannot be asked, is passed
    over; if no other provider gives a model, its failure is raised, so an outage reads
    as an outage and a rejected key as one."""
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
                if provider not in SIGN_IN:
                    raise
                # A sign-in that could not be renewed is passed over like a rejected key.
                unreachable = unreachable or error
            continue
        if provider in OWNER_ENDPOINT:
            try:
                models = await discover_models(db, credentials, provider, factory)
            except LonoraError as error:
                unreachable = unreachable or error
                continue
            model = next((item.id for item in models), None)
        elif provider in SIGN_IN:
            # The plan's models as the signed-in account offers them; its token was just
            # checked by the sign-in or its refresh, so no key check.
            offered = [item.id for item in await read_catalog(db, provider)]
            model = DEFAULT_MODELS[provider] if DEFAULT_MODELS[provider] in offered else None
            model = model or (offered[-1] if offered else None)
        else:
            model = DEFAULT_MODELS[provider]
            if model not in {item.id for item in listed_models(provider)}:
                model = None
            elif rejected := await rejected_key(factory, provider, secret):
                unreachable = unreachable or rejected
                continue
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


async def rejected_key(
    factory: Callable[..., ModelAdapter], provider: str, secret: str
) -> ModelProviderError | None:
    """The provider's refusal of the key (401, 403), or ``None``: accepted, or it could
    not be checked (no answer, another answer), which leaves the key usable."""
    adapter = build_adapter(factory, provider, secret, None)
    try:
        await check_key(adapter)
    except ModelProviderError as error:
        if error.http_status in REJECTED:
            return error
        log.warning("default_model_key_unchecked provider=%s reason=%s", provider, error.code)
    finally:
        await adapter.close()
    return None
