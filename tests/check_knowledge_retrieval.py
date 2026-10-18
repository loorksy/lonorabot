"""Disposable PostgreSQL checks: scoped evidence, fallback, edits/deletes and caps.

Embedding replies are scripted; this never contacts a model or a broker.
"""

import asyncio
from typing import cast
from unittest.mock import AsyncMock, patch
from uuid import uuid4

from check_streaming import Fixture
from lonora_core.user_error import LonoraError
from lonora_db.memory import commit_memory
from lonora_db.schema import SemanticMemoryRow
from lonora_db.transactions import SettingsRepository
from lonora_memory.evidence import CANDIDATE_LIMIT, retrieve_evidence
from lonora_providers.credentials import ProviderCredentials
from sqlalchemy import delete


async def main() -> None:
    fixture = await Fixture().open()
    credentials = cast(ProviderCredentials, object())
    db = fixture.runtime.db
    old_config: dict[str, object] = {}
    try:
        agent = await fixture.agent("Knowledge retrieval")
        peer = await fixture.agent("Separate private memory")
        agent_id = agent["id"]
        old_id = str(uuid4())
        secret_id = str(uuid4())
        async with db.sessions() as session, session.begin():
            old_config = await SettingsRepository().get(session, "semantic_memory")
            await SettingsRepository().put(session, "semantic_memory", {"enabled": False})
            await commit_memory(
                session,
                fixture.owner,
                agent_id,
                "# Owner notes\nمخاطر الذهب مرتفعة\nEURUSD.a risk limit",
                1,
            )
            session.add(
                SemanticMemoryRow(
                    id=old_id,
                    owner_id=fixture.owner,
                    agent_id=agent_id,
                    payload={
                        "text": "needle recall prior evidence",
                        "model": "scripted",
                        "embedding": [1.0, 0.0],
                    },
                )
            )
            session.add(
                SemanticMemoryRow(
                    id=secret_id,
                    owner_id=fixture.owner,
                    agent_id=peer["id"],
                    payload={
                        "text": "needle private peer secret",
                        "model": "scripted",
                        "embedding": [1.0, 0.0],
                    },
                )
            )
        async with db.sessions() as session, session.begin():
            for number in range(CANDIDATE_LIMIT + 12):
                session.add(
                    SemanticMemoryRow(
                        owner_id=fixture.owner,
                        agent_id=agent_id,
                        payload={
                            "text": f"irrelevant archival note {number}",
                            "model": "scripted",
                            "embedding": [0.0, 1.0],
                        },
                    )
                )
        with patch("lonora_memory.semantic.embed_text", new_callable=AsyncMock) as embed:
            result = await retrieve_evidence(db, credentials, fixture.owner, agent_id, "needle")
            embed.assert_not_awaited()
        assert result.mode == "lexical" and result.semantic_status == "disabled"
        assert result.status == "partial" and "candidate_limit" in result.reasons
        assert [item.id for item in result.items] == ["note:" + old_id]
        assert "secret" not in str(result.as_dict())
        arabic = await retrieve_evidence(db, credentials, fixture.owner, agent_id, "مخاطر الذهب")
        assert any(item.source == "memory" and item.version == 2 for item in arabic.items)
        assert arabic.items[0].provenance["source"] == "owner_provided"
        assert arabic.items[0].provenance["event_cursor"]
        exact = await retrieve_evidence(db, credentials, fixture.owner, agent_id, "EURUSD.b")
        assert not exact.items
        with patch("lonora_memory.semantic.embed_text", new_callable=AsyncMock) as embed:
            try:
                await retrieve_evidence(db, credentials, str(uuid4()), agent_id, "needle")
            except LonoraError as error:
                assert error.status == 404
            else:
                raise AssertionError("foreign owner was allowed")
            embed.assert_not_awaited()

        async with db.sessions() as session, session.begin():
            await SettingsRepository().put(
                session, "semantic_memory", {"enabled": True, "model": "scripted"}
            )
        with patch("lonora_memory.semantic.embed_text", AsyncMock(return_value=[1.0, 0.0])):
            result = await retrieve_evidence(db, credentials, fixture.owner, agent_id, "needle")
        assert result.mode == "hybrid" and result.semantic_status == "ready"
        assert result.items[0].id == "note:" + old_id
        with patch(
            "lonora_memory.semantic.embed_text",
            AsyncMock(side_effect=LonoraError("semantic_source_unavailable", 502)),
        ):
            fallback = await retrieve_evidence(db, credentials, fixture.owner, agent_id, "needle")
            unavailable = await retrieve_evidence(
                db, credentials, fixture.owner, agent_id, "unmatched"
            )
        assert fallback.status == "partial" and fallback.semantic_status == "unavailable"
        assert fallback.items and unavailable.status == "unavailable" and not unavailable.items

        # Same durable store, no cached old memory or deleted note on the next read.
        async with db.sessions() as session, session.begin():
            await commit_memory(
                session, fixture.owner, agent_id, "# Current\nreplacement owner note", 2
            )
            await session.execute(delete(SemanticMemoryRow).where(SemanticMemoryRow.id == old_id))
            await SettingsRepository().put(session, "semantic_memory", {"enabled": True})
        revised = await retrieve_evidence(db, credentials, fixture.owner, agent_id, "replacement")
        assert revised.semantic_status == "unconfigured"
        assert any(item.version == 3 and ":v3:" in item.id for item in revised.items)
        deleted = await retrieve_evidence(db, credentials, fixture.owner, agent_id, "needle")
        assert not deleted.items

        # Model mismatch, invalid and oversized payloads remain explicit and bounded.
        async with db.sessions() as session, session.begin():
            await session.execute(
                delete(SemanticMemoryRow).where(SemanticMemoryRow.agent_id == agent_id)
            )
            await SettingsRepository().put(
                session, "semantic_memory", {"enabled": True, "model": "new-model"}
            )
            session.add(
                SemanticMemoryRow(
                    owner_id=fixture.owner,
                    agent_id=agent_id,
                    payload={
                        "text": "needle stale model text",
                        "model": "old-model",
                        "embedding": [1, 0],
                    },
                )
            )
        with patch("lonora_memory.semantic.embed_text", new_callable=AsyncMock) as embed:
            stale_model = await retrieve_evidence(
                db, credentials, fixture.owner, agent_id, "needle"
            )
            embed.assert_not_awaited()
        assert stale_model.semantic_status == "no_embeddings" and stale_model.items
        assert (
            stale_model.items[0].freshness == "unknown" and stale_model.items[0].source_time is None
        )
        async with db.sessions() as session, session.begin():
            session.add(
                SemanticMemoryRow(
                    owner_id=fixture.owner,
                    agent_id=agent_id,
                    payload={
                        "text": "needle " + "x" * 100000,
                        "model": "new-model",
                        "embedding": [0.1] * 50000,
                    },
                )
            )
        with patch("lonora_memory.semantic.embed_text", AsyncMock(return_value=[1.0, 0.0])):
            oversized = await retrieve_evidence(
                db, credentials, fixture.owner, agent_id, "needle", maximum_chars=300
            )
        assert "invalid_embeddings" in oversized.reasons
        assert oversized.truncated and sum(len(item.text) for item in oversized.items) <= 300
        assert all(item.authority == "untrusted_memory_content" for item in oversized.items)
        assert oversized.mode == "lexical" and oversized.semantic_status == "invalid_embeddings"
        async with db.sessions() as session, session.begin():
            await session.execute(
                delete(SemanticMemoryRow).where(SemanticMemoryRow.agent_id == agent_id)
            )
            session.add(
                SemanticMemoryRow(
                    owner_id=fixture.owner,
                    agent_id=agent_id,
                    payload={
                        "text": "Gold historical note",
                        "model": "new-model",
                        "embedding": [0.0, 1.0],
                    },
                )
            )
        with patch("lonora_memory.semantic.embed_text", AsyncMock(return_value=[1.0, 0.0])):
            no_match = await retrieve_evidence(
                db, credentials, fixture.owner, agent_id, "unmatched"
            )
        assert no_match.status == "no_match" and no_match.lexical_status == "no_match"
        assert no_match.semantic_status == "ready" and not no_match.items
        print(
            "PASS real PostgreSQL scoped bounded hybrid/lexical retrieval, Arabic/English, exact symbols, source versions/events, cross-owner denial, peer isolation, provider failure, model mismatch, edits/deletes and oversized vectors/text"
        )
    finally:
        async with db.sessions() as session, session.begin():
            await SettingsRepository().put(session, "semantic_memory", old_config)
        await fixture.close()


if __name__ == "__main__":
    asyncio.run(main())
