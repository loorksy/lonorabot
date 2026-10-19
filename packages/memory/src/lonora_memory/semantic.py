import math
from typing import Any

import httpx
from lonora_core.user_error import LonoraError
from lonora_db.client import Database
from lonora_db.schema import SemanticMemoryRow
from lonora_db.transactions import SettingsRepository, owned_agent
from lonora_providers.credentials import ProviderCredentials
from lonora_session.idempotency import stable_id

from .conversation import ConversationRecallScope


def cosine_similarity(first: list[float], second: list[float]) -> float:
    if not first or len(first) != len(second) or any(not math.isfinite(v) for v in first + second):
        raise LonoraError("invalid_embedding")
    first_norm, second_norm = math.hypot(*first), math.hypot(*second)
    if not math.isfinite(first_norm) or not math.isfinite(second_norm):
        raise LonoraError("invalid_embedding")
    if not first_norm or not second_norm:
        return 0.0
    return sum((a / first_norm) * (b / second_norm) for a, b in zip(first, second, strict=True))


def semantic_retrieve(
    query: list[float], documents: list[tuple[str, list[float]]], limit: int = 5
) -> list[str]:
    scored = sorted(
        ((cosine_similarity(query, vector), text) for text, vector in documents), reverse=True
    )
    return [text for _, text in scored[:limit]]


async def embed_text(credentials: ProviderCredentials, model: str, text: str) -> list[float]:
    token = await credentials.resolve("openai")
    try:
        async with httpx.AsyncClient(timeout=45) as client:
            response = await client.post(
                "https://api.openai.com/v1/embeddings",
                headers={"Authorization": "Bearer " + token},
                json={"model": model, "input": text[:24000]},
            )
            response.raise_for_status()
            vector = [float(value) for value in response.json()["data"][0]["embedding"]]
        if not vector or len(vector) > 8192 or any(not math.isfinite(value) for value in vector):
            raise ValueError()
        return vector
    except (httpx.HTTPError, ValueError, KeyError, TypeError, IndexError, OverflowError):
        raise LonoraError("semantic_source_unavailable", 502) from None


async def retrieve_memory(
    db: Database,
    credentials: ProviderCredentials,
    owner_id: str,
    agent_id: str,
    query: str,
    *,
    conversation_scope: ConversationRecallScope | None = None,
) -> str:
    from .evidence import render_evidence, retrieve_evidence

    return render_evidence(
        await retrieve_evidence(
            db, credentials, owner_id, agent_id, query, conversation_scope=conversation_scope
        )
    )


async def index_note(
    db: Database, credentials: ProviderCredentials, owner_id: str, agent_id: str, text: str
) -> dict[str, Any]:
    if not text.strip():
        raise LonoraError("memory_note_required")
    if len(text) > 24000:
        raise LonoraError("memory_too_large", 413)
    async with db.sessions() as session:
        await owned_agent(session, owner_id, agent_id)
        config = await SettingsRepository().get(session, "semantic_memory")
    if not config.get("enabled") or not config.get("model"):
        raise LonoraError("semantic_model_required", 409)
    model = str(config["model"])
    vector = await embed_text(credentials, model, text)
    document_id = stable_id(agent_id, model + ":" + text)
    async with db.sessions() as session, session.begin():
        await owned_agent(session, owner_id, agent_id)
        row = await session.get(SemanticMemoryRow, document_id, with_for_update=True)
        if row is None:
            row = SemanticMemoryRow(
                id=document_id,
                owner_id=owner_id,
                agent_id=agent_id,
                payload={"text": text, "embedding": vector, "model": model},
            )
            session.add(row)
        return {"id": document_id, "indexed": True}
