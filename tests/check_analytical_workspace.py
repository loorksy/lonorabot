"""Explicit local Docker acceptance; never accesses a broker or production DB.

Build infra/analysis/Dockerfile first, then pass its immutable local image ID:
  .venv/bin/python tests/check_analytical_workspace.py sha256:<image-id>
This suite intentionally fails rather than skips when Docker isolation is absent.
"""

import asyncio
import json
import os
import shlex
import sys

from lonora_agent.workspace import AnalyticalContainer
from lonora_core.user_error import LonoraError


def python(source: str) -> str:
    return "python -c " + shlex.quote(source)


async def expect_error(backend: AnalyticalContainer, command: str, expected: str) -> None:
    try:
        await backend.execute(command)
    except LonoraError as error:
        assert error.code == expected, error.code
    else:
        raise AssertionError("Untrusted workload did not fail closed")


async def main(image: str) -> None:
    backend = AnalyticalContainer(image)
    os.environ["LONORA_WORKSPACE_TEST_SECRET"] = "not-a-real-secret-sentinel"
    checks = 0
    result = await backend.execute(
        python(
            "from pathlib import Path;print(Path('input.txt').read_text());Path('result.txt').write_text('computed')"
        ),
        {"input.txt": b"verified input"},
    )
    assert result.exit_code == 0 and result.stdout == "verified input\n"
    assert result.files == {"input.txt": b"verified input", "result.txt": b"computed"}
    reused = await backend.execute("cat result.txt", result.files)
    assert reused.stdout == "computed"
    checks += 1

    isolated = await backend.execute(
        python("""
import importlib.util, json, os, socket
from pathlib import Path
status = Path('/proc/self/status').read_text()
assert os.getuid() == 10001
assert 'CapEff:\\t0000000000000000' in status
assert 'NoNewPrivs:\\t1' in status
assert 'Seccomp:\\t2' in status
assert not any(key in os.environ for key in ('LONORA_WORKSPACE_TEST_SECRET','DATABASE_URL','METAAPI_TOKEN','OPENAI_API_KEY'))
assert b'not-a-real-secret-sentinel' not in Path('/proc/1/environ').read_bytes() if os.access('/proc/1/environ', os.R_OK) else True
assert not Path('/var/run/docker.sock').exists()
assert not Path('/app').exists() and not Path('/workspace/lonorabot').exists()
assert importlib.util.find_spec('metaapi_cloud_sdk') is None
assert importlib.util.find_spec('lonora_trading') is None
assert set(os.listdir('/sys/class/net')) == {'lo'}
try:
    socket.create_connection(('1.1.1.1',443), timeout=0.25)
except OSError:
    pass
else:
    raise AssertionError('Network unexpectedly available')
try:
    Path('/etc/workspace-must-not-write').write_text('invalid')
except OSError:
    pass
else:
    raise AssertionError('Root filesystem unexpectedly writable')
print(json.dumps({'isolated':True}))
""")
    )
    assert isolated.exit_code == 0, isolated.stderr
    assert json.loads(isolated.stdout) == {"isolated": True}
    checks += 1

    left, right = await asyncio.gather(
        backend.execute("cat exact-symbol.txt", {"exact-symbol.txt": b"EURUSD.suffix"}),
        backend.execute("cat exact-symbol.txt", {"exact-symbol.txt": b"BTCUSD.other"}),
    )
    assert left.stdout == "EURUSD.suffix" and right.stdout == "BTCUSD.other"
    assert left.files != right.files
    checks += 1

    failed = await backend.execute("echo actual-command-error >&2; exit 7")
    assert failed.exit_code == 7 and failed.stderr == "actual-command-error\n"
    checks += 1

    for command in ["ln -s /etc/passwd unsafe", "mkfifo unsafe", "ln a.txt b.txt"]:
        try:
            await backend.execute(command, {"a.txt": b"input"})
        except LonoraError as error:
            assert error.code == "workspace_backend_unavailable"
        else:
            raise AssertionError("Unsafe file exported")
        checks += 1

    await expect_error(backend, python("print('x' * 400000)"), "workspace_output_too_large")
    checks += 1
    try:
        await backend.execute("sleep 60", deadline_seconds=3)
    except LonoraError as error:
        assert error.code == "workspace_timeout"
    else:
        raise AssertionError("Execution deadline not enforced")
    checks += 1

    # A completed shell may leave detached descendants. They must be terminated
    # before snapshot export, without stopping the trusted root control process.
    background = await backend.execute(
        "(while true; do echo updating > changing.txt; done) >/dev/null 2>&1 & sleep 0.1; echo returned"
    )
    assert background.exit_code == 0 and background.stdout == "returned\n"
    assert "changing.txt" in background.files
    checks += 1

    pids = await backend.execute(
        python("""
import errno, subprocess
jobs = []
try:
    for _ in range(64):
        jobs.append(subprocess.Popen(['sleep','10']))
except OSError as error:
    assert error.errno == errno.EAGAIN
else:
    raise AssertionError('Process limit was not enforced')
finally:
    for job in jobs:
        job.kill()
    for job in jobs:
        job.wait()
print(len(jobs))
""")
    )
    assert pids.exit_code == 0 and 1 < int(pids.stdout) < 32, pids.stderr
    checks += 1

    memory = await backend.execute(python("a=bytearray(512*1024*1024);print('unexpected-success')"))
    assert memory.exit_code != 0 and "unexpected-success" not in memory.stdout
    checks += 1

    scratch = await backend.execute(
        python("""
import errno
from pathlib import Path
written = 0
try:
    with open('/tmp/fill', 'wb') as stream:
        for _ in range(100):
            written += stream.write(b'x' * 1048576)
except OSError as error:
    assert error.errno == errno.ENOSPC
else:
    raise AssertionError('Scratch quota was not enforced')
finally:
    Path('/tmp/fill').unlink(missing_ok=True)
assert 0 < written <= 8388608
print('scratch-bounded')
""")
    )
    assert scratch.exit_code == 0 and scratch.stdout == "scratch-bounded\n", scratch.stderr
    checks += 1

    task = asyncio.create_task(backend.execute("sleep 60"))
    await asyncio.sleep(2)
    task.cancel()
    try:
        await task
    except asyncio.CancelledError:
        pass
    else:
        raise AssertionError("Task cancellation was lost")
    checks += 1

    process = await asyncio.create_subprocess_exec(
        "docker",
        "--host=unix:///var/run/docker.sock",
        "ps",
        "--all",
        "--filter",
        "label=ai.lonora.analytical-workspace=1",
        "--format",
        "{{.Names}}",
        stdout=asyncio.subprocess.PIPE,
    )
    output, _ = await process.communicate()
    assert process.returncode == 0
    assert not output.strip(), "An analytical container leaked after acceptance"
    print(f"PASS: {checks} actual analytical-container acceptance checks; no broker access")


if __name__ == "__main__":
    asyncio.run(main(sys.argv[1]))
