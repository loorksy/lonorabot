import argparse
import asyncio
import contextlib
import getpass
import signal
from collections.abc import Generator
from pathlib import Path
from typing import cast

import uvicorn
from lonora_auth.account_security import hash_password, normalize_email
from lonora_core.user_error import LonoraError
from lonora_db.client import Database
from lonora_db.owner import get_owner
from lonora_db.schema import OwnerRow

from .app import create_app
from .cli.app import create_cli_app
from .env import get_settings
from .runtime import ApiRuntime

app = create_app()


async def create_owner(email: str) -> None:
    db = Database.connect(get_settings().database_url)
    password = getpass.getpass("Password: ")
    if password != getpass.getpass("Confirm password: "):
        raise LonoraError("password_mismatch")
    try:
        async with db.sessions() as session, session.begin():
            if await get_owner(session):
                raise LonoraError("owner_already_initialized", 409)
            session.add(
                OwnerRow(email=normalize_email(email), password_hash=hash_password(password))
            )
    finally:
        await db.close()


class _Server(uvicorn.Server):
    """A server whose shutdown ``serve`` below orders; it installs no signal handlers."""

    @contextlib.contextmanager
    def capture_signals(self) -> Generator[None]:
        yield


def cli_socket_path(path: Path) -> str:
    path.parent.mkdir(parents=True, exist_ok=True)
    # A socket left by an earlier process would keep its old mode; start from none.
    path.unlink(missing_ok=True)
    return str(path)


async def serve(host: str, port: int) -> None:
    """The owner API on ``host:port`` and the CLI endpoint on its Unix socket (7.3), in one
    process with one runtime. On a signal the CLI stops first, then the API, whose lifespan
    closes the shared runtime."""
    runtime = cast(ApiRuntime, app.state.runtime)
    api = _Server(uvicorn.Config(app, host=host, port=port))
    cli = _Server(
        uvicorn.Config(
            create_cli_app(runtime),
            uds=cli_socket_path(runtime.settings.cli_socket),
            lifespan="off",
        )
    )
    stop = asyncio.Event()
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(sig, stop.set)
    api_task, cli_task = asyncio.create_task(api.serve()), asyncio.create_task(cli.serve())
    stopping = asyncio.create_task(stop.wait())
    await asyncio.wait({api_task, cli_task, stopping}, return_when=asyncio.FIRST_COMPLETED)
    stopping.cancel()
    cli.should_exit = True
    await cli_task
    api.should_exit = True
    await api_task


def main() -> None:
    parser = argparse.ArgumentParser(prog="lonora-api")
    parser.add_argument("--host", default="0.0.0.0")
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument("--create-owner")
    args = parser.parse_args()
    if args.create_owner:
        asyncio.run(create_owner(args.create_owner))
        return
    asyncio.run(serve(args.host, args.port))


if __name__ == "__main__":
    main()
