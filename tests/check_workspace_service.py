"""Acceptance check of the owner's workspace (mandate 7.1.1-7.1.4) against real Docker.

    sudo python3 tests/check_workspace_service.py --image IMAGE [--domain NAME] [--keep]

It installs a throwaway Compose project from the production files (the bundle inside
IMAGE, or this checkout's infra/ with --bundle), starts it with the real `lonora start`
(which creates and mounts the workspace disk), and proves:

- internet egress works from an agent user (--internet-url, default https://example.com);
- the database, the API, Caddy, the host's published port, Docker's resolver, private
  and link-local ranges, Lonora's own domain and MetaApi hosts are unreachable;
- each agent has its own user and home, /workspace/shared is shared, agent processes have
  no capability, no Docker socket and no access to the supervisor's socket;
- files and user-level packages survive a re-creation of the workspace containers, and
  running processes do not;
- the CPU, memory, process, disk and foreground limits are enforced, background
  processes outlive the foreground limit, one or all processes can be stopped;
- a headless browser runs from the terminal;
- with no workspace setting in .env, Compose renders the mandate's defaults
  (2 CPUs, 4 GiB, 256 processes, 10-minute foreground limit) and the Gateway's reservation.

Needs root (the disk is a loop-mounted ext4 file), Docker with Compose, and nothing else:
standard library only. It prints no secret. Exit 0 only if every check passed.
"""

import argparse
import contextlib
import http.client
import json
import os
import secrets
import shutil
import socket
import subprocess
import sys
import tempfile
import time
import uuid
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
RESULTS: list[tuple[bool, str]] = []
META_HOST = "mt-client-api-v1.london.agiliumtrade.ai"


def record(ok: bool, text: str) -> bool:
    RESULTS.append((ok, text))
    print(("PASS " if ok else "FAIL ") + text, flush=True)
    return ok


def sh(*args: str, check: bool = True, **kw: Any) -> subprocess.CompletedProcess[str]:
    return subprocess.run(args, check=check, text=True, capture_output=True, **kw)


class Unix(http.client.HTTPConnection):
    def __init__(self, path: str, timeout: float) -> None:
        super().__init__("localhost", timeout=timeout)
        self.path = path

    def connect(self) -> None:
        self.sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        self.sock.settimeout(self.timeout)
        self.sock.connect(self.path)


class Stack:
    def __init__(self, args: argparse.Namespace) -> None:
        self.args = args
        self.project = "wscheck" + secrets.token_hex(3)
        self.work = Path(tempfile.mkdtemp(prefix="lonora-wscheck-"))
        self.home = self.work / "home"
        self.agent_a = str(uuid.uuid4())
        self.agent_b = str(uuid.uuid4())
        self.port = free_port()

    # --- setup ---------------------------------------------------------------------
    def env(self) -> dict[str, str]:
        return {
            "LONORA_DOMAIN": self.args.domain,
            "LONORA_PROJECT": self.project,
            "LONORA_PROXY_LISTEN": f"127.0.0.1:{self.port}",
            "LONORA_POSTGRES_PASSWORD": secrets.token_hex(16),
            "LONORA_ENCRYPTION_KEY": secrets.token_urlsafe(32)[:43] + "=",
            "LONORA_BOOTSTRAP_TOKEN": secrets.token_urlsafe(24),
            "LONORA_WORKSPACE_DISK": "1g",
            "LONORA_WORKSPACE_MEMORY": "512m",
            "LONORA_WORKSPACE_CPUS": "1.5",
            "LONORA_WORKSPACE_PROCESSES": "64",
            "LONORA_WORKSPACE_FOREGROUND_SECONDS": "5",
            "LONORA_WORKSPACE_BLOCKED_ADDRESSES": self.args.blocked_address,
        }

    def install(self) -> None:
        self.home.mkdir(parents=True)
        bundle = Path(self.args.bundle) if self.args.bundle else self.extract_bundle()
        shutil.copytree(bundle / "infra", self.home / "infra")
        for directory in ("state", "backups", "maintenance"):
            (self.home / directory).mkdir()
        (self.home / ".env").write_text("".join(f"{k}={v}\n" for k, v in self.env().items()))
        os.chmod(self.home / ".env", 0o600)
        (self.home / "state" / "image.env").write_text(f"LONORA_IMAGE={self.args.image}\n")
        started = subprocess.run(
            [str(self.home / "infra/compose/lonora"), "start"],
            text=True,
            capture_output=True,
            env=os.environ | {"LONORA_READY_TIMEOUT": "180"},
        )
        print(started.stdout[-2000:], started.stderr[-2000:], sep="\n")
        record(
            self.running("workspace") and self.running("workspace-net"),
            "lonora start brings up the workspace and its network guard",
        )
        if started.returncode != 0:
            print(
                "note: lonora start did not reach /ready; the workspace checks continue", flush=True
            )

    def extract_bundle(self) -> Path:
        target = self.work / "bundle"
        container = sh("docker", "create", self.args.image).stdout.strip()
        try:
            copied = sh(
                "docker", "cp", "-q", f"{container}:/app/deploy/.", str(target), check=False
            )
        finally:
            sh("docker", "rm", container, check=False)
        if copied.returncode != 0:
            shutil.copytree(ROOT / "infra", target / "infra")
            print("note: the image carries no /app/deploy bundle; using this checkout's infra/")
        return target

    def compose(self, *args: str, env_file: Path | None = None) -> subprocess.CompletedProcess[str]:
        files = [
            "-f",
            "infra/compose/docker-compose.prod.yml",
            "-f",
            "infra/compose/mode-proxy.yml",
        ]
        envs = ["--env-file", str(env_file or self.home / ".env"), "--env-file", "state/image.env"]
        return sh(
            "docker",
            "compose",
            "-p",
            self.project,
            *envs,
            *files,
            *args,
            cwd=self.home,
            check=False,
            env=os.environ | {"LONORA_WORKSPACE_HOST_ADDRESSES": " ".join(host_addresses())},
        )

    def container(self, service: str) -> str:
        return f"{self.project}-{service}-1"

    def running(self, service: str) -> bool:
        state = sh(
            "docker", "inspect", "-f", "{{.State.Running}}", self.container(service), check=False
        )
        return state.stdout.strip() == "true"

    def ip(self, service: str) -> str:
        return sh(
            "docker",
            "inspect",
            "-f",
            "{{range .NetworkSettings.Networks}}{{.IPAddress}} {{end}}",
            self.container(service),
        ).stdout.split()[0]

    def socket_path(self) -> str:
        mount = sh(
            "docker",
            "volume",
            "inspect",
            "-f",
            "{{.Mountpoint}}",
            f"{self.project}_workspace-control",
        ).stdout.strip()
        return f"{mount}/supervisor.sock"

    def call(
        self, method: str, path: str, body: dict[str, Any] | None = None, timeout: float = 60
    ) -> tuple[int, Any]:
        connection = Unix(self.socket_path(), timeout)
        connection.request(
            method,
            path,
            json.dumps(body) if body is not None else None,
            {"content-type": "application/json"},
        )
        response = connection.getresponse()
        return response.status, json.loads(response.read() or b"null")

    def run(self, agent: str, command: str, **extra: Any) -> dict[str, Any]:
        status, value = self.call(
            "POST", "/v1/run", {"agent_id": agent, "command": command, **extra}, timeout=120
        )
        if status != 200:
            raise RuntimeError(f"supervisor answered {status}: {value}")
        return value

    def wait_healthy(self, service: str, seconds: int = 120) -> bool:
        deadline = time.time() + seconds
        while time.time() < deadline:
            health = sh(
                "docker",
                "inspect",
                "-f",
                "{{if .State.Health}}{{.State.Health.Status}}{{else}}{{.State.Status}}{{end}}",
                self.container(service),
                check=False,
            )
            if (
                health.stdout.strip() in {"healthy", "running"}
                and Path(self.socket_path()).exists()
            ):
                with contextlib.suppress(OSError, http.client.HTTPException, ValueError):
                    if self.call("GET", "/v1/health", timeout=5)[0] == 200:
                        return True
            time.sleep(2)
        return False

    def teardown(self) -> None:
        if self.args.keep:
            print(f"kept: {self.home} (project {self.project})")
            return
        self.compose("down", "-v", "--remove-orphans")
        disk = self.home / "workspace-disk"
        sh("umount", str(disk), check=False)
        unit = sh(
            "systemd-escape", "--path", "--suffix=mount", str(disk), check=False
        ).stdout.strip()
        if unit and Path(f"/etc/systemd/system/{unit}").exists():
            sh("systemctl", "disable", unit, check=False)
            Path(f"/etc/systemd/system/{unit}").unlink()
        shutil.rmtree(self.work, ignore_errors=True)


def host_addresses() -> list[str]:
    """The same list `lonora` hands the guard: every global address of this host."""
    if shutil.which("ip"):
        lines = sh("ip", "-o", "addr", "show", "scope", "global", check=False).stdout.split("\n")
        return sorted({ln.split()[3].split("/")[0] for ln in lines if len(ln.split()) > 3})
    return sorted(set(sh("hostname", "-I", check=False).stdout.split()))


def free_port() -> int:
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        return probe.getsockname()[1]


def tcp(stack: Stack, agent: str, host: str, port: int) -> bool:
    """True when an agent user can open a TCP connection to host:port."""
    out = stack.run(
        agent, f"timeout 8 bash -c '</dev/tcp/{host}/{port}' && echo OPEN || echo CLOSED"
    )
    return "OPEN" in out["stdout"]


def check_defaults(stack: Stack) -> None:
    bare = stack.work / "bare.env"
    bare.write_text(
        "".join(
            f"{k}={v}\n" for k, v in stack.env().items() if not k.startswith("LONORA_WORKSPACE_")
        )
    )
    rendered = stack.compose("config", "--format", "json", env_file=bare)
    if not record(rendered.returncode == 0, "Compose renders with no workspace setting"):
        print(rendered.stderr[-1000:])
        return
    services = json.loads(rendered.stdout)["services"]
    ws, gw = services["workspace"], services["gateway"]
    record(float(ws["cpus"]) == 2.0, f"default workspace CPUs are 2 (got {ws['cpus']})")
    record(
        int(ws["mem_limit"]) == 4 * 1024**3,
        f"default workspace memory is 4 GiB (got {ws['mem_limit']})",
    )
    record(int(ws["memswap_limit"]) == 4 * 1024**3, "the workspace has no swap beyond its memory")
    record(
        int(ws["pids_limit"]) == 256,
        f"default workspace process limit is 256 (got {ws['pids_limit']})",
    )
    record(
        ws["environment"]["LONORA_WORKSPACE_FOREGROUND_SECONDS"] == "600",
        "default foreground limit is 10 minutes",
    )
    record(
        ws.get("oom_score_adj") == 1000 and int(ws.get("cpu_shares", 1024)) < 1024,
        "the workspace is first to be killed and last to get CPU",
    )
    record(
        int(gw.get("mem_reservation", 0)) == int(gw["mem_limit"]),
        "the Gateway's memory is reserved",
    )
    record(
        "env_file" not in ws and "env_file" not in services["workspace-net"],
        "no .env (Lonora's secrets) reaches the workspace",
    )
    record(
        not any("docker.sock" in str(v) for v in ws.get("volumes", [])),
        "no Docker socket is mounted into the workspace",
    )


def check_isolation(stack: Stack, internet_url: str) -> None:
    a = stack.agent_a
    out = stack.run(a, f"curl -sS -o /dev/null -w '%{{http_code}}' --max-time 20 {internet_url}")
    record(
        out["stdout"].strip()[:1] in {"2", "3"},
        f"internet reachable from an agent ({internet_url} -> {out['stdout'].strip() or out['stderr'].strip()[:120]})",
    )
    record(not tcp(stack, a, stack.ip("db"), 5432), "the database is unreachable by address")
    record(
        stack.run(a, "getent hosts db api gateway caddy")["exit_code"] != 0,
        "Lonora's service names do not resolve",
    )
    record(not tcp(stack, a, stack.ip("api"), 8000), "the API is unreachable by address")
    record(not tcp(stack, a, stack.ip("caddy"), 8080), "Caddy is unreachable by address")
    gateway = sh(
        "docker",
        "network",
        "inspect",
        "-f",
        "{{range .IPAM.Config}}{{.Gateway}} {{end}}",
        f"{stack.project}_workspace",
    ).stdout.split()
    if gateway:
        record(
            not tcp(stack, a, gateway[0], stack.port),
            f"the host's published Lonora port is unreachable ({gateway[0]})",
        )
    for host, port in (
        ("10.0.0.1", 80),
        ("172.17.0.1", 80),
        ("192.168.1.1", 80),
        ("169.254.169.254", 80),
        ("100.64.0.1", 80),
    ):
        record(not tcp(stack, a, host, port), f"private or link-local {host} is unreachable")
    probe = (
        'python3 -c "import socket,sys;s=socket.socket(2,2);s.settimeout(3);'
        "q=bytes.fromhex('abcd01000001000000000000')+b'\\x02db\\x00\\x00\\x01\\x00\\x01';"
        "s.sendto(q,('127.0.0.11',53));s.recv(512);print('ANSWERED')\""
    )
    record(
        "ANSWERED" not in stack.run(a, probe)["stdout"],
        "Docker's embedded resolver is closed to agents",
    )
    for name in (
        META_HOST,
        "mt-provisioning-api-v1.agiliumtrade.agiliumtrade.ai",
        "app.metaapi.cloud",
        stack.args.domain,
    ):
        record(
            stack.run(a, f"getent ahosts {name}")["exit_code"] != 0,
            f"{name} does not resolve in the workspace",
        )
    for name in (META_HOST, stack.args.domain):
        with contextlib.suppress(OSError):
            addresses = {
                str(info[4][0]) for info in socket.getaddrinfo(name, 443, proto=socket.IPPROTO_TCP)
            }
            for address in sorted(addresses)[:3]:
                if ":" not in address:
                    record(
                        not tcp(stack, a, address, 443),
                        f"{name} is unreachable by its address {address}",
                    )
    if stack.args.blocked_address:
        address = stack.args.blocked_address.split("/")[0]
        record(
            not tcp(stack, a, address, 443),
            f"a configured blocked address ({address}) is unreachable",
        )
    record(
        stack.run(a, "test -e /var/run/docker.sock || test -e /run/docker.sock")["exit_code"] != 0,
        "no Docker socket in the workspace",
    )
    caps = stack.run(a, "grep -E '^(CapEff|CapPrm|CapBnd|NoNewPrivs)' /proc/self/status")["stdout"]
    record(
        "CapEff:\t0000000000000000" in caps and "CapPrm:\t0000000000000000" in caps,
        "agent processes hold no capability",
    )
    record("NoNewPrivs:\t1" in caps, "agent processes cannot gain privileges")
    sock = stack.run(
        a,
        "python3 -c \"import socket;s=socket.socket(1);s.connect('/run/lonora-workspace/supervisor.sock')\"",
    )
    record(sock["exit_code"] != 0, "agents cannot open the supervisor's socket")
    env = stack.run(a, "env")["stdout"]
    record(
        "LONORA_ENCRYPTION_KEY" not in env and "POSTGRES" not in env and "DATABASE_URL" not in env,
        "no Lonora secret in an agent's environment",
    )


def check_users(stack: Stack) -> None:
    a, b = stack.agent_a, stack.agent_b
    ida, idb = (
        stack.run(a, "id -u; echo $HOME")["stdout"].split(),
        stack.run(b, "id -u; echo $HOME")["stdout"].split(),
    )
    record(
        ida[0] != idb[0] and int(ida[0]) >= 20000 and ida[1] != idb[1],
        f"each agent has its own user and home ({ida[0]} {ida[1]}, {idb[0]} {idb[1]})",
    )
    stack.run(a, "echo private > ~/private.txt && echo from-a > /workspace/shared/note.txt")
    record(
        stack.run(b, f"cat {ida[1]}/private.txt")["exit_code"] != 0,
        "an agent cannot read another agent's home",
    )
    record(
        stack.run(b, "echo from-b >> /workspace/shared/note.txt && cat /workspace/shared/note.txt")[
            "stdout"
        ].split()
        == ["from-a", "from-b"],
        "/workspace/shared is readable and writable by every agent",
    )
    record(
        stack.run(a, "ssh -V")["exit_code"] == 0
        and stack.run(a, "git --version")["exit_code"] == 0,
        "SSH and git are on the command line",
    )


def check_secrets(stack: Stack) -> None:
    a, b = stack.agent_a, stack.agent_b
    value = "check-" + secrets.token_hex(12)
    token = "tok_" + "z" * 40
    out = stack.run(
        a,
        'echo "$CHECK_SECRET"; cat /run/secrets/CHECK_SECRET; echo; sh -c \'echo "$LONORA_AGENT_TOKEN"\';'
        " test -e ~/.lonora/token || echo no-token-file",
        secrets={"CHECK_SECRET": value},
        agent_token=token,
    )
    record(
        out["stdout"].split() == [value, value, token, "no-token-file"],
        "a named secret arrives as env NAME and /run/secrets/NAME; the CLI token reaches the command and its children, never a file",
    )
    other = stack.run(b, 'cat /run/secrets/CHECK_SECRET; echo; echo "${LONORA_AGENT_TOKEN-none}"')
    record(
        other["stdout"].split() == [value, "none"],
        "any agent may use a workspace secret by name; another agent's command has no token",
    )
    stack.run(a, "sleep 300", background=True, agent_token=token)
    time.sleep(1)
    environ = stack.run(
        b, "cat /proc/[0-9]*/environ 2>/dev/null | tr '\\0' '\\n' | grep -c LONORA_AGENT_TOKEN"
    )
    record(
        environ["stdout"].strip() in {"", "0"},
        "another agent cannot read a token from a running process",
    )
    stack.call("POST", "/v1/processes/stop-all", {})
    stack.run(a, "true", current_secrets=[])
    record(
        stack.run(a, "test -e /run/secrets/CHECK_SECRET || echo gone")["stdout"].strip() == "gone",
        "a deleted secret leaves /run/secrets",
    )
    mounts = stack.run(a, "grep ' /run/secrets ' /proc/mounts")["stdout"]
    record(mounts.startswith("tmpfs"), "secret files live in memory only (tmpfs)")


def check_browser(stack: Stack) -> None:
    out = stack.run(
        stack.agent_a,
        "chromium --headless --no-sandbox --disable-gpu --dump-dom 'data:text/html,<p id=x>lonora-browser-ok</p>' 2>/dev/null",
    )
    missing = stack.run(stack.agent_a, "command -v chromium")["exit_code"] != 0
    if missing and stack.args.allow_missing_browser:
        print("SKIP headless browser: chromium is not in this image (--allow-missing-browser)")
        return
    record("lonora-browser-ok" in out["stdout"], "a headless browser runs from the terminal")


def check_persistence(stack: Stack, internet: bool) -> None:
    a = stack.agent_a
    uid = stack.run(a, "id -u")["stdout"].strip()
    if internet:
        installed = stack.run(
            a, "pip install -q six 2>&1 | tail -2; python3 -c 'import six; print(six.__file__)'"
        )
        package_ok = installed["exit_code"] == 0 and "/.local/" in installed["stdout"]
        test_import = "python3 -c 'import six'"
    else:
        print("note: no internet egress here; the user-level package is a local pip install")
        stack.run(
            a,
            'mkdir -p ~/src/lonoracheck/lonoracheck && touch ~/src/lonoracheck/lonoracheck/__init__.py && printf \'[project]\\nname="lonoracheck"\\nversion="1"\\n\' > ~/src/lonoracheck/pyproject.toml',
        )
        installed = stack.run(
            a,
            "pip install -q --no-index --no-build-isolation ~/src/lonoracheck 2>&1 | tail -2; python3 -c 'import lonoracheck,sys; print(lonoracheck.__file__)'",
        )
        package_ok = installed["exit_code"] == 0 and "/.local/" in installed["stdout"]
        test_import = "python3 -c 'import lonoracheck'"
    record(package_ok, f"pip install works at user level ({installed['stdout'].strip()[-120:]})")
    stack.run(
        a,
        "echo kept > ~/kept.txt && mkdir -p ~/.local/bin && printf '#!/bin/sh\\necho tool-ok\\n' > ~/.local/bin/mytool && chmod +x ~/.local/bin/mytool",
    )
    stack.run(a, "sleep 3600", background=True)
    before = stack.call("GET", "/v1/health")[1]["boot_id"]
    recreated = stack.compose(
        "up", "-d", "--force-recreate", "--wait", "workspace-net", "workspace"
    )
    record(
        recreated.returncode == 0 and stack.wait_healthy("workspace"),
        "the workspace containers are re-created",
    )
    after = stack.call("GET", "/v1/health")[1]["boot_id"]
    record(before != after, "the supervisor restarted")
    record(
        stack.run(a, "cat ~/kept.txt")["stdout"].strip() == "kept", "files survive a re-creation"
    )
    record(
        stack.run(a, test_import)["exit_code"] == 0
        and stack.run(a, "mytool")["stdout"].strip() == "tool-ok",
        "user-level packages and tools survive a re-creation",
    )
    record(
        stack.run(a, "id -u")["stdout"].strip() == uid, "the agent keeps its uid across re-creation"
    )
    alive = stack.call("GET", "/v1/processes")[1]["processes"]
    record(
        not any("sleep 3600" in p["command"] for p in alive),
        "running processes do not survive a re-creation",
    )


def check_limits(stack: Stack) -> None:
    a = stack.agent_a
    health = stack.call("GET", "/v1/health")[1]
    limits = health["limits"]
    record(
        limits["memory_bytes"] == 512 * 1024**2,
        f"the kernel enforces the configured memory ({limits['memory_bytes']})",
    )
    record(
        limits["processes"] == 64,
        f"the kernel enforces the configured process limit ({limits['processes']})",
    )
    record(limits["cpus"] == 1.5, f"the kernel enforces the configured CPUs ({limits['cpus']})")
    disk = health["disk"]["total_bytes"]
    record(
        0.8 * 1024**3 < disk <= 1024**3,
        f"the workspace disk has the configured size ({disk} bytes)",
    )
    hog = stack.run(a, "python3 -c 'b=bytearray(900*1024*1024); print(len(b))'")
    record(
        hog["exit_code"] != 0 and stack.call("GET", "/v1/health")[0] == 200,
        f"memory beyond the limit is refused and the supervisor survives (exit {hog['exit_code']})",
    )
    forks = stack.run(
        a,
        "python3 -c 'import os,time\nn=0\ntry:\n while n<300:\n  if os.fork()==0:\n   time.sleep(20); os._exit(0)\n  n+=1\n"
        'except OSError as e:\n print("LIMIT", n, e.errno)\'',
    )
    words = forks["stdout"].split()
    record(
        words[:1] == ["LIMIT"] and int(words[1]) < 64,
        f"no more processes than the limit can start ({forks['stdout'].strip()})",
    )
    stack.call("POST", "/v1/processes/stop-all", {"agent_id": a})
    full = stack.run(a, "dd if=/dev/zero of=~/fill bs=1M count=2000 2>&1; rm -f ~/fill")
    record("No space left" in full["stdout"], "writes beyond the workspace disk fail with no space")
    started = time.time()
    fg = stack.run(a, "sleep 30")
    record(
        fg["timed_out"] and time.time() - started < 15,
        f"a foreground command is stopped at the foreground limit ({fg['duration_ms']} ms)",
    )
    bg = stack.run(a, "sleep 600", background=True)["process"]
    time.sleep(8)
    listed = stack.call("GET", "/v1/processes")[1]
    alive = [p for p in listed["processes"] if p["pid"] == bg["pid"]]
    record(
        bool(alive) and alive[0]["agent_id"] == a,
        "a background process outlives the foreground limit and is listed with its agent",
    )
    stopped = stack.call("POST", "/v1/processes/stop", {"pid": bg["pid"]})[1]
    time.sleep(1)
    listed = stack.call("GET", "/v1/processes")[1]
    job = next(j for j in listed["jobs"] if j["id"] == bg["id"])
    record(
        stopped["stopped"]
        and not any(p["pid"] == bg["pid"] for p in listed["processes"])
        and job["stopped"],
        "one process can be stopped",
    )
    for agent in (a, stack.agent_b):
        stack.run(agent, "sleep 900", background=True)
        stack.run(agent, "nohup setsid sleep 901 >/dev/null 2>&1 &")
    status, _ = stack.call("POST", "/v1/processes/stop-all", {})
    record(status == 200, "stop-all is accepted")
    left: list[Any] = []
    for _ in range(10):
        left = stack.call("GET", "/v1/processes")[1]["processes"]
        if not left:
            break
        time.sleep(0.5)
    record(
        not left,
        f"all processes of every agent can be stopped ({len(left)} left: {[(p['pid'], p['state'], p['command'][:40]) for p in left]})",
    )
    status, refused = stack.call("POST", "/v1/processes/stop", {"pid": 1})
    record(
        status == 422 or not refused.get("stopped"),
        "the supervisor never stops a process that is not an agent's",
    )


def check_gateway_socket(stack: Stack) -> None:
    probe = (
        "import socket;s=socket.socket(1);s.connect('/run/lonora-workspace/supervisor.sock');"
        "s.sendall(b'GET /v1/health HTTP/1.0\\r\\n\\r\\n');print(s.recv(64).split()[1].decode())"
    )
    out = sh(
        "docker",
        "run",
        "--rm",
        "--user",
        "10001:10001",
        "--network",
        "none",
        "--entrypoint",
        "python",
        "-v",
        f"{stack.project}_workspace-control:/run/lonora-workspace",
        stack.args.image,
        "-c",
        probe,
        check=False,
    )
    record(out.stdout.strip() == "200", "the Gateway's user (uid 10001) can reach the supervisor")


def main() -> None:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--image", required=True)
    parser.add_argument(
        "--bundle", help="a directory holding infra/ (default: the image's /app/deploy)"
    )
    parser.add_argument(
        "--domain", default="check.lonora.invalid", help="LONORA_DOMAIN for the throwaway stack"
    )
    parser.add_argument("--internet-url", default="https://example.com")
    parser.add_argument(
        "--blocked-address",
        default="1.1.1.1/32",
        help="a public address added to LONORA_WORKSPACE_BLOCKED_ADDRESSES",
    )
    parser.add_argument(
        "--allow-missing-browser",
        action="store_true",
        help="local runs with an image without Chromium",
    )
    parser.add_argument("--keep", action="store_true")
    args = parser.parse_args()
    if os.geteuid() != 0:
        sys.exit("Run as root: the workspace disk is a loop-mounted file.")
    stack = Stack(args)
    try:
        stack.install()
        check_defaults(stack)
        if not record(stack.wait_healthy("workspace"), "the supervisor answers on its socket"):
            print(stack.compose("logs", "--tail", "40", "workspace", "workspace-net").stdout)
            return
        check_gateway_socket(stack)
        check_users(stack)
        check_secrets(stack)
        check_isolation(stack, args.internet_url)
        internet = any(ok and "internet reachable" in text for ok, text in RESULTS)
        check_browser(stack)
        check_limits(stack)
        check_persistence(stack, internet)
    except Exception as error:
        record(False, f"the check stopped: {type(error).__name__}: {str(error)[:300]}")
    finally:
        stack.teardown()
        failed = [text for ok, text in RESULTS if not ok]
        print(f"\n{len(RESULTS) - len(failed)} passed, {len(failed)} failed")
        for text in failed:
            print("  FAIL " + text)
        sys.exit(1 if failed or not RESULTS else 0)


if __name__ == "__main__":
    main()
