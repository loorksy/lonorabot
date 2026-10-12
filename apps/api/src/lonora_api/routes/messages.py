from typing import Any

from fastapi import APIRouter, Depends, Query, Request
from lonora_auth.identity import OwnerIdentity
from lonora_contracts.domain import MessageCreate
from lonora_db.messages import history, message_data, send_message

from ..middleware.auth import require_owner, runtime

router = APIRouter()


@router.get("/threads/{thread_id}/messages")
async def messages(
    request: Request,
    thread_id: str,
    limit: int = Query(default=100, ge=1, le=200),
    before: int | None = None,
    owner: OwnerIdentity = Depends(require_owner),
) -> list[dict[str, Any]]:
    async with runtime(request).db.sessions() as session:
        return [
            message_data(row) for row in await history(session, owner.id, thread_id, limit, before)
        ]


@router.post("/threads/{thread_id}/messages", status_code=202)
async def send(
    request: Request,
    thread_id: str,
    body: MessageCreate,
    owner: OwnerIdentity = Depends(require_owner),
) -> dict[str, Any]:
    async with runtime(request).db.sessions() as session, session.begin():
        return await send_message(session, owner.id, thread_id, body)
