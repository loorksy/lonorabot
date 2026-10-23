import asyncio
import time

from lonora_db.client import Database
from lonora_db.schema import VoiceSessionRow
from lonora_providers.credentials import ProviderCredentials
from lonora_voice.realtime import RealtimeVoiceSession
from sqlalchemy import select

from .runtime import OwnerServices


async def maintain_voice(
    db: Database, services: OwnerServices, gateway_id: str, tasks: dict[str, asyncio.Task[None]]
) -> None:
    for session_id, task in list(tasks.items()):
        if task.done():
            await asyncio.gather(task, return_exceptions=True)
            tasks.pop(session_id)
    claims: list[str] = []
    async with db.sessions() as session, session.begin():
        rows = (
            await session.scalars(
                select(VoiceSessionRow)
                .where(VoiceSessionRow.owner_id == services.owner_id)
                .with_for_update(skip_locked=True)
            )
        ).all()
        for row in rows:
            if row.payload.get("mode") == "incoming_request":
                continue
            if row.payload.get("mode") != "gpt_live":
                if row.payload.get("status") not in {"closed", "failed"}:
                    row.payload = {
                        **row.payload,
                        "status": "closed",
                        "reason": "transport_replaced",
                    }
                continue
            if not row.payload.get("remote_id"):
                continue
            if row.payload.get("status") not in {"joining", "connected", "closing"}:
                continue
            if (
                row.state.get("gateway") != gateway_id
                and float(row.state.get("lease_until", 0)) > time.time()
            ):
                continue
            row.state = {**row.state, "gateway": gateway_id, "lease_until": time.time() + 60}
            if row.id not in tasks:
                claims.append(row.id)
    credentials = ProviderCredentials(db, services.secrets)
    for session_id in claims:
        voice = RealtimeVoiceSession(db, credentials, session_id, gateway_id)
        tasks[session_id] = asyncio.create_task(voice.serve(), name="voice:" + session_id)


async def close_connections(
    services: dict[str, OwnerServices], voice_tasks: dict[str, asyncio.Task[None]]
) -> None:
    for task in voice_tasks.values():
        task.cancel()
    await asyncio.gather(*voice_tasks.values(), return_exceptions=True)
    for service in services.values():
        await service.close()
