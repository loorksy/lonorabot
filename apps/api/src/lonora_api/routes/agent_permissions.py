"""Read of the stored ladder. Nothing here writes a level or a grant (S1a).

The ladder itself goes in a later slice. Until then a test that must store "No trading"
calls ``change_permission`` in-process. No route does.
"""

from fastapi import APIRouter, Depends, Request
from lonora_auth.identity import OwnerIdentity
from lonora_db.agent_permissions import permission_state

from ..middleware.auth import require_owner, runtime

router = APIRouter(prefix="/agents")


@router.get("/{agent_id}/permissions")
async def read(request: Request, agent_id: str, owner: OwnerIdentity = Depends(require_owner)):
    async with runtime(request).db.sessions() as session:
        return await permission_state(session, owner.id, agent_id)
