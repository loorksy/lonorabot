"""Real PostgreSQL authorization and bounded compacted-history recall, no providers."""

import asyncio
import json
from typing import cast
from uuid import uuid4

from check_streaming import Fixture
from lonora_agent.context.builder import build_context
from lonora_core.user_error import LonoraError
from lonora_db.schema import MessageRow, RunRow, ThreadRow
from lonora_db.transactions import SettingsRepository
from lonora_memory.conversation import ConversationRecallScope
from lonora_memory.evidence import retrieve_evidence
from lonora_providers.credentials import ProviderCredentials
from sqlalchemy import delete, update


async def main() -> None:
    fixture = await Fixture().open()
    db = fixture.runtime.db
    credentials = cast(ProviderCredentials, object())
    try:
        agent, peer = await fixture.agent("Recall owner"), await fixture.agent("Recall peer")
        thread_id = str(uuid4())
        message_ids: dict[int, str] = {}
        async with db.sessions() as session, session.begin():
            await SettingsRepository().put(session, "semantic_memory", {"enabled": False})
            session.add(
                ThreadRow(
                    id=thread_id,
                    owner_id=fixture.owner,
                    agent_id=agent["id"],
                    summary_seq=10,
                    next_seq=14,
                )
            )
            await session.flush()
            rows = [
                (1, "user", None, "XAUUSDm archived first question"),
                (2, "assistant", agent["id"], "Adjacent response without query terms"),
                (3, "assistant", peer["id"], "XAUUSDm peer secret"),
                (4, "system", None, "XAUUSDm system secret"),
                (5, "tool", agent["id"], "XAUUSDm tool secret"),
                (6, "user", peer["id"], "XAUUSDm forged peer user secret"),
                (7, "assistant", agent["id"], "XAUUSDm peer nonce secret"),
                (8, "user", None, "مَخَاطِر الذهب مرتفعة"),
                (9, "assistant", agent["id"], "BTCUSD# archived crypto"),
                (10, "assistant", agent["id"], "EURUSD.a archived risk"),
                (11, "user", None, "XAUUSDm recent context secret"),
                (12, "user", None, "XAUUSDm active input secret"),
                (13, "user", None, "XAUUSDm future steering secret"),
                (14, "user", None, "XAUUSDm uncommitted sequence secret"),
            ]
            for seq, role, author, text in rows:
                identity = message_ids[seq] = str(uuid4())
                session.add(
                    MessageRow(
                        id=identity,
                        thread_id=thread_id,
                        seq=seq,
                        role=role,
                        agent_id=author,
                        content=text,
                        client_nonce="peer:transport" if seq == 7 else None,
                    )
                )
        scope = ConversationRecallScope(thread_id, 12, 100, include_neighbor=True)

        async def recall(
            query: str, selected: ConversationRecallScope | None = scope, **kwargs: int
        ):
            return await retrieve_evidence(
                db,
                credentials,
                fixture.owner,
                agent["id"],
                query,
                conversation_scope=selected,
                **kwargs,
            )

        result = await recall("XAUUSDm")
        assert result.conversation_status == "matched"
        assert [item.provenance["seq"] for item in result.items] == [1, 2]
        assert result.items[0].id == "message:" + message_ids[1]
        assert result.items[0].provenance["author_id"] == fixture.owner
        assert result.items[0].authority == "untrusted_historical_conversation"
        assert result.items[1].provenance["neighbor_of_seq"] == 1
        reverse = await recall("Adjacent response")
        assert [item.provenance["seq"] for item in reverse.items] == [2, 1]
        assert reverse.items[1].provenance["neighbor_of_seq"] == 2
        assert "secret" not in str(result.as_dict())
        assert not (await recall("XAUUSD")).items
        assert not (await recall("EURUSD.b")).items
        assert (await recall("مخاطر الذهب")).items[0].provenance["seq"] == 8
        assert not (await recall("XAUUSDm", None)).items
        # Exercise the real ContextBuilder callsite with server-owned Run cutoffs.
        run = await fixture.request(
            "POST", "/runs", {"agent_id": agent["id"], "thread_id": thread_id, "prompt": "XAUUSDm"}
        )
        async with db.sessions() as session, session.begin():
            await session.execute(update(RunRow).where(RunRow.id == run["id"]).values(input_seq=12))
        context = await fixture.lease(run)
        messages = await build_context(context)
        system = messages[0].content
        marker = "Historical memory does not establish current broker state.\n"
        assert marker in system
        actual_evidence, _ = json.JSONDecoder().raw_decode(system.split(marker, 1)[1])
        actual_items = actual_evidence["items"]
        assert [item["provenance"]["seq"] for item in actual_items] == [1, 2]
        assert actual_items[1]["provenance"]["neighbor_of_seq"] == 1
        assert "secret" not in json.dumps(actual_items)
        assert all(
            item["authority"] == "untrusted_historical_conversation" for item in actual_items
        )
        assert not (await recall("XAUUSDm", ConversationRecallScope(thread_id, 1, 10))).items
        assert not (await recall("XAUUSDm", ConversationRecallScope(thread_id, 12, 0))).items
        limited = await recall("XAUUSDm", maximum_chars=12, limit=1)
        assert len(limited.items) == 1 and sum(len(item.text) for item in limited.items) <= 12
        for owner, aid, tid in [
            (str(uuid4()), agent["id"], thread_id),
            (fixture.owner, peer["id"], thread_id),
            (fixture.owner, agent["id"], str(uuid4())),
        ]:
            try:
                denied = await retrieve_evidence(
                    db,
                    credentials,
                    owner,
                    aid,
                    "XAUUSDm",
                    conversation_scope=ConversationRecallScope(tid, 12, 10),
                )
            except LonoraError as error:
                assert error.status == 404
            else:
                assert denied.conversation_status == "scope_unavailable" and not denied.items
        async with db.sessions() as session, session.begin():
            await session.execute(
                update(ThreadRow).where(ThreadRow.id == thread_id).values(group_id=str(uuid4()))
            )
        group = await recall("XAUUSDm")
        assert not group.items and group.conversation_status == "scope_unavailable"
        async with db.sessions() as session, session.begin():
            await session.execute(
                update(ThreadRow).where(ThreadRow.id == thread_id).values(group_id=None)
            )
            await session.execute(
                update(MessageRow)
                .where(MessageRow.id == message_ids[1])
                .values(content="update_needle account note")
            )
        assert not (await recall("XAUUSDm")).items
        assert (await recall("update_needle")).items[0].id == "message:" + message_ids[1]
        async with db.sessions() as session, session.begin():
            await session.execute(delete(MessageRow).where(MessageRow.id == message_ids[1]))
        assert not (await recall("update_needle")).items
        async with db.sessions() as session, session.begin():
            await session.execute(
                update(ThreadRow)
                .where(ThreadRow.id == thread_id)
                .values(summary_seq=20, next_seq=21)
            )
        async with db.sessions() as pending:
            pending.add(
                MessageRow(thread_id=thread_id, seq=15, role="user", content="uncommitted_needle")
            )
            await pending.flush()
            unseen = await recall("uncommitted_needle", ConversationRecallScope(thread_id, 21, 20))
            assert not unseen.items
            await pending.rollback()
        async with db.sessions() as session, session.begin():
            for seq, role, author, text in [
                (16, "assistant", agent["id"], "previous unrelated answer"),
                (17, "user", None, "exchange_user question"),
                (18, "assistant", agent["id"], "exchange_answer response"),
                (19, "user", None, "isolated_anchor question"),
                (20, "assistant", peer["id"], "peer answer must not expand"),
            ]:
                session.add(
                    MessageRow(
                        thread_id=thread_id, seq=seq, role=role, agent_id=author, content=text
                    )
                )
        expanded_scope = ConversationRecallScope(thread_id, 21, 20, include_neighbor=True)
        assert [
            item.provenance["seq"] for item in (await recall("exchange_user", expanded_scope)).items
        ] == [17, 18]
        assert [
            item.provenance["seq"]
            for item in (await recall("exchange_answer", expanded_scope)).items
        ] == [18, 17]
        assert [
            item.provenance["seq"]
            for item in (await recall("isolated_anchor", expanded_scope)).items
        ] == [19]
        # Old source data is read anew, bounded before returning to the model.
        async with db.sessions() as session, session.begin():
            await session.execute(
                update(ThreadRow)
                .where(ThreadRow.id == thread_id)
                .values(summary_seq=500, next_seq=501)
            )
            for seq in range(21, 166):
                session.add(
                    MessageRow(
                        thread_id=thread_id,
                        seq=seq,
                        role="user",
                        content="boundedsearch " + "z" * 10000,
                    )
                )
        bounded = await recall(
            "boundedsearch",
            ConversationRecallScope(thread_id, 501, 500),
            maximum_chars=500,
            limit=8,
        )
        assert "conversation_candidate_limit" in bounded.reasons
        assert bounded.truncated and sum(len(item.text) for item in bounded.items) <= 500
        oversized = await recall(
            "boundedsearch " * 500, ConversationRecallScope(thread_id, 501, 500)
        )
        assert "query_limit" in oversized.reasons
        print(
            "PASS PostgreSQL conversation recall: direct scope, roles/authors, exact symbols, Arabic, summary/input/next-sequence cutoffs, one neighbor, edits/deletes, query/candidate/output limits"
        )
    finally:
        async with db.sessions() as session, session.begin():
            await session.execute(
                delete(ThreadRow).where(ThreadRow.id == locals().get("thread_id", ""))
            )
        await fixture.close()


if __name__ == "__main__":
    asyncio.run(main())
