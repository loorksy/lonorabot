"""GPT-Live REST negotiation and server-side event attachment (OpenAI Live API)."""

import json
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from typing import Any
from urllib.parse import quote

import httpx
from lonora_core.user_error import LonoraError
from websockets.asyncio.client import ClientConnection, connect


class OpenAILiveAdapter:
    def __init__(self, api_key: str, client: httpx.AsyncClient | None = None):
        self.api_key = api_key
        self.client = client

    async def create(self, configuration: dict[str, Any], sdp: str) -> dict[str, Any]:
        client = self.client or httpx.AsyncClient(timeout=25)
        try:
            response = await client.post(
                "https://api.openai.com/v1/live/sessions",
                headers={"Authorization": "Bearer " + self.api_key},
                json={"session": configuration, "transport": {"type": "webrtc", "sdp": sdp}},
            )
            if response.status_code in {401, 403}:
                raise LonoraError("model_credentials_rejected", 409)
            if response.status_code == 429:
                raise LonoraError("model_rate_limited", 429)
            if response.status_code == 404:
                raise LonoraError("voice_model_unavailable", 409)
            if not response.is_success:
                raise LonoraError("voice_connection_failed", 502)
            value: dict[str, Any] = response.json()
            if not isinstance(value.get("session"), dict) or not isinstance(
                value.get("transport"), dict
            ):
                raise LonoraError("voice_response_invalid", 502)
            if not isinstance(value["session"].get("id"), str) or not isinstance(
                value["transport"].get("sdp"), str
            ):
                raise LonoraError("voice_response_invalid", 502)
            return value
        except (httpx.HTTPError, ValueError):
            raise LonoraError("voice_connection_failed", 502) from None
        finally:
            if self.client is None:
                await client.aclose()

    @asynccontextmanager
    async def attach(self, session_id: str) -> AsyncGenerator[ClientConnection]:
        try:
            async with connect(
                "wss://api.openai.com/v1/live/sessions/" + quote(session_id, safe="") + "/attach",
                additional_headers={"Authorization": "Bearer " + self.api_key},
                open_timeout=20,
                max_size=2**20,
            ) as connection:
                yield connection
        except OSError:
            raise LonoraError("voice_connection_failed", 502) from None

    async def close_session(self, session_id: str) -> bool:
        """Drain final usage on the documented sideband; no guessed DELETE API."""
        import asyncio

        try:
            async with self.attach(session_id) as connection:
                await connection.send(json.dumps({"type": "session.close"}))
                async with asyncio.timeout(5):
                    async for raw in connection:
                        event = json.loads(raw)
                        if event.get("type") == "session.closed":
                            return True
        except Exception:
            return False
        return False
