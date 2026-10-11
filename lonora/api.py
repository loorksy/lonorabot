import uuid
from contextlib import asynccontextmanager
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import cast

import jwt
from fastapi import Depends, FastAPI, HTTPException, Query
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from fastapi.staticfiles import StaticFiles
from sqlalchemy import select, text

from .auth import DUMMY_PASSWORD_HASH, issue_access_token, read_access_token, verify_password
from .config import get_settings
from .database import create_database
from .orm import (
    AgentRow,
    GlobalModelSettingsRow,
    MemoryRow,
    MessageRow,
    RoutineRow,
    RunRow,
    ThreadRow,
    UserRow,
)
from .provider import (
    PROVIDER_BASE_URLS,
    GlobalModelRouter,
    ModelConfigurationError,
    ModelProviderError,
)
from .schemas import (
    AgentCreate,
    LoginRequest,
    MemoryUpdate,
    MessageCreate,
    ModelSettingsUpdate,
    ProviderId,
    RoutineCreate,
    ThreadCreate,
)

settings = get_settings()
engine, sessions = create_database(settings.database_url)
provider = GlobalModelRouter(settings)


@asynccontextmanager
async def lifespan(_: FastAPI):
    yield
    await engine.dispose()


app = FastAPI(title="Lonora", version="0.1.0", lifespan=lifespan)
bearer = HTTPBearer(auto_error=False)


def utcnow() -> datetime:
    return datetime.now(UTC)


def require_row(row, message: str):
    if row is None:
        raise HTTPException(404, message)
    return row


def unauthorized() -> HTTPException:
    return HTTPException(401, "unauthorized", headers={"WWW-Authenticate": "Bearer"})


async def authenticated_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer),
) -> UserRow:
    if credentials is None:
        raise unauthorized()
    try:
        user_id = read_access_token(credentials.credentials, settings)
    except (jwt.InvalidTokenError, ValueError):
        raise unauthorized() from None
    async with sessions() as session:
        user = await session.get(UserRow, user_id)
    if user is None:
        raise unauthorized()
    return user


async def owned_agent(session, user: UserRow, agent_id: uuid.UUID) -> AgentRow:
    agent = await session.scalar(
        select(AgentRow).where(AgentRow.id == agent_id, AgentRow.owner_id == user.id)
    )
    return require_row(agent, "agent_not_found")


async def owned_thread(session, user: UserRow, thread_id: uuid.UUID, *, lock: bool = False):
    query = (
        select(ThreadRow)
        .join(AgentRow, AgentRow.id == ThreadRow.agent_id)
        .where(ThreadRow.id == thread_id, AgentRow.owner_id == user.id)
    )
    if lock:
        query = query.with_for_update(of=ThreadRow)
    return require_row(await session.scalar(query), "thread_not_found")


async def global_model_settings(session) -> GlobalModelSettingsRow:
    row = await session.get(GlobalModelSettingsRow, 1)
    if row is None:
        row = GlobalModelSettingsRow(
            id=1,
            provider=settings.model_provider,
            model_name=settings.model_name,
        )
        session.add(row)
        await session.flush()
    return row


@app.post("/auth/login")
async def login(body: LoginRequest):
    email = body.email.strip().lower()
    async with sessions() as session:
        user = await session.scalar(select(UserRow).where(UserRow.email == email))
    try:
        stored_hash = user.password_hash if user is not None else DUMMY_PASSWORD_HASH
        valid_password = verify_password(body.password, stored_hash)
    except Exception:
        valid_password = False
    if user is None or not valid_password:
        raise unauthorized()
    access_token, expires_in = issue_access_token(user.id, settings)
    return {"access_token": access_token, "token_type": "bearer", "expires_in": expires_in}


@app.get("/auth/me")
async def read_current_user(user: UserRow = Depends(authenticated_user)):
    return {"id": str(user.id), "email": user.email}


@app.get("/health")
async def health():
    try:
        async with sessions() as session:
            await session.execute(text("SELECT 1"))
    except Exception:
        raise HTTPException(503, "database_unavailable") from None
    return {"status": "ok", "model_configured": provider.configured, "worker": "separate process"}


@app.get("/settings/model")
async def read_model_settings(user: UserRow = Depends(authenticated_user)):
    async with sessions() as session, session.begin():
        row = await global_model_settings(session)
        return {
            "provider": row.provider,
            "model_name": row.model_name,
            "key_configured": provider.configured,
            "supported_providers": list(PROVIDER_BASE_URLS),
            "updated_at": row.updated_at.isoformat(),
        }


@app.put("/settings/model")
async def update_model_settings(
    body: ModelSettingsUpdate,
    user: UserRow = Depends(authenticated_user),
):
    async with sessions() as session, session.begin():
        row = await global_model_settings(session)
        row.provider = body.provider
        row.model_name = body.model_name.strip()
        row.updated_at = utcnow()
        await session.flush()
        return {
            "provider": row.provider,
            "model_name": row.model_name,
            "key_configured": provider.configured,
            "supported_providers": list(PROVIDER_BASE_URLS),
            "updated_at": row.updated_at.isoformat(),
        }


@app.get("/settings/model/models")
async def discover_models(
    provider_id: ProviderId | None = Query(default=None, alias="provider"),
    user: UserRow = Depends(authenticated_user),
):
    if provider_id is None:
        async with sessions() as session:
            row = await session.get(GlobalModelSettingsRow, 1)
            provider_id = cast(ProviderId, row.provider if row else settings.model_provider)
    try:
        models = await provider.discover_models(provider_id)
    except ModelConfigurationError as exc:
        raise HTTPException(409, str(exc)) from None
    except ModelProviderError as exc:
        raise HTTPException(502, str(exc)) from None
    return {"provider": provider_id, "models": models}


@app.post("/agents", status_code=201)
async def create_agent(body: AgentCreate, user: UserRow = Depends(authenticated_user)):
    async with sessions() as session, session.begin():
        agent = AgentRow(owner_id=user.id, name=body.name, instructions=body.instructions)
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
async def list_agents(user: UserRow = Depends(authenticated_user)):
    async with sessions() as session:
        rows = (
            await session.scalars(
                select(AgentRow).where(AgentRow.owner_id == user.id).order_by(AgentRow.created_at)
            )
        ).all()
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
async def read_agent(agent_id: uuid.UUID, user: UserRow = Depends(authenticated_user)):
    async with sessions() as session:
        row = await owned_agent(session, user, agent_id)
        return {
            "id": str(row.id),
            "name": row.name,
            "instructions": row.instructions,
            "created_at": row.created_at.isoformat(),
        }


@app.post("/agents/{agent_id}/threads", status_code=201)
async def create_thread(
    agent_id: uuid.UUID,
    body: ThreadCreate,
    user: UserRow = Depends(authenticated_user),
):
    async with sessions() as session, session.begin():
        await owned_agent(session, user, agent_id)
        thread = ThreadRow(agent_id=agent_id, title=body.title)
        session.add(thread)
        await session.flush()
        return {
            "id": str(thread.id),
            "agent_id": str(thread.agent_id),
            "title": thread.title,
            "created_at": thread.created_at.isoformat(),
        }


@app.get("/agents/{agent_id}/threads")
async def list_threads(agent_id: uuid.UUID, user: UserRow = Depends(authenticated_user)):
    async with sessions() as session:
        await owned_agent(session, user, agent_id)
        rows = (
            await session.scalars(
                select(ThreadRow)
                .where(ThreadRow.agent_id == agent_id)
                .order_by(ThreadRow.created_at.desc())
            )
        ).all()
        return [
            {
                "id": str(row.id),
                "agent_id": str(row.agent_id),
                "title": row.title,
                "created_at": row.created_at.isoformat(),
            }
            for row in rows
        ]


@app.get("/threads/{thread_id}")
async def read_thread(thread_id: uuid.UUID, user: UserRow = Depends(authenticated_user)):
    async with sessions() as session:
        thread = await owned_thread(session, user, thread_id)
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
async def send_message(
    thread_id: uuid.UUID,
    body: MessageCreate,
    user: UserRow = Depends(authenticated_user),
):
    async with sessions() as session, session.begin():
        thread = await owned_thread(session, user, thread_id, lock=True)
        message = MessageRow(
            thread_id=thread_id, seq=thread.next_seq, role="user", content=body.content
        )
        thread.next_seq += 1
        run = RunRow(thread_id=thread_id, status="queued")
        session.add_all([message, run])
        await session.flush()
        return {"message_id": str(message.id), "run_id": str(run.id), "status": run.status}


@app.get("/runs/{run_id}")
async def read_run(run_id: uuid.UUID, user: UserRow = Depends(authenticated_user)):
    async with sessions() as session:
        row = require_row(
            await session.scalar(
                select(RunRow)
                .join(ThreadRow, ThreadRow.id == RunRow.thread_id)
                .join(AgentRow, AgentRow.id == ThreadRow.agent_id)
                .where(RunRow.id == run_id, AgentRow.owner_id == user.id)
            ),
            "run_not_found",
        )
        return {
            "id": str(row.id),
            "thread_id": str(row.thread_id),
            "status": row.status,
            "error_code": row.error_code,
            "created_at": row.created_at.isoformat(),
            "updated_at": row.updated_at.isoformat(),
        }


@app.get("/agents/{agent_id}/memory")
async def read_memory(agent_id: uuid.UUID, user: UserRow = Depends(authenticated_user)):
    async with sessions() as session:
        await owned_agent(session, user, agent_id)
        row = require_row(await session.get(MemoryRow, agent_id), "agent_not_found")
        return {
            "agent_id": str(row.agent_id),
            "content": row.content,
            "updated_at": row.updated_at.isoformat(),
        }


@app.put("/agents/{agent_id}/memory")
async def write_memory(
    agent_id: uuid.UUID,
    body: MemoryUpdate,
    user: UserRow = Depends(authenticated_user),
):
    async with sessions() as session, session.begin():
        await owned_agent(session, user, agent_id)
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
async def create_routine(
    agent_id: uuid.UUID,
    body: RoutineCreate,
    user: UserRow = Depends(authenticated_user),
):
    async with sessions() as session, session.begin():
        await owned_agent(session, user, agent_id)
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
            "prompt": routine.prompt,
            "interval_seconds": routine.interval_seconds,
            "next_run_at": routine.next_run_at.isoformat(),
            "enabled": routine.enabled,
        }


@app.get("/agents/{agent_id}/routines")
async def list_routines(agent_id: uuid.UUID, user: UserRow = Depends(authenticated_user)):
    async with sessions() as session:
        await owned_agent(session, user, agent_id)
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


web_build = Path(__file__).resolve().parents[1] / "apps" / "web" / "dist"
if web_build.is_dir():
    app.mount("/", StaticFiles(directory=web_build, html=True), name="web")
