"""Routines, tasks and agents by the name the owner gives them."""

from types import SimpleNamespace
from typing import cast

import pytest
from lonora_contracts.domain import utcnow
from lonora_contracts.tasks import TaskCreate
from lonora_db.client import Database
from lonora_db.schema import AgentRow, RoutineRow
from lonora_db.tasks import create_task
from lonora_tools.context import ToolContext
from lonora_tools.resolve import NotResolved
from lonora_tools.routine import named_routine
from lonora_tools.supervision import named_agent
from lonora_tools.tasks import named_task
from test_task_runtime import task_db as task_db

Fixture = tuple[Database, str, str, str]


def caller(owner: str, agent: str) -> ToolContext:
    return cast(ToolContext, SimpleNamespace(owner_id=owner, agent_id=agent))


@pytest.mark.asyncio
async def test_a_routine_is_switched_off_by_its_title_and_never_on_by_one(task_db: Fixture) -> None:
    db, owner, agent, thread = task_db
    async with db.sessions() as session, session.begin():
        morning = RoutineRow(
            owner_id=owner,
            agent_id=agent,
            thread_id=thread,
            prompt="Read gold at the London open and report",
            title="تقرير الذهب الصباحي",
            interval_seconds=3600,
            next_run_at=utcnow(),
        )
        untitled = RoutineRow(
            owner_id=owner,
            agent_id=agent,
            thread_id=thread,
            prompt="x",
            interval_seconds=3600,
            next_run_at=utcnow(),
        )
        asleep = RoutineRow(
            owner_id=owner,
            agent_id=agent,
            thread_id=thread,
            prompt="Weekly review",
            title="Weekly review",
            interval_seconds=3600,
            next_run_at=utcnow(),
            enabled=False,
        )
        session.add_all([morning, untitled, asleep])
    context = caller(owner, agent)
    async with db.sessions() as session:
        # The alef and the ta marbuta fold as in the owner's search.
        routine_id, note = await named_routine(
            session, context, "تقرير الذهب الصباحى", enabling=False
        )
        assert routine_id == morning.id and note is not None and note["id"] == morning.id
        assert await named_routine(session, context, asleep.id, enabling=True) == (asleep.id, None)
        # Part of a title switches nothing off by itself.
        with pytest.raises(NotResolved) as partial:
            await named_routine(session, context, "تقرير الذهب", enabling=False)
        assert partial.value.details["next_actions"] == [
            {"repeat_with": {"routine_id": morning.id}}
        ]
        # Switching one on starts scheduled work again: refused with the one that is off.
        with pytest.raises(NotResolved) as waking:
            await named_routine(session, context, "weekly review", enabling=True)
        assert waking.value.code == "routine_not_found" and waking.value.details["retryable"]
        assert [item["id"] for item in waking.value.details["candidates"]] == [asleep.id]
        # A routine with no title is not what every request means.
        with pytest.raises(NotResolved) as nothing:
            await named_routine(session, context, "the evening summary", enabling=False)
        assert nothing.value.details["candidates"] == []
        assert {item["id"] for item in nothing.value.details["existing"]} == {
            morning.id,
            untitled.id,
        }


@pytest.mark.asyncio
async def test_a_task_is_read_by_its_title(task_db: Fixture) -> None:
    db, owner, agent, thread = task_db
    async with db.sessions() as session, session.begin():
        managed = await create_task(
            session, owner, agent, thread, TaskCreate(title="Manage the gold account")
        )
        other = await create_task(session, owner, agent, thread, TaskCreate(title="Weekly report"))
    context = caller(owner, agent)
    async with db.sessions() as session:
        for requested in ("manage the gold account", "gold account"):
            task_id, note = await named_task(session, context, requested)
            assert task_id == managed.id and note is not None
        assert note["label"] == "Manage the gold account"
        assert await named_task(session, context, other.id) == (other.id, None)
        with pytest.raises(NotResolved) as missing:
            await named_task(session, context, "the audit")
        assert missing.value.code == "task_not_found"
        assert {item["id"] for item in missing.value.details["existing"]} == {managed.id, other.id}
        assert missing.value.details["next_actions"] == [{"tool": "task_inspect"}]


@pytest.mark.asyncio
async def test_an_agent_is_read_by_its_name_and_only_within_reach(task_db: Fixture) -> None:
    db, owner, agent, _thread = task_db
    async with db.sessions() as session, session.begin():
        lonora = AgentRow(owner_id=owner, name="Lonora", role="personal")
        sara = AgentRow(owner_id=owner, name="Sara")
        session.add_all([lonora, sara])
        await session.flush()
    # Lonora reaches every team agent by its role (3.1.6); a team agent reaches no one.
    context = caller(owner, lonora.id)
    async with db.sessions() as session:
        agent_id, note = await named_agent(session, context, "sara", read=True)
        assert agent_id == sara.id and note is not None and note["label"] == "Sara"
        # A pause, a resume or a message never acts on a name.
        with pytest.raises(NotResolved) as steering:
            await named_agent(session, context, "Sara", read=False)
        assert steering.value.details["next_actions"] == [{"repeat_with": {"agent_id": sara.id}}]
        team = caller(owner, agent)
        # An id is left to the tool's own rule (supervision_required for a team agent).
        assert await named_agent(session, team, sara.id, read=True) == (sara.id, None)
        # An agent this one does not reach is never offered by name.
        with pytest.raises(NotResolved) as unseen:
            await named_agent(session, team, "Sara", read=True)
        assert unseen.value.code == "agent_not_found"
        assert {item["id"] for item in unseen.value.details["existing"]} == {agent}
