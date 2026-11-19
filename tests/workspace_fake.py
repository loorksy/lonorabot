"""A stand-in for the workspace supervisor's file routes, for tool tests without a container.
Paths are kept per agent as the tools send them (relative paths are the agent's home)."""

import base64
import json
import shlex
from collections.abc import Callable
from typing import Any

import httpx
from lonora_workspace.client import WorkspaceClient

BOOT = "boot-test"


Ran = dict[str, Any]


class FakeWorkspace:
    """`run` answers a directory listing (`cd -- DIR && find ...`, as "size path" lines)
    and `rm -rf -- DIR` from the files, and any other command through `commands`
    (default: exit 0, no output)."""

    def __init__(self, commands: Callable[[str, str], Ran] | None = None) -> None:
        self.files: dict[tuple[str, str], bytes] = {}
        self.commands = commands
        self.ran: list[tuple[str, str]] = []

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
        if request.url.path == "/v1/run":
            agent, command = str(body["agent_id"]), str(body["command"])
            self.ran.append((agent, command))
            if "cd -- " in command and "find . " in command:
                directory = shlex.split(command.split("cd -- ", 1)[1].split(" && ", 1)[0])[0]
                prefix = directory.rstrip("/") + "/"
                listed = sorted(
                    (path[len(prefix) :], len(body))
                    for (owner, path), body in self.files.items()
                    if owner == agent
                    and path.startswith(prefix)
                    # find prunes __pycache__ and every dot-name, file or directory.
                    and "__pycache__" not in path[len(prefix) :].split("/")[:-1]
                    and not any(part.startswith(".") for part in path[len(prefix) :].split("/"))
                )
                if not any(owner == agent and p.startswith(prefix) for owner, p in self.files):
                    result: Ran = {"exit_code": 1, "stderr": "No such file or directory"}
                else:
                    result = {
                        "exit_code": 0,
                        "stdout": "".join(f"{size} {name}\n" for name, size in listed),
                    }
            elif command.startswith("rm -rf -- "):
                prefix = shlex.split(command)[3].rstrip("/") + "/"
                for key in [
                    key for key in self.files if key[0] == agent and key[1].startswith(prefix)
                ]:
                    del self.files[key]
                result = {"exit_code": 0}
            else:
                result = self.commands(agent, command) if self.commands else {"exit_code": 0}
            return httpx.Response(
                200,
                json={"boot_id": BOOT, "stdout": "", "stderr": "", "timed_out": False, **result},
            )
        if request.url.path == "/v1/health":
            return httpx.Response(200, json={"boot_id": BOOT, "ok": True})
        return httpx.Response(404, json={"code": "not_found"})
