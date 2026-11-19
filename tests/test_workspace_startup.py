"""The Gateway starts before the workspace (`lonora` starts it after the core services and
never waits for it). Until the supervisor has answered once since the Gateway started, an
unreachable workspace is the normal start-up order: logged at INFO and not a step failure.
After that, an unreachable workspace is a failure as before."""

import asyncio
import json
import logging
from types import SimpleNamespace
from typing import Any

import httpx
import pytest
from lonora_gateway import runtime as gateway_runtime
from lonora_gateway.liveness import Liveness, StepSpec, supervise_step
from lonora_gateway.service import Gateway
from lonora_workspace.client import WorkspaceClient
from test_task_runtime import task_db as task_db


class Supervisor:
    """Not listening until `up`; then it answers an empty listing."""

    def __init__(self) -> None:
        self.up = False

    def handle(self, request: httpx.Request) -> httpx.Response:
        if not self.up:
            raise httpx.ConnectError("connection refused", request=request)
        listing: dict[str, Any] = {"boot_id": "b", "jobs": [], "processes": []}
        return httpx.Response(200, content=json.dumps(listing))


async def tick(gateway: Any, liveness: Liveness) -> None:
    """One run of the real `workspace` step under the Gateway's step runner."""
    spec = StepSpec("workspace", 10, 60, critical=False)
    stop = asyncio.Event()

    async def once() -> None:
        stop.set()
        await Gateway.workspace(gateway)

    await supervise_step(spec, once, stop, liveness)


@pytest.mark.asyncio
async def test_an_unreachable_workspace_at_start_is_not_a_failure_until_it_answered(
    task_db: Any, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    db, _, _, _ = task_db
    supervisor = Supervisor()
    monkeypatch.setattr(
        gateway_runtime,
        "WORKSPACE",
        WorkspaceClient(transport=httpx.MockTransport(supervisor.handle)),
    )

    async def each(_: Any) -> None:
        return None

    gateway: Any = SimpleNamespace(
        db=db,
        workspace_reached=False,
        for_each_owner=each,
        record_running=None,
        unreadable_snapshots=set(),
        run_copies_checked={},
    )
    liveness = Liveness()
    caplog.set_level(logging.INFO, logger="lonora.gateway")

    # Before the supervisor has ever answered: INFO, and the step counts no failure.
    for _ in range(2):
        await tick(gateway, liveness)
    record = liveness.steps["workspace"]
    assert record.failures == 0 and record.last_error is None
    assert not [r for r in caplog.records if r.levelno >= logging.ERROR]
    assert any(
        r.levelno == logging.INFO and "workspace_not_reached_yet" in r.getMessage()
        for r in caplog.records
    )

    # It answers once: from then on, unreachable is a step failure as before.
    supervisor.up = True
    await tick(gateway, liveness)
    assert gateway.workspace_reached and record.failures == 0
    supervisor.up = False
    caplog.clear()
    await tick(gateway, liveness)
    assert record.failures == 1 and record.last_error == "workspace_unavailable"
    assert any(
        r.levelno == logging.ERROR and "step_failed name=workspace" in r.getMessage()
        for r in caplog.records
    )
