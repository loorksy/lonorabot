"""The admission timings are correlated numeric metadata, never message context."""

import httpx
import pytest
from fastapi import FastAPI, Request
from lonora_api.middleware.request_id import RequestIdMiddleware
from lonora_logging.context import request_id


@pytest.mark.asyncio
async def test_message_admission_exposes_separate_stages_with_existing_request_identity():
    app = FastAPI()
    app.add_middleware(RequestIdMiddleware)
    observed: list[str | None] = []

    @app.post("/api/threads/{thread_id}/messages")
    async def admit(request: Request, thread_id: str):
        observed.append(request_id.get())
        request.state.auth_ms = 2.5
        request.state.message_db_ms = 3.25
        return {"thread": thread_id}

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app), base_url="https://lonora.test"
    ) as client:
        response = await client.post(
            "/api/threads/conversation/messages", headers={"X-Request-Id": "client-send-123"}
        )
    assert response.status_code == 200
    assert response.headers["x-request-id"] == "client-send-123"
    timings = dict(
        (name, float(duration))
        for name, duration in (
            item.strip().split(";dur=") for item in response.headers["server-timing"].split(",")
        )
    )
    assert timings["api"] >= 0 and timings["auth"] == 2.5 and timings["message_db"] == 3.25
    assert observed == ["client-send-123"] and request_id.get() is None
