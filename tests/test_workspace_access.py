"""The workspace from the Gateway's side: every byte that comes back is scanned for the
owner's workspace secrets (7.2.6), commands receive only the secrets they name and only
from the workspace scope (7.2.3, 7.2.5), and only an ordinary run gets a CLI token."""

import asyncio
import base64
import json
import os
import shutil
import signal
import tempfile
import uuid
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import httpx
import pytest
from lonora_core.user_error import LonoraError
from lonora_security.secrets import SecretScan
from lonora_tools import terminal
from lonora_workspace import supervisor as supervisor_module
from lonora_workspace.client import WorkspaceClient
from lonora_workspace.supervisor import Limits, RunCommand, Supervisor, signal_agents
from lonora_workspace.users import AGENTS_GID, Users

VALUE = "s3cr3t-Value-0123456789"
SCAN = SecretScan({"API_KEY": VALUE})
AGENT = str(uuid.uuid4())


def supervisor_answering(answers: dict[str, dict[str, Any]], seen: list[Any]) -> WorkspaceClient:
    def handle(request: httpx.Request) -> httpx.Response:
        seen.append((request.url.path, json.loads(request.content or b"null")))
        return httpx.Response(200, json=answers[request.url.path])

    return WorkspaceClient(transport=httpx.MockTransport(handle))


def test_a_command_that_prints_a_secret_or_its_base64_returns_the_marker():
    encoded = base64.b64encode(VALUE.encode()).decode()
    client = supervisor_answering(
        {
            "/v1/run": {
                "boot_id": "b",
                "id": "j",
                "exit_code": 0,
                "timed_out": False,
                "duration_ms": 3,
                "stdout": f"key={VALUE}\nb64={encoded}\n",
                "stderr": f"url=https://x/?k={VALUE}",
                "stdout_dropped_bytes": 0,
                "stderr_dropped_bytes": 0,
            }
        },
        [],
    )
    result = asyncio.run(client.run(SCAN, AGENT, "echo $API_KEY"))
    assert result["stdout"] == "key=[secret:API_KEY]\nb64=[secret:API_KEY]\n"
    assert VALUE not in json.dumps(result) and encoded not in json.dumps(result)


def test_process_lists_and_file_reads_are_scanned_too():
    client = supervisor_answering(
        {
            "/v1/processes": {
                "boot_id": "b",
                "jobs": [{"command": f"curl -H 'k: {VALUE}' x", "agent_id": AGENT}],
                "processes": [
                    {"pid": 9, "command": f"python bot.py --key {VALUE}", "agent_id": AGENT}
                ],
            },
            "/v1/files/read": {
                "boot_id": "b",
                "ok": True,
                "size": 40,
                "offset": 0,
                "truncated": False,
                "content_base64": base64.b64encode(f"token: {VALUE}\n".encode()).decode(),
            },
        },
        [],
    )
    listing = asyncio.run(client.processes(SCAN))
    assert (
        VALUE not in json.dumps(listing)
        and "[secret:API_KEY]" in listing["processes"][0]["command"]
    )
    text = asyncio.run(client.read_text(SCAN, AGENT, "config.txt", 0, 100))
    assert text["content"] == "token: [secret:API_KEY]\n"
    with pytest.raises(LonoraError, match="workspace_file_holds_secret"):
        asyncio.run(client.read_bytes(SCAN, AGENT, "config.txt"))


def test_an_unreachable_supervisor_is_a_plain_unavailable_error():
    def broken(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("no socket")

    client = WorkspaceClient(transport=httpx.MockTransport(broken))
    with pytest.raises(LonoraError, match="workspace_unavailable"):
        asyncio.run(client.processes(SCAN))


class Secrets:
    def __init__(self, values: dict[str, str]):
        self.values = values
        self.reads = 0

    async def workspace_values(self) -> dict[str, str]:
        self.reads += 1
        return dict(self.values)

    async def read(self, secret_id: str) -> str:
        raise AssertionError("the workspace never reads a secret by id (broker scope)")


def context(seen: list[Any], token: Any = None) -> Any:
    client = supervisor_answering(
        {
            "/v1/run": {
                "boot_id": "b",
                "id": "j",
                "exit_code": 0,
                "timed_out": False,
                "duration_ms": 1,
                "stdout": "x" * (terminal.MODEL_OUTPUT + 10),
                "stderr": "",
                "stdout_dropped_bytes": 0,
                "stderr_dropped_bytes": 0,
            }
        },
        seen,
    )
    return SimpleNamespace(
        workspace=client,
        secrets=Secrets({"API_KEY": VALUE, "OTHER": "other-secret-value-1"}),
        agent_id=AGENT,
        owner_id="owner",
        agent_token=token,
    )


@pytest.fixture(autouse=True)
def ordinary(monkeypatch: pytest.MonkeyPatch) -> None:
    async def yes(context: Any) -> bool:
        return True

    monkeypatch.setattr(terminal, "ordinary_run", yes)


def test_a_command_receives_only_the_workspace_secrets_it_names():
    seen: list[Any] = []
    result = asyncio.run(terminal.run(context(seen), {"command": "env", "secrets": ["API_KEY"]}))
    body = seen[0][1]
    assert body["secrets"] == {"API_KEY": VALUE} and "agent_token" not in body
    assert body["current_secrets"] == ["API_KEY", "OTHER"]
    assert len(result["stdout"].encode()) == terminal.MODEL_OUTPUT
    assert result["stdout_omitted_bytes"] == 10


def test_an_unknown_secret_name_is_refused_before_anything_runs():
    seen: list[Any] = []
    with pytest.raises(LonoraError, match="workspace_secret_unknown"):
        asyncio.run(terminal.run(context(seen), {"command": "env", "secrets": ["MISSING"]}))
    assert seen == []


def test_only_an_ordinary_run_may_run_write_or_stop(monkeypatch: pytest.MonkeyPatch):
    async def token(owner_id: str, agent_id: str) -> str:
        return "tok_" + "t" * 32

    seen: list[Any] = []
    asyncio.run(terminal.run(context(seen, token), {"command": "true"}))
    assert seen[0][1]["agent_token"] == "tok_" + "t" * 32

    async def no(context: Any) -> bool:
        return False

    monkeypatch.setattr(terminal, "ordinary_run", no)
    for handler, arguments in (
        (terminal.run, {"command": "cat ~/.lonora/token"}),
        (terminal.write, {"path": "x", "content": "y"}),
        (terminal.stop, {"pid": 99}),
    ):
        seen = []
        with pytest.raises(LonoraError, match="workspace_run_scope_refused"):
            asyncio.run(handler(context(seen, token), arguments))
        assert seen == []


def test_the_cli_token_never_reaches_the_model():
    async def token(owner_id: str, agent_id: str) -> str:
        return "tok_" + "q" * 40

    scanned = asyncio.run(terminal.scan(context([], token)))
    assert scanned.text("LONORA_AGENT_TOKEN=tok_" + "q" * 40) == (
        "LONORA_AGENT_TOKEN=[secret:LONORA_AGENT_TOKEN]"
    )


def test_a_secret_across_a_slice_edge_is_still_replaced():
    content = ("a" * 100 + VALUE + "b" * 100).encode()
    seen: list[Any] = []

    def handle(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        seen.append(body)
        part = content[body["offset"] : body["offset"] + body["limit"]]
        return httpx.Response(
            200,
            json={
                "boot_id": "b",
                "ok": True,
                "size": len(content),
                "offset": body["offset"],
                "truncated": body["offset"] + len(part) < len(content),
                "content_base64": base64.b64encode(part).decode(),
            },
        )

    client = WorkspaceClient(transport=httpx.MockTransport(handle))
    left = asyncio.run(client.read_text(SCAN, AGENT, "f", 0, 110))
    right = asyncio.run(client.read_text(SCAN, AGENT, "f", 110, 200))
    assert left["content"] == "a" * 100 + "[secret:API_KEY]"
    assert right["content"].startswith("[secret:API_KEY]") and right["content"].endswith("b" * 100)
    assert VALUE[:10] not in left["content"] + right["content"]
    assert VALUE[-10:] not in left["content"] + right["content"]


def test_a_stream_cut_inside_a_secret_never_shows_its_half():
    from lonora_workspace.client import MARGIN

    client = supervisor_answering(
        {
            "/v1/run": {
                "boot_id": "b",
                "id": "j",
                "exit_code": 0,
                "timed_out": False,
                "duration_ms": 1,
                "stdout": "x" * (MARGIN * 2) + VALUE[:12],
                "stderr": "",
                "stdout_dropped_bytes": 100,
                "stderr_dropped_bytes": 0,
            }
        },
        [],
    )
    result = asyncio.run(client.run(SCAN, AGENT, "true"))
    assert VALUE[:12] not in result["stdout"] and result["stdout_dropped_bytes"] > 100


def _etc(root: Path) -> Path:
    etc = root / "etc"
    etc.mkdir()
    (etc / "passwd").write_text("root:x:0:0:root:/root:/bin/bash\n")
    (etc / "group").write_text("root:x:0:\n")
    return etc


@pytest.mark.skipif(os.geteuid() != 0, reason="runs commands as agent users")
def test_secrets_arrive_as_env_and_file_and_the_token_only_for_its_user(
    monkeypatch: pytest.MonkeyPatch,
):
    root = Path(tempfile.mkdtemp(dir="/tmp"))
    root.chmod(0o755)
    secrets = root / "run-secrets"
    secrets.mkdir(mode=0o750)
    os.chown(secrets, 0, AGENTS_GID)
    monkeypatch.setattr(supervisor_module, "SECRETS", secrets)
    try:
        sup = Supervisor(Users(root, _etc(root)), Limits(foreground_seconds=20))
        sup.users.load()
        a, b = uuid.uuid4(), uuid.uuid4()

        async def go(agent: uuid.UUID, command: str, **extra: Any) -> dict[str, Any]:
            return await sup.foreground(RunCommand(agent_id=agent, command=command, **extra))

        token = "tok_" + "x" * 40
        out = asyncio.run(
            go(
                a,
                'echo "$API_KEY"; cat "$S/API_KEY"; echo;'
                ' echo "$LONORA_AGENT_TOKEN"; test -e ~/.lonora/token || echo no-file',
                secrets={"API_KEY": VALUE},
                agent_token=token,
                env={"S": str(secrets)},
            )
        )
        assert out["stdout"].split() == [VALUE, VALUE, token, "no-file"], out
        assert (secrets / "API_KEY").stat().st_mode & 0o777 == 0o440
        other = asyncio.run(
            go(b, 'echo "${LONORA_AGENT_TOKEN-none}"; cat "$S/API_KEY"', env={"S": str(secrets)})
        )
        assert other["stdout"].split() == ["none", VALUE]
        asyncio.run(go(a, "true", current_secrets=["OTHER"]))
        assert not (secrets / "API_KEY").exists()
        with pytest.raises(ValueError, match="workspace_secret_name_invalid"):
            asyncio.run(go(a, "true", secrets={"PATH": "x"}))
        signal_agents(signal.SIGKILL, None, sup.users)
    finally:
        shutil.rmtree(root, ignore_errors=True)
