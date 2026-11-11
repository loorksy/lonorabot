from fastapi import APIRouter, Depends, Request
from lonora_auth.identity import OwnerIdentity
from lonora_contracts.model_catalog import ProviderCredential
from lonora_contracts.model_routing import ProviderId
from lonora_core.user_error import LonoraError
from lonora_db.agent_models import provider_in_use
from lonora_db.model_credentials import credential_id
from lonora_db.schema import SecretRow, SettingRow
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


@router.delete("/{provider}/credential")
async def remove_credential(
    request: Request, provider: ProviderId, owner: OwnerIdentity = Depends(require_owner)
) -> dict[str, bool]:
    """Forget a provider's stored key and the models discovered with it. Refused while a
    route, a backup, an allowed model or an Agent's own choice still names the provider."""
    rt = runtime(request)
    async with rt.db.sessions() as session, session.begin():
        secret_id = await credential_id(session, provider)
        row = await session.get(SecretRow, secret_id, with_for_update=True) if secret_id else None
        if row is None or row.owner_id != owner.id:
            raise LonoraError("provider_credential_not_stored", 404)
        if await provider_in_use(session, owner.id, provider):
            raise LonoraError("provider_in_use", 409)
        await session.delete(row)
        catalog = await session.get(SettingRow, "catalog:" + provider)
        if catalog is not None:
            await session.delete(catalog)
    credentials = ProviderCredentials(rt.db, rt.services(owner.id).secrets)
    return {"configured": await credentials.configured(provider)}


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
