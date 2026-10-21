"""Agent -> PostgreSQL -> Unix host bridge -> real isolated Python -> saved files.

Pass a locally built immutable infra/analysis image ID. Uses a disposable DB,
scripted model, task-owned local host processes, and no broker calls.
"""

import asyncio
import hashlib
import json
import os
import signal
import sys
from dataclasses import replace
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any
from unittest.mock import patch
from uuid import uuid4

from check_streaming import Fixture
from lonora_adapter_kit.types import ModelReply, ToolCall
from lonora_agent.executor import execute_run
from lonora_agent.workspace import AnalyticalContainer
from lonora_agent.workspace_access import RunWorkspaceAccess
from lonora_agent.workspace_client import WorkspaceClient
from lonora_contracts.model_routing import ModelSelection
from lonora_core.user_error import LonoraError
from lonora_db.schema import (
    AnalyticalWorkspaceRow,
    MessageRow,
    RunRow,
    TradeApprovalRow,
    TradingJournalRow,
)
from lonora_tools.loader import load_tools
from sqlalchemy import func, select


async def docker(*args: str) -> bytes:
    process = await asyncio.create_subprocess_exec(
        "docker",
        "--host=unix:///var/run/docker.sock",
        *args,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    out, err = await process.communicate()
    assert process.returncode == 0, err.decode()
    return out


async def main(image: str) -> None:
    fixture = await Fixture().open()
    original_root = fixture.settings.artifact_root
    host: asyncio.subprocess.Process | None = None
    checks = 0
    foreign: str | None = None
    with TemporaryDirectory(prefix="lonora-workspace-bridge-") as temporary:
        fixture.settings.artifact_root = Path(temporary) / "artifacts"
        directory = Path(temporary) / "service"
        socket = directory / "host.sock"
        namespace = hashlib.sha256(
            str(await asyncio.to_thread(directory.resolve)).encode()
        ).hexdigest()[:32]
        backend = AnalyticalContainer(image, namespace=namespace)

        async def spawn() -> asyncio.subprocess.Process:
            # The trusted bridge itself needs no DB, model or broker secrets.
            env = {key: os.environ[key] for key in ("PATH", "HOME", "LANG") if key in os.environ}
            return await asyncio.create_subprocess_exec(
                sys.executable,
                "-m",
                "lonora_agent.workspace_host",
                "--image",
                image,
                "--directory",
                str(directory),
                "--group",
                str(os.getgid()),
                "--concurrency",
                "1",
                env=env,
                stdout=asyncio.subprocess.DEVNULL,
                stderr=asyncio.subprocess.PIPE,
            )

        async def start() -> asyncio.subprocess.Process:
            process = await spawn()
            for _ in range(200):
                if process.returncode is not None:
                    _, err = await process.communicate()
                    raise AssertionError("Host startup failed: " + (err or b"").decode())
                if await asyncio.to_thread(socket.exists):
                    # Wait for the actual bridge response: the Unix listener is
                    # bound before orphan cleanup and Uvicorn admission.
                    try:
                        probe = await WorkspaceClient(socket).execute("true")
                        assert probe.exit_code == 0
                        return process
                    except LonoraError as error:
                        assert error.code == "workspace_execution_uncertain"
                await asyncio.sleep(0.05)
            process.kill()
            await process.communicate()
            raise AssertionError("Host did not become ready")

        async def stop(process: asyncio.subprocess.Process) -> None:
            if process.returncode is None:
                process.terminate()
            try:
                await asyncio.wait_for(process.communicate(), 15)
            except TimeoutError:
                process.kill()
                await process.communicate()
                raise AssertionError("Host did not shut down cleanly") from None
            assert process.returncode in {0, -signal.SIGTERM}

        try:
            orphan = "lonora-analysis-" + uuid4().hex
            await docker(*backend.create_arguments(orphan))
            await docker("start", orphan)
            foreign = "lonora-analysis-" + uuid4().hex
            await docker(*AnalyticalContainer(image, namespace="f" * 32).create_arguments(foreign))
            await docker("start", foreign)
            host = await start()
            assert not (
                await docker("ps", "--all", "--filter", "name=" + orphan, "--format", "{{.Names}}")
            ).strip()
            assert (
                await docker("ps", "--filter", "name=" + foreign, "--format", "{{.Names}}")
            ).strip(), "A host reaped another host namespace"
            await docker("rm", "--force", foreign)
            foreign = None
            assert (await asyncio.to_thread(socket.stat)).st_mode & 0o777 == 0o660
            assert (await asyncio.to_thread(directory.stat)).st_mode & 0o777 == 0o750
            checks += 1

            agent = await fixture.agent("Container analysis")
            thread = await fixture.conversation(agent)
            context = await fixture.lease(await fixture.run(agent, thread))
            context = replace(context, workspace_access=RunWorkspaceAccess(WorkspaceClient(socket)))
            registry = load_tools()
            async with context.db.sessions() as session:
                before_journal = await session.scalar(
                    select(func.count()).select_from(TradingJournalRow)
                )
                before_approvals = await session.scalar(
                    select(func.count()).select_from(TradeApprovalRow)
                )
            script = "import json,statistics\nfrom pathlib import Path\nvalues=json.loads(Path('input.json').read_text())\nresult={'mean':statistics.mean(values),'count':len(values)}\nPath('result.json').write_text(json.dumps(result))\nprint(json.dumps(result))\n"
            rounds = 0
            exported_id = ""

            async def model(_capability: Any, messages: Any, _tools: Any, **_kwargs: Any):
                nonlocal rounds, exported_id
                rounds += 1
                observed: dict[str, Any] = {}
                if rounds > 1:
                    observed = json.loads(messages[-1].content)
                    assert observed["ok"], observed
                if rounds == 1:
                    call = ToolCall(id="inspect", name="workspace_inspect", arguments={})
                elif rounds == 2:
                    assert observed["execution_configured"] is True and observed["revision"] == 0
                    call = ToolCall(
                        id="files",
                        name="workspace_update",
                        arguments={
                            "revision": 0,
                            "files": {"analysis.py": script, "input.json": "[100, 101, 102]"},
                        },
                    )
                elif rounds == 3:
                    assert observed["revision"] == 1
                    call = ToolCall(
                        id="compute",
                        name="workspace_execute",
                        arguments={"revision": 1, "command": "python analysis.py"},
                    )
                elif rounds == 4:
                    assert observed["exit_code"] == 0 and json.loads(observed["stdout"]) == {
                        "mean": 101,
                        "count": 3,
                    }
                    assert observed["revision"] == 2 and observed["image"] == image
                    call = ToolCall(
                        id="read-result",
                        name="workspace_read",
                        arguments={"revision": 2, "path": "result.json"},
                    )
                elif rounds == 5:
                    assert json.loads(observed["content"]) == {"mean": 101, "count": 3}
                    call = ToolCall(
                        id="export-result",
                        name="workspace_export",
                        arguments={"revision": 2, "path": "result.json"},
                    )
                elif rounds == 6:
                    exported_id = observed["id"]
                    assert observed["state"]["workspace_source"]["revision"] == 2
                    call = ToolCall(
                        id="verify-attachment",
                        name="artifact_read",
                        arguments={"artifact_id": exported_id},
                    )
                else:
                    assert json.loads(observed["content"]) == {"mean": 101, "count": 3}
                    return ModelReply(
                        text="The saved analysis contains three observations with a mean of 101."
                    ), ModelSelection(provider="openai", model="scripted-container-analysis")
                return ModelReply(tool_calls=[call]), ModelSelection(
                    provider="openai", model="scripted-container-analysis"
                )

            with patch.object(context.router, "complete", model):
                await execute_run(context, registry, 120, 8)
            async with context.db.sessions() as session:
                run = await session.get(RunRow, context.lease.run_id)
                assert run and run.status == "completed"
                stored = await session.get(AnalyticalWorkspaceRow, agent["id"])
                assert stored and stored.revision == 2
                message = await session.scalar(
                    select(MessageRow)
                    .where(
                        MessageRow.thread_id == context.thread_id, MessageRow.role == "assistant"
                    )
                    .order_by(MessageRow.seq.desc())
                    .limit(1)
                )
                assert message and exported_id in message.attachment_ids
            downloaded = await fixture.client.get("/api/artifacts/" + exported_id + "/file")
            assert downloaded.status_code == 200 and downloaded.json() == {"mean": 101, "count": 3}
            assert rounds == 7
            checks += 1

            await stop(host)
            host = None
            resumed = await fixture.lease(await fixture.run(agent, thread))
            # Files survive a host restart and are readable without its socket.
            saved = await registry.execute(
                ToolCall(
                    id="saved",
                    name="workspace_read",
                    arguments={"revision": 2, "path": "result.json"},
                ),
                resumed,
            )
            assert json.loads(saved["content"]) == {"mean": 101, "count": 3}
            host = await start()
            resumed = replace(resumed, workspace_access=RunWorkspaceAccess(WorkspaceClient(socket)))
            reused = await registry.execute(
                ToolCall(
                    id="reuse",
                    name="workspace_execute",
                    arguments={"revision": 2, "command": "python analysis.py"},
                ),
                resumed,
            )
            assert reused["revision"] == 3 and json.loads(reused["stdout"])["mean"] == 101
            checks += 1

            work = asyncio.create_task(WorkspaceClient(socket).execute("sleep 2"))
            for _ in range(100):
                if (
                    await docker(
                        "ps",
                        "--filter",
                        "label=ai.lonora.analytical-workspace=1",
                        "--format",
                        "{{.Names}}",
                    )
                ).strip():
                    break
                await asyncio.sleep(0.05)
            try:
                await WorkspaceClient(socket).execute("must-not-run")
            except LonoraError as error:
                assert error.code == "workspace_busy"
            else:
                raise AssertionError("Host concurrency limit was bypassed")
            duplicate = await spawn()
            _, rejected = await duplicate.communicate()
            assert duplicate.returncode != 0 and b"BlockingIOError" in (rejected or b"")
            assert (await work).exit_code == 0, (
                "Duplicate host killed active work during startup cleanup"
            )
            checks += 1

            async with context.db.sessions() as session:
                assert (
                    await session.scalar(select(func.count()).select_from(TradingJournalRow))
                    == before_journal
                )
                assert (
                    await session.scalar(select(func.count()).select_from(TradeApprovalRow))
                    == before_approvals
                )
            assert not (
                await docker(
                    "ps",
                    "--all",
                    "--filter",
                    "label=ai.lonora.analytical-workspace=1",
                    "--format",
                    "{{.Names}}",
                )
            ).strip()
            print(
                f"PASS: {checks} actual Agent/PostgreSQL/Unix/Docker/restart/host-lock acceptance groups; zero financial effects"
            )
        finally:
            if foreign is not None:
                await docker("rm", "--force", foreign)
            if host is not None:
                await stop(host)
            fixture.settings.artifact_root = original_root
            await fixture.close()


if __name__ == "__main__":
    asyncio.run(main(sys.argv[1]))
