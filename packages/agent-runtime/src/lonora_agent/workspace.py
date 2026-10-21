"""Host-side analytical container boundary, not an Agent or financial executor.

This adapter requires a trusted, dedicated host process with Docker access. Never
mount the Docker socket into the API/Gateway or into an analytical container.
Owner authorization, durable snapshots and tool integration belong above this
boundary; there is deliberately no automatic activation in the default registry.
"""

import asyncio
import base64
import hashlib
import json
import logging
import re
from dataclasses import dataclass
from pathlib import PurePosixPath
from typing import cast
from uuid import uuid4

from lonora_core.user_error import LonoraError

MAX_FILES = 128
MAX_FILE_BYTES = 2 * 1024 * 1024
MAX_SNAPSHOT_BYTES = 8 * 1024 * 1024
MAX_TRANSFER_BYTES = 12 * 1024 * 1024
MAX_OUTPUT_BYTES = 128 * 1024
MEMORY_BYTES = 256 * 1024 * 1024
PIDS = 32
CPU_QUOTA = "50000 100000"
logger = logging.getLogger(__name__)
PROXY_VARIABLES = (
    "HTTP_PROXY",
    "HTTPS_PROXY",
    "ALL_PROXY",
    "NO_PROXY",
    "http_proxy",
    "https_proxy",
    "all_proxy",
    "no_proxy",
    "FTP_PROXY",
    "ftp_proxy",
)

# These fixed control programs run from the administrator-pinned Python image.
# No untrusted job is running when EXPORT reads the tmpfs. Docker cp does not
# include tmpfs content, so it cannot provide this snapshot boundary.
QUIESCE = """
import os, signal, time
from pathlib import Path
for attempt in range(100):
    active = []
    for entry in Path('/proc').iterdir():
        if not entry.name.isdecimal():
            continue
        try:
            fields = dict(line.split(':', 1) for line in (entry/'status').read_text().splitlines() if ':' in line)
            if fields['Uid'].split()[0] == '10001' and not fields['State'].strip().startswith('Z'):
                active.append(int(entry.name))
        except (FileNotFoundError, ProcessLookupError):
            pass
    if not active:
        break
    for pid in active:
        try:
            os.kill(pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
    time.sleep(0.005)
else:
    raise RuntimeError('workspace_processes_not_stopped')
"""

EXPORT = """
import base64, json, os, stat
from pathlib import Path
files = {}
total = 0
entries = 0
for parent, dirs, names in os.walk('/work', followlinks=False):
    for name in dirs + names:
        entries += 1
        path = Path(parent)/name
        relative = str(path.relative_to('/work'))
        mode = path.lstat().st_mode
        if entries > 1024 or len(relative) > 256 or len(Path(relative).parts) > 8:
            raise RuntimeError('workspace_snapshot_too_large')
        if stat.S_ISDIR(mode):
            continue
        if not stat.S_ISREG(mode):
            raise RuntimeError('workspace_file_unsafe')
        fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
        with os.fdopen(fd, 'rb') as stream:
            info = os.fstat(stream.fileno())
            if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1 or info.st_size > 2097152:
                raise RuntimeError('workspace_file_unsafe')
            body = stream.read(2097153)
        total += len(body)
        if len(body) > 2097152 or total > 8388608 or len(files) >= 128:
            raise RuntimeError('workspace_snapshot_too_large')
        files[relative] = base64.b64encode(body).decode('ascii')
print(json.dumps(files))
"""


def _path(name: str) -> str:
    path = PurePosixPath(name)
    if (
        not name
        or len(name) > 256
        or len(path.parts) > 8
        or path.is_absolute()
        or any(part in {".", ".."} for part in name.split("/"))
        or "\\" in name
        or "\x00" in name
        or str(path) != name
    ):
        raise LonoraError("workspace_path_unsafe", 422)
    return name


def encode_snapshot(files: dict[str, bytes]) -> bytes:
    """Validate bounded regular-file bytes without reading any host path."""
    if len(files) > MAX_FILES or sum(map(len, files.values())) > MAX_SNAPSHOT_BYTES:
        raise LonoraError("workspace_snapshot_too_large", 422)
    for name, body in files.items():
        _path(name)
        if len(body) > MAX_FILE_BYTES:
            raise LonoraError("workspace_file_too_large", 422)
    return json.dumps(
        {name: base64.b64encode(body).decode("ascii") for name, body in sorted(files.items())}
    ).encode()


def read_snapshot(content: bytes) -> dict[str, bytes]:
    """Validate exported bytes; no archive extraction or host filesystem writes."""
    if len(content) > MAX_TRANSFER_BYTES:
        raise LonoraError("workspace_snapshot_too_large", 422)
    try:

        def pairs(items: list[tuple[str, object]]) -> dict[str, object]:
            result: dict[str, object] = {}
            for key, value in items:
                if key in result:
                    raise LonoraError("workspace_path_duplicate", 422)
                result[key] = value
            return result

        value: object = json.loads(content, object_pairs_hook=pairs)
        if not isinstance(value, dict):
            raise ValueError()
        mapping = cast(dict[str, object], value)
        if len(mapping) > MAX_FILES:
            raise ValueError()
        files: dict[str, bytes] = {}
        for name, encoded in mapping.items():
            if not isinstance(encoded, str):
                raise ValueError()
            files[_path(name)] = base64.b64decode(encoded, validate=True)
        encode_snapshot(files)
        return files
    except (ValueError, TypeError, RecursionError):
        raise LonoraError("workspace_snapshot_invalid", 422) from None


@dataclass(frozen=True)
class WorkspaceResult:
    exit_code: int
    stdout: str
    stderr: str
    files: dict[str, bytes]
    image: str

    @property
    def file_hashes(self) -> dict[str, str]:
        return {name: hashlib.sha256(body).hexdigest() for name, body in self.files.items()}


class AnalyticalContainer:
    """One ephemeral, networkless job with a caller-supplied bounded snapshot.

    The image is an administrator-configured immutable local image ID; no image
    pull, bind mount, Docker flags, environment or executable is supplied by a
    model. Stdout/stderr and files remain untrusted analytical evidence.
    """

    def __init__(self, image: str) -> None:
        if not re.fullmatch(r"sha256:[0-9a-f]{64}", image):
            raise LonoraError("workspace_image_unpinned", 422)
        self.image = image

    def create_arguments(self, name: str) -> list[str]:
        return [
            "create",
            "--pull=never",
            "--name",
            name,
            "--label",
            "ai.lonora.analytical-workspace=1",
            "--network=none",
            "--init",
            "--ipc=private",
            "--cgroupns=private",
            "--read-only",
            "--cap-drop=ALL",
            "--cap-add=KILL",
            "--security-opt=no-new-privileges",
            "--user=0:0",
            "--memory",
            str(MEMORY_BYTES),
            "--memory-swap",
            str(MEMORY_BYTES),
            "--pids-limit",
            str(PIDS),
            "--cpus=0.5",
            "--restart=no",
            "--ulimit",
            "nofile=128:128",
            "--ulimit",
            "core=0:0",
            "--log-driver=none",
            "--workdir=/work",
            "--tmpfs",
            "/work:rw,noexec,nosuid,nodev,size=33554432,uid=10001,gid=10001,mode=0700",
            "--tmpfs",
            "/tmp:rw,noexec,nosuid,nodev,size=8388608,mode=1777",
            *[f"--env={variable}=" for variable in PROXY_VARIABLES],
            "--env=HOME=/work",
            "--entrypoint=/bin/sleep",
            self.image,
            "120",
        ]

    async def _docker(
        self,
        *args: str,
        data: bytes | None = None,
        limit: int = MAX_OUTPUT_BYTES,
        check: bool = True,
    ) -> tuple[int, bytes, bytes]:
        # Explicit endpoint: inherited Docker contexts cannot select a remote
        # privileged daemon. Docker client credentials are never sent to the job.
        process = await asyncio.create_subprocess_exec(
            "docker",
            "--host=unix:///var/run/docker.sock",
            *args,
            stdin=asyncio.subprocess.PIPE if data is not None else asyncio.subprocess.DEVNULL,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )

        async def read(stream: asyncio.StreamReader | None) -> bytes:
            assert stream is not None
            output = bytearray()
            while block := await stream.read(16384):
                output.extend(block)
                if len(output) > limit:
                    raise LonoraError("workspace_output_too_large", 422)
            return bytes(output)

        async def write() -> None:
            if process.stdin is not None:
                try:
                    process.stdin.write(data or b"")
                    await process.stdin.drain()
                except (BrokenPipeError, ConnectionResetError):
                    pass
                finally:
                    process.stdin.close()

        try:
            async with asyncio.TaskGroup() as group:
                stdout_task = group.create_task(read(process.stdout))
                stderr_task = group.create_task(read(process.stderr))
                group.create_task(write())
                group.create_task(process.wait())
        except BaseExceptionGroup as errors:
            # Preserve the public bounded-output failure, not TaskGroup internals.
            if any(isinstance(error, LonoraError) for error in errors.exceptions):
                raise LonoraError("workspace_output_too_large", 422) from None
            raise
        finally:
            if process.returncode is None:
                try:
                    process.kill()
                except ProcessLookupError:
                    pass

            # A cancelled bounded reader can leave asyncio's pipe transport
            # paused. Waiting for exit without draining both pipes then
            # deadlocks even after SIGKILL. Drain even if the child exit was
            # already observed: buffered unread pipe transports still need EOF.
            async def discard(stream: asyncio.StreamReader | None) -> None:
                if stream is not None:
                    while await stream.read(16384):
                        pass

            await asyncio.gather(discard(process.stdout), discard(process.stderr), process.wait())
        stdout, stderr = stdout_task.result(), stderr_task.result()
        code = process.returncode if process.returncode is not None else 125
        if check and code:
            # Daemon messages can include host paths. Do not expose them to the
            # model or logs; command stderr itself is returned separately below.
            raise LonoraError("workspace_backend_unavailable", 503)
        return code, stdout, stderr

    async def _verify(self, name: str) -> None:
        # Test the actual kernel boundary, not merely accepted Docker flags.
        source = (
            "import json,os;from pathlib import Path;"
            "s=dict(line.split(':',1) for line in Path('/proc/self/status').read_text().splitlines() if ':' in line);"
            "print(json.dumps([os.getuid(),"
            "*[Path('/sys/fs/cgroup/'+n).read_text().strip() "
            "for n in ('memory.max','pids.max','cpu.max')],"
            "*[s[n].strip() for n in ('CapEff','NoNewPrivs','Seccomp')],"
            "sorted(os.listdir('/sys/class/net'))]))"
        )
        _, output, _ = await self._docker(
            "exec", "--user=10001:10001", name, "/usr/local/bin/python", "-I", "-c", source
        )
        try:
            actual = json.loads(output)
        except ValueError:
            raise LonoraError("workspace_isolation_unavailable", 503) from None
        if actual != [
            10001,
            str(MEMORY_BYTES),
            str(PIDS),
            CPU_QUOTA,
            "0000000000000000",
            "1",
            "2",
            ["lo"],
        ]:
            raise LonoraError("workspace_isolation_unavailable", 503)

    async def execute(
        self,
        command: str,
        files: dict[str, bytes] | None = None,
        *,
        deadline_seconds: float = 30,
    ) -> WorkspaceResult:
        if (
            not command.strip()
            or "\x00" in command
            or len(command.encode()) > 32768
            or not 0 < deadline_seconds <= 45
        ):
            raise LonoraError("workspace_command_invalid", 422)
        payload = encode_snapshot(files or {})
        name = "lonora-analysis-" + uuid4().hex
        try:
            async with asyncio.timeout(deadline_seconds):
                await self._docker(*self.create_arguments(name))
                await self._docker("start", name)
                await self._verify(name)
                # Docker cp-to-container refuses read-only rootfs even for a
                # writable tmpfs. Bootstrap only our validated regular files via
                # a fixed interpreter program before executing untrusted code.
                bootstrap = (
                    "import base64,json;from pathlib import Path;import sys;"
                    "files=json.load(sys.stdin);"
                    "[(Path(n).parent.mkdir(parents=True,exist_ok=True),"
                    "Path(n).write_bytes(base64.b64decode(v,validate=True))) "
                    "for n,v in files.items()]"
                )
                await self._docker(
                    "exec",
                    "--user=10001:10001",
                    "-i",
                    name,
                    "/usr/local/bin/python",
                    "-I",
                    "-c",
                    bootstrap,
                    data=payload,
                )
                code, stdout, stderr = await self._docker(
                    "exec",
                    "--user=10001:10001",
                    name,
                    "/usr/bin/env",
                    "-i",
                    "PATH=/usr/local/bin:/usr/bin:/bin",
                    "HOME=/work",
                    "TMPDIR=/tmp",
                    "LANG=C.UTF-8",
                    "PYTHONDONTWRITEBYTECODE=1",
                    "/bin/sh",
                    "-c",
                    command,
                    check=False,
                )
                # A fixed root control process can only kill inside this PID
                # namespace (CAP_KILL). Model code always runs as UID10001 with
                # no effective capabilities and cannot alter this root process.
                await self._docker(
                    "exec", "--user=0:0", name, "/usr/local/bin/python", "-I", "-c", QUIESCE
                )
                _, exported, _ = await self._docker(
                    "exec",
                    "--user=10001:10001",
                    name,
                    "/usr/local/bin/python",
                    "-I",
                    "-c",
                    EXPORT,
                    limit=MAX_TRANSFER_BYTES,
                )
                snapshot = read_snapshot(exported)
                return WorkspaceResult(
                    code,
                    stdout.decode(errors="replace"),
                    stderr.decode(errors="replace"),
                    snapshot,
                    self.image,
                )
        except TimeoutError:
            raise LonoraError("workspace_timeout", 408) from None
        finally:
            # Removing the whole container kills descendants and frees tmpfs.
            # Shield cleanup from ordinary task cancellation; bound daemon waits.
            cleanup = asyncio.create_task(self._remove(name))
            try:
                await asyncio.shield(cleanup)
            except asyncio.CancelledError:
                await cleanup
                raise

    async def _remove(self, name: str) -> None:
        try:
            async with asyncio.timeout(10):
                code, _, _ = await self._docker("rm", "--force", name, check=False)
                if code:
                    logger.warning("workspace_cleanup_unconfirmed")
        except (TimeoutError, OSError, LonoraError):
            # The 120-second root PID1 workload lifetime bounds an orphan job.
            # A host supervisor must reap labelled stopped containers on restart.
            logger.warning("workspace_cleanup_unconfirmed")
