from typing import Any

from lonora_contracts.domain import utcnow
from lonora_core.user_error import LonoraError
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from .schema import AgentRow, EventRow, ResourceRow, SettingRow, ThreadRow


def resource_data(row: ResourceRow) -> dict[str, Any]:
    return {
        "id": row.id,
        "agent_id": row.agent_id,
        "thread_id": row.thread_id,
        "payload": row.payload,
        "version": row.version,
        "created_at": row.created_at.isoformat(),
        "updated_at": row.updated_at.isoformat(),
    }


async def owned_agent(
    session: AsyncSession, owner_id: str, agent_id: str, lock: bool = False
) -> AgentRow:
    query = select(AgentRow).where(AgentRow.id == agent_id, AgentRow.owner_id == owner_id)
    if lock:
        query = query.with_for_update()
    row = await session.scalar(query)
    if row is None:
        raise LonoraError("agent_not_found", 404)
    return row


async def owned_thread(
    session: AsyncSession, owner_id: str, thread_id: str, lock: bool = False
) -> ThreadRow:
    query = select(ThreadRow).where(ThreadRow.id == thread_id, ThreadRow.owner_id == owner_id)
    if lock:
        query = query.with_for_update()
    row = await session.scalar(query)
    if row is None:
        raise LonoraError("thread_not_found", 404)
    return row


class ResourceRepository:
    row_type: type[ResourceRow]
    payload_model: type[BaseModel] | None = None
    kind: str

    async def list(
        self, session: AsyncSession, owner_id: str, agent_id: str | None = None
    ) -> list[ResourceRow]:
        query = select(self.row_type).where(self.row_type.owner_id == owner_id)
        if agent_id:
            query = query.where(self.row_type.agent_id == agent_id)
        return list(
            (
                await session.scalars(query.order_by(self.row_type.created_at.desc()).limit(200))
            ).all()
        )

    async def get(
        self, session: AsyncSession, owner_id: str, resource_id: str, lock: bool = False
    ) -> ResourceRow:
        query = select(self.row_type).where(
            self.row_type.owner_id == owner_id, self.row_type.id == resource_id
        )
        if lock:
            query = query.with_for_update()
        row = await session.scalar(query)
        if row is None:
            raise LonoraError(self.kind + "_not_found", 404)
        return row

    def validate(self, payload: dict[str, Any]) -> dict[str, Any]:
        if self.payload_model:
            return self.payload_model.model_validate(payload).model_dump(mode="json")
        return payload

    async def create(
        self,
        session: AsyncSession,
        owner_id: str,
        payload: dict[str, Any],
        *,
        agent_id: str | None = None,
        thread_id: str | None = None,
        resource_id: str | None = None,
    ) -> ResourceRow:
        if agent_id:
            await owned_agent(session, owner_id, agent_id)
        if thread_id:
            await owned_thread(session, owner_id, thread_id)
        row = self.row_type(
            owner_id=owner_id,
            agent_id=agent_id,
            thread_id=thread_id,
            payload=self.validate(payload),
        )
        if resource_id:
            row.id = resource_id
        session.add(row)
        await session.flush()
        session.add(
            EventRow(
                owner_id=owner_id,
                agent_id=agent_id,
                thread_id=thread_id,
                kind=self.kind + ".created",
                payload={"id": row.id},
            )
        )
        return row

    async def update(
        self,
        session: AsyncSession,
        owner_id: str,
        resource_id: str,
        payload: dict[str, Any],
        version: int,
    ) -> ResourceRow:
        row = await self.get(session, owner_id, resource_id, lock=True)
        if row.version != version:
            raise LonoraError("version_conflict", 409)
        row.payload = self.validate(payload)
        row.version += 1
        row.updated_at = utcnow()
        session.add(
            EventRow(
                owner_id=owner_id,
                agent_id=row.agent_id,
                thread_id=row.thread_id,
                kind=self.kind + ".updated",
                payload={"id": row.id, "version": row.version},
            )
        )
        return row

    async def delete(self, session: AsyncSession, owner_id: str, resource_id: str) -> None:
        row = await self.get(session, owner_id, resource_id, lock=True)
        session.add(
            EventRow(
                owner_id=owner_id,
                agent_id=row.agent_id,
                thread_id=row.thread_id,
                kind=self.kind + ".deleted",
                payload={"id": row.id},
            )
        )
        await session.delete(row)


class SettingsRepository:
    async def get(self, session: AsyncSession, key: str) -> dict[str, Any]:
        row = await session.get(SettingRow, key)
        return row.payload if row else {}

    async def put(self, session: AsyncSession, key: str, payload: dict[str, Any]) -> None:
        row = await session.get(SettingRow, key, with_for_update=True)
        if row is None:
            session.add(SettingRow(key=key, payload=payload))
        else:
            row.payload = payload
            row.updated_at = utcnow()
