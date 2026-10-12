import asyncio
from datetime import timedelta
from typing import Any

from lonora_contracts.domain import utcnow
from lonora_db.client import Database
from lonora_db.schema import VoiceSessionRow
from lonora_providers.credentials import ProviderCredentials
from lonora_voice.realtime import RealtimeVoiceSession
from sqlalchemy import select

from .runtime import OwnerServices


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
