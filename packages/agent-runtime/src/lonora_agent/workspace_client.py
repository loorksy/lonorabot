"""Fixed Unix-socket transport; it never exposes Docker to application services."""

import asyncio
import json
import re
from pathlib import Path
from typing import Any, cast

import httpx
from lonora_core.user_error import LonoraError

from .workspace import (
    MAX_OUTPUT_BYTES,
    MAX_TRANSFER_BYTES,
    WorkspaceResult,
    encode_snapshot,
    read_snapshot,
)


class WorkspaceClient:
    def __init__(self, socket: Path) -> None:
        if not socket.is_absolute():
            raise LonoraError("workspace_socket_invalid", 500)
        self.socket = socket

    async def profile(self) -> str:
        try:
            async with (
                asyncio.timeout(5),
                httpx.AsyncClient(
                    transport=httpx.AsyncHTTPTransport(uds=str(self.socket)),
                    trust_env=False,
                    timeout=5,
                    follow_redirects=False,
                ) as client,
            ):
                async with client.stream("GET", "http://workspace.local/profile") as response:
                    if response.status_code != 200:
                        raise LonoraError("workspace_profile_unavailable", 503)
                    body = bytearray()
                    async for block in response.aiter_bytes(chunk_size=1024):
                        body.extend(block)
                        if len(body) > 1024:
                            raise LonoraError("workspace_profile_invalid", 502)
        except (TimeoutError, httpx.HTTPError):
            raise LonoraError("workspace_profile_unavailable", 503) from None
        try:
            raw: object = json.loads(body)
            if not isinstance(raw, dict):
                raise ValueError()
            value = cast(dict[str, Any], raw)
            image = value.get("image")
            if set(value) != {"image"} or not isinstance(image, str):
                raise ValueError()
            if not re.fullmatch(r"sha256:[0-9a-f]{64}", image):
                raise ValueError()
            return image
        except (ValueError, TypeError, RecursionError):
            raise LonoraError("workspace_profile_invalid", 502) from None

    async def execute(
        self,
        command: str,
        files: dict[str, bytes] | None = None,
        *,
        deadline_seconds: float = 30,
        expected_image: str | None = None,
    ) -> WorkspaceResult:
        if expected_image is not None and not re.fullmatch(r"sha256:[0-9a-f]{64}", expected_image):
            raise LonoraError("workspace_profile_invalid", 422)
        payload = {
            "command": command,
            "deadline_seconds": deadline_seconds,
            "snapshot": json.loads(encode_snapshot(files or {})),
        }
        if expected_image is not None:
            payload["expected_image"] = expected_image
        try:
            async with httpx.AsyncClient(
                transport=httpx.AsyncHTTPTransport(uds=str(self.socket)),
                trust_env=False,
                timeout=60,
                follow_redirects=False,
            ) as client:
                async with client.stream(
                    "POST", "http://workspace.local/execute", json=payload
                ) as response:
                    body = bytearray()
                    async for block in response.aiter_bytes():
                        body.extend(block)
                        if len(body) > MAX_TRANSFER_BYTES:
                            raise LonoraError("workspace_response_too_large", 502)
                    if response.status_code == 429:
                        raise LonoraError("workspace_busy", 409)
                    if response.status_code != 200:
                        # Host errors contain only controlled codes, never raw
                        # daemon messages. Still validate instead of trusting IPC.
                        try:
                            failure: object = json.loads(body)
                            code = (
                                cast(dict[str, Any], failure).get("code")
                                if isinstance(failure, dict)
                                else None
                            )
                        except ValueError:
                            code = None
                        if isinstance(code, str) and re.fullmatch(r"workspace_[a-z_]{1,60}", code):
                            raise LonoraError(code, 409)
                        raise LonoraError("workspace_backend_unavailable", 503)
        except httpx.HTTPError:
            # No automatic transport retry: the host might already be running
            # the command. The durable operation is settled without publication.
            raise LonoraError("workspace_execution_uncertain", 503) from None
        try:
            raw: object = json.loads(body)
            if not isinstance(raw, dict):
                raise ValueError()
            result = cast(dict[str, Any], raw)
            if (
                type(result.get("exit_code")) is not int
                or not -255 <= result["exit_code"] <= 255
                or not isinstance(result.get("stdout"), str)
                or not isinstance(result.get("stderr"), str)
                or len(result["stdout"].encode()) > MAX_OUTPUT_BYTES * 3
                or len(result["stderr"].encode()) > MAX_OUTPUT_BYTES * 3
                or not isinstance(result.get("image"), str)
                or not re.fullmatch(r"sha256:[0-9a-f]{64}", result["image"])
            ):
                raise ValueError()
            snapshot = read_snapshot(json.dumps(result["snapshot"]).encode())
            if expected_image is not None and result["image"] != expected_image:
                raise LonoraError("workspace_profile_changed", 409)
            return WorkspaceResult(
                result["exit_code"], result["stdout"], result["stderr"], snapshot, result["image"]
            )
        except (ValueError, TypeError, KeyError, RecursionError):
            raise LonoraError("workspace_response_invalid", 502) from None
