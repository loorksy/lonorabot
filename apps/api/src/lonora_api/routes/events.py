import json
from collections.abc import AsyncIterator
from typing import Any

from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import StreamingResponse
from lonora_auth.identity import OwnerIdentity
from lonora_bus.durable_events import stream_events
from lonora_db.events import event_data, events_after

from ..middleware.auth import require_owner, runtime

router = APIRouter(prefix="/events")


@router.get("")
async def events(
    request: Request,
    cursor: int = Query(default=0, ge=0),
    thread_id: str | None = None,
    owner: OwnerIdentity = Depends(require_owner),
) -> list[dict[str, Any]]:
    async with runtime(request).db.sessions() as session:
        return [event_data(row) for row in await events_after(session, owner.id, cursor, thread_id)]


@router.get("/stream")
async def stream(
    request: Request, cursor: int = 0, owner: OwnerIdentity = Depends(require_owner)
) -> StreamingResponse:
    async def lines() -> AsyncIterator[str]:
        async for event in stream_events(runtime(request).db, owner.id, cursor):
            if await request.is_disconnected():
                break
            yield (
                "id: "
                + str(event["cursor"])
                + "\ndata: "
                + json.dumps(event, ensure_ascii=False)
                + "\n\n"
            )

    return StreamingResponse(
        lines(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
