"""Trusted local execution bridge. No model, database, secrets or scheduler.

Run only on a dedicated trusted host, never inside the API or Gateway container.
The socket grants analytical execution to its Unix group, not Docker authority.
"""

import argparse
import asyncio
import fcntl
import hashlib
import json
import logging
import os
import socket
from pathlib import Path
from typing import Any, cast

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from lonora_core.user_error import LonoraError

from .workspace import MAX_TRANSFER_BYTES, AnalyticalContainer, encode_snapshot, read_snapshot


def create_host(backend: AnalyticalContainer, concurrency: int = 2) -> FastAPI:
    if not 1 <= concurrency <= 4:
        raise ValueError("workspace_concurrency_invalid")
    app = FastAPI(docs_url=None, redoc_url=None, openapi_url=None)
    slots = asyncio.Semaphore(concurrency)

    @app.post("/execute")
    async def execute(request: Request) -> JSONResponse:
        if slots.locked():
            return JSONResponse({"code": "workspace_busy"}, status_code=429)
        await slots.acquire()
        try:
            async with asyncio.timeout(10):
                body = bytearray()
                async for block in request.stream():
                    body.extend(block)
                    if len(body) > MAX_TRANSFER_BYTES:
                        raise LonoraError("workspace_request_too_large", 413)
            try:
                raw: object = json.loads(body)
                if not isinstance(raw, dict):
                    raise ValueError()
                value = cast(dict[str, Any], raw)
                if set(value) != {
                    "command",
                    "snapshot",
                    "deadline_seconds",
                }:
                    raise ValueError()
                command, deadline = value["command"], value["deadline_seconds"]
                if (
                    not isinstance(command, str)
                    or not command.strip()
                    or "\x00" in command
                    or len(command.encode()) > 32768
                    or type(deadline) not in {float, int}
                    or not 0 < deadline <= 45
                ):
                    raise ValueError()
                snapshot = read_snapshot(json.dumps(value["snapshot"]).encode())
            except (ValueError, TypeError, RecursionError):
                raise LonoraError("workspace_request_invalid", 422) from None
            outcome = await backend.execute(command, snapshot, deadline_seconds=deadline)
            return JSONResponse(
                {
                    "exit_code": outcome.exit_code,
                    "stdout": outcome.stdout,
                    "stderr": outcome.stderr,
                    "snapshot": json.loads(encode_snapshot(outcome.files)),
                    "image": outcome.image,
                }
            )
        except LonoraError as error:
            return JSONResponse({"code": error.code}, status_code=error.status)
        except TimeoutError:
            return JSONResponse({"code": "workspace_request_timeout"}, status_code=408)
        except Exception as error:
            logging.getLogger(__name__).warning(
                "workspace_host_failed type=%s", type(error).__name__
            )
            return JSONResponse({"code": "workspace_backend_unavailable"}, status_code=503)
        finally:
            slots.release()

    return app


def serve(image: str, directory: Path, group: int, concurrency: int) -> None:
    import uvicorn

    if not directory.is_absolute() or group < 0:
        raise ValueError("workspace_host_configuration_invalid")
    directory.mkdir(mode=0o750, parents=True, exist_ok=True)
    if directory.is_symlink() or directory.stat().st_uid != os.getuid():
        raise ValueError("workspace_host_directory_unsafe")
    os.chown(directory, os.getuid(), group)
    directory.chmod(0o750)
    # Prevent startup cleanup from killing a concurrently serving host's jobs.
    with (directory / "host.lock").open("a") as lock:
        fcntl.flock(lock.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        namespace = hashlib.sha256(str(directory.resolve()).encode()).hexdigest()[:32]
        backend = AnalyticalContainer(image, namespace=namespace)
        path = directory / "host.sock"
        path.unlink(missing_ok=True)
        with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as listener:
            listener.bind(str(path))
            os.chown(path, os.getuid(), group)
            path.chmod(0o660)
            listener.listen(16)
            listener.setblocking(False)
            try:
                config = uvicorn.Config(
                    create_host(backend, concurrency),
                    access_log=False,
                    log_level="warning",
                    timeout_keep_alive=2,
                    limit_concurrency=16,
                    limit_max_requests=None,
                    timeout_graceful_shutdown=55,
                )

                async def run() -> None:
                    await backend.reap_orphans()
                    await uvicorn.Server(config).serve(sockets=[listener])

                asyncio.run(run())
            finally:
                path.unlink(missing_ok=True)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--image", required=True)
    parser.add_argument("--directory", type=Path, default=Path("/run/lonora-analysis"))
    parser.add_argument("--group", type=int, default=10001)
    parser.add_argument("--concurrency", type=int, default=2)
    args = parser.parse_args()
    serve(args.image, args.directory, args.group, args.concurrency)


if __name__ == "__main__":
    main()
