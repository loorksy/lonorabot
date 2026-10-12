import asyncio
import json
import os
from typing import Any, Protocol

import httpx
from lonora_core.user_error import LonoraError
from lonora_security.network import validate_public_url


class McpTransport(Protocol):
    async def request(self, payload: dict[str, Any]) -> dict[str, Any]: ...
    async def close(self) -> None: ...


class HttpMcpTransport:
    def __init__(self, url: str, token: str | None = None):
        self.url, self.token, self.session_id = url, token, None
        self.client = httpx.AsyncClient(timeout=30, follow_redirects=False)

    async def request(self, payload: dict[str, Any]) -> dict[str, Any]:
        await validate_public_url(self.url)
        headers = {
            "Accept": "application/json, text/event-stream",
            "MCP-Protocol-Version": "2025-06-18",
        }
        if self.token:
            headers["Authorization"] = "Bearer " + self.token
        if self.session_id:
            headers["Mcp-Session-Id"] = self.session_id
        response = await self.client.post(self.url, headers=headers, json=payload)
        if response.is_error:
            raise LonoraError("mcp_request_failed", 502)
        self.session_id = response.headers.get("Mcp-Session-Id", self.session_id)
        if response.status_code == 202:
            return {}
        if "text/event-stream" in response.headers.get("Content-Type", ""):
            for line in response.text.splitlines():
                if line.startswith("data:"):
                    result = json.loads(line[5:].strip())
                    if result.get("id") == payload.get("id"):
                        return result
            raise LonoraError("mcp_response_missing", 502)
        return response.json()

    async def close(self) -> None:
        await self.client.aclose()


class StdioMcpTransport:
    def __init__(self, command: list[str]):
        if not command:
            raise LonoraError("mcp_command_required")
        self.command = command
        self.process: asyncio.subprocess.Process | None = None
        self.lock = asyncio.Lock()

    async def request(self, payload: dict[str, Any]) -> dict[str, Any]:
        async with self.lock:
            if self.process is None:
                env = {
                    name: value
                    for name, value in os.environ.items()
                    if name
                    in {
                        "PATH",
                        "LANG",
                        "HTTP_PROXY",
                        "HTTPS_PROXY",
                        "NO_PROXY",
                        "SSL_CERT_FILE",
                        "REQUESTS_CA_BUNDLE",
                        "NODE_EXTRA_CA_CERTS",
                    }
                }
                self.process = await asyncio.create_subprocess_exec(
                    *self.command,
                    stdin=asyncio.subprocess.PIPE,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.DEVNULL,
                    env=env,
                )
            if self.process.stdin is None or self.process.stdout is None:
                raise LonoraError("mcp_transport_unavailable", 502)
            self.process.stdin.write(json.dumps(payload).encode() + b"\n")
            await self.process.stdin.drain()
            if "id" not in payload:
                return {}
            async with asyncio.timeout(30):
                while True:
                    line = await self.process.stdout.readline()
                    if not line:
                        raise LonoraError("mcp_process_stopped", 502)
                    if len(line) > 2 * 1024 * 1024:
                        raise LonoraError("mcp_response_too_large", 502)
                    value = json.loads(line)
                    if value.get("id") == payload["id"]:
                        return value

    async def close(self) -> None:
        if self.process and self.process.returncode is None:
            self.process.terminate()
            try:
                await asyncio.wait_for(self.process.wait(), 5)
            except TimeoutError:
                self.process.kill()
                await self.process.wait()
