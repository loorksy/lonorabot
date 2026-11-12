"""The workspace supervisor: the one root process in the owner's workspace (7.1).

It runs each agent's commands under that agent's own Unix user and home, in the
foreground (bounded by the foreground limit) or in the background (no limit), keeps the
table of processes it started, and stops one process or all of them. It answers only on
a Unix socket that the Gateway's group can open; agent users cannot reach it. It holds
no secret, model, database or broker credential.
"""

import argparse
import asyncio
import base64
import contextlib
import logging
import os
import re
import signal
import socket
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Annotated, Any

from fastapi import FastAPI
from fastapi import Request as HttpRequest
from lonora_security.secrets import SecretScan
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field, StringConstraints

from .users import AGENTS_GID, Users, is_agent_uid, user_name

ROOT = Path("/workspace")
SHARED = ROOT / "shared"
MARKER = ROOT / ".lonora-workspace-disk"
CONTROL = Path("/run/lonora-workspace")
SECRETS = Path("/run/secrets")
FILE_LIMIT = 2 * 1024 * 1024
OUTPUT_LIMIT = 1024 * 1024
ENDED_KEPT = 500
PROTECTED_ENV = {"HOME", "USER", "LOGNAME", "SHELL", "PATH", "PWD", "LONORA_AGENT_TOKEN"}
ENV_NAME = re.compile(r"^[A-Z_][A-Z0-9_]{0,127}$")
SECRET_NAME = r"^[A-Z][A-Z0-9_]{0,63}$"
# Runs as the agent's user: every path below is resolved with the agent's permissions.
WRAPPER = (
    'cd -- "$1" || exit 126\n'
    'if [ -n "$2" ]; then mkdir -p -- "${2%/*}" && exec >>"$2" 2>&1 </dev/null || exit 126; fi\n'
    'exec /bin/bash -c "$3"\n'
)
log = logging.getLogger("lonora.workspace.supervisor")


class Request(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


Command = Annotated[str, StringConstraints(min_length=1, max_length=32768)]


class RunCommand(Request):
    agent_id: uuid.UUID
    command: Command
    background: bool = False
    timeout_seconds: float | None = Field(default=None, gt=0)
    cwd: str | None = Field(default=None, max_length=4096)
    env: dict[str, Annotated[str, StringConstraints(max_length=65536)]] = Field(
        default_factory=dict, max_length=64
    )
    # Workspace secrets the command names (7.2.5): env NAME and the file /run/secrets/NAME.
    secrets: dict[
        Annotated[str, StringConstraints(pattern=SECRET_NAME)],
        Annotated[str, StringConstraints(min_length=1, max_length=16000)],
    ] = Field(default_factory=dict, max_length=64)
    # The agent's CLI token (7.3.3): in the environment only, never in a file, so only
    # this command and its children (the agent's own processes) hold it.
    agent_token: Annotated[str, StringConstraints(pattern=r"^[A-Za-z0-9_-]{16,512}$")] | None = None


AgentPath = Annotated[str, StringConstraints(min_length=1, max_length=4096)]


class ReadFile(Request):
    agent_id: uuid.UUID
    path: AgentPath
    offset: int = Field(default=0, ge=0)
    limit: int = Field(default=FILE_LIMIT, ge=1, le=FILE_LIMIT)


class WriteFile(Request):
    agent_id: uuid.UUID
    path: AgentPath
    content_base64: str = Field(max_length=(FILE_LIMIT * 4) // 3 + 8)
    append: bool = False


class StopProcess(Request):
    pid: int = Field(gt=1)
    # When given, the process must belong to this agent.
    agent_id: uuid.UUID | None = None


class StopAll(Request):
    agent_id: uuid.UUID | None = None


@dataclass
class Job:
    id: str
    agent_id: str
    uid: int
    pid: int
    command: str
    background: bool
    started_at: float
    log: str | None
    ended_at: float | None = None
    exit_code: int | None = None
    stopped: bool = False
    process: Any = field(default=None, repr=False)

    def view(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "agent_id": self.agent_id,
            "pid": self.pid,
            "command": self.command,
            "background": self.background,
            "started_at": self.started_at,
            "ended_at": self.ended_at,
            "exit_code": self.exit_code,
            "stopped": self.stopped,
            "log": self.log,
        }


@dataclass(frozen=True)
class Limits:
    foreground_seconds: float

    @classmethod
    def from_environment(cls) -> "Limits":
        value = float(os.environ.get("LONORA_WORKSPACE_FOREGROUND_SECONDS", "600"))
        if not 0 < value <= 86400:
            raise ValueError("workspace_foreground_limit_invalid")
        return cls(foreground_seconds=value)


def cgroup_limits() -> dict[str, Any]:
    """The limits the kernel enforces on this container, read back (v2, then v1)."""

    def read(*paths: str) -> str | None:
        for path in paths:
            with contextlib.suppress(OSError):
                return Path(path).read_text().strip()
        return None

    memory = read("/sys/fs/cgroup/memory.max", "/sys/fs/cgroup/memory/memory.limit_in_bytes")
    pids = read("/sys/fs/cgroup/pids.max", "/sys/fs/cgroup/pids/pids.max")
    cpu = read("/sys/fs/cgroup/cpu.max")
    if cpu is None:
        quota = read("/sys/fs/cgroup/cpu/cpu.cfs_quota_us")
        period = read("/sys/fs/cgroup/cpu/cpu.cfs_period_us")
        cpu = f"{quota} {period}" if quota and period else None
    cpus = None
    if cpu and cpu.split()[0] not in {"max", "-1"}:
        quota_text, period_text = cpu.split()
        cpus = int(quota_text) / int(period_text)
    return {
        "memory_bytes": int(memory) if memory and memory.isdigit() else None,
        "processes": int(pids) if pids and pids.isdigit() else None,
        "cpus": cpus,
    }


def live_processes(users: Users) -> list[dict[str, Any]]:
    """Every process of an agent user, from /proc: the truth, including children."""
    ticks = os.sysconf("SC_CLK_TCK")
    boot = 0.0
    with contextlib.suppress(OSError, ValueError, StopIteration):
        stat = Path("/proc/stat").read_text().splitlines()
        boot = float(next(line for line in stat if line.startswith("btime")).split()[1])
    found: list[dict[str, Any]] = []
    for entry in Path("/proc").iterdir():
        if not entry.name.isdigit():
            continue
        try:
            uid = owner(int(entry.name))
            if uid is None or not is_agent_uid(uid):
                continue
            raw = (entry / "cmdline").read_bytes()[:4096]
            stat = (entry / "stat").read_text()
        except OSError:
            continue
        fields = stat[stat.rindex(")") + 2 :].split()
        if fields[0] in {"Z", "X"}:
            continue  # ended, waiting to be reaped: no longer running
        found.append(
            {
                "pid": int(entry.name),
                "ppid": int(fields[1]),
                "agent_id": users.agent_of(uid),
                "user": user_name(uid),
                "command": raw.replace(b"\0", b" ").decode("utf-8", "replace").strip(),
                "started_at": boot + int(fields[19]) / ticks,
                "state": fields[0],
            }
        )
    return sorted(found, key=lambda item: item["pid"])


def owner(pid: int) -> int | None:
    """The real uid of a process. Not the owner of /proc/<pid>, which the kernel shows as
    root for a process that made itself non-dumpable (which would hide it)."""
    try:
        status = Path(f"/proc/{pid}/status").read_text()
    except OSError:
        return None
    for line in status.splitlines():
        if line.startswith("Uid:"):
            return int(line.split()[1])
    return None


def stop_family(pid: int, job_id: str) -> None:
    """A job's process group, every descendant that left it (setsid), and every process
    still carrying its job marker (a double-forked daemon, reparented to init)."""
    family = set(descendants(pid)) | marked(job_id)
    with contextlib.suppress(OSError):
        os.killpg(pid, signal.SIGKILL)
    for member in family:
        with contextlib.suppress(OSError):
            os.kill(member, signal.SIGKILL)


def descendants(root: int) -> list[int]:
    """Every live descendant of `root`, by parent links in /proc."""
    children: dict[int, list[int]] = {}
    for entry in Path("/proc").iterdir():
        if not entry.name.isdigit():
            continue
        try:
            stat = (entry / "stat").read_text()
        except OSError:
            continue
        parent = int(stat[stat.rindex(")") + 2 :].split()[1])
        children.setdefault(parent, []).append(int(entry.name))
    found: list[int] = []
    pending = [root]
    while pending:
        for child in children.get(pending.pop(), []):
            found.append(child)
            pending.append(child)
    return found


def running(pid: int) -> bool:
    try:
        stat = Path(f"/proc/{pid}/stat").read_text()
    except OSError:
        return False
    return stat[stat.rindex(")") + 2 :][:1] != "Z"


def signal_agents(sig: int, uids: set[int] | None, users: Users) -> int:
    count = 0
    for item in live_processes(users):
        pid = item["pid"]
        if uids is not None and owner(pid) not in uids:
            continue
        with contextlib.suppress(OSError):
            os.kill(pid, sig)
            count += 1
    return count


async def exited(process: asyncio.subprocess.Process, seconds: float) -> bool:
    """Whether the command's own process ended within `seconds`. Watched through a pidfd,
    not `process.wait()`, which also waits for every pipe to close: a background child
    that keeps stdout open must not hold a foreground command until its limit."""
    loop = asyncio.get_running_loop()
    try:
        descriptor = os.pidfd_open(process.pid)
    except ProcessLookupError:
        return True
    done: asyncio.Future[None] = loop.create_future()
    loop.add_reader(descriptor, lambda: done.done() or done.set_result(None))
    try:
        await asyncio.wait_for(done, seconds)
        return True
    except TimeoutError:
        return False
    finally:
        loop.remove_reader(descriptor)
        os.close(descriptor)


async def returncode(process: asyncio.subprocess.Process) -> int | None:
    for _ in range(100):  # the child watcher reaps it a moment after it ends
        if process.returncode is not None:
            return process.returncode
        await asyncio.sleep(0.02)
    return None


async def watch_network(interval: float = 10) -> None:
    """The workspace lives in the guard's network namespace. If the guard container is
    restarted on its own, that namespace is gone and only loopback is left: exit, so the
    restart policy starts the workspace again inside the guard's new namespace."""
    missed = 0
    while True:
        await asyncio.sleep(interval)
        interfaces = set(os.listdir("/sys/class/net"))
        missed = missed + 1 if interfaces <= {"lo"} else 0
        if missed >= 2:
            log.warning("workspace_network_lost")
            os._exit(1)


class Supervisor:
    def __init__(self, users: Users, limits: Limits) -> None:
        self.users = users
        self.limits = limits
        self.boot_id = str(uuid.uuid4())
        self.jobs: dict[str, Job] = {}
        # job id -> the secrets (name -> value) that job was started with, while it runs.
        self.job_secrets: dict[str, dict[str, str]] = {}
        self.lock = asyncio.Lock()

    def environment(self, uid: int, extra: dict[str, str]) -> dict[str, str]:
        home = str(self.users.home(uid))
        local = f"{home}/.local"
        base = {
            "HOME": home,
            "USER": user_name(uid),
            "LOGNAME": user_name(uid),
            "SHELL": "/bin/bash",
            "PATH": f"{local}/bin:{home}/bin:/usr/local/bin:/usr/bin:/bin",
            "LANG": "C.UTF-8",
            "TMPDIR": "/tmp",
            "PYTHONUSERBASE": local,
            "NPM_CONFIG_PREFIX": local,
            "LONORA_WORKSPACE_SHARED": str(SHARED),
        }
        for name in extra:
            if not ENV_NAME.match(name) or name in PROTECTED_ENV:
                raise ValueError("workspace_environment_invalid")
        return base | extra

    def place_secrets(self, secrets: dict[str, str]) -> None:
        """/run/secrets/NAME, root:agents 0440 on a tmpfs: any agent may use any workspace
        secret by name (7.2.4). Rewritten on each use, so a rotated value takes effect, and
        removed when no running job named it (`release`)."""
        for name, value in secrets.items():
            temporary = SECRETS / f".{name}.{uuid.uuid4().hex}"
            try:
                descriptor = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o440)
                try:
                    os.write(descriptor, value.encode())
                    os.fchown(descriptor, 0, AGENTS_GID)
                    os.fchmod(descriptor, 0o440)
                finally:
                    os.close(descriptor)
                os.replace(temporary, SECRETS / name)
            except OSError:
                temporary.unlink(missing_ok=True)
                raise

    def release(self, job_id: str) -> None:
        """A job ended: each secret file no running job names any more is removed."""
        named = self.job_secrets.pop(job_id, {})
        still = {name for values in self.job_secrets.values() for name in values}
        for name in set(named) - still:
            (SECRETS / name).unlink(missing_ok=True)

    def guard(self, value: Any) -> Any:
        """Every value a running job was given, also old (rotated) and deleted ones,
        replaced in what the supervisor answers. The Gateway scans current values; only
        the supervisor knows which older ones are still alive in processes."""
        pairs = {(n, v) for values in self.job_secrets.values() for n, v in values.items()}
        while pairs:
            batch: dict[str, str] = {}
            for name, secret in sorted(pairs):
                batch.setdefault(name, secret)
            pairs -= set(batch.items())
            value = SecretScan(batch).data(value)
        return value

    async def start(self, request: RunCommand) -> tuple[Job, asyncio.subprocess.Process]:
        if "\0" in request.command or (request.cwd and "\0" in request.cwd):
            raise ValueError("workspace_command_invalid")
        async with self.lock:
            uid = self.users.ensure(str(request.agent_id))
        job_id = uuid.uuid4().hex
        home = self.users.home(uid)
        cwd = request.cwd or str(home)
        if not cwd.startswith("/"):
            raise ValueError("workspace_cwd_invalid")
        log_path = f"{home}/.lonora/processes/{job_id}.log" if request.background else ""
        pipe = asyncio.subprocess.DEVNULL if request.background else asyncio.subprocess.PIPE
        env = self.environment(uid, request.env)
        if set(request.secrets) & (PROTECTED_ENV | set(request.env)):
            raise ValueError("workspace_secret_name_invalid")
        self.place_secrets(request.secrets)
        env |= request.secrets
        if request.agent_token:
            env["LONORA_AGENT_TOKEN"] = request.agent_token
        process = await asyncio.create_subprocess_exec(
            "/bin/bash",
            "-c",
            WRAPPER,
            "lonora-workspace",
            cwd,
            log_path,
            request.command,
            stdin=asyncio.subprocess.DEVNULL,
            stdout=pipe,
            stderr=pipe,
            cwd="/",
            env=env,
            user=uid,
            group=uid,
            extra_groups=[AGENTS_GID],
            umask=0o002,
            start_new_session=True,
        )
        job = Job(
            id=job_id,
            agent_id=str(request.agent_id),
            uid=uid,
            pid=process.pid,
            command=request.command,
            background=request.background,
            started_at=time.time(),
            log=log_path or None,
            process=process,
        )
        self.jobs[job_id] = job
        if request.secrets:
            self.job_secrets[job_id] = dict(request.secrets)
        return job, process

    def ended(self, job: Job, code: int | None) -> None:
        self.release(job.id)
        job.ended_at = time.time()
        job.exit_code = code
        job.process = None
        finished = [j for j in self.jobs.values() if j.ended_at is not None]
        for old in sorted(finished, key=lambda j: j.ended_at or 0)[:-ENDED_KEPT]:
            self.jobs.pop(old.id, None)

    async def watch(self, job: Job, process: asyncio.subprocess.Process) -> None:
        await process.wait()
        self.ended(job, process.returncode)

    async def foreground(self, request: RunCommand) -> dict[str, Any]:
        limit = self.limits.foreground_seconds
        timeout = min(request.timeout_seconds or limit, limit)
        job, process = await self.start(request)
        started = time.monotonic()
        streams = {"stdout": bytearray(), "stderr": bytearray()}
        dropped = {"stdout": 0, "stderr": 0}

        async def drain(name: str, stream: asyncio.StreamReader | None) -> None:
            if stream is None:
                return
            while block := await stream.read(65536):
                room = OUTPUT_LIMIT - len(streams[name])
                streams[name].extend(block[:room])
                dropped[name] += max(0, len(block) - room)

        readers = [
            asyncio.create_task(drain("stdout", process.stdout)),
            asyncio.create_task(drain("stderr", process.stderr)),
        ]
        try:
            timed_out = not await exited(process, timeout)
        except asyncio.CancelledError:
            # The caller went away (its run was cancelled): the command stops with it.
            stop_family(process.pid, job.id)
            for task in readers:
                task.cancel()
            self.ended(job, None)
            raise
        if timed_out:
            # Its process group, and every descendant that left it (setsid, daemonize).
            family = descendants(process.pid)
            with contextlib.suppress(OSError):
                os.killpg(process.pid, signal.SIGKILL)
            for pid in family:
                with contextlib.suppress(OSError):
                    os.kill(pid, signal.SIGKILL)
            await exited(process, 10)
        code = await returncode(process)
        # A background child may keep the pipes open: read what is there, then stop.
        _, pending = await asyncio.wait(readers, timeout=1)
        for task in pending:
            task.cancel()
        # Release our ends of the pipes; a child still holding them gets SIGPIPE, not a hang.
        process._transport.close()  # pyright: ignore[reportPrivateUsage, reportUnknownMemberType, reportAttributeAccessIssue]
        answer = self.guard(
            {
                "stdout": streams["stdout"].decode("utf-8", "replace"),
                "stderr": streams["stderr"].decode("utf-8", "replace"),
            }
        )
        self.ended(job, code)
        return {
            "boot_id": self.boot_id,
            "id": job.id,
            "exit_code": code,
            "timed_out": timed_out,
            "duration_ms": int((time.monotonic() - started) * 1000),
            "stdout": answer["stdout"],
            "stderr": answer["stderr"],
            "stdout_dropped_bytes": dropped["stdout"],
            "stderr_dropped_bytes": dropped["stderr"],
        }

    async def background(self, request: RunCommand) -> dict[str, Any]:
        if request.timeout_seconds is not None:
            raise ValueError("workspace_background_has_no_timeout")
        job, process = await self.start(request)
        asyncio.get_running_loop().create_task(self.watch(job, process))
        return {"boot_id": self.boot_id, "process": job.view()}

    async def as_agent(
        self, agent_id: uuid.UUID, script: str, *args: str, data: bytes = b""
    ) -> tuple[int, bytes, bytes]:
        """A short command as the agent's own user, from its home: every path is resolved
        with the agent's permissions, never root's."""
        async with self.lock:
            uid = self.users.ensure(str(agent_id))
        process = await asyncio.create_subprocess_exec(
            "/bin/bash",
            "-c",
            'cd -- "$HOME" || exit 126\n' + script,
            "lonora-workspace",
            *args,
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd="/",
            env=self.environment(uid, {}),
            user=uid,
            group=uid,
            extra_groups=[AGENTS_GID],
            umask=0o002,
            start_new_session=True,
        )
        try:
            out, err = await asyncio.wait_for(process.communicate(data), 60)
        except TimeoutError:
            with contextlib.suppress(OSError):
                os.killpg(process.pid, signal.SIGKILL)
            raise ValueError("workspace_file_timeout") from None
        return process.returncode or 0, out, err

    async def read_file(self, request: ReadFile) -> dict[str, Any]:
        code, out, err = await self.as_agent(
            request.agent_id,
            '[ -f "$1" ] || { echo "not a regular file" >&2; exit 3; }\n'
            'stat -L -c %s -- "$1" && tail -c +"$2" -- "$1" | head -c "$3"',
            request.path,
            str(request.offset + 1),
            str(request.limit),
        )
        if code != 0:
            return {
                "boot_id": self.boot_id,
                "ok": False,
                "error": err.decode("utf-8", "replace")[-2000:],
            }
        size_line, _, body = out.partition(b"\n")
        size = int(size_line)
        if self.job_secrets:
            text = body.decode("utf-8", "replace")
            guarded = self.guard(text)
            if guarded != text:
                body = guarded.encode()
        return {
            "boot_id": self.boot_id,
            "ok": True,
            "size": size,
            "offset": request.offset,
            "content_base64": base64.b64encode(body).decode(),
            "truncated": request.offset + len(body) < size,
        }

    async def write_file(self, request: WriteFile) -> dict[str, Any]:
        try:
            data = base64.b64decode(request.content_base64, validate=True)
        except ValueError:
            raise ValueError("workspace_file_content_invalid") from None
        if len(data) > FILE_LIMIT:
            raise ValueError("workspace_file_too_large")
        operator = ">>" if request.append else ">"
        code, _, err = await self.as_agent(
            request.agent_id,
            f'case "$1" in */*) mkdir -p -- "${{1%/*}}" || exit 3;; esac\ncat {operator}"$1" && stat -c %s -- "$1"',
            request.path,
            data=data,
        )
        if code != 0:
            return {
                "boot_id": self.boot_id,
                "ok": False,
                "error": err.decode("utf-8", "replace")[-2000:],
            }
        return {"boot_id": self.boot_id, "ok": True, "written": len(data)}

    def processes(self) -> dict[str, Any]:
        jobs = sorted(self.jobs.values(), key=lambda job: job.started_at)
        return self.guard(
            {
                "boot_id": self.boot_id,
                "jobs": [job.view() for job in jobs],
                "processes": live_processes(self.users),
            }
        )

    async def stop(self, pid: int, agent_id: uuid.UUID | None = None) -> bool:
        uid = owner(pid)
        if uid is None or not is_agent_uid(uid):
            return False
        if agent_id is not None and self.users.by_agent.get(str(agent_id)) != uid:
            return False
        job = next((j for j in self.jobs.values() if j.pid == pid and j.ended_at is None), None)
        with contextlib.suppress(OSError):
            if job is not None:
                job.stopped = True
                os.killpg(pid, signal.SIGTERM)
            else:
                os.kill(pid, signal.SIGTERM)
        for _ in range(30):
            await asyncio.sleep(0.1)
            if not running(pid):
                return True
        with contextlib.suppress(OSError):
            if job is not None:
                os.killpg(pid, signal.SIGKILL)
            else:
                os.kill(pid, signal.SIGKILL)
        return True

    async def stop_all(self, agent_id: uuid.UUID | None) -> int:
        uids: set[int] | None = None
        if agent_id is not None:
            uid = self.users.by_agent.get(str(agent_id))
            uids = {uid} if uid is not None else set()
        for job in self.jobs.values():
            if job.ended_at is None and (uids is None or job.uid in uids):
                job.stopped = True
        total = signal_agents(signal.SIGKILL, uids, self.users)
        for _ in range(50):
            await asyncio.sleep(0.05)
            if not signal_agents(signal.SIGKILL, uids, self.users):
                break
        return total


def create_app(supervisor: Supervisor) -> FastAPI:
    app = FastAPI(docs_url=None, redoc_url=None, openapi_url=None)

    @app.exception_handler(RequestValidationError)
    async def invalid(request: Any, error: RequestValidationError) -> JSONResponse:
        # Never echo the input: it can hold a secret's value.
        fields = [{"loc": list(e.get("loc", ())), "type": e.get("type")} for e in error.errors()]
        return JSONResponse(
            {"code": "workspace_request_invalid", "errors": fields, "boot_id": supervisor.boot_id},
            status_code=422,
        )

    def refused(code: str, status: int = 422) -> JSONResponse:
        return JSONResponse({"code": code, "boot_id": supervisor.boot_id}, status_code=status)

    @app.get("/v1/health")
    async def health() -> dict[str, Any]:
        disk = os.statvfs(ROOT)
        return {
            "boot_id": supervisor.boot_id,
            "foreground_seconds": supervisor.limits.foreground_seconds,
            "limits": cgroup_limits(),
            "disk": {
                "total_bytes": disk.f_blocks * disk.f_frsize,
                "free_bytes": disk.f_bavail * disk.f_frsize,
            },
        }

    @app.post("/v1/run", response_model=None)
    async def run(request: RunCommand, http: HttpRequest) -> dict[str, Any] | JSONResponse:
        try:
            if request.background:
                return await supervisor.background(request)
            task = asyncio.create_task(supervisor.foreground(request))
            while True:
                done, _ = await asyncio.wait({task}, timeout=1)
                if done:
                    return task.result()
                if await http.is_disconnected():
                    task.cancel()
                    with contextlib.suppress(asyncio.CancelledError):
                        await task
                    return refused("workspace_caller_gone", 499)
        except ValueError as error:
            return refused(str(error))
        except OSError:
            # Typically the process limit: nothing was started.
            return refused("workspace_start_failed", 503)

    @app.post("/v1/files/read", response_model=None)
    async def read_file(request: ReadFile) -> dict[str, Any] | JSONResponse:
        try:
            return await supervisor.read_file(request)
        except ValueError as error:
            return refused(str(error))

    @app.post("/v1/files/write", response_model=None)
    async def write_file(request: WriteFile) -> dict[str, Any] | JSONResponse:
        try:
            return await supervisor.write_file(request)
        except ValueError as error:
            return refused(str(error))

    @app.get("/v1/processes")
    async def processes() -> dict[str, Any]:
        return supervisor.processes()

    @app.post("/v1/processes/stop")
    async def stop(request: StopProcess) -> dict[str, Any]:
        return {
            "boot_id": supervisor.boot_id,
            "stopped": await supervisor.stop(request.pid, request.agent_id),
        }

    @app.post("/v1/processes/stop-all")
    async def stop_all(request: StopAll) -> dict[str, Any]:
        return {
            "boot_id": supervisor.boot_id,
            "stopped": await supervisor.stop_all(request.agent_id),
        }

    return app


def prepare(root: Path, control_gid: int) -> Users:
    if not (root / MARKER.name).is_file():
        # The workspace disk is not mounted: refuse rather than write to the host disk.
        raise SystemExit("workspace_disk_missing")
    users = Users(root)
    users.load()
    shared = root / SHARED.name
    shared.mkdir(exist_ok=True)
    os.chown(shared, 0, AGENTS_GID, follow_symlinks=False)
    os.chmod(shared, 0o2775)
    SECRETS.mkdir(mode=0o750, exist_ok=True)
    os.chown(SECRETS, 0, AGENTS_GID)
    os.chmod(SECRETS, 0o750)
    for stale in SECRETS.iterdir():
        stale.unlink()
    CONTROL.mkdir(mode=0o750, exist_ok=True)
    os.chown(CONTROL, 0, control_gid)
    os.chmod(CONTROL, 0o750)
    return users


def serve() -> None:
    import uvicorn

    control_gid = int(os.environ.get("LONORA_WORKSPACE_CONTROL_GID", "10001"))
    supervisor = Supervisor(prepare(ROOT, control_gid), Limits.from_environment())
    path = CONTROL / "supervisor.sock"
    path.unlink(missing_ok=True)
    with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as listener:
        previous = os.umask(0o177)
        try:
            listener.bind(str(path))
        finally:
            os.umask(previous)
        os.chown(path, 0, control_gid)
        os.chmod(path, 0o660)
        listener.listen(64)
        listener.setblocking(False)
        config = uvicorn.Config(
            create_app(supervisor),
            access_log=False,
            log_level="warning",
            timeout_keep_alive=5,
            limit_max_requests=None,
            timeout_graceful_shutdown=5,
        )
        log.warning("workspace_supervisor_ready boot_id=%s", supervisor.boot_id)

        async def run() -> None:
            watcher = asyncio.create_task(watch_network())
            try:
                await uvicorn.Server(config).serve(sockets=[listener])
            finally:
                watcher.cancel()

        asyncio.run(run())


def main() -> None:
    argparse.ArgumentParser(description=__doc__).parse_args()
    logging.basicConfig(level=logging.WARNING, format="%(message)s")
    serve()


if __name__ == "__main__":
    main()
