"""A Gateway whose event loop is blocked exits so its restart policy brings it back (P1-06).

Neither Docker's ``restart: unless-stopped`` nor systemd's ``Restart=on-failure`` fires
for a process that is alive but stuck, so the worker watches its own loop from a plain
thread and leaves with exit code 70 once the loop has not run for the limit.
"""

import os
import subprocess
import sys
import textwrap
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

BLOCKED = textwrap.dedent(
    """
    import asyncio
    import time

    from lonora_worker.main import stall_guard


    async def main() -> None:
        async with stall_guard(2.0):
            await asyncio.sleep(0.2)
            time.sleep(30)  # A synchronous call that never returns blocks the loop.


    asyncio.run(main())
    """
)

HEALTHY = textwrap.dedent(
    """
    import asyncio

    from lonora_worker.main import stall_guard


    async def main() -> None:
        async with stall_guard(2.0):
            await asyncio.sleep(4)


    asyncio.run(main())
    print("served")
    """
)


def run(script: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "-c", script],
        capture_output=True,
        text=True,
        timeout=60,
        cwd=ROOT,
        env=os.environ.copy(),
    )


def test_a_blocked_loop_exits_with_code_70_and_writes_the_stacks() -> None:
    result = run(BLOCKED)
    assert result.returncode == 70
    assert "gateway_loop_stalled" in result.stderr
    # faulthandler's dump names every thread and the line each one is stuck on.
    assert "thread" in result.stderr.lower()
    assert 'File "<string>"' in result.stderr


def test_a_loop_that_keeps_running_is_left_alone() -> None:
    result = run(HEALTHY)
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "served"
