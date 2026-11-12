"""The Gateway's client of the workspace supervisor.

Every answer is decoded through one `SecretScan` before anything else sees it: command
output, file contents, process lists and job command lines alike (7.2.6; map Q11 (b)).
A file whose bytes are returned raw (an export) is refused when it carries a secret,
because bytes cannot be rewritten.
"""

import base64
import os
from typing import Any

import httpx
from lonora_core.user_error import LonoraError
from lonora_security.secrets import SecretScan

SOCKET = "/run/lonora-workspace/supervisor.sock"


class WorkspaceClient:
    def __init__(
        self, socket_path: str = SOCKET, transport: httpx.AsyncBaseTransport | None = None
    ):
        self.socket_path = None if transport else socket_path
        self.transport = transport or httpx.AsyncHTTPTransport(uds=socket_path, retries=0)

    def present(self) -> bool:
        """Whether the supervisor's socket is there (presentation only)."""
        return self.socket_path is None or os.path.exists(self.socket_path)

    async def _call(
        self, method: str, path: str, body: dict[str, Any] | None, seconds: float
    ) -> dict[str, Any]:
        async with httpx.AsyncClient(
            transport=self.transport, base_url="http://workspace", timeout=seconds
        ) as client:
            try:
                response = await client.request(method, path, json=body)
            except httpx.TransportError:
                raise LonoraError("workspace_unavailable", 503) from None
        if response.status_code == 422 or response.status_code == 503:
            code = response.json().get("code") if response.content else None
            raise LonoraError(str(code or "workspace_request_invalid"), response.status_code)
        if response.status_code != 200:
            raise LonoraError("workspace_unavailable", 503)
        value = response.json()
        if not isinstance(value, dict):
            raise LonoraError("workspace_unavailable", 503)
        return value  # pyright: ignore[reportUnknownVariableType]

    async def run(
        self,
        scan: SecretScan,
        agent_id: str,
        command: str,
        *,
        background: bool = False,
        timeout_seconds: float | None = None,
        secrets: dict[str, str] | None = None,
        agent_token: str | None = None,
    ) -> dict[str, Any]:
        body: dict[str, Any] = {"agent_id": agent_id, "command": command, "background": background}
        if timeout_seconds is not None:
            body["timeout_seconds"] = timeout_seconds
        if secrets:
            body["secrets"] = secrets
        if agent_token:
            body["agent_token"] = agent_token
        # The supervisor bounds the command itself; the transport waits a little longer.
        wait = (timeout_seconds or 600) + 30 if not background else 60
        return scan.data(await self._call("POST", "/v1/run", body, wait))

    async def processes(self, scan: SecretScan) -> dict[str, Any]:
        return scan.data(await self._call("GET", "/v1/processes", None, 30))

    async def stop(self, scan: SecretScan, pid: int) -> dict[str, Any]:
        return scan.data(await self._call("POST", "/v1/processes/stop", {"pid": pid}, 30))

    async def stop_all(self, scan: SecretScan, agent_id: str | None = None) -> dict[str, Any]:
        body = {"agent_id": agent_id} if agent_id else {}
        return scan.data(await self._call("POST", "/v1/processes/stop-all", body, 30))

    async def read_text(
        self, scan: SecretScan, agent_id: str, path: str, offset: int, limit: int
    ) -> dict[str, Any]:
        """A slice of a file as text, with every secret form replaced."""
        value = await self._call(
            "POST",
            "/v1/files/read",
            {"agent_id": agent_id, "path": path, "offset": offset, "limit": limit},
            90,
        )
        if not value.get("ok"):
            return scan.data({"ok": False, "error": value.get("error", "")})
        data = base64.b64decode(value["content_base64"])
        return {
            "ok": True,
            "path": scan.text(path),
            "size": value["size"],
            "offset": value["offset"],
            "truncated": value["truncated"],
            "binary": b"\0" in data,
            "content": scan.text(data.decode("utf-8", "replace")),
        }

    async def read_bytes(self, scan: SecretScan, agent_id: str, path: str) -> bytes:
        """A whole file's bytes (an export). Refused when they carry a secret."""
        value = await self._call("POST", "/v1/files/read", {"agent_id": agent_id, "path": path}, 90)
        if not value.get("ok"):
            raise LonoraError("workspace_file_unreadable", 404)
        if value["truncated"]:
            raise LonoraError("workspace_file_too_large", 413)
        data = base64.b64decode(value["content_base64"])
        if scan.found(data) or scan.text(data.decode("utf-8", "replace")) != data.decode(
            "utf-8", "replace"
        ):
            raise LonoraError("workspace_file_holds_secret", 409)
        return data

    async def write(
        self, scan: SecretScan, agent_id: str, path: str, data: bytes, *, append: bool = False
    ) -> dict[str, Any]:
        body = {
            "agent_id": agent_id,
            "path": path,
            "content_base64": base64.b64encode(data).decode(),
            "append": append,
        }
        return scan.data(await self._call("POST", "/v1/files/write", body, 90))
