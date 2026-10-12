import json
from typing import Any

from fastapi import APIRouter, Request
from lonora_agent.automation.webhooks import webhook_wake
from lonora_channels.webhook.runtime import verify_signature
from lonora_contracts.runs import RunRequest
from lonora_core.user_error import LonoraError
from lonora_db.owner import get_owner

from ..middleware.auth import runtime

router = APIRouter()


@router.post("/webhook", status_code=202)
async def receive(request: Request) -> dict[str, Any]:
    rt = runtime(request)
    if not rt.settings.webhook_secret:
        raise LonoraError("webhook_not_configured", 409)
    body = await request.body()
    verify_signature(
        body,
        request.headers.get("x-lonora-signature"),
        rt.settings.webhook_secret.get_secret_value(),
    )
    payload = json.loads(body)
    async with rt.db.sessions() as session:
        owner = await get_owner(session)
    if owner is None:
        raise LonoraError("owner_not_initialized", 409)
    return await webhook_wake(
        rt.db, owner.id, RunRequest.model_validate(payload["run"]), str(payload["nonce"])
    )
