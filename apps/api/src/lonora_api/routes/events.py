import asyncio
import json
from collections.abc import AsyncGenerator
from time import monotonic
from typing import Any

from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import StreamingResponse
from lonora_auth.identity import OwnerIdentity
from lonora_auth.sessions import read_session
from lonora_bus.durable_events import stream_events
from lonora_core.user_error import LonoraError
from lonora_db.events import current_event_cursor, event_data, events_after

from ..middleware.auth import require_owner, runtime

router = APIRouter(prefix="/events")
AUTH_REFRESH_SECONDS = 5
KEEPALIVE_SECONDS = 10
MAX_CURSOR = 2**63 - 1


@router.get("")
async def events(
    request: Request,
    cursor: int = Query(default=0, ge=0),
    thread_id: str | None = None,
    owner: OwnerIdentity = Depends(require_owner),
) -> list[dict[str, Any]]:
    async with runtime(request).db.sessions() as session:
        return [event_data(row) for row in await events_after(session, owner.id, cursor, thread_id)]


def resume_cursor(request: Request, cursor: int) -> int:
    value = request.headers.get("last-event-id")
    if value is None:
        return cursor
    try:
        resumed = int(value)
    except ValueError:
        raise LonoraError("event_cursor_invalid", 400) from None
    if not 0 <= resumed <= MAX_CURSOR:
        raise LonoraError("event_cursor_invalid", 400)
    return max(cursor, resumed)


async def event_lines(request: Request, owner_id: str, cursor: int) -> AsyncGenerator[str, None]:
    """Flush readiness immediately and keep an idle stream live and revocable."""
    rt = runtime(request)
    authorization = request.headers.get("authorization", "")
    token = (
        authorization[7:]
        if authorization.lower().startswith("bearer ")
        else request.cookies.get("lonora_session")
    )
    # On first live mount, the baseline was captured before this frame. The
    # client refreshes canonical snapshots only after receiving readiness.
    yield f"id: {cursor}\nevent: ready\ndata: {json.dumps({'cursor': cursor})}\n\n"
    iterator = stream_events(rt.db, owner_id, cursor)
    pending = asyncio.create_task(anext(iterator))
    next_auth, next_ping = monotonic() + AUTH_REFRESH_SECONDS, monotonic() + KEEPALIVE_SECONDS
    try:
        while True:
            if await request.is_disconnected():
                return
            now = monotonic()
            if now >= next_auth:
                try:
                    async with rt.db.sessions() as session:
                        identity = await read_session(session, token)
                    if identity.id != owner_id:
                        return
                except LonoraError:
                    return
                next_auth = monotonic() + AUTH_REFRESH_SECONDS
            if now >= next_ping:
                yield ": keepalive\n\n"
                next_ping = monotonic() + KEEPALIVE_SECONDS
            timeout = max(0.01, min(next_auth, next_ping) - monotonic())
            done, _ = await asyncio.wait({pending}, timeout=timeout)
            if pending not in done:
                continue
            try:
                event = pending.result()
            except StopAsyncIteration:
                return
            yield (
                "id: "
                + str(event["cursor"])
                + "\ndata: "
                + json.dumps(event, ensure_ascii=False)
                + "\n\n"
            )
            pending = asyncio.create_task(anext(iterator))
    finally:
        pending.cancel()
        await asyncio.gather(pending, return_exceptions=True)
        await iterator.aclose()


@router.get("/stream")
async def stream(
    request: Request,
    cursor: int = Query(default=0, ge=0, le=MAX_CURSOR),
    live: bool = False,
    owner: OwnerIdentity = Depends(require_owner),
) -> StreamingResponse:
    cursor = resume_cursor(request, cursor)
    if live and cursor == 0 and request.headers.get("last-event-id") is None:
        async with runtime(request).db.sessions() as session:
            cursor = await current_event_cursor(session, owner.id)
    return StreamingResponse(
        event_lines(request, owner.id, cursor),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache, no-transform", "X-Accel-Buffering": "no"},
    )
