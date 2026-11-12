"""Knowing the owner (8.1-8.3): signals the server records, and who writes the profile.

Lonora writes what it observes of the owner without his message; a team agent keeps
the typed-message rule; the structured reach-me record changes only on the owner's
typed message, whoever asks. Thread reads and positions closed outside Lonora are
appended to the owner-signals record, and only Lonora's context carries their summary.
PostgreSQL cases (LONORA_DATABASE_URL) use the real tool registry and owner API.
"""

import json
from decimal import Decimal
from typing import Any
from uuid import uuid4

import pytest
from lonora_contracts.runs import RunRequest
from lonora_tools.loader import load_tools
from test_owner_profile import call, database, owner_turn, reset_profile


async def routine_run(
    fixture: Any, agent_id: str, trigger: str = "routine", metadata: dict[str, Any] | None = None
) -> Any:
    """A routine wake (or another trigger): no owner message in the run."""
    from lonora_db.runs import create_run
    from lonora_db.threads import conversation_thread

    async with fixture.runtime.db.sessions() as session, session.begin():
        thread = await conversation_thread(session, fixture.owner, agent_id)
        run = await create_run(
            session,
            fixture.owner,
            RunRequest(
                thread_id=thread.id,
                agent_id=agent_id,
                trigger=trigger,
                prompt="Daily owner review",
                metadata=metadata or {},
            ),
        )
        data = {"id": run.id, "agent_id": agent_id, "thread_id": thread.id}
    return await fixture.lease(data)


async def seed_earlier(fixture: Any, text: str, *, system: bool) -> None:
    """A profile line from before origins: 0039's system merge, or no revision at all."""
    from lonora_db.memory_revisions import record_revision
    from lonora_db.schema import OwnerProfileRow

    async with fixture.runtime.db.sessions() as session, session.begin():
        row = await session.get(OwnerProfileRow, fixture.owner)
        assert row is not None
        before, row.content = row.content, row.content + text + "\n"
        row.version += 1
        if system:
            await record_revision(
                session,
                fixture.owner,
                document="owner_profile",
                agent_id=None,
                version=row.version,
                previous_content=before,
                content=row.content,
                author="system",
                change="merge",
            )


async def lonora(fixture: Any) -> dict[str, Any]:
    from lonora_db.personal_agent import ensure_personal_agent

    async with fixture.runtime.db.sessions() as session, session.begin():
        row = await ensure_personal_agent(session, fixture.owner)
        return {"id": row.id, "name": row.name}


@pytest.mark.asyncio
async def test_lonora_writes_observations_and_team_agents_keep_the_owner_rule():
    database()
    from check_streaming import Fixture
    from lonora_db.schema import MemoryRevisionRow, OwnerProfileRow
    from sqlalchemy import select

    fixture = await Fixture().open()
    try:
        await reset_profile(fixture)
        registry = load_tools()
        lead = await lonora(fixture)
        # Lonora, in a routine run with no owner message, records an observation (8.2).
        context = await routine_run(fixture, lead["id"])
        observed = await call(
            registry,
            context,
            "memory_write",
            version=1,
            observed=True,
            operations=[
                {
                    "action": "add",
                    "section": "USER.md",
                    "content": "- Reads the morning report around 07:30 on weekdays",
                }
            ],
        )
        assert observed.get("owner_profile", observed).get("changed") is True, observed
        async with fixture.runtime.db.sessions() as session:
            profile = await session.get(OwnerProfileRow, fixture.owner)
            assert profile is not None and "07:30" in profile.content
            revision = await session.scalar(
                select(MemoryRevisionRow)
                .where(
                    MemoryRevisionRow.owner_id == fixture.owner,
                    MemoryRevisionRow.document == "owner_profile",
                )
                .order_by(MemoryRevisionRow.created_at.desc())
            )
            # No owner message: the line is Lonora's observation, not the owner's words.
            assert revision is not None and revision.source_message_id is None
            assert revision.author == "agent" and revision.author_agent_id == lead["id"]
        # Reach-me stays on the owner's typed message, even for Lonora.
        refused = await call(registry, context, "owner_preferences_update", reach_me="call")
        assert refused["code"] == "owner_preferences_require_owner_message"
        # A team agent in a run without the owner's message is refused, and told to
        # send the observation to Lonora.
        team = await fixture.agent("Gold")
        background = await routine_run(fixture, team["id"])
        denied = await call(
            registry,
            background,
            "memory_write",
            version=1,
            operations=[{"action": "add", "section": "USER.md", "content": "- Likes risk"}],
        )
        assert denied["code"] == "owner_profile_requires_owner_message"
        assert "peer_send" not in denied["recovery"] and "MEMORY.md" in denied["recovery"]
        denied = await call(registry, background, "owner_preferences_update", reach_me="call")
        assert denied["code"] == "owner_preferences_require_owner_message"
        # With the owner's own message a team agent still records his words, but never
        # an observation of its own.
        said, message_id = await owner_turn(fixture, team, "أنا أفضّل التقارير القصيرة")
        inferred = await call(
            registry,
            said,
            "memory_write",
            version=1,
            observed=True,
            operations=[{"action": "add", "section": "USER.md", "content": "- Anxious owner"}],
        )
        assert inferred["code"] == "owner_profile_requires_owner_message"
        written = await call(
            registry,
            said,
            "memory_write",
            version=1,
            operations=[
                {"action": "add", "section": "USER.md", "content": "- Prefers short reports"}
            ],
        )
        assert written.get("owner_profile", written).get("changed") is True, written
        async with fixture.runtime.db.sessions() as session:
            latest = await session.scalar(
                select(MemoryRevisionRow)
                .where(
                    MemoryRevisionRow.owner_id == fixture.owner,
                    MemoryRevisionRow.document == "owner_profile",
                )
                .order_by(MemoryRevisionRow.created_at.desc())
            )
            assert latest is not None and latest.source_message_id == message_id
        # Lonora answering the owner's message marks an inference as observed: the
        # revision carries no owner message, so the view never shows it as his words.
        answer, _ = await owner_turn(fixture, lead, "كيف حالك؟")
        await call(
            registry,
            answer,
            "memory_write",
            version=1,
            observed=True,
            operations=[{"action": "add", "section": "USER.md", "content": "- Replies late"}],
        )
        async with fixture.runtime.db.sessions() as session:
            latest = await session.scalar(
                select(MemoryRevisionRow)
                .where(
                    MemoryRevisionRow.owner_id == fixture.owner,
                    MemoryRevisionRow.document == "owner_profile",
                )
                .order_by(MemoryRevisionRow.created_at.desc())
            )
            assert latest is not None and latest.source_message_id is None
    finally:
        await reset_profile(fixture)
        await fixture.close()


@pytest.mark.asyncio
async def test_lonora_observes_only_in_untainted_runs_and_agents_see_observations_apart():
    database()
    from check_streaming import Fixture
    from lonora_agent.context.memory import read_memory_context
    from lonora_tools.restrictions import mark_external_content

    fixture = await Fixture().open()
    try:
        await reset_profile(fixture)
        registry = load_tools()
        lead = await lonora(fixture)
        line = {"action": "add", "section": "USER.md", "content": "- Closes gold before news"}
        # Answering the owner, but after reading a web page: no longer his word, and not
        # Lonora's own observation either (6.10).
        tainted, _ = await owner_turn(fixture, lead, "راجع الأخبار")
        async with fixture.runtime.db.sessions() as session, session.begin():
            await mark_external_content(session, tainted.lease.run_id, "web_fetch")
        refused = await call(registry, tainted, "memory_write", version=1, operations=[line])
        assert refused["code"] == "owner_profile_tainted_run", refused
        # A peer woke Lonora: the peer's words are data, never an observation of the owner.
        peer = await routine_run(fixture, lead["id"], trigger="peer")
        refused = await call(
            registry, peer, "memory_write", version=1, observed=True, operations=[line]
        )
        assert refused["code"] == "owner_profile_tainted_run", refused
        # Lonora's own routine run still records what it observed.
        routine = await routine_run(fixture, lead["id"])
        written = await call(
            registry, routine, "memory_write", version=1, observed=True, operations=[line]
        )
        assert written.get("owner_profile", written).get("changed") is True, written
        # The owner's words and Lonora's observation reach a team agent apart.
        team = await fixture.agent("Silver")
        said, _ = await owner_turn(fixture, team, "I prefer Arabic reports")
        await call(
            registry,
            said,
            "memory_write",
            version=1,
            operations=[{"action": "add", "section": "USER.md", "content": "- Arabic reports"}],
        )
        # Lines from before origins were recorded rank with his words.
        await seed_earlier(fixture, "- Merged old line", system=True)
        await seed_earlier(fixture, "- Unrecorded line", system=False)
        async with fixture.runtime.db.sessions() as session:
            sections = await read_memory_context(session, fixture.owner, team["id"])
        body = json.loads(sections[0].body.split("\n", 1)[1])
        assert sections[0].name == "owner_preferences"
        assert body["profile"] == "- Arabic reports\n- Merged old line\n- Unrecorded line"
        assert body["lonora_observations"] == "- Closes gold before news"
        assert "not his word" in sections[0].body
    finally:
        await reset_profile(fixture)
        await fixture.close()


@pytest.mark.asyncio
async def test_a_routine_or_watch_a_tainted_run_made_wakes_without_observations():
    database()
    from check_streaming import Fixture
    from lonora_db.schema import OwnerProfileRow, RunRow
    from lonora_tools.profile_taint import mark_from
    from lonora_tools.restrictions import mark_external_content

    fixture = await Fixture().open()
    try:
        await reset_profile(fixture)
        registry = load_tools()
        lead = await lonora(fixture)
        schedule = {"prompt": "Review the owner's trading", "interval_seconds": 3600}
        # The reviewer's probe: an owner turn reads a web page, then schedules a routine.
        tainted, _ = await owner_turn(fixture, lead, "اقرأ هذه الصفحة وراجعها كل ساعة")
        async with fixture.runtime.db.sessions() as session, session.begin():
            await mark_external_content(session, tainted.lease.run_id, "web_fetch")
        steered = await call(registry, tainted, "routine_create", **schedule)
        # The same routine from a clean owner turn.
        clean, _ = await owner_turn(fixture, lead, "راجع تداولي كل ساعة")
        trusted = await call(registry, clean, "routine_create", **schedule)
        line = {
            "action": "add",
            "section": "USER.md",
            "content": "- Prefers the largest lot size on every trade",
        }
        woken = await routine_run(fixture, lead["id"], metadata={"routine_id": steered["id"]})
        refused = await call(
            registry, woken, "memory_write", version=1, observed=True, operations=[line]
        )
        assert refused["code"] == "owner_profile_tainted_run", refused
        async with fixture.runtime.db.sessions() as session:
            assert await session.get(OwnerProfileRow, fixture.owner) is None
        woken = await routine_run(fixture, lead["id"], metadata={"routine_id": trusted["id"]})
        line["content"] = "- Reviews trades hourly"
        written = await call(
            registry, woken, "memory_write", version=1, observed=True, operations=[line]
        )
        assert written.get("owner_profile", written).get("changed") is True, written
        # A watch carries the same mark; only the observation check reads it.
        watched, unmarked = "watch-" + uuid4().hex, "watch-" + uuid4().hex
        async with fixture.runtime.db.sessions() as session, session.begin():
            row = await session.get(RunRow, tainted.lease.run_id)
            assert row is not None
            await mark_from(session, row, "watch", watched)
        woken = await routine_run(fixture, lead["id"], "watch", {"watch_id": watched})
        line["content"] = "- Closes gold before news"
        refused = await call(
            registry, woken, "memory_write", version=1, observed=True, operations=[line]
        )
        assert refused["code"] == "owner_profile_tainted_run", refused
        woken = await routine_run(fixture, lead["id"], "watch", {"watch_id": unmarked})
        written = await call(
            registry, woken, "memory_write", version=1, observed=True, operations=[line]
        )
        assert written.get("owner_profile", written).get("changed") is True, written
    finally:
        await reset_profile(fixture)
        await fixture.close()


@pytest.mark.asyncio
async def test_reads_and_outside_closes_are_signals_only_lonora_sees():
    database()
    from check_streaming import Fixture
    from lonora_agent.context.memory import read_memory_context
    from lonora_contracts.account import Position
    from lonora_contracts.broker_activity import BrokerActivity
    from lonora_contracts.domain import utcnow
    from lonora_db.owner_signals import owner_model
    from lonora_db.schema import OwnerSignalRow
    from lonora_trading.broker_recovery import wake_for_activity
    from sqlalchemy import delete, select

    fixture = await Fixture().open()
    try:
        async with fixture.runtime.db.sessions() as session, session.begin():
            await session.execute(
                delete(OwnerSignalRow).where(OwnerSignalRow.owner_id == fixture.owner)
            )
        lead = await lonora(fixture)
        team = await fixture.agent("Euro")
        thread, _ = await owner_turn(fixture, team, "hello")
        # The owner reads the conversation.
        await fixture.request("POST", f"/threads/{thread.thread_id}/read", {"seq": 10_000})
        # A position closed outside Lonora.
        position = Position(
            id="9001",
            symbol="XAUUSD",
            side="buy",
            volume=Decimal("0.10"),
            open_price=Decimal("2400"),
            stop_loss=Decimal("2390"),
        )
        change = BrokerActivity(
            id="activity-" + uuid4().hex,
            account_id="acct-" + uuid4().hex[:8],
            symbol="XAUUSD",
            ticket="9001",
            resource="position",
            change="closed",
            origin="external",
            observed_at=utcnow(),
            previous=position,
        )
        async with fixture.runtime.db.sessions() as session, session.begin():
            await wake_for_activity(session, fixture.owner, change.account_id, 1, [change])
        async with fixture.runtime.db.sessions() as session:
            kinds = list(
                await session.scalars(
                    select(OwnerSignalRow.kind).where(OwnerSignalRow.owner_id == fixture.owner)
                )
            )
            assert sorted(kinds) == ["external_close", "thread_read"]
            model = await owner_model(session, fixture.owner)
            assert model["signals"]["reads_by_day"][0]["reads"] == 1
            close = model["signals"]["closes_outside_lonora"][0]
            assert close["symbol"] == "XAUUSD" and close["position_of"] == "owner"
            assert close["had_stop_loss"] is True and close["had_take_profit"] is False
            mine = await read_memory_context(session, fixture.owner, lead["id"], lead=True)
            theirs = await read_memory_context(session, fixture.owner, team["id"])
        assert "owner_signals" in [section.name for section in mine if section.body]
        assert "owner_signals" not in [section.name for section in theirs]
    finally:
        await fixture.close()


@pytest.mark.asyncio
async def test_what_i_know_lists_origins_and_records_corrections_as_the_owners_word():
    database()
    from check_streaming import Fixture
    from lonora_db.schema import MemoryRevisionRow
    from sqlalchemy import select

    fixture = await Fixture().open()
    try:
        await reset_profile(fixture)
        registry = load_tools()
        lead = await lonora(fixture)
        observed = await call(
            registry,
            await routine_run(fixture, lead["id"]),
            "memory_write",
            version=1,
            operations=[{"action": "add", "section": "USER.md", "content": "- Reads at 07:30"}],
        )
        assert observed.get("owner_profile", observed).get("changed") is True, observed
        said, _ = await owner_turn(fixture, lead, "I prefer short reports")
        await call(
            registry,
            said,
            "memory_write",
            version=1,
            operations=[{"action": "add", "section": "USER.md", "content": "- Short reports"}],
        )
        known = await fixture.request("GET", "/owner/profile/lines")
        origins = {line["text"]: line["origin"] for line in known["lines"]}
        assert origins == {"- Reads at 07:30": "observed", "- Short reports": "you_said"}
        # The owner corrects the observed line: it becomes his own word.
        corrected = await fixture.request(
            "POST",
            "/owner/profile/lines",
            {
                "version": known["version"],
                "text": "- Reads at 07:30",
                "replacement": "- Reads at 08:00",
            },
        )
        origins = {line["text"]: line["origin"] for line in corrected["lines"]}
        assert origins == {"- Reads at 08:00": "you_said", "- Short reports": "you_said"}
        async with fixture.runtime.db.sessions() as session:
            latest = await session.scalar(
                select(MemoryRevisionRow)
                .where(
                    MemoryRevisionRow.owner_id == fixture.owner,
                    MemoryRevisionRow.document == "owner_profile",
                )
                .order_by(MemoryRevisionRow.created_at.desc())
            )
            assert latest is not None and latest.author == "owner"
            assert latest.change == "correction"
        # Deleting a line; a stale version or a line that is gone is refused.
        deleted = await fixture.request(
            "POST",
            "/owner/profile/lines",
            {"version": corrected["version"], "text": "- Short reports", "replacement": None},
        )
        assert [line["text"] for line in deleted["lines"]] == ["- Reads at 08:00"]
        stale = await fixture.client.post(
            "/api/owner/profile/lines",
            json={"version": corrected["version"], "text": "- Reads at 08:00"},
        )
        assert stale.status_code == 409
        gone = await fixture.client.post(
            "/api/owner/profile/lines",
            json={"version": deleted["version"], "text": "- Short reports"},
        )
        assert gone.status_code == 409 and gone.json()["code"] == "owner_profile_line_not_found"
        # His correction stands: a later routine patch back to the observation is refused.
        back = {"action": "patch", "section": "USER.md", "old_text": "08:00", "content": "07:30"}
        refused = await call(
            registry,
            await routine_run(fixture, lead["id"]),
            "memory_write",
            version=1,
            observed=True,
            operations=[back],
        )
        assert refused["code"] == "owner_profile_line_is_owners_word", refused
        removed = {"action": "remove", "section": "USER.md", "old_text": "Reads at 08:00"}
        refused = await call(
            registry,
            await routine_run(fixture, lead["id"]),
            "memory_write",
            version=1,
            operations=[removed],
        )
        assert refused["code"] == "owner_profile_line_is_owners_word", refused
        # On his own message it changes.
        asked, _ = await owner_turn(fixture, lead, "Actually I read at 07:30")
        patched = await call(registry, asked, "memory_write", version=1, operations=[back])
        assert patched.get("owner_profile", patched).get("changed") is True, patched
        # An owner revert brings an observed line back as observed, not as his word;
        # a line no kept revision added is "earlier".
        await call(
            registry,
            await routine_run(fixture, lead["id"]),
            "memory_write",
            version=1,
            observed=True,
            operations=[{"action": "add", "section": "USER.md", "content": "- Sleeps late"}],
        )
        known = await fixture.request("GET", "/owner/profile/lines")
        cut = await fixture.request(
            "POST",
            "/owner/profile/lines",
            {"version": known["version"], "text": "- Sleeps late", "replacement": None},
        )
        async with fixture.runtime.db.sessions() as session, session.begin():
            correction = await session.scalar(
                select(MemoryRevisionRow)
                .where(
                    MemoryRevisionRow.owner_id == fixture.owner,
                    MemoryRevisionRow.document == "owner_profile",
                )
                .order_by(MemoryRevisionRow.created_at.desc())
            )
            assert correction is not None and correction.change == "correction"
            correction_id = correction.id
        await fixture.request(
            "POST", f"/memory/revisions/{correction_id}/revert", {"version": cut["version"]}
        )
        await seed_earlier(fixture, "- Legacy line", system=False)
        await seed_earlier(fixture, "- Merged old line", system=True)
        known = await fixture.request("GET", "/owner/profile/lines")
        origins = {line["text"]: line["origin"] for line in known["lines"]}
        assert origins == {
            "- Reads at 07:30": "you_said",
            "- Sleeps late": "observed",
            "- Legacy line": "earlier",
            "- Merged old line": "earlier",
        }
        # An earlier line is protected like his word.
        for old_text in ("Legacy line", "Merged old line"):
            refused = await call(
                registry,
                await routine_run(fixture, lead["id"]),
                "memory_write",
                version=1,
                operations=[{"action": "remove", "section": "USER.md", "old_text": old_text}],
            )
            assert refused["code"] == "owner_profile_line_is_owners_word", refused
    finally:
        await reset_profile(fixture)
        await fixture.close()
