"""Knowing the owner (8.1-8.3): signals the server records, and who writes the profile.

Lonora writes what it observes of the owner without his message; a team agent keeps
the typed-message rule; the structured reach-me record changes only on the owner's
typed message, whoever asks. Thread reads and positions closed outside Lonora are
appended to the owner-signals record, and only Lonora's context carries their summary.
PostgreSQL cases (LONORA_DATABASE_URL) use the real tool registry and owner API.
"""

from typing import Any
from uuid import uuid4

import pytest
from lonora_contracts.runs import RunRequest
from lonora_tools.loader import load_tools
from test_owner_profile import call, database, owner_turn, reset_profile


async def routine_run(fixture: Any, agent_id: str) -> Any:
    """A routine wake: no owner message in the run."""
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
                trigger="routine",
                prompt="Daily owner review",
            ),
        )
        data = {"id": run.id, "agent_id": agent_id, "thread_id": thread.id}
    return await fixture.lease(data)


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
        assert "peer_send" in denied["recovery"]
        denied = await call(registry, background, "owner_preferences_update", reach_me="call")
        assert denied["code"] == "owner_preferences_require_owner_message"
        # With the owner's own message a team agent still records his words.
        said, message_id = await owner_turn(fixture, team, "أنا أفضّل التقارير القصيرة")
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
            volume="0.10",
            open_price="2400",
            stop_loss="2390",
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
