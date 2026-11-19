from fastapi import APIRouter, Depends, Request
from lonora_auth.identity import OwnerIdentity
from lonora_contracts.model_routing import ProviderId
from lonora_core.user_error import LonoraError
from lonora_providers.catalog import read_catalog
from lonora_providers.registry import OWNER_ENDPOINT

from ..middleware.auth import require_owner, runtime

router = APIRouter(prefix="/providers")


def settings_provider(provider: ProviderId) -> ProviderId:
    """The providers the settings screens knew. A provider's key is connected from chat
    (Q14 (b)); this read is not extended (0.4) to the owner's own endpoint."""
    if provider in OWNER_ENDPOINT:
        raise LonoraError("provider_not_supported", 404)
    return provider


@router.get("/{provider}/models")
async def models(
    request: Request,
    provider: ProviderId = Depends(settings_provider),
    owner: OwnerIdentity = Depends(require_owner),
) -> list[dict[str, object]]:
    """The stored catalog, read only: the model routing and knowledge pages choose from it."""
    return [
        model.model_dump(mode="json") for model in await read_catalog(runtime(request).db, provider)
    ]
