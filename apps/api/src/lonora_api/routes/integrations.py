from typing import Literal

from fastapi import Depends, Request
from lonora_auth.identity import OwnerIdentity
from lonora_contracts.agent_secrets import SecretCreate
from lonora_contracts.domain import Contract
from lonora_db.schema import IntegrationRow
from lonora_db.transactions import ResourceRepository
from pydantic import Field

from ..middleware.auth import require_owner, runtime
from . import resource_router


class Integration(Contract):
    type: Literal["brave_search", "economic_calendar", "telegram", "webhook"]
    name: str
    url: str | None = None
    secret_id: str | None = None
    enabled: bool = False
    thread_id: str | None = None
    allowed_destinations: list[str] = Field(default_factory=list[str])


class IntegrationRepository(ResourceRepository):
    row_type = IntegrationRow
    payload_model = Integration
    kind = "integrations"


router = resource_router("/integrations", IntegrationRepository())


@router.post("/secrets", status_code=201)
async def secret(
    request: Request, body: SecretCreate, owner: OwnerIdentity = Depends(require_owner)
) -> dict[str, str]:
    secret_id = (
        await runtime(request)
        .services(owner.id)
        .secrets.write(body.name, body.value, "integration")
    )
    return {"id": secret_id}
