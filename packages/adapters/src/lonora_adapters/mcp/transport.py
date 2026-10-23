import asyncio
import json
from typing import Any, Protocol, cast

import httpx
from lonora_core.user_error import LonoraError
from lonora_security.network import validate_public_url

MAX_RESPONSE_BYTES = 2 * 1024 * 1024
REQUEST_TIMEOUT_SECONDS = 30


class McpTransport(Protocol):
    async def request(self, payload: dict[str, Any]) -> dict[str, Any]: ...
    async def close(self) -> None: ...


def decode_response(raw: bytes) -> dict[str, Any]:
    try:
        result = json.loads(raw)
    except (ValueError, UnicodeError, RecursionError):
        raise LonoraError("mcp_response_invalid", 502) from None
    if not isinstance(result, dict):
        raise LonoraError("mcp_response_invalid", 502)
    return cast(dict[str, Any], result)


class HttpMcpTransport:
    def __init__(self, url: str, token: str | None = None):
        self.url, self.token, self.session_id = url, token, None
        self.client = httpx.AsyncClient(timeout=REQUEST_TIMEOUT_SECONDS, follow_redirects=False)

    async def request(self, payload: dict[str, Any]) -> dict[str, Any]:
        try:
            async with asyncio.timeout(REQUEST_TIMEOUT_SECONDS):
                return await self._request(payload)
        except (TimeoutError, httpx.TimeoutException):
            raise LonoraError("mcp_connection_timeout", 504) from None
        except httpx.HTTPError:
            raise LonoraError("mcp_connection_failed", 502) from None

    async def _request(self, payload: dict[str, Any]) -> dict[str, Any]:
        await validate_public_url(self.url)
        headers = {
            "Accept": "application/json, text/event-stream",
            # The response limit applies before any decompressor can allocate
            # an unbounded expanded chunk. Compression is not supported here.
            "Accept-Encoding": "identity",
            "MCP-Protocol-Version": "2025-06-18",
        }
        if self.token:
            headers["Authorization"] = "Bearer " + self.token
        if self.session_id:
            headers["Mcp-Session-Id"] = self.session_id
        async with self.client.stream("POST", self.url, headers=headers, json=payload) as response:
            if response.status_code >= 300:
                raise LonoraError("mcp_request_failed", 502)
            if response.headers.get("Content-Encoding", "identity").strip().casefold() not in {
                "",
                "identity",
            }:
                raise LonoraError("mcp_response_encoding_unsupported", 502)
            session_id = response.headers.get("Mcp-Session-Id", self.session_id)
            if session_id is not None and (
                len(session_id) > 256
                or any(ord(char) < 33 or ord(char) > 126 for char in session_id)
            ):
                raise LonoraError("mcp_response_invalid", 502)
            self.session_id = session_id
            if response.status_code == 202 and "id" not in payload:
                return {}
            raw = bytearray()
            received = 0
            is_sse = "text/event-stream" in response.headers.get("Content-Type", "")
            # Preserve SSE event latency; buffering to a fixed chunk size can
            # wait forever after a complete event on a still-open stream.
            async for chunk in response.aiter_bytes():
                received += len(chunk)
                if received > MAX_RESPONSE_BYTES:
                    raise LonoraError("mcp_response_too_large", 502)
                raw.extend(chunk)
                if is_sse:
                    normalized = bytes(raw).replace(b"\r\n", b"\n")
                    while b"\n\n" in normalized:
                        event, normalized = normalized.split(b"\n\n", 1)
                        result = self._sse_response(event, payload.get("id"))
                        if result is not None:
                            return result
                    raw = bytearray(normalized)
            if is_sse:
                raise LonoraError("mcp_response_missing", 502)
            return decode_response(bytes(raw))

    @staticmethod
    def _sse_response(raw: bytes, request_id: Any) -> dict[str, Any] | None:
        try:
            contents = raw.decode("utf-8")
        except UnicodeError:
            raise LonoraError("mcp_response_invalid", 502) from None
        data = [line[5:].lstrip() for line in contents.splitlines() if line.startswith("data:")]
        if data:
            result = decode_response("\n".join(data).encode())
            if result.get("id") == request_id:
                return result
        return None

    async def close(self) -> None:
        await self.client.aclose()


class StdioMcpTransport:
    def __init__(self, command: list[str]):
        # Owner/imported commands cannot run as the Gateway UID. Do not restore
        # this transport until a separately authorized isolated host exists.
        raise LonoraError("mcp_stdio_isolation_required", 403)

    async def request(self, payload: dict[str, Any]) -> dict[str, Any]:
        raise LonoraError("mcp_stdio_isolation_required", 403)

    async def close(self) -> None:
        pass
