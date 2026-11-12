"""The `lonora` CLI token in the workspace (7.3.3): set as LONORA_AGENT_TOKEN in every
command an agent's run starts, inherited by its children, readable only by the agent's
own Unix user, and never shown back: the scan replaces it with [secret:LONORA_AGENT_TOKEN]."""

import asyncio
import json
import os
import shutil
import signal
import subprocess
import tempfile
import uuid
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest
from lonora_tools import terminal
from lonora_workspace import supervisor as supervisor_module
from lonora_workspace.supervisor import Limits, RunCommand, Supervisor, signal_agents
from lonora_workspace.users import Users
from pydantic import ValidationError
from test_workspace_access import supervisor_answering

TOKEN = "lnr_" + "A1b2C3d4" * 5
OTHER = "lnr_" + "Z9y8X7w6" * 5


class Tokens:
    def __init__(self, token: str | None):
        self.token = token
        self.asked: list[str] = []

    async def for_run(self, run_id: str, agent_id: str) -> str | None:
        self.asked.append(run_id)
        return self.token

    async def values(self) -> list[str]:
        return [TOKEN, OTHER]


def etc(root: Path) -> Path:
    folder = root / "etc"
    folder.mkdir()
    (folder / "passwd").write_text("root:x:0:0:root:/root:/bin/bash\n")
    (folder / "group").write_text("root:x:0:\n")
    return folder


class Secrets:
    async def workspace_values(self) -> dict[str, str]:
        return {}

    async def scanned_values(self) -> dict[str, str]:
        return {}


def context(seen: list[Any], tokens: Tokens) -> Any:
    client = supervisor_answering(
        {
            "/v1/run": {
                "boot_id": "b",
                "id": "j",
                "exit_code": 0,
                "timed_out": False,
                "duration_ms": 1,
                "stdout": f"mine={TOKEN} theirs={OTHER}\n",
                "stderr": "",
                "stdout_dropped_bytes": 0,
                "stderr_dropped_bytes": 0,
            }
        },
        seen,
    )
    return SimpleNamespace(
        workspace=client,
        secrets=Secrets(),
        agent_id=str(uuid.uuid4()),
        owner_id="owner",
        workspace_given=None,
        cli_tokens=tokens,
        lease=SimpleNamespace(run_id="run-1"),
    )


@pytest.fixture(autouse=True)
def ordinary(monkeypatch: pytest.MonkeyPatch) -> None:
    async def yes(context: Any) -> bool:
        return True

    monkeypatch.setattr(terminal, "ordinary_run", yes)


def test_a_run_passes_its_token_and_every_token_is_scanned_out_of_the_output() -> None:
    seen: list[Any] = []
    tokens = Tokens(TOKEN)
    result = asyncio.run(terminal.run(context(seen, tokens), {"command": "lonora account"}))
    assert tokens.asked == ["run-1"], "the token is the run's, decided by token_for_command"
    assert seen[0][1]["agent_token"] == TOKEN
    marker = "[secret:LONORA_AGENT_TOKEN]"
    assert result["stdout"] == f"mine={marker} theirs={marker}\n"
    assert TOKEN not in json.dumps(result) and OTHER not in json.dumps(result)


def test_a_run_without_a_token_sends_none() -> None:
    seen: list[Any] = []
    asyncio.run(terminal.run(context(seen, Tokens(None)), {"command": "true"}))
    assert "agent_token" not in seen[0][1]


def test_only_a_cli_token_shape_is_accepted_by_the_supervisor() -> None:
    agent = uuid.uuid4()
    assert RunCommand(agent_id=agent, command="true", agent_token=TOKEN).agent_token == TOKEN
    for bad in ("", "x" * 40, "lnr_short", "lnr_" + "a" * 40 + "\n", "lnr_" + "a b" * 15):
        with pytest.raises(ValidationError):
            RunCommand(agent_id=agent, command="true", agent_token=bad)


@pytest.mark.skipif(os.geteuid() != 0, reason="runs commands as agent users")
def test_children_inherit_the_token_and_no_other_agent_user_can_read_it(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root = Path(tempfile.mkdtemp(dir="/tmp"))
    root.chmod(0o755)
    secrets = root / "run-secrets"
    secrets.mkdir(mode=0o750)
    monkeypatch.setattr(supervisor_module, "SECRETS", secrets)
    try:
        sup = Supervisor(Users(root, etc(root)), Limits(foreground_seconds=20))
        sup.users.load()
        mine, theirs = uuid.uuid4(), uuid.uuid4()

        async def go() -> dict[str, Any]:
            seen: dict[str, Any] = {}
            child = await sup.foreground(
                RunCommand(
                    agent_id=mine,
                    command="sh -c 'echo \"$LONORA_AGENT_TOKEN\"'",
                    agent_token=TOKEN,
                )
            )
            seen["child"] = child["stdout"].strip()
            held = await sup.background(
                RunCommand(agent_id=mine, command="sleep 20", agent_token=TOKEN)
            )
            pid = held["process"]["pid"]
            sleeper = None
            for _ in range(50):
                listed = await asyncio.to_thread(
                    subprocess.run,
                    ["pgrep", "-P", str(pid), "sleep"],
                    capture_output=True,
                    text=True,
                )
                found = listed.stdout.split()
                sleeper = int(found[0]) if found else None
                if sleeper:
                    break
                await asyncio.sleep(0.1)
            target = sleeper or pid
            seen["cmdline"] = await asyncio.to_thread(Path(f"/proc/{target}/cmdline").read_bytes)
            probe = f"cat /proc/{target}/environ 2>/dev/null | tr '\\0' '\\n' | grep -c ^LONORA_AGENT_TOKEN= || true"
            own = await sup.foreground(RunCommand(agent_id=mine, command=probe))
            other = await sup.foreground(RunCommand(agent_id=theirs, command=probe))
            seen["own"], seen["other"] = own["stdout"].strip(), other["stdout"].strip()
            later = await sup.foreground(
                RunCommand(agent_id=mine, command='echo "${LONORA_AGENT_TOKEN:-none}"')
            )
            seen["without"] = later["stdout"].strip()
            await sup.stop(pid)
            return seen

        seen = asyncio.run(go())
        assert seen["child"] == TOKEN, "a child process inherits the token"
        assert TOKEN.encode() not in seen["cmdline"], "never on a command line"
        assert seen["own"] == "1", "the agent's own user reads its process environment"
        assert seen["other"] in {"", "0"}, "another agent's user cannot"
        assert seen["without"] == "none", "a command started without a token has none"
        signal_agents(signal.SIGKILL, None, sup.users)
    finally:
        shutil.rmtree(root, ignore_errors=True)


@pytest.mark.asyncio
async def test_command_tokens_issue_the_runs_token_and_list_every_agents() -> None:
    if not os.environ.get("LONORA_DATABASE_URL"):
        pytest.skip("needs a disposable database")
    from lonora_db.schema import RunRow
    from lonora_tools.cli_token import CommandTokens
    from test_cli_endpoint import Setup

    setup = await Setup().open()
    try:
        runtime = setup.fixture.runtime
        key = runtime.settings.encryption_key.get_secret_value()
        thread = (await setup.fixture.request("POST", "/threads", {"agent_id": setup.agent}))["id"]
        async with runtime.db.sessions() as session, session.begin():
            full = RunRow(thread_id=thread, agent_id=setup.agent, trigger="user")
            helper = RunRow(thread_id=thread, agent_id=setup.agent, trigger="subagent")
            session.add_all([full, helper])
            await session.flush()
            ids = full.id, helper.id
        tokens = CommandTokens(runtime.db, key, setup.fixture.owner)
        issued = await tokens.for_run(ids[0], setup.agent)
        assert issued is not None and issued == await setup.token()
        assert await tokens.for_run(ids[1], setup.agent) is None
        # A command run as another agent's user never gets this run's token.
        assert await tokens.for_run(ids[0], (await setup.fixture.agent("x"))["id"]) is None
        assert issued in await tokens.values()
        # The endpoint knows the injected token as this agent's.
        assert (await setup.call("orders", issued))[0] != 77
    finally:
        await setup.close()


@pytest.mark.asyncio
async def test_a_text_artifact_reads_back_through_the_one_workspace_scan() -> None:
    """An exported workspace file can hold an agent's CLI token or a value given to a
    command and since rotated; artifact_read replaces both (7.2.6, terminal.owner_scan)."""
    if not os.environ.get("LONORA_DATABASE_URL"):
        pytest.skip("needs a disposable database")
    from check_streaming import Fixture
    from lonora_adapter_kit.types import ToolCall
    from lonora_db.secrets import WORKSPACE
    from lonora_tools.loader import load_tools

    fixture = await Fixture().open()
    services = fixture.runtime.services(fixture.owner)
    name = "ART_GIVEN_" + uuid.uuid4().hex[:8].upper()
    old, new = "old-art-" + uuid.uuid4().hex, "new-art-" + uuid.uuid4().hex
    secret_id = await services.secrets.write(name, old, WORKSPACE)
    try:
        assert services.given is not None and services.cli_tokens is not None
        await services.given.record({name: old})
        await services.secrets.write(name, new, WORKSPACE)  # rotated: only "given" knows old
        agent = await fixture.agent("Artifacts")
        run = await fixture.run(agent, await fixture.conversation(agent))
        context = await fixture.lease(run)
        token = await services.cli_tokens.for_run(run["id"], agent["id"])
        assert token is not None
        registry = load_tools()
        content = f"old {old} token {token}"
        created = await registry.execute(
            ToolCall(
                id="make", name="artifact_create", arguments={"name": "x.txt", "content": content}
            ),
            context,
        )
        read = await registry.execute(
            ToolCall(id="read", name="artifact_read", arguments={"artifact_id": created["id"]}),
            context,
        )
        assert read["content"] == f"old [secret:{name}] token [secret:LONORA_AGENT_TOKEN]"
    finally:
        await services.secrets.delete(secret_id)
        await fixture.close()
