"""Thread preferences, chat lists and the owner's unified search (UI phase 2, WP-A/B/C).

The pure cases run everywhere. The PostgreSQL cases (LONORA_DATABASE_URL) go through the
owner API on the migrated schema: the read cursor and unread counts, the pin limit,
archive and keep-archived, «مسح» as a visibility cursor, the consumed marker, the group
lead, the persisted template, chat lists, folded search with paging and ``around=seq``.
"""

import os
from pathlib import Path
from typing import Any, cast
from uuid import uuid4

import pytest
from lonora_contracts.chat_lists import ChatListCreate
from lonora_contracts.groups import GroupCreate
from lonora_contracts.thread_prefs import ThreadPrefsUpdate
from lonora_core.message_preview import message_kind, message_preview
from lonora_core.search_fold import FOLD_FROM, FOLD_TO, fold
from lonora_db.search import knowledge_sections, snippet
from lonora_db.thread_prefs import consumed
from pydantic import ValidationError

# --- Pure ---------------------------------------------------------------------------


def test_folding_normalises_alef_ya_ta_marbuta_and_strips_tashkeel():
    assert fold("أَحْمَد") == "احمد"
    assert fold("إِلَى  المَدْرَسَة") == "الي المدرسه"
    assert fold("Ècole XAUUSD") == "ècole xauusd"
    assert fold("مـــرحبا") == "مرحبا"
    # Every folded source maps to one target or is deleted; the SQL translate() agrees.
    assert len(FOLD_FROM) > len(FOLD_TO) and FOLD_TO == "اااايه"


def test_snippet_is_the_reference_preview_window():
    text = "كلمة " * 60 + "هنا أَحْمَد يظهر" + " كلمة" * 60
    piece = snippet(text, "احمد")
    # Past the 55th character the window starts 45 characters before the hit.
    assert piece.startswith("…") and piece.endswith("…") and "أَحْمَد" in piece
    assert len(piece) == 145 + 2 and piece[1:].index("أَحْمَد") == 45
    assert snippet("short text", "zzz") == "short text"
    # A message that fits is never cut, wherever the hit is.
    briefing = "صباح الخير أحمد! موجز اليوم جاهز: " + " ".join(
        ["الذهب يرتفع قبل بيانات التضخم"] * 2
    )
    assert len(briefing) <= 145 and snippet(briefing, "الذهب") == briefing
    # A hit near the start keeps the start.
    early = "الذهب " + "نص " * 80
    assert snippet(early, "الذهب").startswith("الذهب") and snippet(early, "الذهب").endswith("…")


def test_knowledge_sections_are_titled_plain_text_without_file_names():
    view = (
        "# MEMORY.md\n## خطة الذهب\n- **الدخول** عند [الدعم](https://x.test)\n"
        "> ملاحظة `مهمة`\n\n# OPERATING.md\nGeneral agent: no pair.\n"
    )
    assert knowledge_sections(view) == [
        ("خطة الذهب", "الدخول عند الدعم ملاحظة مهمة"),
        ("", "General agent: no pair."),
    ]
    assert knowledge_sections("# MEMORY.md\n\n") == []


def test_preview_and_kind_follow_text_rich_parts_and_attachments():
    card: dict[str, Any] = {
        "version": 1,
        "parts": [{"type": "ui", "document": {}}, {"type": "text", "text": "  نص  "}],
    }
    assert message_kind(card, []) == "card"
    assert message_preview("", card, []) == "نص"
    assert message_kind(None, ["image", "file"]) == "image"
    assert message_preview("", None, ["report.pdf"]) == "report.pdf"
    assert message_preview(" a \n b ", None, []) == "a b"
    assert len(message_preview("x" * 500, None, [])) == 160


def test_consumed_marks_owner_messages_a_started_run_has_read():
    assert consumed({"role": "user", "seq": 3, "id": "m"}, 3, set()) is True
    assert consumed({"role": "user", "seq": 4, "id": "m"}, 3, set()) is False
    assert consumed({"role": "user", "seq": 4, "id": "m"}, 3, {"m"}) is True
    assert consumed({"role": "assistant", "seq": 1, "id": "m"}, 9, set()) is None


def test_contracts_refuse_empty_changes_and_a_lead_outside_the_group():
    with pytest.raises(ValidationError):
        ThreadPrefsUpdate.model_validate({})
    with pytest.raises(ValidationError):
        GroupCreate.model_validate({"name": "x", "member_ids": ["a"], "lead_agent_id": "b"})
    assert (
        GroupCreate.model_validate(
            {"name": "x", "member_ids": ["a"], "lead_agent_id": "a", "purpose": "p"}
        ).purpose
        == "p"
    )
    assert ChatListCreate.model_validate({"name": "  عملي   ١ "}).name == "عملي ١"
    with pytest.raises(ValidationError):
        ChatListCreate.model_validate({"name": "x" * 31})


def test_search_doc_matches_the_categories_only_response():
    doc = (Path(__file__).resolve().parents[1] / "docs/thread-preferences.md").read_text()
    section = doc.split("## Unified search", 1)[1].split("\n## ", 1)[0]
    assert "`agents`, `messages` and `memory` lists" not in section


# --- PostgreSQL: the owner API on the migrated schema -----------------------------------


def database() -> None:
    if not os.environ.get("LONORA_DATABASE_URL"):
        pytest.skip("The thread preference cases use the real migrated PostgreSQL schema.")


async def agent_reply(fixture: Any, thread_id: str, agent_id: str, text: str) -> str:
    """An agent's message as the runtime writes it: the row and its message.created event."""
    from lonora_db.events import emit
    from lonora_db.messages import message_data
    from lonora_db.schema import MessageRow, ThreadRow

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
        return message.id


async def owner_message(fixture: Any, thread_id: str, text: str) -> dict[str, Any]:
    return await fixture.request(
        "POST",
        f"/threads/{thread_id}/messages",
        {"content": text, "client_nonce": "prefs-" + uuid4().hex},
    )


async def listing(fixture: Any, path: str) -> list[dict[str, Any]]:
    return cast(list[dict[str, Any]], await fixture.request("GET", path))


async def inbox_entry(fixture: Any, thread_id: str) -> dict[str, Any]:
    entries = await listing(fixture, "/threads/inbox")
    return next(entry for entry in entries if entry["thread_id"] == thread_id)


async def events_of(fixture: Any, kind: str, thread_id: str | None = None) -> list[Any]:
    from lonora_db.schema import EventRow
    from sqlalchemy import select

    async with fixture.runtime.db.sessions() as session:
        query = select(EventRow).where(EventRow.owner_id == fixture.owner, EventRow.kind == kind)
        if thread_id:
            query = query.where(EventRow.thread_id == thread_id)
        return list(await session.scalars(query.order_by(EventRow.cursor)))


async def tick(fixture: Any) -> int:
    from lonora_gateway.thread_prefs import thread_prefs_tick

    return await thread_prefs_tick(fixture.runtime.db, fixture.owner)


@pytest.mark.asyncio
async def test_read_cursor_is_max_wins_and_drives_unread_counts():
    database()
    from check_streaming import Fixture

    fixture = await Fixture().open()
    try:
        agent = await fixture.agent("Reader")
        thread = await fixture.conversation(agent)
        await owner_message(fixture, thread["id"], "سؤال")
        await agent_reply(fixture, thread["id"], agent["id"], "جواب أول")
        await agent_reply(fixture, thread["id"], agent["id"], "جواب ثانٍ")
        entry = await inbox_entry(fixture, thread["id"])
        assert entry["unread_count"] == 2 and entry["last_read_seq"] == 0
        assert entry["last_message"]["role"] == "assistant"
        assert entry["last_message"]["agent_id"] == agent["id"]
        assert entry["last_message"]["preview"] == "جواب ثانٍ"
        assert entry["last_message"]["kind"] == "text" and entry["last_message"]["consumed"] is None
        read = await fixture.request("POST", f"/threads/{thread['id']}/read", {"seq": 2})
        assert read["last_read_seq"] == 2
        assert (await inbox_entry(fixture, thread["id"]))["unread_count"] == 1
        # Max-wins: an older cursor from another device changes nothing.
        read = await fixture.request("POST", f"/threads/{thread['id']}/read", {"seq": 1})
        assert read["last_read_seq"] == 2
        # Clamped to the latest message: a cursor past the end cannot hide the future.
        read = await fixture.request("POST", f"/threads/{thread['id']}/read", {"seq": 999})
        assert read["last_read_seq"] == 3
        assert (await inbox_entry(fixture, thread["id"]))["unread_count"] == 0
        await agent_reply(fixture, thread["id"], agent["id"], "جواب ثالث")
        assert (await inbox_entry(fixture, thread["id"]))["unread_count"] == 1
        # Marked unread shows as such; opening (read) clears both.
        marked = await fixture.request(
            "PATCH", f"/threads/{thread['id']}/prefs", {"marked_unread": True}
        )
        assert marked["marked_unread"] is True
        await fixture.request("POST", f"/threads/{thread['id']}/read", {"seq": 4})
        entry = await inbox_entry(fixture, thread["id"])
        assert entry["marked_unread"] is False and entry["unread_count"] == 0
        assert len(await events_of(fixture, "thread.read", thread["id"])) == 3
        # Read-all touches only what changed.
        await agent_reply(fixture, thread["id"], agent["id"], "جواب رابع")
        # Other conversations of this owner (Lonora's included) may change too.
        changed = cast(list[dict[str, Any]], await fixture.request("POST", "/threads/read-all"))
        mine = next(item for item in changed if item["thread_id"] == thread["id"])
        assert mine["last_read_seq"] == 5
        again = cast(list[dict[str, Any]], await fixture.request("POST", "/threads/read-all"))
        assert all(item["thread_id"] != thread["id"] for item in again)
    finally:
        await fixture.close()


@pytest.mark.asyncio
async def test_pin_limit_is_three_archiving_unpins_and_orders_renumber():
    database()
    from check_streaming import Fixture

    fixture = await Fixture().open()
    try:
        threads = [
            await fixture.conversation(await fixture.agent(f"Pin {index}")) for index in range(4)
        ]
        for thread in threads[:3]:
            pinned = await fixture.request(
                "PATCH", f"/threads/{thread['id']}/prefs", {"pinned": True}
            )
            assert pinned["pinned_order"] == 1  # new pins go on top
        orders = {
            entry["thread_id"]: entry["pinned_order"]
            for entry in await listing(fixture, "/threads/inbox")
            if entry["pinned_order"]
        }
        assert [orders[thread["id"]] for thread in threads[:3]] == [3, 2, 1]
        response = await fixture.client.patch(
            f"/api/threads/{threads[3]['id']}/prefs", json={"pinned": True}
        )
        assert response.status_code == 409 and response.json()["code"] == "thread_pin_limit"
        # The bulk variant refuses the whole batch past the limit.
        response = await fixture.client.post(
            "/api/threads/prefs", json={"thread_ids": [threads[3]["id"]], "pinned": True}
        )
        assert response.status_code == 409
        # Archiving the top pin frees a slot and renumbers the others.
        archived = await fixture.request(
            "PATCH", f"/threads/{threads[2]['id']}/prefs", {"archived": True}
        )
        assert archived["archived"] is True and archived["pinned_order"] is None
        orders = {
            entry["thread_id"]: entry["pinned_order"]
            for entry in await listing(fixture, "/threads/inbox")
            if entry["pinned_order"]
        }
        assert orders == {threads[0]["id"]: 2, threads[1]["id"]: 1}
        pinned = await fixture.request(
            "PATCH", f"/threads/{threads[3]['id']}/prefs", {"pinned": True}
        )
        assert pinned["pinned_order"] == 1
        # Bulk mute and favourite, then unpin.
        bulk = cast(
            list[dict[str, Any]],
            await fixture.request(
                "POST",
                "/threads/prefs",
                {
                    "thread_ids": [threads[0]["id"], threads[1]["id"]],
                    "muted": True,
                    "favourite": True,
                },
            ),
        )
        assert all(item["muted"] and item["favourite"] for item in bulk)
        unpinned = await fixture.request(
            "PATCH", f"/threads/{threads[3]['id']}/prefs", {"pinned": False}
        )
        assert unpinned["pinned_order"] is None
        assert (await inbox_entry(fixture, threads[1]["id"]))["pinned_order"] == 1
        assert (await inbox_entry(fixture, threads[0]["id"]))["pinned_order"] == 2
    finally:
        await fixture.close()


@pytest.mark.asyncio
async def test_keep_archived_off_returns_an_archived_chat_on_a_new_message():
    database()
    from check_streaming import Fixture

    fixture = await Fixture().open()
    try:
        # The tick applies a bounded batch; drain what earlier tests in this shared
        # database left, so each tick below reads only this test's own events.
        for _ in range(100):
            if not await tick(fixture):
                break
        agent = await fixture.agent("Archive")
        thread = await fixture.conversation(agent)
        await fixture.request("PUT", "/threads/settings", {"keep_archived": True})
        await fixture.request("PATCH", f"/threads/{thread['id']}/prefs", {"archived": True})
        await tick(fixture)
        await agent_reply(fixture, thread["id"], agent["id"], "تحديث")
        await tick(fixture)
        assert (await inbox_entry(fixture, thread["id"]))["archived"] is True
        assert (await fixture.request("GET", "/threads/settings")) == {"keep_archived": True}
        await fixture.request("PUT", "/threads/settings", {"keep_archived": False})
        await agent_reply(fixture, thread["id"], agent["id"], "تحديث آخر")
        before = len(await events_of(fixture, "thread.prefs_updated", thread["id"]))
        assert await tick(fixture) >= 1
        entry = await inbox_entry(fixture, thread["id"])
        assert entry["archived"] is False and entry["unread_count"] == 2
        assert len(await events_of(fixture, "thread.prefs_updated", thread["id"])) == before + 1
        # Applied once: a second tick reads nothing new.
        assert await tick(fixture) == 0
    finally:
        await fixture.request("PUT", "/threads/settings", {"keep_archived": True})
        await fixture.close()


@pytest.mark.asyncio
async def test_clear_hides_history_for_the_owner_and_keeps_it_for_the_agent():
    database()
    from check_streaming import Fixture
    from lonora_db.messages import history

    fixture = await Fixture().open()
    try:
        agent = await fixture.agent("Clear")
        thread = await fixture.conversation(agent)
        await owner_message(fixture, thread["id"], "الرسالة الأولى")
        await agent_reply(fixture, thread["id"], agent["id"], "الرد الأول")
        cleared = await fixture.request("POST", f"/threads/{thread['id']}/clear")
        assert cleared["hidden_before_seq"] == 2 and cleared["last_read_seq"] == 2
        assert await fixture.request("GET", f"/threads/{thread['id']}/messages") == []
        entry = await inbox_entry(fixture, thread["id"])
        assert entry["last_message"] is None and entry["hidden_before_seq"] == 2
        assert entry["unread_count"] == 0
        found = await fixture.request("GET", "/search?q=الاولى&category=messages")
        assert found["counts"]["messages"] == 0
        response = await fixture.client.get(f"/api/threads/{thread['id']}/messages?around=1")
        assert response.status_code == 404 and response.json()["code"] == "message_not_found"
        # The thread and the agent stay; the agent's own view of the history is complete.
        assert (await fixture.request("GET", f"/threads/{thread['id']}"))["id"] == thread["id"]
        async with fixture.runtime.db.sessions() as session:
            assert len(await history(session, fixture.owner, thread["id"])) == 2
        # Later messages are visible again.
        await agent_reply(fixture, thread["id"], agent["id"], "رد جديد")
        visible = await listing(fixture, f"/threads/{thread['id']}/messages")
        assert [item["seq"] for item in visible] == [3]
        assert (await inbox_entry(fixture, thread["id"]))["last_message"]["seq"] == 3
    finally:
        await fixture.close()


@pytest.mark.asyncio
async def test_consumed_follows_the_run_that_started_on_the_owner_message():
    database()
    from check_streaming import Fixture

    fixture = await Fixture().open()
    try:
        agent = await fixture.agent("Ticks")
        thread = await fixture.conversation(agent)
        sent = await owner_message(fixture, thread["id"], "ابدأ")
        messages = await listing(fixture, f"/threads/{thread['id']}/messages")
        assert messages[-1]["consumed"] is False  # accepted: one grey tick
        assert (await inbox_entry(fixture, thread["id"]))["last_message"]["consumed"] is False
        run = {"id": sent["run_ids"][0], "agent_id": agent["id"], "thread_id": thread["id"]}
        await fixture.lease(run)  # the run is running: two accent ticks
        messages = await listing(fixture, f"/threads/{thread['id']}/messages")
        assert messages[-1]["consumed"] is True
        assert (await inbox_entry(fixture, thread["id"]))["last_message"]["consumed"] is True
        # A later message the running run has not merged is not consumed.
        await owner_message(fixture, thread["id"], "وأيضاً")
        messages = await listing(fixture, f"/threads/{thread['id']}/messages")
        assert [item["consumed"] for item in messages] == [True, False]
    finally:
        await fixture.close()


@pytest.mark.asyncio
async def test_the_group_lead_answers_when_nobody_is_mentioned():
    database()
    from check_streaming import Fixture

    fixture = await Fixture().open()
    try:
        first = await fixture.agent("First")
        lead = await fixture.agent("Lead")
        response = await fixture.client.post(
            "/api/groups/create",
            json={"name": "فريق", "member_ids": [first["id"]], "lead_agent_id": lead["id"]},
        )
        assert response.status_code == 422
        group = await fixture.request(
            "POST",
            "/groups/create",
            {
                "name": "فريق",
                "member_ids": [first["id"], lead["id"]],
                "purpose": "تحليل الذهب",
                "lead_agent_id": lead["id"],
            },
        )
        fixture.groups.append(group["id"])
        fixture.group_threads.append(group["thread_id"])
        assert group["payload"]["purpose"] == "تحليل الذهب"
        plain = await owner_message(fixture, group["thread_id"], "ما رأيكم؟")
        assert [run["agent_id"] for run in plain["runs"]] == [lead["id"]]
        mentioned = await fixture.request(
            "POST",
            f"/threads/{group['thread_id']}/messages",
            {
                "content": "سؤال للأول",
                "client_nonce": uuid4().hex,
                "mention_agent_ids": [first["id"]],
            },
        )
        assert [run["agent_id"] for run in mentioned["runs"]] == [first["id"]]
        # The group's purpose is searchable.
        found = await fixture.request("GET", "/search?q=الذهب&category=chats")
        assert any(
            item["id"] == group["id"] and item["kind"] == "group"
            for item in found["results"]["chats"]
        )
    finally:
        await fixture.close()


@pytest.mark.asyncio
async def test_chat_lists_are_unique_by_name_and_hold_the_owners_threads():
    database()
    from check_streaming import Fixture

    fixture = await Fixture().open()
    name = "قائمة " + uuid4().hex[:6]
    created: dict[str, Any] | None = None
    try:
        agent = await fixture.agent("Listed")
        thread = await fixture.conversation(agent)
        created = await fixture.request("POST", "/chat-lists", {"name": name})
        assert created["thread_ids"] == []
        response = await fixture.client.post("/api/chat-lists", json={"name": name.upper()})
        assert response.status_code == 409 and response.json()["code"] == "chat_list_name_taken"
        response = await fixture.client.put(
            f"/api/chat-lists/{created['id']}/members", json={"thread_ids": [thread["id"], "nope"]}
        )
        assert response.status_code == 404
        members = await fixture.request(
            "PUT", f"/chat-lists/{created['id']}/members", {"thread_ids": [thread["id"]]}
        )
        assert members["thread_ids"] == [thread["id"]]
        renamed = await fixture.request(
            "PUT", f"/chat-lists/{created['id']}", {"name": name + " ٢", "position": 7}
        )
        assert renamed["name"] == name + " ٢" and renamed["position"] == 7
        listed = await listing(fixture, "/chat-lists")
        assert any(
            item["id"] == created["id"] and item["thread_ids"] == [thread["id"]] for item in listed
        )
        events = await events_of(fixture, "chat_list.updated")
        assert sum(1 for event in events if event.payload.get("id") == created["id"]) == 3
        assert await fixture.request("DELETE", f"/chat-lists/{created['id']}") == {"deleted": True}
        events = await events_of(fixture, "chat_list.updated")
        assert any(
            event.payload.get("id") == created["id"] and event.payload.get("deleted")
            for event in events
        )
        created = None
    finally:
        if created:
            await fixture.client.delete(f"/api/chat-lists/{created['id']}")
        await fixture.close()


@pytest.mark.asyncio
async def test_unified_search_folds_arabic_pages_and_browses_recent_items():
    database()
    from check_streaming import Fixture
    from lonora_db.schema import ArtifactRow, MemoryRow

    fixture = await Fixture().open()
    marker = uuid4().hex[:8]
    try:
        agent = await fixture.agent("Searcher")
        thread = await fixture.conversation(agent)
        for index in range(5):
            await owner_message(fixture, thread["id"], f"رسالة {marker} رقم {index}")
        await agent_reply(fixture, thread["id"], agent["id"], f"الذَّهَبُ {marker} يرتفع")
        found = await fixture.request("GET", f"/search?q=الذهب {marker}&category=messages")
        assert found["counts"]["messages"] == 1
        hit = found["results"]["messages"][0]
        assert hit["thread_id"] == thread["id"] and hit["seq"] == 6 and hit["role"] == "assistant"
        assert hit["agent_id"] == agent["id"] and marker in hit["snippet"]
        # Paging within a category, newest first.
        first = await fixture.request("GET", f"/search?q={marker}&category=messages&limit=2")
        second = await fixture.request(
            "GET", f"/search?q={marker}&category=messages&limit=2&offset=2"
        )
        assert first["counts"]["messages"] == 6 and len(first["results"]["messages"]) == 2
        assert [item["seq"] for item in first["results"]["messages"]] == [6, 5]
        assert [item["seq"] for item in second["results"]["messages"]] == [4, 3]
        # Knowledge is owner-wide: this agent's memory and a file are found by the owner.
        async with fixture.runtime.db.sessions() as session, session.begin():
            memory = await session.get(MemoryRow, agent["id"])
            assert memory is not None
            memory.content = (
                f"# MEMORY.md\n- {marker} ملاحظة عن الذّهب\n## خطة\n- **دخول** {marker[::-1]}\n"
            )
            session.add(
                ArtifactRow(
                    owner_id=fixture.owner,
                    agent_id=agent["id"],
                    thread_id=thread["id"],
                    payload={
                        "name": f"تقرير-{marker}.pdf",
                        "media_type": "application/pdf",
                        "size": 3,
                    },
                )
            )
        skill = await fixture.request(
            "POST",
            "/skills",
            {"agent_id": agent["id"], "payload": {"name": f"skill-{marker}", "content": "خطوات"}},
        )
        everything = await fixture.request("GET", f"/search?q={marker}&limit=3")
        assert everything["counts"]["knowledge"] == 1 and everything["counts"]["files"] == 1
        assert everything["counts"]["skills"] == 1 and everything["counts"]["messages"] == 6
        assert len(everything["results"]["messages"]) == 3
        knowledge = everything["results"]["knowledge"][0]
        assert knowledge["kind"] == "memory" and knowledge["agent_id"] == agent["id"]
        # The first matching section: no heading of its own, so the agent's name titles it;
        # its text is plain, without the list mark or the file name.
        assert knowledge["title"] == agent["name"]
        assert knowledge["snippet"] == f"{marker} ملاحظة عن الذّهب"
        titled = await fixture.request("GET", f"/search?q={marker[::-1]}&category=knowledge")
        assert titled["results"]["knowledge"][0]["title"] == "خطة"
        assert titled["results"]["knowledge"][0]["snippet"] == f"دخول {marker[::-1]}"
        assert everything["results"]["skills"][0]["id"] == skill["id"]
        # The reference UI reads the categories only; the old page's lists are gone.
        assert "memory" not in everything and "agents" not in everything
        # An empty query is the recent feed: the newest messages across conversations.
        recent = await fixture.request("GET", "/search?category=messages&limit=2")
        assert recent["results"]["messages"][0]["id"] == hit["id"]
        assert recent["counts"]["messages"] >= 6
        chats = await fixture.request("GET", "/search?category=chats&limit=50")
        assert chats["results"]["chats"][0]["id"] == agent["id"]  # latest message first
        # A chat with nothing said comes after one with a message, even when it is newer.
        talker = await fixture.agent(f"Talker {marker}")
        await owner_message(fixture, (await fixture.conversation(talker))["id"], "hello")
        quiet = await fixture.agent(f"Quiet {marker}")
        pair = await fixture.request("GET", f"/search?q={marker}&category=chats")
        assert [item["id"] for item in pair["results"]["chats"]] == [talker["id"], quiet["id"]]
        # around=seq centres a page on the hit.
        window = await listing(fixture, f"/threads/{thread['id']}/messages?around=4&limit=4")
        assert [item["seq"] for item in window] == [2, 3, 4, 5]
    finally:
        await fixture.close()


@pytest.mark.asyncio
async def test_a_message_hit_routes_by_the_thread_owner_and_titles_by_the_speaker():
    database()
    from check_streaming import Fixture

    fixture = await Fixture().open()
    marker = uuid4().hex[:8]
    try:
        alpha = await fixture.agent(f"Alpha {marker}")
        beta = await fixture.agent(f"Beta {marker}")
        side = await fixture.request("POST", "/threads", {"agent_id": alpha["id"], "title": "Side"})
        # A peer's outcome lands in the asking agent's thread under the peer's id.
        await agent_reply(fixture, side["id"], beta["id"], f"Peer outcome {marker}")
        found = await fixture.request("GET", f"/search?q=outcome {marker}&category=messages")
        hit = found["results"]["messages"][0]
        assert hit["thread_id"] == side["id"]
        assert hit["agent_id"] == beta["id"]
        assert hit["thread_agent_id"] == alpha["id"] and hit["group_id"] is None
    finally:
        await fixture.close()
