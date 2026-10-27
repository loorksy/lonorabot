import hashlib
import logging
from time import perf_counter
from typing import Any

from fastapi import APIRouter, Depends, Query, Request
from lonora_auth.identity import OwnerIdentity
from lonora_contracts.domain import MessageCreate
from lonora_db.messages import history, message_data, send_message

from ..middleware.auth import require_owner, runtime

router = APIRouter()
log = logging.getLogger("lonora.chat")


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
    started = perf_counter()
    async with runtime(request).db.sessions() as session, session.begin():
        result = await send_message(session, owner.id, thread_id, body)
    duration = round((perf_counter() - started) * 1000, 2)
    request.state.message_db_ms = duration
    # Correlate admission with the existing request/run IDs; user-controlled
    # text, credentials and the raw arbitrary nonce never enter diagnostics.
    nonce = hashlib.sha256(body.client_nonce.encode()).hexdigest()[:16]
    log.info(
        "message_ack message_id=%s nonce_hash=%s runs=%s duplicate=%s db_ms=%.2f",
        result["message"]["id"],
        nonce,
        ",".join(result["run_ids"]),
        result["deduplicated"],
        duration,
    )
    return result
