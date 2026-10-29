"""Authenticated per-Agent approval preferences; no unsigned autonomy toggle."""

from fastapi import APIRouter, Depends, Request
from lonora_auth.identity import OwnerIdentity
from lonora_contracts.agent_permissions import PermissionChange, PermissionCustomizationChange
from lonora_db.agent_permissions import change_permission, permission_state, save_customization

from ..middleware.auth import require_owner, runtime

router = APIRouter(prefix="/agents")


@router.get("/{agent_id}/permissions")
async def read(request: Request, agent_id: str, owner: OwnerIdentity = Depends(require_owner)):
    async with runtime(request).db.sessions() as session:
        return await permission_state(session, owner.id, agent_id)


@router.put("/{agent_id}/permissions")
async def update(
    request: Request,
    agent_id: str,
    body: PermissionChange,
    owner: OwnerIdentity = Depends(require_owner),
):
    async with runtime(request).db.sessions() as session, session.begin():
        return await change_permission(session, owner.id, agent_id, body)


@router.put("/{agent_id}/permissions/customization")
async def customization(
    request: Request,
    agent_id: str,
    body: PermissionCustomizationChange,
    owner: OwnerIdentity = Depends(require_owner),
):
    async with runtime(request).db.sessions() as session, session.begin():
        return await save_customization(session, owner.id, agent_id, body)
