from fastapi import APIRouter, Depends, Request
from lonora_auth.identity import OwnerIdentity
from lonora_db.secrets import WORKSPACE, secret_metadata

from ..middleware.auth import require_owner, runtime

router = APIRouter()


@router.get("/secrets")
async def list_secrets(
    request: Request, owner: OwnerIdentity = Depends(require_owner)
) -> list[dict[str, str]]:
    """The owner's workspace secrets by name; values never leave the store. A secret is
    saved only through a Secret card (``secret_cards``)."""
    async with runtime(request).db.sessions() as session:
        return await secret_metadata(session, owner.id, WORKSPACE)


@router.delete("/secrets/{secret_id}")
async def delete_secret(
    request: Request, secret_id: str, owner: OwnerIdentity = Depends(require_owner)
) -> dict[str, bool]:
    """The only route that deletes a stored secret; one a connection uses is refused. A
    value already given to a workspace command stays encrypted in ln_workspace_given for
    up to 30 days, so the output scan keeps hiding it (docs/operations.md)."""
    await runtime(request).services(owner.id).secrets.delete(secret_id)
    return {"deleted": True}
