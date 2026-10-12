from fastapi import APIRouter, Depends, Request
from lonora_auth.identity import OwnerIdentity
from lonora_contracts.model_catalog import ProviderCredential
from lonora_contracts.model_routing import ProviderId
from lonora_providers.catalog import read_catalog
from lonora_providers.credentials import ProviderCredentials
from lonora_providers.discovery import discover_models
from lonora_providers.registry import PROVIDERS

from ..middleware.auth import require_owner, runtime

router = APIRouter(prefix="/providers")


@router.get("")
async def providers(
    request: Request, owner: OwnerIdentity = Depends(require_owner)
) -> list[dict[str, object]]:
    rt = runtime(request)
    credentials = ProviderCredentials(rt.db, rt.services(owner.id).secrets)
    return [
        {"id": provider, "configured": await credentials.configured(provider)}
        for provider in PROVIDERS
    ]


@router.put("/{provider}/credential")
async def save_credential(
    request: Request,
    provider: ProviderId,
    body: ProviderCredential,
    owner: OwnerIdentity = Depends(require_owner),
) -> dict[str, bool]:
    await runtime(request).services(owner.id).secrets.write(provider, body.api_key, "provider")
    return {"configured": True}


@router.get("/{provider}/models")
async def models(
    request: Request, provider: ProviderId, owner: OwnerIdentity = Depends(require_owner)
) -> list[dict[str, object]]:
    return [
        model.model_dump(mode="json") for model in await read_catalog(runtime(request).db, provider)
    ]


@router.post("/{provider}/discover")
async def discover(
    request: Request, provider: ProviderId, owner: OwnerIdentity = Depends(require_owner)
) -> list[dict[str, object]]:
    rt = runtime(request)
    credentials = ProviderCredentials(rt.db, rt.services(owner.id).secrets)
    return [
        model.model_dump(mode="json")
        for model in await discover_models(rt.db, credentials, provider)
    ]
