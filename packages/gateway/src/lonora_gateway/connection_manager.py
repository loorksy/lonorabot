import asyncio
import os
import sys
from datetime import timedelta
from typing import Any
from urllib.parse import urlparse

from lonora_contracts.domain import utcnow
from lonora_db.client import Database
from lonora_db.schema import VoiceSessionRow
from lonora_providers.credentials import ProviderCredentials
from lonora_voice.realtime import RealtimeVoiceSession
from sqlalchemy import select

from .runtime import OwnerServices


async def isolated_local_voice(db: Database, session_id: str, gateway_id: str) -> None:
    """The RTC SDK ignores NO_PROXY; isolate its loopback WS transport from HTTPS egress."""
    environment = dict(os.environ)
    environment["LONORA_DATABASE_URL"] = db.engine.url.render_as_string(hide_password=False)
    # Only the local, plain-WebSocket transport uses HTTP_PROXY. Preserve HTTPS_PROXY
    # and CA trust so STT/TTS still use the configured HTTPS proxy and credential injection.
    if not environment.get("HTTPS_PROXY") and not environment.get("https_proxy"):
        environment["HTTPS_PROXY"] = environment.get("HTTP_PROXY") or environment.get(
            "http_proxy", ""
        )
    environment["HTTP_PROXY"] = ""
    environment["http_proxy"] = ""
    process = await asyncio.create_subprocess_exec(
        sys.executable,
        "-m",
        "lonora_voice.realtime",
        "--session",
        session_id,
        "--gateway",
        gateway_id,
        env=environment,
    )
    try:
        await process.wait()
    finally:
        if process.returncode is None:
            process.terminate()
            try:
                await asyncio.wait_for(process.wait(), 10)
            except TimeoutError:
                process.kill()
                await process.wait()


async def maintain_voice(
    db: Database,
    services: OwnerServices,
    gateway_id: str,
    tasks: dict[str, asyncio.Task[None]],
    configuration: dict[str, str],
) -> None:
    if not all(configuration.get(key) for key in ("url", "key", "secret")):
        return
    now = utcnow()
    for session_id, task in list(tasks.items()):
        if task.done():
            await asyncio.gather(task, return_exceptions=True)
            tasks.pop(session_id)
    async with db.sessions() as session, session.begin():
        rows = (
            await session.scalars(
                select(VoiceSessionRow)
                .where(VoiceSessionRow.owner_id == services.owner_id)
                .with_for_update(skip_locked=True)
            )
        ).all()
        claims: list[str] = []
        for row in rows:
            if row.payload.get("status") not in {"joining", "connected"}:
                if row.id in tasks:
                    tasks[row.id].cancel()
                continue
            state: dict[str, Any] = dict(row.state)
            if (
                state.get("gateway") != gateway_id
                and float(state.get("lease_until", 0)) > now.timestamp()
            ):
                continue
            row.state = {
                **state,
                "gateway": gateway_id,
                "lease_until": (now + timedelta(seconds=60)).timestamp(),
            }
            if row.id not in tasks:
                claims.append(row.id)
    credentials = ProviderCredentials(db, services.secrets)
    for session_id in claims:
        url = urlparse(configuration["url"])
        if (
            url.scheme == "ws"
            and url.hostname in {"localhost", "127.0.0.1", "::1", "livekit"}
            and (os.environ.get("HTTP_PROXY") or os.environ.get("http_proxy"))
        ):
            tasks[session_id] = asyncio.create_task(
                isolated_local_voice(db, session_id, gateway_id)
            )
            continue
        voice = RealtimeVoiceSession(
            db,
            credentials,
            session_id,
            configuration["url"],
            configuration["key"],
            configuration["secret"],
            gateway_id,
        )
        tasks[session_id] = asyncio.create_task(voice.serve(), name="voice:" + session_id)


async def close_connections(
    services: dict[str, OwnerServices], voice_tasks: dict[str, asyncio.Task[None]]
) -> None:
    for task in voice_tasks.values():
        task.cancel()
    await asyncio.gather(*voice_tasks.values(), return_exceptions=True)
    for service in services.values():
        await service.close()
