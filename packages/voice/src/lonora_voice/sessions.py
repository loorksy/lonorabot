import asyncio
import hashlib
import time
from typing import Any

from lonora_adapters.voice.realtime import OpenAILiveAdapter
from lonora_contracts.voice import VoiceSessionCreate
from lonora_core.user_error import LonoraError
from lonora_db.client import Database
from lonora_db.schema import EffectReceiptRow, VoiceSessionRow
from lonora_db.transactions import owned_agent, owned_thread
from lonora_db.voice import VoiceSessionRepository
from lonora_providers.credentials import ProviderCredentials
from sqlalchemy import text

from .context import voice_context
from .routing import live_model

VOICE_INSTRUCTIONS = (
    "You are the spoken interface of a persistent Lonora trading agent. Reply in the user's "
    "language, naturally and concisely. Delegate all trading operations, portfolio and market "
    "lookups, calculations, research, memory changes, and scheduled work to the existing backend "
    "agent. Do not invent prices, balances, fills or completed actions. Speak verified backend "
    "results. Transcripts may be incomplete or incorrect: ask for clarification of ambiguous "
    "financial instructions, except the bound trading pair. If this agent has a bound account "
    "and symbol, never ask which pair and never ask the owner to repeat the symbol. "
    "When a trade needs a decision, an approval card with Approve and Reject buttons is inside "
    "this call. Tell the owner only to press one of those buttons. A spoken or typed yes is not "
    "approval. The backend owns trading permissions and tools. Casual conversation "
    "may continue while backend work is running. Interruptions do not authorize a new order."
)


async def create_voice_session(
    db: Database, credentials: ProviderCredentials, owner_id: str, request: VoiceSessionCreate
) -> dict[str, Any]:
    model = await live_model(db)
    adapter = OpenAILiveAdapter(await credentials.resolve("openai"))
    digest = hashlib.sha256((owner_id + ":" + request.client_nonce).encode()).hexdigest()
    session_id = digest[:36]
    allocate = False
    instructions = VOICE_INSTRUCTIONS
    seed: list[dict[str, Any]] = []
    # Commit admission before the external paid effect: an ambiguous HTTP failure
    # must never admit the same client receipt as another paid negotiation.
    async with db.sessions() as session, session.begin():
        if session.get_bind().dialect.name == "postgresql":
            await session.execute(
                text("SELECT pg_advisory_xact_lock(:key)"), {"key": int(digest[:15], 16)}
            )
        if await session.get(EffectReceiptRow, "voice:init-cancel:" + digest):
            raise LonoraError("voice_session_closed", 409)
        thread = await owned_thread(session, owner_id, request.thread_id)
        agent = await owned_agent(session, owner_id, request.agent_id)
        if thread.agent_id != request.agent_id:
            raise LonoraError("voice_agent_thread_mismatch", 409)
        if agent.paused:
            raise LonoraError("agent_paused", 409)
        previous = await session.get(VoiceSessionRow, session_id)
        if previous:
            if (
                previous.owner_id != owner_id
                or previous.thread_id != thread.id
                or previous.agent_id != request.agent_id
                or previous.state.get("offer_hash")
                != hashlib.sha256(request.sdp.encode()).hexdigest()
            ):
                raise LonoraError("voice_session_mismatch", 409)
            if previous.payload.get("status") not in {"allocating", "joining", "connected"}:
                raise LonoraError("voice_session_closed", 409)
        else:
            instructions, seed = await voice_context(
                session, owner_id, agent, thread.id, VOICE_INSTRUCTIONS
            )
            row = await VoiceSessionRepository().create(
                session,
                owner_id,
                {
                    "mode": "gpt_live",
                    "status": "allocating",
                    "model": model.model,
                },
                agent_id=agent.id,
                thread_id=thread.id,
                resource_id=session_id,
            )
            row.state = {
                "offer_hash": hashlib.sha256(request.sdp.encode()).hexdigest(),
                "input": [],
                "output": [],
                "delegations": {},
                "input_offset": -1,
                "last_activity": time.time(),
            }
            allocate = True
    remote_id = ""
    if allocate:
        try:
            result = await adapter.create(
                {
                    "model": model.model,
                    "instructions": instructions,
                    "delegation": {"type": "client"},
                    "input": seed,
                    "store": False,
                },
                request.sdp,
            )
            remote_id = str(result["session"]["id"])
            async with db.sessions() as session, session.begin():
                row = await VoiceSessionRepository().get(session, owner_id, session_id, lock=True)
                cancelled = row.payload.get("status") != "allocating"
                row.payload = {
                    **row.payload,
                    "remote_id": remote_id,
                    "status": "closing" if cancelled else "joining",
                }
                row.state = {**row.state, "answer": result["transport"]["sdp"]}
            if cancelled:
                await adapter.close_session(remote_id)
                raise LonoraError("voice_session_closed", 409)
        except BaseException:
            if remote_id:
                await adapter.close_session(remote_id)
            async with db.sessions() as session, session.begin():
                row = await VoiceSessionRepository().get(session, owner_id, session_id, lock=True)
                if row.payload.get("status") == "allocating":
                    row.payload = {
                        **row.payload,
                        "status": "failed",
                        "error": "voice_connection_failed",
                    }
            raise
    # The resident Gateway alone processes transcripts and delegated actions.
    # Do not return the microphone answer before that observer is attached.
    try:
        async with asyncio.timeout(20):
            while True:
                async with db.sessions() as session:
                    row = await VoiceSessionRepository().get(session, owner_id, session_id)
                    remote_id = str(row.payload.get("remote_id") or "")
                    status = row.payload.get("status")
                    if status == "connected":
                        return {"session_id": row.id, "sdp": row.state["answer"]}
                    if status in {"closed", "failed", "closing"}:
                        raise LonoraError(
                            str(row.payload.get("error", "voice_connection_failed")), 502
                        )
                await asyncio.sleep(0.2)
    except (TimeoutError, asyncio.CancelledError) as failure:
        await end_voice_session(db, owner_id, session_id)
        if remote_id:
            await adapter.close_session(remote_id)
        if isinstance(failure, asyncio.CancelledError):
            raise
        raise LonoraError("voice_backend_unavailable", 503) from None


async def end_voice_session(db: Database, owner_id: str, session_id: str) -> None:
    async with db.sessions() as session, session.begin():
        row = await VoiceSessionRepository().get(session, owner_id, session_id, lock=True)
        if row.payload.get("status") not in {"closed", "failed"}:
            row.payload = {**row.payload, "status": "closing"}
            row.version += 1


async def voice_session_data(db: Database, owner_id: str, session_id: str) -> dict[str, Any]:
    async with db.sessions() as session:
        row = await VoiceSessionRepository().get(session, owner_id, session_id)
        return {
            "session_id": row.id,
            "status": row.payload.get("status"),
            "model": row.payload.get("model"),
            "error": row.payload.get("error"),
            "input": row.state.get("input", []),
            "output": row.state.get("output", []),
            "usage": row.state.get("usage"),
            "finalized": row.state.get("finalized", False),
        }


async def cancel_voice_initialization(db: Database, owner_id: str, client_nonce: str) -> None:
    digest = hashlib.sha256((owner_id + ":" + client_nonce).encode()).hexdigest()
    async with db.sessions() as session, session.begin():
        if session.get_bind().dialect.name == "postgresql":
            await session.execute(
                text("SELECT pg_advisory_xact_lock(:key)"), {"key": int(digest[:15], 16)}
            )
        receipt = "voice:init-cancel:" + digest
        if await session.get(EffectReceiptRow, receipt) is None:
            session.add(EffectReceiptRow(key=receipt, result={"cancelled": True}))
        row = await session.get(VoiceSessionRow, digest[:36], with_for_update=True)
        if (
            row
            and row.owner_id == owner_id
            and row.payload.get("status") not in {"closed", "failed"}
        ):
            row.payload = {**row.payload, "status": "closing"}
