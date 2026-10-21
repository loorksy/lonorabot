"""Offline validation of the host/container transfer and immutable job contract."""

import base64
import json

import pytest
from lonora_agent.workspace import (
    MAX_FILE_BYTES,
    MAX_FILES,
    MAX_TRANSFER_BYTES,
    PROXY_VARIABLES,
    AnalyticalContainer,
    WorkspaceResult,
    encode_snapshot,
    read_snapshot,
)
from lonora_core.user_error import LonoraError

IMAGE = "sha256:" + "a" * 64


def test_binary_snapshot_roundtrip_and_hashes() -> None:
    files = {"analysis/result.bin": bytes(range(256)), "notes.txt": b"current evidence"}
    assert read_snapshot(encode_snapshot(files)) == files
    result = WorkspaceResult(0, "done", "", files, IMAGE)
    assert result.file_hashes["analysis/result.bin"] == (
        "40aff2e9d2d8922e47afd4648e6967497158785fbd1da870e7110266bf944880"
    )


@pytest.mark.parametrize(
    "name",
    ["", "../secret", "/etc/passwd", "a/../b", "a/./b", "a//b", "a\\b", "a\x00b", "a/", "x" * 257],
)
def test_unsafe_names_rejected_in_both_directions(name: str) -> None:
    with pytest.raises(LonoraError, match="workspace_path_unsafe"):
        encode_snapshot({name: b"test"})
    with pytest.raises(LonoraError, match="workspace_path_unsafe"):
        read_snapshot(json.dumps({name: "dGVzdA=="}).encode())


def test_snapshot_limits() -> None:
    with pytest.raises(LonoraError, match="workspace_snapshot_too_large"):
        encode_snapshot({f"file{index}": b"" for index in range(MAX_FILES + 1)})
    with pytest.raises(LonoraError, match="workspace_file_too_large"):
        encode_snapshot({"large": b"x" * (MAX_FILE_BYTES + 1)})
    with pytest.raises(LonoraError, match="workspace_snapshot_too_large"):
        encode_snapshot({f"file{index}": b"x" * MAX_FILE_BYTES for index in range(5)})
    with pytest.raises(LonoraError, match="workspace_snapshot_too_large"):
        read_snapshot(b" " * (MAX_TRANSFER_BYTES + 1))


@pytest.mark.parametrize("content", [b"[]", b"null", b'{"x":12}', b'{"x":"!"}', b"invalid"])
def test_invalid_transfer_rejected(content: bytes) -> None:
    with pytest.raises(LonoraError, match="workspace_snapshot_invalid"):
        read_snapshot(content)


def test_duplicate_keys_are_not_silently_replaced() -> None:
    with pytest.raises(LonoraError, match="workspace_path_duplicate"):
        read_snapshot(b'{"same":"YQ==","same":"Yg=="}')


def test_export_is_revalidated_against_input_limits() -> None:
    payload = json.dumps({"large": base64.b64encode(b"x" * (MAX_FILE_BYTES + 1)).decode()})
    with pytest.raises(LonoraError, match="workspace_file_too_large"):
        read_snapshot(payload.encode())


@pytest.mark.parametrize(
    "image", ["python:latest", "python@sha256:" + "a" * 64, "sha256:" + "a" * 63]
)
def test_mutable_or_remote_image_identity_is_not_allowed(image: str) -> None:
    with pytest.raises(LonoraError, match="workspace_image_unpinned"):
        AnalyticalContainer(image)


def test_fixed_boundary_has_no_mounts_or_credential_inheritance() -> None:
    args = AnalyticalContainer(IMAGE).create_arguments("lonora-analysis-test")
    assert "--network=none" in args and "--read-only" in args
    assert "--security-opt=no-new-privileges" in args and "--cap-drop=ALL" in args
    assert "--pids-limit" in args and "--memory-swap" in args and "--cpus=0.5" in args
    assert not any(value.startswith(("--mount", "--volume", "--privileged")) for value in args)
    assert all(f"--env={name}=" in args for name in PROXY_VARIABLES)
    assert args[-2:] == [IMAGE, "120"]


@pytest.mark.asyncio
async def test_invalid_command_never_contacts_docker() -> None:
    backend = AnalyticalContainer(IMAGE)
    for command in ["", " ", "x\x00y", "x" * 32769]:
        with pytest.raises(LonoraError, match="workspace_command_invalid"):
            await backend.execute(command)
    with pytest.raises(LonoraError, match="workspace_command_invalid"):
        await backend.execute("echo done", deadline_seconds=46)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "field,value",
    [
        (1, "max"),
        (2, "max"),
        (3, "max 100000"),
        (4, "0000000000000020"),
        (5, "0"),
        (6, "0"),
        (7, ["lo", "eth0"]),
    ],
)
async def test_missing_kernel_boundary_blocks_command_and_removes_job(
    field: int, value: object
) -> None:
    calls: list[tuple[str, ...]] = []
    observed: list[object] = [
        10001,
        "268435456",
        "32",
        "50000 100000",
        "0000000000000000",
        "1",
        "2",
        ["lo"],
    ]
    observed[field] = value

    class UnavailableBoundary(AnalyticalContainer):
        async def _docker(
            self,
            *args: str,
            data: bytes | None = None,
            limit: int = 131072,
            check: bool = True,
        ) -> tuple[int, bytes, bytes]:
            calls.append(args)
            if args[0] == "exec":
                assert "/bin/sh" not in args, "Command ran before kernel validation"
                return 0, json.dumps(observed).encode(), b""
            return 0, b"", b""

    with pytest.raises(LonoraError, match="workspace_isolation_unavailable"):
        await UnavailableBoundary(IMAGE).execute("must-not-run")
    assert [args[0] for args in calls] == ["create", "start", "exec", "rm"]


def test_host_identity_is_not_a_docker_argument() -> None:
    with pytest.raises(LonoraError, match="workspace_host_identity_invalid"):
        AnalyticalContainer(IMAGE, namespace="--privileged")


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "name,allowed", [("lonora-analysis-" + "a" * 32, True), ("other-container", False)]
)
async def test_reaper_filters_host_identity_and_rejects_foreign_names(
    name: str, allowed: bool
) -> None:
    calls: list[tuple[str, ...]] = []

    class HostFixture(AnalyticalContainer):
        async def _docker(
            self, *args: str, data: bytes | None = None, limit: int = 131072, check: bool = True
        ) -> tuple[int, bytes, bytes]:
            calls.append(args)
            return 0, name.encode() if args[0] == "ps" else b"", b""

    host = HostFixture(IMAGE, namespace="b" * 32)
    if allowed:
        await host.reap_orphans()
        assert calls[1] == ("rm", "--force", name)
    else:
        with pytest.raises(LonoraError, match="workspace_orphan_identity_invalid"):
            await host.reap_orphans()
        assert len(calls) == 1
    assert "label=ai.lonora.analytical-host=" + "b" * 32 in calls[0]
