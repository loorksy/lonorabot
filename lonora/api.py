import uuid
from contextlib import asynccontextmanager
from datetime import UTC, datetime, timedelta

from fastapi import FastAPI, HTTPException
from sqlalchemy import select, text

from .config import get_settings
from .database import create_database
from .orm import AgentRow, MemoryRow, MessageRow, RoutineRow, RunRow, ThreadRow
from .provider import GrokProvider
from .schemas import AgentCreate, MemoryUpdate, MessageCreate, RoutineCreate, ThreadCreate

settings = get_settings()
engine, sessions = create_database(settings.database_url)
provider = GrokProvider(settings)


@asynccontextmanager
async def lifespan(_: FastAPI):
    yield
    await engine.dispose()


app = FastAPI(title="Lonora", version="0.1.0", lifespan=lifespan)


def utcnow() -> datetime:
    return datetime.now(UTC)


def require_row(row, message: str):
    if row is None:
        raise HTTPException(404, message)
    return row


@app.get("/health")
async def health():
    try:
        async with sessions() as session:
            await session.execute(text("SELECT 1"))
    except Exception:
        raise HTTPException(503, "database_unavailable") from None
    return {"status": "ok", "model_configured": provider.configured, "worker": "separate process"}


@app.post("/agents", status_code=201)
async def create_agent(body: AgentCreate):
    async with sessions() as session, session.begin():
        agent = AgentRow(name=body.name, instructions=body.instructions)
        agent.memory = MemoryRow(content="")
        session.add(agent)
        await session.flush()
        return {
            "id": str(agent.id),
            "name": agent.name,
            "instructions": agent.instructions,
            "created_at": agent.created_at.isoformat(),
        }


@app.get("/agents")
async def list_agents():
    async with sessions() as session:
        rows = (await session.scalars(select(AgentRow).order_by(AgentRow.created_at))).all()
        return [
            {
                "id": str(row.id),
                "name": row.name,
                "instructions": row.instructions,
                "created_at": row.created_at.isoformat(),
            }
            for row in rows
        ]


@app.get("/agents/{agent_id}")
async def read_agent(agent_id: uuid.UUID):
    async with sessions() as session:
        row = require_row(await session.get(AgentRow, agent_id), "agent_not_found")
        return {
            "id": str(row.id),
            "name": row.name,
            "instructions": row.instructions,
            "created_at": row.created_at.isoformat(),
        }


@app.post("/agents/{agent_id}/threads", status_code=201)
async def create_thread(agent_id: uuid.UUID, body: ThreadCreate):
    async with sessions() as session, session.begin():
        require_row(await session.get(AgentRow, agent_id), "agent_not_found")
        thread = ThreadRow(agent_id=agent_id, title=body.title)
        session.add(thread)
        await session.flush()
        return {
            "id": str(thread.id),
            "agent_id": str(thread.agent_id),
            "title": thread.title,
            "created_at": thread.created_at.isoformat(),
        }


@app.get("/threads/{thread_id}")
async def read_thread(thread_id: uuid.UUID):
    async with sessions() as session:
        thread = require_row(await session.get(ThreadRow, thread_id), "thread_not_found")
        messages = (
            await session.scalars(
                select(MessageRow).where(MessageRow.thread_id == thread_id).order_by(MessageRow.seq)
            )
        ).all()
        return {
            "thread": {
                "id": str(thread.id),
                "agent_id": str(thread.agent_id),
                "title": thread.title,
                "created_at": thread.created_at.isoformat(),
            },
            "messages": [
                {
                    "id": str(m.id),
                    "seq": m.seq,
                    "role": m.role,
                    "content": m.content,
                    "created_at": m.created_at.isoformat(),
                }
                for m in messages
            ],
        }


@app.post("/threads/{thread_id}/messages", status_code=202)
async def send_message(thread_id: uuid.UUID, body: MessageCreate):
    async with sessions() as session, session.begin():
        thread = require_row(
            (
                await session.execute(
                    select(ThreadRow).where(ThreadRow.id == thread_id).with_for_update()
                )
            ).scalar_one_or_none(),
            "thread_not_found",
        )
        message = MessageRow(
            thread_id=thread_id, seq=thread.next_seq, role="user", content=body.content
        )
        thread.next_seq += 1
        run = RunRow(thread_id=thread_id, status="queued")
        session.add_all([message, run])
        await session.flush()
        return {"message_id": str(message.id), "run_id": str(run.id), "status": run.status}


@app.get("/runs/{run_id}")
async def read_run(run_id: uuid.UUID):
    async with sessions() as session:
        row = require_row(await session.get(RunRow, run_id), "run_not_found")
        return {
            "id": str(row.id),
            "thread_id": str(row.thread_id),
            "status": row.status,
            "error_code": row.error_code,
            "created_at": row.created_at.isoformat(),
            "updated_at": row.updated_at.isoformat(),
        }


@app.get("/agents/{agent_id}/memory")
async def read_memory(agent_id: uuid.UUID):
    async with sessions() as session:
        row = require_row(await session.get(MemoryRow, agent_id), "agent_not_found")
        return {
            "agent_id": str(row.agent_id),
            "content": row.content,
            "updated_at": row.updated_at.isoformat(),
        }


@app.put("/agents/{agent_id}/memory")
async def write_memory(agent_id: uuid.UUID, body: MemoryUpdate):
    async with sessions() as session, session.begin():
        row = require_row(
            await session.get(MemoryRow, agent_id, with_for_update=True), "agent_not_found"
        )
        row.content, row.updated_at = body.content, utcnow()
        await session.flush()
        return {
            "agent_id": str(row.agent_id),
            "content": row.content,
            "updated_at": row.updated_at.isoformat(),
        }


@app.post("/agents/{agent_id}/routines", status_code=201)
async def create_routine(agent_id: uuid.UUID, body: RoutineCreate):
    async with sessions() as session, session.begin():
        require_row(await session.get(AgentRow, agent_id), "agent_not_found")
        thread = ThreadRow(agent_id=agent_id, title=f"Routine: {body.prompt[:60]}")
        session.add(thread)
        await session.flush()
        routine = RoutineRow(
            agent_id=agent_id,
            thread_id=thread.id,
            prompt=body.prompt,
            interval_seconds=body.interval_seconds,
            next_run_at=utcnow() + timedelta(seconds=body.interval_seconds),
        )
        session.add(routine)
        await session.flush()
        return {
            "id": str(routine.id),
            "agent_id": str(agent_id),
            "thread_id": str(thread.id),
            "interval_seconds": routine.interval_seconds,
            "enabled": routine.enabled,
        }


@app.get("/agents/{agent_id}/routines")
async def list_routines(agent_id: uuid.UUID):
    async with sessions() as session:
        require_row(await session.get(AgentRow, agent_id), "agent_not_found")
        rows = (
            await session.scalars(
                select(RoutineRow)
                .where(RoutineRow.agent_id == agent_id)
                .order_by(RoutineRow.created_at)
            )
        ).all()
        return [
            {
                "id": str(row.id),
                "thread_id": str(row.thread_id),
                "prompt": row.prompt,
                "interval_seconds": row.interval_seconds,
                "next_run_at": row.next_run_at.isoformat(),
                "enabled": row.enabled,
            }
            for row in rows
        ]
