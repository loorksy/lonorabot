import uuid
from datetime import timedelta

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select, update

from lonora import api
from lonora.auth import hash_password
from lonora.orm import Base, MessageRow, RoutineRow, UserRow, utcnow
from lonora.provider import GrokProvider
from lonora.worker import Worker


class FakeProvider:
    async def respond(self, messages: list[dict[str, str]]) -> str:
        latest = messages[-1]["content"]
        if latest == "Scheduled task: summarize the market":
            return "Market summary ready"
        return "Welcome to Lonora"


@pytest.mark.asyncio
async def test_agent_conversation_memory_and_routine_survive_worker_execution():
    async with api.engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)

    try:
        async with api.sessions() as session, session.begin():
            session.add_all(
                [
                    UserRow(
                        email="owner@example.com",
                        password_hash=hash_password("a long test password"),
                    ),
                    UserRow(
                        email="other@example.com",
                        password_hash=hash_password("another long test password"),
                    ),
                ]
            )
        async with AsyncClient(
            transport=ASGITransport(app=api.app), base_url="http://lonora"
        ) as client:
            assert (await client.get("/health")).status_code == 200
            assert (await client.get("/")).headers["content-type"].startswith("text/html")
            assert (await client.get("/agents")).status_code == 401
            login = await client.post(
                "/auth/login",
                json={"email": "OWNER@example.com", "password": "a long test password"},
            )
            assert login.status_code == 200
            client.headers["Authorization"] = f"Bearer {login.json()['access_token']}"
            assert (await client.get("/auth/me")).json()["email"] == "owner@example.com"
            agent = (
                await client.post(
                    "/agents", json={"name": "Lonora", "instructions": "Respond in Arabic."}
                )
            ).json()
            owner_agent_id = agent["id"]
            other_login = await client.post(
                "/auth/login",
                json={"email": "other@example.com", "password": "another long test password"},
            )
            client.headers["Authorization"] = f"Bearer {other_login.json()['access_token']}"
            assert (await client.get(f"/agents/{owner_agent_id}")).status_code == 404
            client.headers["Authorization"] = f"Bearer {login.json()['access_token']}"
            thread = (
                await client.post(
                    f"/agents/{agent['id']}/threads", json={"title": "First conversation"}
                )
            ).json()
            assert len((await client.get(f"/agents/{agent['id']}/threads")).json()) == 1
            queued = await client.post(
                f"/threads/{thread['id']}/messages", json={"content": "مرحبا"}
            )
            assert queued.status_code == 202

            worker = Worker(settings=api.settings, sessions=api.sessions, worker_id="test-worker")
            worker.provider = FakeProvider()
            run = await worker._claim_next()
            assert run is not None
            await worker._execute(run)

            status = (await client.get(f"/runs/{run['id']}")).json()
            conversation = (await client.get(f"/threads/{thread['id']}")).json()
            assert status["status"] == "completed"
            assert [message["content"] for message in conversation["messages"]] == [
                "مرحبا",
                "Welcome to Lonora",
            ]

            failed_turn = await client.post(
                f"/threads/{thread['id']}/messages", json={"content": "Another request"}
            )
            worker.provider = GrokProvider(api.settings)
            failed_run = await worker._claim_next()
            assert failed_run is not None
            await worker._execute(failed_run)
            failed_status = (await client.get(f"/runs/{failed_run['id']}")).json()
            assert failed_turn.status_code == 202
            assert failed_status["status"] == "failed"
            assert failed_status["error_code"] == "model_not_configured"
            failed_conversation = (await client.get(f"/threads/{thread['id']}")).json()
            assert [message["role"] for message in failed_conversation["messages"]] == [
                "user",
                "assistant",
                "user",
            ]

            saved_memory = await client.put(
                f"/agents/{agent['id']}/memory", json={"content": "يفضل المستخدم العربية."}
            )
            assert saved_memory.json()["content"] == "يفضل المستخدم العربية."

            routine = (
                await client.post(
                    f"/agents/{agent['id']}/routines",
                    json={"prompt": "summarize the market", "interval_seconds": 60},
                )
            ).json()
            assert routine["prompt"] == "summarize the market"
            assert routine["next_run_at"]
            worker.provider = FakeProvider()
            async with api.sessions() as session, session.begin():
                await session.execute(
                    update(RoutineRow)
                    .where(RoutineRow.id == uuid.UUID(routine["id"]))
                    .values(next_run_at=utcnow() - timedelta(seconds=1))
                )

            scheduled_run = await worker._claim_next()
            assert scheduled_run is not None
            assert scheduled_run["routine_id"] is not None
            await worker._execute(scheduled_run)
            scheduled_status = (await client.get(f"/runs/{scheduled_run['id']}")).json()
            assert scheduled_status["status"] == "completed"

            async with api.sessions() as session:
                scheduled_messages = (
                    await session.scalars(
                        select(MessageRow)
                        .where(MessageRow.thread_id == uuid.UUID(routine["thread_id"]))
                        .order_by(MessageRow.seq)
                    )
                ).all()
            assert [message.content for message in scheduled_messages] == [
                "Scheduled task: summarize the market",
                "Market summary ready",
            ]
    finally:
        await api.engine.dispose()
