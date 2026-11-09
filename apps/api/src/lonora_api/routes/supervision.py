"""Supervision grants on the agents' profiles: list, add and revoke, owner session only.

A grant lets one agent read and steer another's work and never carries money authority
(``lonora_db.supervision``), so adding one from the profile is one tap, like revoking
one. A revoked grant ends the supervisor's reads and control at once. Agents set
supervision only from the owner's message or the owner's tap on a card.
"""

from typing import Any

from fastapi import APIRouter, Depends, Request
from lonora_auth.identity import OwnerIdentity
from lonora_contracts.supervision import SupervisionCreate
from lonora_db.supervision import (
    agent_names,
    grant_data,
    grant_supervision,
    revoke_supervision,
    supervision_view,
)

from ..middleware.auth import require_owner, runtime

router = APIRouter(prefix="/supervision")


@router.get("")
async def supervision(
    request: Request, agent_id: str, owner: OwnerIdentity = Depends(require_owner)
) -> dict[str, Any]:
    async with runtime(request).db.sessions() as session:
        return await supervision_view(session, owner.id, agent_id)


@router.post("", status_code=201)
async def create(
    request: Request, body: SupervisionCreate, owner: OwnerIdentity = Depends(require_owner)
) -> dict[str, Any]:
    async with runtime(request).db.sessions() as session, session.begin():
        row, _ = await grant_supervision(
            session, owner.id, body.supervisor_id, body.supervised_id, via="owner_ui"
        )
        names = await agent_names(
            session, owner.id, {row.supervisor_agent_id, row.supervised_agent_id}
        )
        return grant_data(row, names)


@router.post("/{grant_id}/revoke")
async def revoke(
    request: Request, grant_id: str, owner: OwnerIdentity = Depends(require_owner)
) -> dict[str, Any]:
    async with runtime(request).db.sessions() as session, session.begin():
        row = await revoke_supervision(session, owner.id, grant_id, via="owner_ui")
        names = await agent_names(
            session, owner.id, {row.supervisor_agent_id, row.supervised_agent_id}
        )
        return grant_data(row, names)
