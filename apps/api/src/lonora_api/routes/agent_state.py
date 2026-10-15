from fastapi import APIRouter, Depends, Request
from lonora_auth.identity import OwnerIdentity
from lonora_contracts.agent_state import AgentLiveState
from lonora_db.agent_state import agent_live_state

from ..middleware.auth import require_owner, runtime

router = APIRouter(prefix="/agents")


@router.get("/{agent_id}/state")
async def state(
    request: Request, agent_id: str, owner: OwnerIdentity = Depends(require_owner)
) -> AgentLiveState:
    async with runtime(request).db.sessions() as session:
        return await agent_live_state(session, owner.id, agent_id)
