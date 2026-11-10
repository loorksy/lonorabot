"""Per-agent delivery rules (owner decision Q47): GET/PUT /api/agents/{id}/notifications."""

from fastapi import APIRouter, Depends, Request
from lonora_auth.identity import OwnerIdentity
from lonora_contracts.agent_delivery import AgentDeliveryRulesUpdate
from lonora_db.agent_delivery import all_delivery_rules, delivery_rules, set_delivery_rules
from lonora_db.transactions import owned_agent

from ..middleware.auth import require_owner, runtime

router = APIRouter(prefix="/agents")


@router.get("/notifications")
async def list_rules(request: Request, owner: OwnerIdentity = Depends(require_owner)):
    """The agents that have rules of their own; any other agent follows the defaults."""
    async with runtime(request).db.sessions() as session:
        rules = await all_delivery_rules(session, owner.id)
    return {agent_id: value.model_dump(mode="json") for agent_id, value in rules.items()}


@router.get("/{agent_id}/notifications")
async def get_rules(request: Request, agent_id: str, owner: OwnerIdentity = Depends(require_owner)):
    async with runtime(request).db.sessions() as session:
        await owned_agent(session, owner.id, agent_id)
        return (await delivery_rules(session, owner.id, agent_id)).model_dump(mode="json")


@router.put("/{agent_id}/notifications")
async def put_rules(
    request: Request,
    agent_id: str,
    body: AgentDeliveryRulesUpdate,
    owner: OwnerIdentity = Depends(require_owner),
):
    async with runtime(request).db.sessions() as session, session.begin():
        rules = await set_delivery_rules(session, owner.id, agent_id, body)
    return rules.model_dump(mode="json")
