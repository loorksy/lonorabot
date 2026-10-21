"""Offline bounds, error and concurrency checks for the local execution bridge."""

import asyncio
import json
from pathlib import Path
from typing import Any
from unittest.mock import patch

import httpx
import pytest
from lonora_agent.workspace import MAX_TRANSFER_BYTES, AnalyticalContainer, WorkspaceResult
from lonora_agent.workspace_client import WorkspaceClient
from lonora_agent.workspace_host import create_host
from lonora_core.user_error import LonoraError

IMAGE = "sha256:" + "a" * 64
PAYLOAD: dict[str, Any] = {"command": "analysis", "snapshot": {}, "deadline_seconds": 30}


class ScriptedContainer(AnalyticalContainer):
    def __init__(self) -> None:
        super().__init__(IMAGE)
        self.calls = 0
        self.started = asyncio.Event()
        self.release = asyncio.Event()

    async def execute(
        self, command: str, files: dict[str, bytes] | None = None, *, deadline_seconds: float = 30
    ) -> WorkspaceResult:
        self.calls += 1
        if command == "wait":
            self.started.set()
            await self.release.wait()
        if command == "private-error":
            raise RuntimeError("fake-private-credential-must-not-escape")
        return WorkspaceResult(0, "computed", "", files or {}, IMAGE)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "payload",
    [
        [],
        None,
        {},
        {**PAYLOAD, "image": "evil"},
        {**PAYLOAD, "command": []},
        {**PAYLOAD, "command": ""},
        {**PAYLOAD, "command": "x\x00y"},
        {**PAYLOAD, "deadline_seconds": True},
        {**PAYLOAD, "deadline_seconds": 46},
        {**PAYLOAD, "snapshot": {"../secret": "YQ=="}},
    ],
)
async def test_host_rejects_invalid_or_privilege_changing_requests(payload: object) -> None:
    backend = ScriptedContainer()
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(create_host(backend)), base_url="http://workspace.local"
    ) as client:
        result = await client.post("/execute", json=payload)
        assert result.status_code == 422
        assert backend.calls == 0


@pytest.mark.asyncio
async def test_host_bounds_body_and_hides_unexpected_exception(
    caplog: pytest.LogCaptureFixture,
) -> None:
    backend = ScriptedContainer()
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(create_host(backend)), base_url="http://workspace.local"
    ) as client:
        oversized = await client.post("/execute", content=b"x" * (MAX_TRANSFER_BYTES + 1))
        assert oversized.status_code == 413 and backend.calls == 0
        failed = await client.post("/execute", json={**PAYLOAD, "command": "private-error"})
        assert failed.status_code == 503
        assert "fake-private-credential" not in failed.text + caplog.text
        assert "RuntimeError" in caplog.text
        recovered = await client.post("/execute", json=PAYLOAD)
        assert recovered.status_code == 200, "Invalid requests leaked a concurrency slot"


@pytest.mark.asyncio
async def test_host_has_bounded_concurrency_without_unbounded_queue() -> None:
    backend = ScriptedContainer()
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(create_host(backend, 1)), base_url="http://workspace.local"
    ) as client:
        task = asyncio.create_task(client.post("/execute", json={**PAYLOAD, "command": "wait"}))
        await asyncio.wait_for(backend.started.wait(), 2)
        refused = await client.post("/execute", json=PAYLOAD)
        assert refused.status_code == 429 and backend.calls == 1
        backend.release.set()
        assert (await task).status_code == 200


@pytest.mark.asyncio
async def test_client_uses_fixed_protocol_and_validates_real_file_bytes() -> None:
    def request(message: httpx.Request) -> httpx.Response:
        assert message.url == "http://workspace.local/execute"
        assert json.loads(message.content) == {
            "command": "analysis",
            "deadline_seconds": 30,
            "snapshot": {"input": "ZGF0YQ=="},
        }
        return httpx.Response(
            200,
            json={
                "exit_code": 7,
                "stdout": "actual output",
                "stderr": "actual error",
                "image": IMAGE,
                "snapshot": {"result": "Y29tcHV0ZWQ="},
            },
        )

    with patch(
        "lonora_agent.workspace_client.httpx.AsyncHTTPTransport",
        return_value=httpx.MockTransport(request),
    ) as transport:
        result = await WorkspaceClient(Path("/run/analysis/host.sock")).execute(
            "analysis", {"input": b"data"}
        )
    transport.assert_called_once_with(uds="/run/analysis/host.sock")
    assert result.exit_code == 7 and result.files == {"result": b"computed"}


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "body",
    [
        None,
        [],
        {},
        {"exit_code": True},
        {"exit_code": 0, "stdout": "", "stderr": "", "image": "mutable:latest", "snapshot": {}},
    ],
)
async def test_client_rejects_invalid_success_responses(body: object) -> None:
    with patch(
        "lonora_agent.workspace_client.httpx.AsyncHTTPTransport",
        return_value=httpx.MockTransport(lambda request: httpx.Response(200, json=body)),
    ):
        with pytest.raises(LonoraError, match="workspace_response_invalid"):
            await WorkspaceClient(Path("/run/analysis/host.sock")).execute("analysis")


@pytest.mark.asyncio
async def test_client_never_retries_an_uncertain_command() -> None:
    calls = 0

    def timeout(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        raise httpx.ReadTimeout("private upstream details", request=request)

    with patch(
        "lonora_agent.workspace_client.httpx.AsyncHTTPTransport",
        return_value=httpx.MockTransport(timeout),
    ):
        with pytest.raises(LonoraError, match="workspace_execution_uncertain"):
            await WorkspaceClient(Path("/run/analysis/host.sock")).execute("analysis")
    assert calls == 1


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "status,body,code",
    [
        (429, {}, "workspace_busy"),
        (503, {"code": "workspace_timeout"}, "workspace_timeout"),
        (503, [], "workspace_backend_unavailable"),
        (503, {"code": "private-token-here"}, "workspace_backend_unavailable"),
    ],
)
async def test_client_error_diagnostics_do_not_forward_arbitrary_text(
    status: int, body: object, code: str
) -> None:
    with patch(
        "lonora_agent.workspace_client.httpx.AsyncHTTPTransport",
        return_value=httpx.MockTransport(lambda request: httpx.Response(status, json=body)),
    ):
        with pytest.raises(LonoraError, match=code):
            await WorkspaceClient(Path("/run/analysis/host.sock")).execute("analysis")
