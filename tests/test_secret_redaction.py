"""Workspace output never carries a secret's value (VISION.md 7.2.6).

Each stored workspace secret's value and its base64, hex and URL-encoded forms become
``[secret:NAME]`` in every byte returned from the workspace.
"""

import base64
import json
import os
import re
import sys
import time
from dataclasses import replace
from io import BytesIO
from pathlib import Path
from typing import Any
from urllib.parse import quote, quote_plus
from uuid import uuid4

import pytest
from lonora_adapter_kit.types import ToolCall
from lonora_agent.workspace import WorkspaceResult
from lonora_agent.workspace_access import RunWorkspaceAccess
from lonora_core.user_error import LonoraError
from lonora_db.schema import WorkspaceOperationRow
from lonora_security.runtime_storage import confined_path
from lonora_security.secrets import SecretScan
from lonora_tools.loader import load_tools
from PIL import Image
from PIL.PngImagePlugin import PngInfo
from sqlalchemy import select

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tests"))
IMAGE = "sha256:" + "a" * 64

VALUE = "sk-live/9f+Qx=7&z"
SCAN = SecretScan({"API_KEY": VALUE, "SHORT": "ab"})
MARK = "[secret:API_KEY]"


def wrap(text: str, width: int) -> str:
    return "\n".join(text[i : i + width] for i in range(0, len(text), width)) + "\n"


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
        quote(VALUE),
        re.sub(r"%[0-9A-F]{2}", lambda escape: escape[0].lower(), quote(VALUE, safe="")),
        quote_plus(VALUE),
        json.dumps(VALUE)[1:-1],
    ):
        assert SCAN.text("key=" + form + "\n") == f"key={MARK}\n", form


def test_base64_is_caught_at_every_alignment_and_length() -> None:
    for length in range(3, 40):
        value = "".join(chr(33 + (i * 7 + length) % 90) for i in range(length))
        scan = SecretScan({"K": value})
        for before in (b"", b"K=", b"KEY="):
            for after in (b"", b"\n", b"Z\n", b" tail"):
                for encode in (base64.b64encode, base64.urlsafe_b64encode):
                    printed = encode(before + value.encode() + after).decode()
                    scanned = scan.text("out " + printed + " end")
                    assert scanned.count("[secret:K]") == 1, (length, before, after)
                    # Only characters encoding the bytes around the value survive.
                    marker = scanned.index("[secret:K]")
                    left, right = marker - 4, len(scanned) - marker - len("[secret:K]") - 4
                    assert left <= len(before) * 4 // 3, (scanned, before)
                    assert right <= -(-len(after) * 4 // 3) + 2, (scanned, after)


def test_wrapped_base64_and_hex_of_a_long_secret_are_replaced() -> None:
    token = "eyJhbGciOiJIUzI1NiJ9." + "x" * 120 + ".signature"
    scan = SecretScan({"JWT": token})
    for printed in (
        wrap(base64.b64encode(token.encode() + b"\n").decode(), 76),  # base64
        wrap(base64.b64encode(token.encode()).decode(), 64),  # openssl base64
        wrap(token.encode().hex(), 60),  # xxd -p
    ):
        scanned = scan.text(printed)
        assert scanned.startswith("[secret:JWT]")
        assert len(scanned) < 30, scanned


def test_overlapping_secrets_never_leak_one_another() -> None:
    scan = SecretScan({"SHORT": "ab", "LONG": "bsecretvalue"})
    assert scan.text("absecretvalue!") == "[secret:LONG]!"
    scan = SecretScan({"A": "xyz123", "B": "123456"})
    assert scan.text("xyz123456") in {"[secret:A]", "[secret:B]"}


def test_every_occurrence_and_every_secret_is_replaced() -> None:
    text = f"{VALUE} and ab and {VALUE.encode().hex()}"
    assert SCAN.text(text) == f"{MARK} and [secret:SHORT] and {MARK}"


def test_short_values_and_their_own_forms_are_replaced() -> None:
    scan = SecretScan({"PIN": "7"})
    assert scan.text("pin=7, b64=Nw==") == "pin=[secret:PIN], b64=[secret:PIN]"


def test_text_without_secrets_and_an_empty_store_are_unchanged() -> None:
    assert SCAN.text("price 2425.10, nothing secret") == "price 2425.10, nothing secret"
    assert SecretScan({}).text(VALUE) == VALUE
    assert not SecretScan({}).found(VALUE.encode())


def test_many_short_texts_are_scanned_one_for_one() -> None:
    assert SCAN.texts([]) == []
    assert SCAN.texts(["a", VALUE + ".txt", ""]) == ["a", MARK + ".txt", ""]
    assert SecretScan({}).texts(["x"]) == ["x"]


def test_scanned_data_covers_keys_and_nested_values() -> None:
    assert SCAN.data({VALUE: [VALUE, {"x": VALUE}], "n": 3}) == {
        MARK: [MARK, {"x": MARK}],
        "n": 3,
    }


def test_binary_bytes_carrying_a_secret_are_detected() -> None:
    assert SCAN.found(b"\x89PNG\x00" + VALUE.encode() + b"\xff")
    assert SCAN.found(b"\x00" + base64.b64encode(VALUE.encode()) + b"\x00")
    assert SCAN.found(b"\x00" + wrap(VALUE.encode().hex(), 10).encode() + b"\x00")
    assert not SCAN.found(b"\x89PNG\x00\xff nothing")


def test_the_scan_stays_fast_with_many_secrets() -> None:
    secrets = {f"KEY_{i}": f"value-{i}-" + "q" * 30 for i in range(100)}
    output = ("2425.10,2426.30,1.0845,BUY,ok\n" * 4500)[: 128 * 1024]
    started = time.perf_counter()
    SecretScan(secrets).text(output)
    assert time.perf_counter() - started < 2


def database() -> None:
    if not os.environ.get("LONORA_DATABASE_URL"):
        pytest.skip("Workspace output uses the PostgreSQL test database.")


class PrintingExecutor:
    """Stands in for a shell. `print NAME` echoes a secret, `print64 NAME` its base64,
    `say TEXT` echoes text, `mkfile NAME` saves a file named by a secret, `png NAME`
    saves an image carrying a secret in a text chunk."""

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
        verb, argument = command.split(maxsplit=1)
        files = dict(files or {})
        printed = ""
        if verb == "say":
            printed = argument + "\n"
        elif verb in {"print", "print64"}:
            value = self.values[argument].encode() + b"\n"
            printed = base64.b64encode(value).decode() if verb == "print64" else value.decode()
        elif verb == "mkfile":
            files[self.values[argument] + ".txt"] = b"made"
        elif verb == "png":
            info = PngInfo()
            info.add_text("comment", self.values[argument])
            image = BytesIO()
            Image.new("RGB", (4, 4)).save(image, "PNG", pnginfo=info)
            files["chart.png"] = image.getvalue()
        return WorkspaceResult(0, printed, "error: " + printed, files, IMAGE)


@pytest.mark.asyncio
async def test_a_command_that_prints_a_secret_returns_its_name() -> None:
    database()
    from check_streaming import Fixture

    fixture = await Fixture().open()
    registry = load_tools()
    name, late = ("KEY_" + uuid4().hex[:8].upper() for _ in range(2))
    value, late_value = ("live-" + uuid4().hex for _ in range(2))
    saved: list[str] = []
    try:
        saved.append(
            (await fixture.request("POST", "/secrets", {"name": name, "value": value}))["id"]
        )
        services = fixture.runtime.services(fixture.owner)
        # A value too short to find at every base64 alignment is not stored.
        for short in ("ab", "\u00e9\u00e9"):
            with pytest.raises(LonoraError) as refused:
                await services.secrets.write(name, short, "workspace")
            assert refused.value.code == "secret_value_too_short"
        assert await services.secrets.read(saved[0]) == value
        # Every stored value outside the broker scope is scanned (VISION.md 7.2.6); a
        # broker value is read only by the execution door and provisioning (7.2.3).
        other, provider, broker = (scope + "-" + uuid4().hex for scope in ("feed", "model", "acct"))
        other_name, provider_name, broker_name = (item[:12] for item in (other, provider, broker))
        saved.append(await services.secrets.write(other_name, other, "integration"))
        saved.append(await services.secrets.write(provider_name, provider, "provider"))
        # Broker values are written only through the broker layer's own store (7.2.3).
        from lonora_adapters.storage.broker_secrets import BrokerSecrets

        broker_store = BrokerSecrets(
            fixture.runtime.db,
            fixture.runtime.settings.encryption_key.get_secret_value(),
            fixture.owner,
        )
        async with fixture.runtime.db.sessions() as session, session.begin():
            saved.append(await broker_store.write_in_session(session, broker_name, broker))
        scanned = await services.secrets.scanned_values()
        assert scanned[name] == value and scanned[other_name] == other
        assert scanned[provider_name] == provider
        assert broker_name not in scanned and broker not in scanned.values()
        # The workspace reader (what agents use by name) holds the workspace scope only.
        workspace = await services.secrets.workspace_values()
        assert workspace[name] == value
        assert not {other_name, provider_name, broker_name} & set(workspace)
        agent = await fixture.agent("Redaction")
        context = await fixture.lease(await fixture.run(agent, await fixture.conversation(agent)))
        context = replace(
            context, workspace_access=RunWorkspaceAccess(PrintingExecutor({name: value}))
        )

        async def call(identity: str, tool: str, arguments: dict[str, Any]) -> dict[str, Any]:
            return await registry.execute(
                ToolCall(id=identity, name=tool, arguments=arguments), context
            )

        async def run(identity: str, revision: int, command: str) -> dict[str, Any]:
            arguments = {"revision": revision, "command": command}
            return await call(identity, "workspace_execute", arguments)

        # A secret that crosses a page boundary never comes back in two halves.
        body = "A" * 7990 + value + "B" * 100
        files = {"notes.txt": body, "short.txt": "key " + value, value + ".md": "x"}
        written = await call(
            "write", "workspace_update", {"revision": 0, "files": files, "delete": []}
        )
        assert written["revision"] == 1
        pages: list[str] = []
        offset: int | None = 0
        while offset is not None:
            page = await call(
                f"page-{offset}",
                "workspace_read",
                {"revision": 1, "path": "notes.txt", "offset": offset, "limit": 8000},
            )
            pages.append(page["content"])
            offset = page["next_offset"]
        assert len(pages) == 2 and "".join(pages) == f"{'A' * 7990}[secret:{name}]{'B' * 100}"
        assert not any(value[:8] in page or value[-8:] in page for page in pages)
        # The path a read echoes is scanned like the content.
        named = await call(
            "named",
            "workspace_read",
            {"revision": 1, "path": value + ".md", "offset": 0, "limit": 100},
        )
        assert named["path"] == f"[secret:{name}].md" and named["content"] == "x"

        plain = await run("print", 1, "print " + name)
        assert plain["stdout"] == f"[secret:{name}]\n"
        assert plain["stderr"] == f"error: [secret:{name}]\n"
        encoded = await run("print64", 2, "print64 " + name)
        # What remains after the marker encodes only the newline echo added.
        assert re.fullmatch(rf"\[secret:{name}\][A-Za-z0-9+/]{{0,2}}=*", encoded["stdout"])
        assert base64.b64encode(value.encode()).decode()[:12] not in json.dumps(encoded)
        integration = await run("other", 3, "say " + other)
        assert integration["stdout"] == f"[secret:{other_name}]\n"

        # A result stored before its value became a secret is scanned when replayed.
        said = await run("late", 4, "say " + late_value)
        assert said["stdout"] == late_value + "\n"
        saved.append(
            (await fixture.request("POST", "/secrets", {"name": late, "value": late_value}))["id"]
        )
        replayed = await run("late", 4, "say " + late_value)
        assert replayed["stdout"] == f"[secret:{late}]\n"

        # File paths are workspace output too.
        made = await run("mkfile", 5, "mkfile " + name)
        assert f"[secret:{name}].txt" in [item["path"] for item in made["files"]]
        inspected = await call("inspect", "workspace_inspect", {})
        assert value not in json.dumps(inspected)

        # The stored receipts (replayed on retry, kept in the database) hold no value.
        async with fixture.runtime.db.sessions() as session:
            receipts = (
                await session.scalars(
                    select(WorkspaceOperationRow).where(
                        WorkspaceOperationRow.agent_id == agent["id"]
                    )
                )
            ).all()
        assert receipts and all(value not in json.dumps(row.result) for row in receipts)

        # An exported text file reaches the chat scanned; reading it back scans it again.
        exported = await call(
            "export", "workspace_export", {"revision": 6, "path": "short.txt", "name": None}
        )
        stored_file = confined_path(context.artifact_root, exported["payload"]["key"])
        assert stored_file.read_text() == f"key [secret:{name}]"
        reread = await call("reread", "artifact_read", {"artifact_id": exported["id"]})
        assert reread["content"] == f"key [secret:{name}]"
        # An image that carries a secret is not exported.
        await run("png", 6, "png " + name)
        with pytest.raises(LonoraError) as refused:
            await call(
                "export-png", "workspace_export", {"revision": 7, "path": "chart.png", "name": None}
            )
        assert refused.value.code == "workspace_export_contains_secret"
    finally:
        for secret_id in saved:
            await fixture.client.delete("/api/secrets/" + secret_id)
        await fixture.close()
