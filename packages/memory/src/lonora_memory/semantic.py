import math
from typing import Any

import httpx
from lonora_core.user_error import LonoraError
from lonora_db.client import Database
from lonora_db.schema import SemanticMemoryRow
from lonora_db.transactions import SettingsRepository, owned_agent
from lonora_providers.credentials import ProviderCredentials
from lonora_session.idempotency import stable_id
from sqlalchemy import select


def cosine_similarity(first: list[float], second: list[float]) -> float:
    if not first or len(first) != len(second) or any(not math.isfinite(v) for v in first + second):
        raise LonoraError("invalid_embedding")
    norm = math.sqrt(sum(x * x for x in first) * sum(x * x for x in second))
    return sum(a * b for a, b in zip(first, second, strict=True)) / norm if norm else 0.0


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
        if not vector or any(not math.isfinite(value) for value in vector):
            raise ValueError()
        return vector
    except (httpx.HTTPError, ValueError, KeyError, TypeError):
        raise LonoraError("semantic_source_unavailable", 502) from None


async def retrieve_memory(
    db: Database, credentials: ProviderCredentials, owner_id: str, agent_id: str, query: str
) -> str:
    async with db.sessions() as session:
        await owned_agent(session, owner_id, agent_id)
        config = await SettingsRepository().get(session, "semantic_memory")
        if not config.get("enabled"):
            return ""
        model = config.get("model")
        if not model:
            raise LonoraError("semantic_model_required", 409)
        rows = (
            await session.scalars(
                select(SemanticMemoryRow).where(
                    SemanticMemoryRow.owner_id == owner_id, SemanticMemoryRow.agent_id == agent_id
                )
            )
        ).all()
    if not rows:
        return ""
    vector = await embed_text(credentials, str(model), query)
    documents = [
        (str(row.payload["text"]), [float(value) for value in row.payload["embedding"]])
        for row in rows
        if row.payload.get("model") == model
    ]
    return (
        "<semantic_memory>\n"
        + "\n\n".join(semantic_retrieve(vector, documents))
        + "\n</semantic_memory>"
        if documents
        else ""
    )


async def index_note(
    db: Database, credentials: ProviderCredentials, owner_id: str, agent_id: str, text: str
) -> dict[str, Any]:
    async with db.sessions() as session:
        await owned_agent(session, owner_id, agent_id)
        config = await SettingsRepository().get(session, "semantic_memory")
    if not config.get("enabled") or not config.get("model"):
        raise LonoraError("semantic_model_required", 409)
    model = str(config["model"])
    vector = await embed_text(credentials, model, text)
    document_id = stable_id(agent_id, model + ":" + text)
    async with db.sessions() as session, session.begin():
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
