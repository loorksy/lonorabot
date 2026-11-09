"""One owner profile for every Agent, revertible memory and reach-me set from chat.

Runs on a fresh migrated PostgreSQL database (LONORA_DATABASE_URL):

1. Migration 0039 merges every Agent's legacy USER.md section into the owner profile
   without losing a line or touching an Agent row, and running it again changes nothing.
   An Agent's write after the upgrade keeps the retired section in its row, so a
   downgrade still finds every earlier preference line.
2. A preference the Personal Agent records from the owner's message reaches another
   Agent's next model request through a real Run.
3. "Send me a message instead of calling", said in chat, changes the channel of the
   next qualifying event exactly once: no call rings and one message is written.
   Delivery is in-app only; nothing here proves a device rang.
"""

import asyncio
import hashlib
import importlib.util
import json
import subprocess
import sys
from pathlib import Path
from typing import Any, cast
from unittest.mock import patch
from uuid import uuid4

from check_streaming import Fixture
from lonora_adapter_kit.types import ModelMessage, ModelReply, ToolCall
from lonora_agent.executor import execute_run
from lonora_contracts.domain import new_id, utcnow
from lonora_contracts.model_routing import ModelSelection
from lonora_db.schema import (
    AttentionRow,
    DeviceCredentialRow,
    MemoryRow,
    MessageRow,
    RunRow,
    VoiceSessionRow,
)
from lonora_db.transactions import SettingsRepository
from lonora_tools.loader import load_tools
from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import create_async_engine

ROOT = Path(__file__).resolve().parents[1]
MIGRATION = ROOT / "packages/db/migrations/versions/0039_owner_profile_memory_revisions.py"
LEGACY = {
    "Owner profile Lonora": "# USER.md\n- يفضّل الردود القصيرة بالعربية\n- Timezone Asia/Riyadh\n",
    "Owner profile Gold": (
        "Legacy fact.\n\n# USER.md\n- Timezone Asia/Riyadh\n- Message me instead of calling\n\n"
        "# MEMORY.md\n- XAUUSD spreads widen at rollover\n"
    ),
    "Owner profile Silver": "# MEMORY.md\n- Silver follows gold\n",
}


async def listing(fixture: Fixture, path: str) -> list[dict[str, Any]]:
    return cast(list[dict[str, Any]], await fixture.request("GET", path))


def migration() -> Any:
    spec = importlib.util.spec_from_file_location("owner_profile_migration", MIGRATION)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


async def alembic(action: str, revision: str) -> None:
    await asyncio.to_thread(
        subprocess.run,
        [sys.executable, "-m", "alembic", "-c", "packages/db/alembic.ini", action, revision],
        check=True,
        cwd=ROOT,
        stdout=subprocess.DEVNULL,
    )


def digest(rows: list[tuple[str, str]]) -> str:
    return hashlib.sha256(json.dumps(sorted(rows), ensure_ascii=False).encode()).hexdigest()


async def migration_is_lossless_and_idempotent(url: str, owner: str, agents: list[str]) -> str:
    engine = create_async_engine(url)
    module = migration()
    try:
        async with engine.connect() as connection:
            rows = (
                await connection.execute(
                    text("SELECT agent_id, content FROM ln_memory WHERE agent_id = ANY(:ids)"),
                    {"ids": agents},
                )
            ).all()
        before = digest([(str(row[0]), str(row[1])) for row in rows])
        union = {
            line.strip()
            for _, content in rows
            for line in module.user_section(str(content)).splitlines()
            if line.strip()
        }
        assert len(union) == 3, union
        # Remove what the upgrade created, then upgrade again from the old schema.
        await alembic("downgrade", "0038_owner_actions")
        await alembic("upgrade", "head")
        profiles: list[str] = []
        for attempt in range(2):
            async with engine.connect() as connection:
                profile = (
                    await connection.execute(
                        text("SELECT content, version FROM ln_owner_profile WHERE owner_id = :o"),
                        {"o": owner},
                    )
                ).one()
                after_rows = (
                    await connection.execute(
                        text("SELECT agent_id, content FROM ln_memory WHERE agent_id = ANY(:ids)"),
                        {"ids": agents},
                    )
                ).all()
                revisions = (
                    await connection.execute(
                        text(
                            "SELECT author, change, previous_content, content FROM "
                            "ln_memory_revisions WHERE owner_id = :o AND document = "
                            "'owner_profile'"
                        ),
                        {"o": owner},
                    )
                ).all()
            content = str(profile[0])
            kept = {line.strip() for line in content.splitlines() if not line.startswith("<!--")}
            assert union <= kept, (union, content)
            # Exact-line dedupe: the shared timezone line appears once.
            assert content.count("Timezone Asia/Riyadh") == 1
            assert "<!-- Merged from Owner profile Lonora -->" in content
            assert "<!-- Merged from Owner profile Gold -->" in content
            assert "Silver" not in content and "rollover" not in content
            assert digest([(str(r[0]), str(r[1])) for r in after_rows]) == before
            assert profile[1] == 1 and len(revisions) == 1
            assert revisions[0][0] == "system" and revisions[0][1] == "merge"
            assert revisions[0][2] == "" and revisions[0][3] == content
            profiles.append(content)
            # Running the data step again finds nothing new and writes nothing.
            async with engine.begin() as connection:
                changed = await connection.run_sync(module.merge_legacy_user_sections)
            assert changed == 0
            if attempt == 0:
                await alembic("downgrade", "0038_owner_actions")
                await alembic("upgrade", "head")
        assert profiles[0] == profiles[1]
        print(
            "PASS migration 0039 merges every legacy USER.md line once with provenance, "
            "leaves Agent rows byte-identical and is idempotent across re-runs"
        )
        return profiles[0]
    finally:
        await engine.dispose()


async def agent_write_keeps_legacy_lines_through_downgrade(
    fixture: Fixture, gold: str, merged: str
) -> None:
    module = migration()
    async with fixture.runtime.db.sessions() as session:
        row = await session.get(MemoryRow, gold)
        assert row is not None
        version, legacy = row.version, module.user_section(row.content)
    assert "Message me instead of calling" in legacy
    # A real Run of that Agent changes its memory after the upgrade.
    context = await owner_run(fixture, {"id": gold}, "Remember that gold gaps on Mondays")
    seen = await run_script(
        context,
        [
            ToolCall(
                id="gold-note",
                name="memory_write",
                arguments={
                    "version": version,
                    "operations": [{"action": "add", "content": "- Gold gaps on Mondays"}],
                },
            ),
            "Noted.",
        ],
    )
    assert result_of(seen[-1], "gold-note")["changed"] is True
    revisions = await listing(fixture, f"/agents/{gold}/memory/revisions")
    assert revisions[0]["changes"] == [{"change": "added", "text": "- Gold gaps on Mondays"}]
    url = fixture.settings.database_url
    await fixture.runtime.db.close()
    engine = create_async_engine(url)
    try:
        await alembic("downgrade", "0038_owner_actions")
        async with engine.connect() as connection:
            content = str(
                (
                    await connection.execute(
                        text("SELECT content FROM ln_memory WHERE agent_id = :id"), {"id": gold}
                    )
                ).scalar_one()
            )
        # The pre-0039 runtime reads its USER.md section again, line for line.
        assert module.user_section(content) == legacy, content
        assert "- Gold gaps on Mondays" in content
        await alembic("upgrade", "head")
        async with engine.connect() as connection:
            profile = str(
                (
                    await connection.execute(
                        text("SELECT content FROM ln_owner_profile WHERE owner_id = :o"),
                        {"o": fixture.owner},
                    )
                ).scalar_one()
            )
        assert profile == merged, profile
    finally:
        await engine.dispose()
    print(
        "PASS an Agent's write after the upgrade keeps its retired USER.md lines; a downgrade "
        "finds every one and the re-upgrade merges the same profile"
    )


def scripted(script: list[Any], seen: list[list[ModelMessage]]) -> Any:
    """A provider that replays tool calls, then a final reply, and records each request."""

    async def complete(_: Any, messages: list[ModelMessage], tools: Any, **kwargs: Any):
        seen.append(list(messages))
        step = script.pop(0)
        if isinstance(step, ToolCall):
            reply = ModelReply(tool_calls=[step], text="")
        else:
            reply = ModelReply(tool_calls=[], text=str(step))
        return reply, ModelSelection(provider="openai", model="scripted-owner-profile")

    return complete


def context_text(messages: list[ModelMessage]) -> str:
    return "\n".join(message.content for message in messages)


def result_of(messages: list[ModelMessage], call_id: str) -> dict[str, Any]:
    return json.loads(
        next(
            message.content
            for message in reversed(messages)
            if message.role == "tool" and message.tool_call_id == call_id
        )
    )


async def owner_run(fixture: Fixture, agent: dict[str, Any], words: str) -> Any:
    thread = await fixture.conversation(agent)
    sent = await fixture.request(
        "POST",
        f"/threads/{thread['id']}/messages",
        {"content": words, "client_nonce": "profile-" + uuid4().hex},
    )
    run = {"id": sent["run_ids"][0], "agent_id": agent["id"], "thread_id": thread["id"]}
    return await fixture.lease(run)


async def run_script(context: Any, script: list[Any]) -> list[list[ModelMessage]]:
    seen: list[list[ModelMessage]] = []
    with patch.object(context.router, "complete", scripted(script, seen)):
        await execute_run(context, load_tools(), 120, 8)
    assert not script, script
    async with context.db.sessions() as session:
        run = await session.get(RunRow, context.lease.run_id)
        assert run is not None and run.status == "completed", run and run.status
    return seen


async def preference_reaches_every_agent(
    fixture: Fixture, lonora: dict[str, Any], gold: dict[str, Any]
) -> None:
    context = await owner_run(fixture, lonora, "ردودك قصيرة بالعربي، وراسلني بدل ما تتصل")
    await run_script(
        context,
        [
            ToolCall(
                id="profile-add",
                name="memory_write",
                arguments={
                    "version": 1,
                    "operations": [
                        {"action": "add", "section": "USER.md", "content": "- ردود قصيرة جدًا"}
                    ],
                },
            ),
            ToolCall(
                id="profile-language",
                name="tool_call",
                arguments={
                    "name": "owner_preferences_update",
                    "arguments": {"reply_language": "ar"},
                },
            ),
            "حفظت تفضيلك: ردود قصيرة بالعربية، ويطبقه كل الوكلاء.",
        ],
    )
    gold_context = await owner_run(fixture, gold, "ما وضع الذهب؟")
    seen = await run_script(gold_context, ["الذهب مستقر."])
    first = context_text(seen[0])
    assert "ردود قصيرة جدًا" in first and '"reply_language": "ar"' in first
    assert 'name="owner_preferences" source="owner_profile" trust="owner_attributed"' in first
    revisions = await listing(fixture, "/owner/profile/revisions")
    assert {item["document"] for item in revisions[:2]} == {"owner_profile", "owner_preferences"}
    assert all(item["author_agent_name"] == lonora["name"] for item in revisions[:2])
    assert all(item["from_owner_message"] for item in revisions[:2])
    print(
        "PASS a preference the Personal Agent records from the owner's message reaches the "
        "gold agent's next request, attributed and revertible"
    )


async def attention(fixture: Fixture, agent: dict[str, Any], thread_id: str) -> str:
    identifier = new_id()
    async with fixture.runtime.db.sessions() as session, session.begin():
        session.add(
            AttentionRow(
                id=identifier,
                owner_id=fixture.owner,
                agent_id=agent["id"],
                thread_id=thread_id,
                importance="critical",
                code="emergency_stop",
                status="ready",
                logical_key=identifier,
                coalesce_key=identifier,
                parameters={},
                source_events=[],
                source_count=1,
                version=1,
                due_at=utcnow(),
            )
        )
    return identifier


async def incoming(fixture: Fixture, attention_id: str | None = None) -> int:
    async with fixture.runtime.db.sessions() as session:
        query = (
            select(func.count())
            .select_from(VoiceSessionRow)
            .where(
                VoiceSessionRow.owner_id == fixture.owner,
                VoiceSessionRow.payload["mode"].as_string() == "incoming_request",
            )
        )
        if attention_id:
            query = query.where(VoiceSessionRow.payload["attention_id"].as_string() == attention_id)
        return int(await session.scalar(query) or 0)


async def assistant_messages(fixture: Fixture, thread_id: str) -> int:
    async with fixture.runtime.db.sessions() as session:
        return int(
            await session.scalar(
                select(func.count())
                .select_from(MessageRow)
                .where(MessageRow.thread_id == thread_id, MessageRow.role == "assistant")
            )
            or 0
        )


async def message_instead_of_calling(fixture: Fixture, lonora: dict[str, Any]) -> None:
    device = new_id()
    async with fixture.runtime.db.sessions() as session, session.begin():
        session.add(
            DeviceCredentialRow(
                id=device,
                owner_id=fixture.owner,
                name="Owner phone",
                credential_id="profile-" + device,
                public_key="fixture-not-authentication",
                sign_count=0,
                revoked=False,
            )
        )
        # A qualifying, still-current critical event: new trading is stopped.
        await SettingsRepository().put(session, "trading_control", {"emergency_stop": True})
    # 1. "Call me if a decision is needed": the reach-me preference becomes call.
    context = await owner_run(fixture, lonora, "راقب الذهب واتصل بي إذا احتاج الأمر قراري")
    thread_id = context.thread_id
    first = await attention(fixture, lonora, thread_id)
    await run_script(
        context,
        [
            ToolCall(
                id="reach-call",
                name="tool_call",
                arguments={"name": "owner_preferences_update", "arguments": {"reach_me": "call"}},
            ),
            ToolCall(
                id="call-1",
                name="owner_call_request",
                arguments={"attention_id": first, "reason": "Trading is stopped; your decision"},
            ),
            "اتصلت بك لأن التداول متوقف ويحتاج قرارك.",
        ],
    )
    assert await incoming(fixture, first) == 1
    # 2. While monitoring continues: "Send me a message instead of calling".
    context = await owner_run(fixture, lonora, "Send me a message instead of calling")
    await run_script(
        context,
        [
            ToolCall(
                id="reach-message",
                name="tool_call",
                arguments={
                    "name": "owner_preferences_update",
                    "arguments": {"reach_me": "message"},
                },
            ),
            "Done: I will message you instead of calling.",
        ],
    )
    policy = await fixture.request("GET", "/voice/incoming/policy")
    assert policy["channel"] == "message" and policy["enabled"] is False
    # 3. The next qualifying event, in a background Run: the updated channel is used once.
    second = await attention(fixture, lonora, thread_id)
    before = await assistant_messages(fixture, thread_id)
    wake = await fixture.lease(await fixture.run(lonora, {"id": thread_id}))
    seen = await run_script(
        wake,
        [
            ToolCall(
                id="call-2",
                name="owner_call_request",
                arguments={"attention_id": second, "reason": "Trading is still stopped"},
            ),
            "التداول ما زال متوقفًا ويحتاج قرارك؛ راسلتك بدل الاتصال كما طلبت.",
        ],
    )
    assert '"reach_me": "message"' in context_text(seen[0])
    refused = result_of(seen[-1], "call-2")
    assert refused["code"] == "owner_prefers_other_channel" and refused["reach_me"] == "message"
    assert await incoming(fixture, second) == 0 and await incoming(fixture) == 1
    assert await assistant_messages(fixture, thread_id) == before + 1
    print(
        "PASS 'message me instead of calling' set from chat: the next qualifying event rang "
        "nothing and produced exactly one message (in-app delivery only)"
    )


async def main() -> None:
    fixture = await Fixture().open()
    try:
        lonora = await fixture.agent("Owner profile Lonora")
        gold = await fixture.agent("Owner profile Gold")
        silver = await fixture.agent("Owner profile Silver")
        named = {lonora["name"]: lonora, gold["name"]: gold, silver["name"]: silver}
        async with fixture.runtime.db.sessions() as session, session.begin():
            for offset, (prefix, content) in enumerate(LEGACY.items()):
                agent = next(row for name, row in named.items() if name.startswith(prefix))
                row = await session.get(MemoryRow, agent["id"])
                assert row is not None
                row.content = content
                row.updated_at = utcnow().replace(microsecond=offset)
                # The fixture names carry a suffix; the merge names its source agent.
                await session.execute(
                    text("UPDATE ln_agents SET name = :name WHERE id = :id"),
                    {"name": prefix, "id": agent["id"]},
                )
        url = fixture.settings.database_url
        await fixture.runtime.db.close()
        merged = await migration_is_lossless_and_idempotent(
            url, fixture.owner, [lonora["id"], gold["id"], silver["id"]]
        )
    finally:
        await fixture.close(cleanup=False)
    fixture = await Fixture().open()
    try:
        await agent_write_keeps_legacy_lines_through_downgrade(fixture, gold["id"], merged)
    finally:
        await fixture.close(cleanup=False)
    fixture = await Fixture().open()
    try:
        await fixture.request("PUT", "/owner/profile", {"content": "", "version": 1})
        lonora = await fixture.agent("Lonora")
        gold = await fixture.agent("Gold")
        await preference_reaches_every_agent(fixture, lonora, gold)
        await message_instead_of_calling(fixture, lonora)
    finally:
        await fixture.close()


if __name__ == "__main__":
    asyncio.run(main())
