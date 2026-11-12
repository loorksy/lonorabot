from typing import Any

from lonora_contracts.domain import utcnow
from lonora_core.user_error import LonoraError
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from .schema import (
    AgentRow,
    BoardRow,
    BrokerSessionRow,
    EventRow,
    ResourceRow,
    SecretRow,
    SettingRow,
    ThreadRow,
)


def resource_data(row: ResourceRow) -> dict[str, Any]:
    return {
        "id": row.id,
        "agent_id": row.agent_id,
        "thread_id": row.thread_id,
        "payload": row.payload,
        "state": row.state,
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
    # The scopes of the secret a resource's ``secret_id`` may name; empty: no secret.
    secret_scopes: tuple[str, ...] = ()
    secret_scope_refusal = "secret_scope_forbidden"

    async def list(
        self,
        session: AsyncSession,
        owner_id: str,
        agent_id: str | None = None,
        thread_id: str | None = None,
    ) -> list[ResourceRow]:
        query = select(self.row_type).where(self.row_type.owner_id == owner_id)
        if agent_id:
            query = query.where(self.row_type.agent_id == agent_id)
        if thread_id:
            await owned_thread(session, owner_id, thread_id)
            query = query.where(self.row_type.thread_id == thread_id)
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

    async def validate_references(
        self, session: AsyncSession, owner_id: str, payload: dict[str, Any]
    ) -> None:
        for agent_id in payload.get("member_ids", []):
            await owned_agent(session, owner_id, agent_id)
        board_id = payload.get("board_id")
        if board_id:
            board = await session.get(BoardRow, board_id)
            if board is None or board.owner_id != owner_id:
                raise LonoraError("board_id_not_found", 404)
        # The secrets a connection names: its token, and an MCP server's stored address.
        for key in ("secret_id", "url_secret_id"):
            secret_id = payload.get(key)
            if not secret_id:
                continue
            # Shared lock: a delete of this secret waits for this write, then sees it used.
            secret = await session.get(SecretRow, secret_id, with_for_update={"read": True})
            if secret is None or secret.owner_id != owner_id:
                raise LonoraError("secret_id_not_found", 404)
            # A connection names only a secret of a scope it may use: a broker value goes
            # only to a broker connection, and no connection names a provider key.
            if secret.scope not in self.secret_scopes:
                raise LonoraError(self.secret_scope_refusal, 403)
        if self.kind in {"charts", "watches", "cloud_charts", "market_watches"} and payload.get(
            "account_id"
        ):
            row = await session.get(BrokerSessionRow, payload["account_id"])
            if row is None or row.owner_id != owner_id:
                raise LonoraError("broker_connection_not_found", 404)
        if payload.get("thread_id"):
            await owned_thread(session, owner_id, payload["thread_id"])

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
            agent = await owned_agent(session, owner_id, agent_id)
            if self.kind in {"charts", "watches", "cloud_charts", "market_watches"}:
                from .agent_binding import assert_payload_binding

                assert_payload_binding(agent, payload)
        if thread_id:
            thread = await owned_thread(session, owner_id, thread_id)
            if (
                self.kind in {"charts", "watches", "cloud_charts", "market_watches"}
                and thread.agent_id
            ):
                from .agent_binding import assert_payload_binding

                assert_payload_binding(
                    await owned_agent(session, owner_id, thread.agent_id), payload
                )
                if agent_id and agent_id != thread.agent_id:
                    raise LonoraError("agent_thread_mismatch", 409)
        validated = self.validate(payload)
        await self.validate_references(session, owner_id, validated)
        row = self.row_type(
            owner_id=owner_id,
            agent_id=agent_id,
            thread_id=thread_id,
            payload=validated,
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
        validated = self.validate(payload)
        await self.validate_references(session, owner_id, validated)
        if row.agent_id and self.kind in {"charts", "watches", "cloud_charts", "market_watches"}:
            from .agent_binding import assert_payload_binding

            assert_payload_binding(await owned_agent(session, owner_id, row.agent_id), validated)
        if row.thread_id and self.kind in {"charts", "watches", "cloud_charts", "market_watches"}:
            thread = await owned_thread(session, owner_id, row.thread_id)
            if thread.agent_id:
                from .agent_binding import assert_payload_binding

                assert_payload_binding(
                    await owned_agent(session, owner_id, thread.agent_id), validated
                )
        row.payload = validated
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


def execution_policy_key(owner_id: str, account_id: str) -> str:
    """Settings key of an account's execution policy and owner money limits."""
    return f"execution_policy:{owner_id}:{account_id}"


class SettingsRepository:
    async def get(self, session: AsyncSession, key: str, *, fresh: bool = False) -> dict[str, Any]:
        # fresh: read the stored row even if this session loaded it earlier, as a read
        # under a lock must.
        row = await (
            session.get(SettingRow, key, populate_existing=True)
            if fresh
            else session.get(SettingRow, key)
        )
        return row.payload if row else {}

    async def put(self, session: AsyncSession, key: str, payload: dict[str, Any]) -> None:
        row = await session.get(SettingRow, key, with_for_update=True, populate_existing=True)
        if row is None:
            session.add(SettingRow(key=key, payload=payload))
        else:
            row.payload = payload
            row.updated_at = utcnow()
