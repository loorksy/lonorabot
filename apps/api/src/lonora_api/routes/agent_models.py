"""The owner's model choice per Agent: Automatic (Lonora chooses) or Fixed (one model).

It orders models and never grants authority; changing it repeats nothing.
"""

from datetime import timedelta
from typing import Any

from fastapi import APIRouter, Depends, Request
from lonora_auth.identity import OwnerIdentity
from lonora_contracts.domain import utcnow
from lonora_contracts.model_routing import AgentModelChange, AgentModelRecord, Capability
from lonora_core.user_error import LonoraError
from lonora_db.agent_models import (
    agent_model_record,
    allowed_models,
    catalog_models,
    change_agent_model,
)
from lonora_db.model_cards import model_label
from lonora_db.usage import agent_usage
from lonora_providers.credentials import ProviderCredentials
from lonora_providers.registry import PROVIDERS

from ..middleware.auth import require_owner, runtime

router = APIRouter(prefix="/agents")
USAGE_DAYS = 30


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


@router.get("/{agent_id}/model/summary")
async def summary(
    request: Request, agent_id: str, owner: OwnerIdentity = Depends(require_owner)
) -> dict[str, Any]:
    """Everything the model card shows: the choice, the model answering now, the allowed
    models, the models a Fixed choice can pick, and this agent's usage."""
    rt = runtime(request)
    services = rt.services(owner.id)
    async with rt.db.sessions() as session:
        await agent_model_record(session, owner.id, agent_id)  # 404 for another owner's
    credentials = ProviderCredentials(rt.db, services.secrets)
    connected = [provider for provider in PROVIDERS if await credentials.configured(provider)]
    try:
        route = await services.router.route(
            Capability.CONVERSATION, owner_id=owner.id, agent_id=agent_id
        )
        current = route.choices[0]
    except LonoraError as error:
        if error.code != "model_not_configured":
            raise
        current = None
    since = utcnow() - timedelta(days=USAGE_DAYS)
    async with rt.db.sessions() as session:
        record = await agent_model_record(session, owner.id, agent_id)
        allowed = await allowed_models(session)
        available = await catalog_models(session, connected)
        usage = await agent_usage(session, owner.id, since, agent_id)
        return {
            "record": record.model_dump(mode="json"),
            "current": await model_label(session, current),
            "allowed": [await model_label(session, item) for item in allowed],
            "available": available,
            "connected_providers": connected,
            "usage": {
                "days": USAGE_DAYS,
                "requests": usage[0]["requests"] if usage else 0,
                "input_tokens": usage[0]["input_tokens"] if usage else 0,
                "output_tokens": usage[0]["output_tokens"] if usage else 0,
                "cached_tokens": usage[0]["cached_tokens"] if usage else 0,
                "models": usage[0]["models"] if usage else [],
            },
        }
