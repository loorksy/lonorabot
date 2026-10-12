import asyncio
import signal
from collections.abc import Callable


def install_signals(stop: Callable[[], None]) -> None:
    loop = asyncio.get_running_loop()
    for value in [signal.SIGTERM, signal.SIGINT]:
        loop.add_signal_handler(value, stop)
