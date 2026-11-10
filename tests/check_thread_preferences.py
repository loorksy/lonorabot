"""Phase 2 storage on a fresh disposable PostgreSQL: the migration round trip
0045 → 0043 → 0045 with exactly one head, then the inbox projection through the owner API
(read cursor, pins, mute, archive and keep-archived, «مسح», custom lists, folded search)."""

import asyncio
import subprocess
import sys
from typing import Any
from uuid import uuid4

from check_streaming import Fixture, test_settings
from lonora_db.client import Database
from lonora_db.events import emit
from lonora_db.messages import message_data
from lonora_db.schema import MessageRow, ThreadRow
from lonora_gateway.thread_prefs import thread_prefs_tick
from sqlalchemy import inspect

ALEMBIC = [sys.executable, "-m", "alembic", "-c", "packages/db/alembic.ini"]


def alembic(*arguments: str) -> str:
    completed = subprocess.run([*ALEMBIC, *arguments], check=True, capture_output=True, text=True)
    return completed.stdout


async def table_names(db: Database) -> tuple[set[str], set[str], set[str]]:
    async with db.engine.connect() as connection:
        tables = set(await connection.run_sync(lambda conn: inspect(conn).get_table_names()))
        columns = {
            column["name"]
            for column in await connection.run_sync(
                lambda conn: inspect(conn).get_columns("ln_agents")
            )
        }
        indexes = {
            str(index["name"])
            for index in await connection.run_sync(
                lambda conn: inspect(conn).get_indexes("ln_messages")
            )
        }
    return tables, columns, indexes


async def round_trip() -> None:
    db = Database.connect(test_settings().database_url)
    try:
        heads = [line.strip() for line in alembic("heads").splitlines() if line.strip()]
        # Exactly one head; later phases chain their revisions after 0045.
        assert len(heads) == 1 and heads[0].endswith("(head)"), heads
        tables, columns, indexes = await table_names(db)
        assert {"ln_thread_prefs", "ln_chat_lists", "ln_chat_list_members"} <= tables
        assert "template" in columns and "ln_messages_content_folded" in indexes
        await db.close()
        await asyncio.to_thread(alembic, "downgrade", "0043_owner_held_pauses")
        tables, columns, indexes = await table_names(db)
        assert not {"ln_thread_prefs", "ln_chat_lists", "ln_chat_list_members"} & tables
        assert "template" not in columns and "ln_messages_content_folded" not in indexes
        assert "ln_agents" in tables and "ln_messages" in tables
        await db.close()
        await asyncio.to_thread(alembic, "upgrade", "head")
        tables, columns, indexes = await table_names(db)
        assert {"ln_thread_prefs", "ln_chat_lists", "ln_chat_list_members"} <= tables
        assert "template" in columns and "ln_messages_content_folded" in indexes
        print("PASS migration round trip 0045 -> 0043 -> 0045 with one head")
    finally:
        await db.close()


async def reply(fixture: Fixture, thread_id: str, agent_id: str, text: str) -> None:
    async with fixture.runtime.db.sessions() as session, session.begin():
        thread = await session.get(ThreadRow, thread_id, with_for_update=True)
        assert thread is not None
        message = MessageRow(
            thread_id=thread_id,
            agent_id=agent_id,
            seq=thread.next_seq,
            role="assistant",
            content=text,
        )
        thread.next_seq += 1
        session.add(message)
        await session.flush()
        emit(
            session,
            fixture.owner,
            "message.created",
            thread_id=thread_id,
            agent_id=agent_id,
            payload=message_data(message),
        )


async def entry(fixture: Fixture, thread_id: str) -> dict[str, Any]:
    inbox: Any = await fixture.request("GET", "/threads/inbox")
    return next(item for item in inbox if item["thread_id"] == thread_id)


async def projection() -> None:
    fixture = await Fixture().open()
    try:
        gold = await fixture.agent("Gold")
        news = await fixture.agent("News")
        gold_thread = await fixture.conversation(gold)
        news_thread = await fixture.conversation(news)
        await fixture.request(
            "POST",
            f"/threads/{gold_thread['id']}/messages",
            {"content": "ما وضع الذَّهَب اليوم؟", "client_nonce": uuid4().hex},
        )
        await reply(fixture, gold_thread["id"], gold["id"], "الذهب يرتفع فوق 2400")
        await reply(fixture, gold_thread["id"], gold["id"], "تم فتح مراقبة")
        await reply(fixture, news_thread["id"], news["id"], "أخبار الفيدرالي")
        gold_entry = await entry(fixture, gold_thread["id"])
        assert gold_entry["unread_count"] == 2 and gold_entry["last_message"]["seq"] == 3
        assert gold_entry["last_message"]["preview"] == "تم فتح مراقبة"
        assert gold_entry["last_message"]["agent_id"] == gold["id"]
        assert (await entry(fixture, news_thread["id"]))["unread_count"] == 1
        print("PASS inbox carries unread counts, the agent and the preview of the last message")

        await fixture.request("POST", f"/threads/{gold_thread['id']}/read", {"seq": 3})
        assert (await entry(fixture, gold_thread["id"]))["unread_count"] == 0
        await fixture.request("PATCH", f"/threads/{news_thread['id']}/prefs", {"pinned": True})
        await fixture.request(
            "PATCH", f"/threads/{gold_thread['id']}/prefs", {"pinned": True, "muted": True}
        )
        assert (await entry(fixture, gold_thread["id"]))["pinned_order"] == 1
        assert (await entry(fixture, news_thread["id"]))["pinned_order"] == 2
        archived = await fixture.request(
            "PATCH", f"/threads/{gold_thread['id']}/prefs", {"archived": True}
        )
        assert archived["pinned_order"] is None and archived["muted"] is True
        assert (await entry(fixture, news_thread["id"]))["pinned_order"] == 1
        print("PASS read cursor, pin order and archive-unpins through the API")

        await fixture.request("PUT", "/threads/settings", {"keep_archived": False})
        await thread_prefs_tick(fixture.runtime.db, fixture.owner)
        await reply(fixture, gold_thread["id"], gold["id"], "تحديث جديد")
        await thread_prefs_tick(fixture.runtime.db, fixture.owner)
        gold_entry = await entry(fixture, gold_thread["id"])
        assert gold_entry["archived"] is False and gold_entry["unread_count"] == 1
        await fixture.request("PUT", "/threads/settings", {"keep_archived": True})
        print("PASS keep-archived off returns the conversation on a new message")

        cleared = await fixture.request("POST", f"/threads/{gold_thread['id']}/clear")
        assert cleared["hidden_before_seq"] == 4
        assert await fixture.request("GET", f"/threads/{gold_thread['id']}/messages") == []
        assert (await entry(fixture, gold_thread["id"]))["last_message"] is None
        assert (await fixture.request("GET", f"/threads/{gold_thread['id']}"))["id"] == gold_thread[
            "id"
        ]
        print("PASS «مسح» hides the history for the owner and keeps the thread")

        listed = await fixture.request("POST", "/chat-lists", {"name": "تداول"})
        await fixture.request(
            "PUT", f"/chat-lists/{listed['id']}/members", {"thread_ids": [news_thread["id"]]}
        )
        lists: Any = await fixture.request("GET", "/chat-lists")
        assert lists[0]["thread_ids"] == [news_thread["id"]]
        await fixture.request("DELETE", f"/chat-lists/{listed['id']}")
        print("PASS custom lists hold the owner's conversations")

        found = await fixture.request("GET", "/search?q=الفِيدرالي&category=messages")
        assert found["counts"]["messages"] == 1
        assert found["results"]["messages"][0]["thread_id"] == news_thread["id"]
        hidden = await fixture.request("GET", "/search?q=2400&category=messages")
        assert hidden["counts"]["messages"] == 0
        print("PASS folded search finds the visible message and not the hidden one")
    finally:
        await fixture.close()


async def main() -> None:
    await round_trip()
    await projection()


if __name__ == "__main__":
    asyncio.run(main())
