"""A stand-in for the workspace supervisor's file routes, for tool tests without a container.
Paths are kept per agent as the tools send them (relative paths are the agent's home)."""

import base64
import json
from typing import Any

import httpx
from lonora_workspace.client import WorkspaceClient

BOOT = "boot-test"


class FakeWorkspace:
    def __init__(self) -> None:
        self.files: dict[tuple[str, str], bytes] = {}

    def client(self) -> WorkspaceClient:
        return WorkspaceClient(transport=httpx.MockTransport(self.handle))

    def handle(self, request: httpx.Request) -> httpx.Response:
        body: dict[str, Any] = json.loads(request.content or b"{}")
        key = (str(body.get("agent_id")), str(body.get("path")))
        if request.url.path == "/v1/files/write":
            data = base64.b64decode(body["content_base64"])
            self.files[key] = (self.files.get(key, b"") if body.get("append") else b"") + data
            return httpx.Response(200, json={"boot_id": BOOT, "ok": True, "written": len(data)})
        if request.url.path == "/v1/files/read":
            if key not in self.files:
                return httpx.Response(200, json={"boot_id": BOOT, "ok": False, "error": "missing"})
            data = self.files[key]
            offset = int(body.get("offset", 0))
            limit = int(body.get("limit", 2 * 1024 * 1024))
            part = data[offset : offset + limit]
            return httpx.Response(
                200,
                json={
                    "boot_id": BOOT,
                    "ok": True,
                    "size": len(data),
                    "offset": offset,
                    "content_base64": base64.b64encode(part).decode(),
                    "truncated": offset + len(part) < len(data),
                },
            )
        if request.url.path == "/v1/health":
            return httpx.Response(200, json={"boot_id": BOOT, "ok": True})
        return httpx.Response(404, json={"code": "not_found"})
