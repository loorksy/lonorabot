import asyncio
import faulthandler
import os
import threading
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from time import monotonic

from lonora_adapter_kit.tokenization import cached_encoding
from lonora_api.env import get_settings
from lonora_logging.logger import configure_logging

from .runtime import create_gateway
from .signals import install_signals

# A Gateway whose event loop is blocked or deadlocked never exits by itself, so neither
# Docker's restart policy nor systemd's Restart=on-failure would bring it back. Past this
# long without one loop turn (above the longest legitimate synchronous section) the
# process leaves with STALL_EXIT_CODE and is restarted. That is safe: leases are fenced,
# and an uncertain send is reconciled and never resent (VISION 6.3).
STALL_SECONDS = 120.0
STALL_EXIT_CODE = 70


@asynccontextmanager
async def stall_guard(limit: float = STALL_SECONDS) -> AsyncGenerator[None]:
    """Watch the running loop from a plain thread: once the loop has not updated its
    timestamp for ``limit`` seconds, write every thread's stack and exit at once."""
    last = [monotonic()]
    stopped = threading.Event()

    async def beat() -> None:
        while True:
            last[0] = monotonic()
            await asyncio.sleep(1)

    def watch() -> None:
        while not stopped.wait(1):
            stalled = monotonic() - last[0]
            if stalled > limit:
                # Straight to stderr, without the logging lock a stuck thread may hold.
                os.write(2, f"gateway_loop_stalled seconds={stalled:.0f}\n".encode())
                faulthandler.dump_traceback(all_threads=True)
                os._exit(STALL_EXIT_CODE)

    task = asyncio.create_task(beat())
    threading.Thread(target=watch, name="lonora-stall-guard", daemon=True).start()
    try:
        yield
    finally:
        stopped.set()
        task.cancel()


async def serve() -> None:
    settings = get_settings()
    configure_logging(settings.log_level)
    db, gateway = create_gateway(settings)
    install_signals(gateway.request_stop)
    try:
        async with stall_guard():
            # These only read hash-verified setup caches. Pay cold encoding setup
            # before readiness, never in the owner's first conversational request.
            for encoding in ("cl100k_base", "o200k_base"):
                await asyncio.to_thread(cached_encoding, encoding)
            await gateway.serve()
    finally:
        await db.close()


def main() -> None:
    asyncio.run(serve())


if __name__ == "__main__":
    main()
