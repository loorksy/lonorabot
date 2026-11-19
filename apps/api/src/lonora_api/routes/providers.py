from fastapi import APIRouter, Depends, Request
from lonora_auth.identity import OwnerIdentity
from lonora_contracts.model_catalog import ProviderCredential
from lonora_contracts.model_routing import ProviderId
from lonora_core.user_error import LonoraError
from lonora_providers.catalog import read_catalog
from lonora_providers.credentials import ProviderCredentials
from lonora_providers.discovery import discover_models
from lonora_providers.registry import OWNER_ENDPOINT, PROVIDERS

from ..middleware.auth import require_owner, runtime
from .model_router import answer_unconfigured

router = APIRouter(prefix="/providers")


def settings_provider(provider: ProviderId) -> ProviderId:
    """The providers the settings screens knew. Those screens are removed (P5) and not
    extended (0.4): the owner's own endpoint is connected from chat, never here."""
    if provider in OWNER_ENDPOINT:
        raise LonoraError("provider_not_supported", 404)
    return provider


@router.get("")
async def providers(
    request: Request, owner: OwnerIdentity = Depends(require_owner)
) -> list[dict[str, object]]:
    rt = runtime(request)
    credentials = ProviderCredentials(rt.db, rt.services(owner.id).secrets)
    return [
        {"id": provider, "configured": await credentials.configured(provider)}
        for provider in PROVIDERS
        if provider not in OWNER_ENDPOINT
    ]


@router.put("/{provider}/credential")
async def save_credential(
    request: Request,
    body: ProviderCredential,
    provider: ProviderId = Depends(settings_provider),
    owner: OwnerIdentity = Depends(require_owner),
) -> dict[str, bool]:
    await runtime(request).services(owner.id).secrets.write(provider, body.api_key, "provider")
    # With a key the router can choose a model: what failed for lack of one is retried.
    await answer_unconfigured(request, owner)
    return {"configured": True}


@router.get("/{provider}/models")
async def models(
    request: Request,
    provider: ProviderId = Depends(settings_provider),
    owner: OwnerIdentity = Depends(require_owner),
) -> list[dict[str, object]]:
    return [
        model.model_dump(mode="json") for model in await read_catalog(runtime(request).db, provider)
    ]


@router.post("/{provider}/discover")
async def discover(
    request: Request,
    provider: ProviderId = Depends(settings_provider),
    owner: OwnerIdentity = Depends(require_owner),
) -> list[dict[str, object]]:
    rt = runtime(request)
    credentials = ProviderCredentials(rt.db, rt.services(owner.id).secrets)
    return [
        model.model_dump(mode="json")
        for model in await discover_models(rt.db, credentials, provider)
    ]
