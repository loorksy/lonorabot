"""Workspace output never carries a secret's value (VISION.md 7.2.6).

Each stored workspace secret's value and its base64, hex and URL-encoded forms become
``[secret:NAME]`` in every byte returned from the workspace.
"""

import base64
import json
import os
import sys
from dataclasses import replace
from pathlib import Path
from typing import Any
from urllib.parse import quote, quote_plus
from uuid import uuid4

import pytest
from lonora_adapter_kit.types import ToolCall
from lonora_agent.workspace import WorkspaceResult
from lonora_agent.workspace_access import RunWorkspaceAccess
from lonora_db.schema import WorkspaceOperationRow
from lonora_security.runtime_storage import confined_path
from lonora_security.secrets import SecretScan
from lonora_tools.loader import load_tools
from sqlalchemy import select

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tests"))
IMAGE = "sha256:" + "a" * 64

VALUE = "sk-live/9f+Qx=7&z"
SCAN = SecretScan({"BROKER_API_KEY": VALUE, "SHORT": "ab"})


def test_a_printed_secret_and_its_encoded_forms_are_replaced() -> None:
    raw = VALUE.encode()
    for form in (
        VALUE,
        base64.b64encode(raw).decode(),
        base64.b64encode(raw).decode().rstrip("="),
        base64.urlsafe_b64encode(raw).decode(),
        raw.hex(),
        raw.hex().upper(),
        quote(VALUE, safe=""),
        quote_plus(VALUE),
    ):
        assert SCAN.text("key=" + form + "\n") == "key=[secret:BROKER_API_KEY]\n", form


def test_base64_of_the_value_with_a_trailing_newline_is_replaced() -> None:
    # `echo "$KEY" | base64` encodes the value and the newline echo adds.
    printed = base64.b64encode(VALUE.encode() + b"\n").decode()
    assert VALUE not in SCAN.text(printed)
    assert SCAN.text(printed).startswith("[secret:BROKER_API_KEY]")
    assert base64.b64encode(VALUE.encode()).decode()[:20] not in SCAN.text(printed)


def test_every_occurrence_and_every_secret_is_replaced() -> None:
    text = f"{VALUE} and ab and {VALUE.encode().hex()}"
    assert SCAN.text(text) == (
        "[secret:BROKER_API_KEY] and [secret:SHORT] and [secret:BROKER_API_KEY]"
    )


def test_text_without_secrets_and_an_empty_store_are_unchanged() -> None:
    assert SCAN.text("price 2425.10, nothing secret") == "price 2425.10, nothing secret"
    assert SecretScan({}).text(VALUE) == VALUE
    assert not SecretScan({}).found(VALUE.encode())


def test_binary_bytes_carrying_a_secret_are_detected() -> None:
    assert SCAN.found(b"\x89PNG\x00" + VALUE.encode() + b"\xff")
    assert SCAN.found(b"\x00" + base64.b64encode(VALUE.encode()) + b"\x00")
    assert not SCAN.found(b"\x89PNG\x00\xff nothing")


def database() -> None:
    if not os.environ.get("LONORA_DATABASE_URL"):
        pytest.skip("Workspace output uses the PostgreSQL test database.")


class PrintingExecutor:
    """Stands in for a shell: `print NAME` echoes a value, `print64 NAME` its base64."""

    def __init__(self, values: dict[str, str]) -> None:
        self.values = values

    async def profile(self) -> str:
        return IMAGE

    async def execute(
        self,
        command: str,
        files: dict[str, bytes] | None = None,
        *,
        deadline_seconds: float = 30,
        expected_image: str | None = None,
    ) -> WorkspaceResult:
        verb, name = command.split()
        value = self.values[name].encode() + b"\n"
        printed = base64.b64encode(value).decode() if verb == "print64" else value.decode()
        return WorkspaceResult(0, printed, "error: " + printed, files or {}, IMAGE)


@pytest.mark.asyncio
async def test_a_command_that_prints_a_secret_returns_its_name() -> None:
    database()
    from check_streaming import Fixture

    fixture = await Fixture().open()
    registry = load_tools()
    name = "KEY_" + uuid4().hex[:8].upper()
    value = "live-" + uuid4().hex
    try:
        stored = await fixture.request("POST", "/secrets", {"name": name, "value": value})
        agent = await fixture.agent("Redaction")
        context = await fixture.lease(await fixture.run(agent, await fixture.conversation(agent)))
        context = replace(
            context, workspace_access=RunWorkspaceAccess(PrintingExecutor({name: value}))
        )

        async def call(identity: str, tool: str, arguments: dict[str, Any]) -> dict[str, Any]:
            return await registry.execute(
                ToolCall(id=identity, name=tool, arguments=arguments), context
            )

        written = await call(
            "write",
            "workspace_update",
            {"revision": 0, "files": {"notes.txt": "key " + value}, "delete": []},
        )
        read = await call(
            "read",
            "workspace_read",
            {"revision": 1, "path": "notes.txt", "offset": 0, "limit": 200},
        )
        assert read["content"] == f"key [secret:{name}]"
        plain = await call(
            "print", "workspace_execute", {"revision": 1, "command": "print " + name}
        )
        assert plain["stdout"] == f"[secret:{name}]\n"
        assert plain["stderr"] == f"error: [secret:{name}]\n"
        encoded = await call(
            "print64", "workspace_execute", {"revision": 2, "command": "print64 " + name}
        )
        assert value not in json.dumps(encoded)
        assert encoded["stdout"].startswith(f"[secret:{name}]")
        # The stored receipt (replayed on retry, kept in the database) is redacted too.
        async with fixture.runtime.db.sessions() as session:
            receipts = (
                await session.scalars(
                    select(WorkspaceOperationRow).where(
                        WorkspaceOperationRow.agent_id == agent["id"]
                    )
                )
            ).all()
        assert receipts and all(value not in json.dumps(row.result) for row in receipts)
        assert written["revision"] == 1
        # An exported text file reaches the chat scanned like any other workspace output.
        exported = await call(
            "export", "workspace_export", {"revision": 3, "path": "notes.txt", "name": None}
        )
        stored_file = confined_path(context.artifact_root, exported["payload"]["key"])
        assert stored_file.read_text() == f"key [secret:{name}]"
        await fixture.request("DELETE", "/secrets/" + stored["id"])
    finally:
        await fixture.close()
