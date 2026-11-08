"""Owner-chosen model preference per Agent; it orders models, never grants authority."""

from fastapi import APIRouter, Depends, Request
from lonora_auth.identity import OwnerIdentity
from lonora_contracts.model_routing import AgentModelChange, AgentModelRecord
from lonora_db.agent_models import agent_model_record, change_agent_model

from ..middleware.auth import require_owner, runtime

router = APIRouter(prefix="/agents")


@router.get("/{agent_id}/model")
async def read(
    request: Request, agent_id: str, owner: OwnerIdentity = Depends(require_owner)
) -> AgentModelRecord:
    async with runtime(request).db.sessions() as session:
        return await agent_model_record(session, owner.id, agent_id)


@router.put("/{agent_id}/model")
async def update(
    request: Request,
    agent_id: str,
    body: AgentModelChange,
    owner: OwnerIdentity = Depends(require_owner),
) -> AgentModelRecord:
    async with runtime(request).db.sessions() as session, session.begin():
        return await change_agent_model(session, owner.id, agent_id, body)
