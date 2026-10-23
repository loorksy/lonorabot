"""Offline bounds, error and concurrency checks for the local execution bridge."""

import asyncio
import json
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, patch

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
        self,
        command: str,
        files: dict[str, bytes] | None = None,
        *,
        deadline_seconds: float = 30,
        expected_image: str | None = None,
    ) -> WorkspaceResult:
        if expected_image is not None and expected_image != IMAGE:
            raise LonoraError("workspace_profile_changed", 409)
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
        {**PAYLOAD, "expected_image": "mutable:latest"},
        {**PAYLOAD, "expected_image": None},
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


@pytest.mark.asyncio
async def test_profile_reports_fixed_image_without_launching_a_job() -> None:
    backend = ScriptedContainer()
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(create_host(backend)), base_url="http://workspace.local"
    ) as client:
        response = await client.get("/profile")
        assert response.status_code == 200 and response.json() == {"image": IMAGE}
        assert backend.calls == 0
        rejected = await client.post(
            "/execute", json={**PAYLOAD, "expected_image": "sha256:" + "b" * 64}
        )
        assert rejected.status_code == 409
        assert rejected.json() == {"code": "workspace_profile_changed"}
        assert backend.calls == 0
        accepted = await client.post("/execute", json={**PAYLOAD, "expected_image": IMAGE})
        assert accepted.status_code == 200 and backend.calls == 1


@pytest.mark.asyncio
async def test_direct_container_mismatch_fails_before_docker_or_snapshot_access() -> None:
    backend = AnalyticalContainer(IMAGE)
    assert await backend.profile() == IMAGE
    with patch.object(backend, "_docker", AsyncMock()) as docker:
        with pytest.raises(LonoraError, match="workspace_profile_changed"):
            await backend.execute("analysis", expected_image="sha256:" + "b" * 64)
        docker.assert_not_awaited()


@pytest.mark.asyncio
async def test_client_profile_uses_fixed_socket_and_validates_image() -> None:
    def request(message: httpx.Request) -> httpx.Response:
        assert message.method == "GET" and message.url == "http://workspace.local/profile"
        return httpx.Response(200, json={"image": IMAGE})

    with patch(
        "lonora_agent.workspace_client.httpx.AsyncHTTPTransport",
        return_value=httpx.MockTransport(request),
    ) as transport:
        assert await WorkspaceClient(Path("/run/analysis/host.sock")).profile() == IMAGE
    transport.assert_called_once_with(uds="/run/analysis/host.sock")


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "status,body,code",
    [
        (404, {"code": "unknown host"}, "workspace_profile_unavailable"),
        (200, {"image": "mutable:latest"}, "workspace_profile_invalid"),
        (200, {"image": IMAGE, "private": "not accepted"}, "workspace_profile_invalid"),
        (200, [], "workspace_profile_invalid"),
        (200, None, "workspace_profile_invalid"),
        (200, {"image": "x" * 1024}, "workspace_profile_invalid"),
    ],
)
async def test_client_profile_rejects_unconfigured_or_invalid_response(
    status: int, body: object, code: str
) -> None:
    with patch(
        "lonora_agent.workspace_client.httpx.AsyncHTTPTransport",
        return_value=httpx.MockTransport(lambda request: httpx.Response(status, json=body)),
    ):
        with pytest.raises(LonoraError, match=code):
            await WorkspaceClient(Path("/run/analysis/host.sock")).profile()


@pytest.mark.asyncio
async def test_client_pins_execution_and_does_not_accept_a_different_receipt_image() -> None:
    def request(message: httpx.Request) -> httpx.Response:
        assert json.loads(message.content)["expected_image"] == IMAGE
        return httpx.Response(
            200,
            json={
                "exit_code": 0,
                "stdout": "",
                "stderr": "",
                "snapshot": {},
                "image": "sha256:" + "b" * 64,
            },
        )

    with patch(
        "lonora_agent.workspace_client.httpx.AsyncHTTPTransport",
        return_value=httpx.MockTransport(request),
    ):
        with pytest.raises(LonoraError, match="workspace_profile_changed"):
            await WorkspaceClient(Path("/run/analysis/host.sock")).execute(
                "analysis", expected_image=IMAGE
            )


@pytest.mark.asyncio
async def test_client_profile_timeout_is_bounded_and_not_retried() -> None:
    calls = 0

    def request(message: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        raise httpx.ReadTimeout("private details", request=message)

    with patch(
        "lonora_agent.workspace_client.httpx.AsyncHTTPTransport",
        return_value=httpx.MockTransport(request),
    ):
        with pytest.raises(LonoraError, match="workspace_profile_unavailable") as caught:
            await WorkspaceClient(Path("/run/analysis/host.sock")).profile()
        assert "private" not in str(caught.value) and calls == 1
