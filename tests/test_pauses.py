"""The owner's pauses (14.3.6): an agent, routine, watch or Task the owner paused stays
paused until the owner resumes it, and a supervisor's hold the owner takes over becomes
the owner's.

The PostgreSQL tests run the real tools and owner routes against the test database
(skipped without ``LONORA_DATABASE_URL``).
"""

import json
import os
from typing import Any, cast
from uuid import uuid4

import pytest
from lonora_adapter_kit.types import ToolCall
from lonora_core.user_error import LonoraError
from lonora_db.schema import EventRow, MessageRow, ThreadRow
from lonora_tools.loader import load_tools
from sqlalchemy import func, select


def database() -> None:
    if not os.environ.get("LONORA_DATABASE_URL"):
        pytest.skip("Supervision reads use PostgreSQL full-text search.")


async def add_messages(fixture: Any, thread_id: str, messages: list[tuple[str, str | None, str]]):
    async with fixture.runtime.db.sessions() as session, session.begin():
        thread = await session.get(ThreadRow, thread_id, with_for_update=True)
        assert thread is not None
        for role, agent_id, content in messages:
            session.add(
                MessageRow(
                    thread_id=thread_id,
                    seq=thread.next_seq,
                    role=role,
                    agent_id=agent_id,
                    content=content,
                )
            )
            thread.next_seq += 1


async def wake(fixture: Any, agent: dict[str, Any], thread: dict[str, Any]) -> Any:
    """A Run no owner message started: a routine wake."""
    from lonora_contracts.runs import RunRequest
    from lonora_db.runs import create_run

    async with fixture.runtime.db.sessions() as session, session.begin():
        run = await create_run(
            session,
            fixture.owner,
            RunRequest(
                thread_id=thread["id"], agent_id=agent["id"], trigger="routine", prompt="Check"
            ),
        )
        data = {"id": run.id, "agent_id": agent["id"], "thread_id": thread["id"]}
    return await fixture.lease(data)


async def owner_says(fixture: Any, agent: dict[str, Any], thread: dict[str, Any], text: str) -> Any:
    """A Run that answers the owner's message."""
    await add_messages(fixture, thread["id"], [("user", None, text)])
    return await fixture.lease(await fixture.run(agent, thread))


async def call(context: Any, name: str, **arguments: Any) -> dict[str, Any]:
    result = await load_tools().execute(
        ToolCall(id="call-" + uuid4().hex, name=name, arguments=arguments), context
    )
    json.dumps(result)  # A Run stores every observation as JSON.
    return result


async def refused(context: Any, name: str, **arguments: Any) -> str:
    try:
        await call(context, name, **arguments)
    except LonoraError as error:
        return error.code
    raise AssertionError("expected a refusal from " + name)


async def grant(fixture: Any, supervisor: dict[str, Any], supervised: dict[str, Any]) -> str:
    row = await fixture.request(
        "POST",
        "/supervision",
        {"supervisor_id": supervisor["id"], "supervised_id": supervised["id"]},
    )
    assert row["created_via"] == "owner_ui" and row["revoked_at"] is None
    return cast(str, row["id"])


async def held(fixture: Any, target_id: str) -> Any:
    """The latest hold on one item (live or released)."""
    from lonora_db.schema import SupervisionHoldRow

    async with fixture.runtime.db.sessions() as session:
        return await session.scalar(
            select(SupervisionHoldRow)
            .where(SupervisionHoldRow.target_id == target_id)
            .order_by(SupervisionHoldRow.created_at.desc())
            .limit(1)
        )


@pytest.mark.asyncio
async def test_pauses_are_held_by_their_supervisor_and_the_owner_wins():
    database()
    from check_streaming import Fixture
    from lonora_contracts.routines import RoutineCreate
    from lonora_db.routines import create_routine
    from lonora_db.schema import AgentRow, RoutineRow, SupervisionHoldRow

    fixture = await Fixture().open()
    try:
        lead, gold = await fixture.agent("Lead"), await fixture.agent("Gold")
        await grant(fixture, lead, gold)
        lead_thread, gold_thread = (
            await fixture.conversation(lead),
            await fixture.conversation(gold),
        )
        async with fixture.runtime.db.sessions() as session, session.begin():
            routine = await create_routine(
                session,
                fixture.owner,
                gold["id"],
                RoutineCreate(prompt="Review gold", interval_seconds=3600),
            )
            routine_id = routine.id
        lead_context = await wake(fixture, lead, lead_thread)
        gold_context = await wake(fixture, gold, gold_thread)

        async def routine_enabled() -> bool:
            async with fixture.runtime.db.sessions() as session:
                row = await session.get(RoutineRow, routine_id)
                assert row is not None
                return row.enabled

        paused = await call(
            lead_context,
            "agent_control",
            agent_id=gold["id"],
            action="pause",
            target="routine",
            target_id=routine_id,
        )
        assert paused["changed"] is True and paused["money_authority"] == "none"
        assert not await routine_enabled()
        again = await call(
            lead_context,
            "agent_control",
            agent_id=gold["id"],
            action="pause",
            target="routine",
            target_id=routine_id,
        )
        assert again["changed"] is False and again["paused_by"] == "you"
        # The paused agent cannot resume what its supervisor paused.
        assert (
            await refused(gold_context, "routine_toggle", routine_id=routine_id, enabled=True)
            == "work_paused_by_supervisor"
        )
        # Cycle rule: holding a pause over Lead, Gold may not pause or narrow Lead back.
        await grant(fixture, gold, lead)
        assert await refused(
            gold_context, "agent_control", agent_id=lead["id"], action="pause"
        ) == ("supervision_cycle")
        # ...unless the owner's message asks.
        owner_context = await owner_says(fixture, gold, gold_thread, "Pause Lead for now")
        paused_lead = await call(
            owner_context, "agent_control", agent_id=lead["id"], action="pause"
        )
        assert paused_lead["changed"] is True
        # A pause made from the owner's message is the owner's (4.7.2): the agent that
        # made it never lifts it on its own; the owner lifts it, by a control or by
        # asking in chat (P5).
        made = await held(fixture, lead["id"])
        assert made.source == "owner" and made.holder_agent_id == gold["id"]
        assert await refused(
            gold_context, "agent_control", agent_id=lead["id"], action="resume"
        ) == ("supervision_resume_not_yours")
        asked_back = await owner_says(fixture, gold, gold_thread, "Resume Lead")
        assert (await call(asked_back, "agent_control", agent_id=lead["id"], action="resume"))[
            "changed"
        ]
        assert (await held(fixture, lead["id"])).released_by == "owner"
        # The supervisor lifts its own hold; routine_toggle follows the same rules.
        resumed = await call(lead_context, "routine_toggle", routine_id=routine_id, enabled=True)
        assert resumed["enabled"] is True and await routine_enabled()
        # Pausing the agent itself. Saving its profile (the form sends the switch with
        # every save) leaves the supervisor's pause the supervisor's.
        assert (await call(lead_context, "agent_control", agent_id=gold["id"], action="pause"))[
            "paused"
        ]
        await fixture.request(
            "PATCH", f"/agents/{gold['id']}", {"name": "Gold renamed", "paused": True}
        )
        overview = await call(lead_context, "agent_inspect", agent_id=gold["id"])
        assert overview["profile"]["paused_by"] == "you"
        assert (await call(lead_context, "agent_control", agent_id=gold["id"], action="resume"))[
            "changed"
        ]
        # The owner switching it back on releases the supervisor's pause.
        assert (await call(lead_context, "agent_control", agent_id=gold["id"], action="pause"))[
            "paused"
        ]
        await fixture.request("PATCH", f"/agents/{gold['id']}", {"paused": False})
        async with fixture.runtime.db.sessions() as session:
            agent = await session.get(AgentRow, gold["id"])
            assert agent is not None and not agent.paused
            holds = list(
                await session.scalars(
                    select(SupervisionHoldRow).where(SupervisionHoldRow.agent_id == gold["id"])
                )
            )
            assert holds and all(hold.released_at is not None for hold in holds)
            assert {hold.released_by for hold in holds} >= {"holder", "owner"}
            # Every intervention is recorded for the actor and for the agent acted on.
            for agent_id in (lead["id"], gold["id"]):
                count = await session.scalar(
                    select(func.count())
                    .select_from(EventRow)
                    .where(
                        EventRow.kind == "supervision.intervention",
                        EventRow.agent_id == agent_id,
                    )
                )
                assert (count or 0) >= 3, agent_id
        # A Task follows the same rules through its own control.
        from lonora_contracts.tasks import TaskCreate
        from lonora_db.tasks import create_task, get_task

        async with fixture.runtime.db.sessions() as session, session.begin():
            task = await create_task(
                session, fixture.owner, gold["id"], gold_thread["id"], TaskCreate(title="Review")
            )
            task_id = task.id
        held_task = await call(
            lead_context,
            "agent_control",
            agent_id=gold["id"],
            action="pause",
            target="task",
            target_id=task_id,
        )
        assert held_task["changed"] is True and held_task["paused"] is True

        async def task_version() -> int:
            async with fixture.runtime.db.sessions() as session:
                return (await get_task(session, fixture.owner, task_id)).version

        assert (
            await refused(
                gold_context,
                "task_control",
                task_id=task_id,
                action="resume",
                expected_version=await task_version(),
            )
            == "work_paused_by_supervisor"
        )
        freed = await call(
            lead_context,
            "agent_control",
            agent_id=gold["id"],
            action="resume",
            target="task",
            target_id=task_id,
        )
        assert freed["changed"] is True and freed["paused"] is False
        # Without a grant there is nothing to steer, and another agent's routine is hidden.
        outsider = await fixture.agent("Outsider")
        outsider_context = await wake(fixture, outsider, await fixture.conversation(outsider))
        assert (
            await refused(outsider_context, "agent_control", agent_id=gold["id"], action="pause")
            == "supervision_required"
        )
        assert (
            await refused(outsider_context, "routine_toggle", routine_id=routine_id, enabled=False)
            == "routine_not_found"
        )
    finally:
        await fixture.close()


@pytest.mark.asyncio
async def test_the_owners_pause_is_the_owners_and_the_owners_word_resumes():
    """The owner pausing held work makes the pause the owner's, never weaker; the
    owner's message lifts a supervisor's pause; a watch the agent cancelled stays
    cancelled when its supervisor resumes."""
    database()
    from check_streaming import Fixture
    from lonora_contracts.routines import RoutineCreate
    from lonora_contracts.tasks import TaskCreate
    from lonora_db.routines import create_routine
    from lonora_db.schema import MarketWatchRow, RoutineRow
    from lonora_db.tasks import create_task

    fixture = await Fixture().open()
    try:
        lead, gold, helper = (
            await fixture.agent("Lead"),
            await fixture.agent("Gold"),
            await fixture.agent("Helper"),
        )
        await grant(fixture, lead, gold)
        lead_thread, gold_thread, helper_thread = (
            await fixture.conversation(lead),
            await fixture.conversation(gold),
            await fixture.conversation(helper),
        )
        async with fixture.runtime.db.sessions() as session, session.begin():
            routine = await create_routine(
                session,
                fixture.owner,
                gold["id"],
                RoutineCreate(prompt="Review gold", interval_seconds=3600),
            )
            watch = MarketWatchRow(
                owner_id=fixture.owner,
                agent_id=gold["id"],
                thread_id=gold_thread["id"],
                payload={
                    "kind": "price",
                    "symbol": "XAUUSD",
                    "condition": "above",
                    "level": "2100",
                    "prompt": "Gold above 2100",
                    "enabled": True,
                },
                state={},
            )
            session.add(watch)
            task = await create_task(
                session, fixture.owner, gold["id"], gold_thread["id"], TaskCreate(title="Review")
            )
            routine_id, task_id = routine.id, task.id
            await session.flush()
            watch_id = watch.id
        lead_context = await wake(fixture, lead, lead_thread)
        gold_context = await wake(fixture, gold, gold_thread)

        async def watch_state() -> tuple[bool, str | None]:
            async with fixture.runtime.db.sessions() as session:
                row = await session.get(MarketWatchRow, watch_id)
                assert row is not None
                return bool(row.payload.get("enabled", True)), row.state.get("code")

        # A routine: saving its schedule with the switch unchanged takes nothing over.
        await call(
            lead_context,
            "agent_control",
            agent_id=gold["id"],
            action="pause",
            target="routine",
            target_id=routine_id,
        )
        await fixture.request(
            "PUT",
            f"/routines/{routine_id}",
            {"prompt": "Review gold", "interval_seconds": 3600, "enabled": False},
        )
        assert (await held(fixture, routine_id)).source == "agent"
        assert (
            await refused(gold_context, "routine_toggle", routine_id=routine_id, enabled=True)
            == "work_paused_by_supervisor"
        )
        # The owner's word to the paused agent lifts its supervisor's pause.
        asked = await owner_says(fixture, gold, gold_thread, "Resume your review routine")
        assert (await call(asked, "routine_toggle", routine_id=routine_id, enabled=True))["enabled"]
        async with fixture.runtime.db.sessions() as session:
            row = await session.get(RoutineRow, routine_id)
            assert row is not None and row.enabled
        assert (await held(fixture, routine_id)).released_by == "owner"

        # A watch: the owner pausing it too makes the pause the owner's.
        await call(
            lead_context,
            "agent_control",
            agent_id=gold["id"],
            action="pause",
            target="watch",
            target_id=watch_id,
        )
        await fixture.request("POST", f"/watches/{watch_id}/control", {"action": "pause"})
        hold = await held(fixture, watch_id)
        assert hold.source == "owner" and hold.released_at is None
        assert hold.holder_agent_id == lead["id"]
        assert await refused(
            lead_context,
            "agent_control",
            agent_id=gold["id"],
            action="resume",
            target="watch",
            target_id=watch_id,
        ) == ("supervision_resume_not_yours")
        again = await call(
            lead_context,
            "agent_control",
            agent_id=gold["id"],
            action="pause",
            target="watch",
            target_id=watch_id,
        )
        assert again["changed"] is False and again["paused_by"] == "owner"
        asked = await owner_says(fixture, gold, gold_thread, "Resume your gold watch")
        for context in (gold_context, asked):
            assert (
                await refused(context, "watch_resume", watch_id=watch_id) == "work_paused_by_owner"
            )
        # The owner holds no pause over Gold for the cycle rule: Lead did not.
        gold_over_lead = await grant(fixture, gold, lead)
        assert (await call(gold_context, "agent_control", agent_id=lead["id"], action="pause"))[
            "changed"
        ]
        assert (await call(gold_context, "agent_control", agent_id=lead["id"], action="resume"))[
            "changed"
        ]
        await fixture.request("POST", f"/supervision/{gold_over_lead}/revoke")
        await fixture.request("POST", f"/watches/{watch_id}/control", {"action": "resume"})
        assert await watch_state() == (True, None)
        assert (await held(fixture, watch_id)).released_by == "owner"

        # The agent cancels a watch its supervisor paused: the cancel stays its own.
        await call(
            lead_context,
            "agent_control",
            agent_id=gold["id"],
            action="pause",
            target="watch",
            target_id=watch_id,
        )
        assert (await call(gold_context, "watch_cancel", watch_id=watch_id))["state"][
            "code"
        ] == "watch_cancelled"
        assert (
            await refused(gold_context, "watch_resume", watch_id=watch_id)
            == "work_paused_by_supervisor"
        )
        lifted = await call(
            lead_context,
            "agent_control",
            agent_id=gold["id"],
            action="resume",
            target="watch",
            target_id=watch_id,
        )
        assert lifted["changed"] is True and lifted["stays_cancelled_by_the_agent"] is True
        assert await watch_state() == (False, "watch_cancelled")
        assert (await held(fixture, watch_id)).released_by == "holder"

        # A Task: Lonora lifts only pauses Lonora made (4.7.2), even with the owner's
        # word; an agent with no grant does not, whatever message its Run answers.
        await call(
            lead_context,
            "agent_control",
            agent_id=gold["id"],
            action="pause",
            target="task",
            target_id=task_id,
        )
        helper_woke = await wake(fixture, helper, helper_thread)
        assert (
            await refused(
                helper_woke,
                "agent_control",
                agent_id=gold["id"],
                action="resume",
                target="task",
                target_id=task_id,
            )
            == "supervision_required"
        )
        told = await owner_says(fixture, helper, helper_thread, "Resume Gold's review task")
        assert (
            await refused(
                told,
                "agent_control",
                agent_id=gold["id"],
                action="resume",
                target="task",
                target_id=task_id,
            )
            == "supervision_required"
        )
        from lonora_db.personal_agent import ensure_personal_agent
        from lonora_db.schema import SupervisionGrantRow
        from lonora_db.supervision import revoke_supervision
        from sqlalchemy import select

        async with fixture.runtime.db.sessions() as session, session.begin():
            lonora = {"id": (await ensure_personal_agent(session, fixture.owner)).id}
            # Even without its default grant, Lonora acts on the owner's word.
            default = await session.scalar(
                select(SupervisionGrantRow).where(
                    SupervisionGrantRow.supervisor_agent_id == lonora["id"],
                    SupervisionGrantRow.supervised_agent_id == gold["id"],
                    SupervisionGrantRow.revoked_at.is_(None),
                )
            )
            if default is not None:
                await revoke_supervision(session, fixture.owner, default.id, via="owner_ui")
        told = await owner_says(
            fixture, lonora, await fixture.conversation(lonora), "Resume Gold's review task"
        )
        task_call = {"agent_id": gold["id"], "target": "task", "target_id": task_id}
        assert (
            await refused(told, "agent_control", action="resume", **task_call)
            == "supervision_resume_not_yours"
        )
        freed = await call(lead_context, "agent_control", action="resume", **task_call)
        assert freed["changed"] is True and freed["paused"] is False
        assert (await held(fixture, task_id)).released_by == "holder"
        # Lonora pausing it because the owner asked makes the pause the owner's.
        told = await owner_says(
            fixture, lonora, await fixture.conversation(lonora), "Pause Gold's review task"
        )
        assert (await call(told, "agent_control", action="pause", **task_call))["changed"]
        hold = await held(fixture, task_id)
        assert hold.source == "owner" and hold.holder_agent_id == lonora["id"]
        await grant(fixture, lonora, gold)
        lonora_woke = await wake(fixture, lonora, await fixture.conversation(lonora))
        # Lonora never lifts it on its own initiative.
        assert (
            await refused(lonora_woke, "agent_control", action="resume", **task_call)
            == "supervision_resume_not_yours"
        )
        # Lonora lifts a pause it made on its own.
        async with fixture.runtime.db.sessions() as session, session.begin():
            from lonora_contracts.tasks import TaskControl
            from lonora_db.tasks import control_task, get_task

            row = await get_task(session, fixture.owner, task_id)
            await control_task(
                session,
                fixture.owner,
                TaskControl(task_id=task_id, action="resume", expected_version=row.version),
            )
        assert (await held(fixture, task_id)).released_by == "owner"
        assert (await call(lonora_woke, "agent_control", action="pause", **task_call))["changed"]
        assert (await held(fixture, task_id)).source == "agent"
        lifted = await call(lonora_woke, "agent_control", action="resume", **task_call)
        assert lifted["changed"] is True
        assert (await held(fixture, task_id)).released_by == "holder"
    finally:
        await fixture.close()


@pytest.mark.asyncio
async def test_the_owners_own_pause_or_cancel_is_never_lifted_by_the_agent():
    """The owner's Pause or Cancel of a watch, switch-off of a routine and Pause of a
    Task are the owner's: the agent cannot undo them in a wake or from the owner's
    message, and the owner's own Resume lifts them."""
    database()
    from check_streaming import Fixture
    from lonora_contracts.routines import RoutineCreate
    from lonora_contracts.tasks import TaskControl, TaskCreate
    from lonora_db.routines import create_routine
    from lonora_db.schema import MarketWatchRow, RoutineRow, SupervisionHoldRow
    from lonora_db.tasks import control_task, create_task, get_task
    from sqlalchemy import select

    fixture = await Fixture().open()
    try:
        gold = await fixture.agent("Gold owner stops")
        thread = await fixture.conversation(gold)
        async with fixture.runtime.db.sessions() as session, session.begin():
            watch = MarketWatchRow(
                owner_id=fixture.owner,
                agent_id=gold["id"],
                thread_id=thread["id"],
                payload={"enabled": True, "kind": "price", "symbol": "XAUUSD"},
                state={},
            )
            session.add(watch)
            routine = await create_routine(
                session,
                fixture.owner,
                gold["id"],
                RoutineCreate(prompt="Scan gold", interval_seconds=3600),
            )
            await session.flush()
            watch_id, routine_id = watch.id, routine.id
        for action in ("pause", "cancel"):
            response = await fixture.client.post(
                f"/api/watches/{watch_id}/control", json={"action": action}
            )
            assert response.is_success, response.text
            for context in (
                await wake(fixture, gold, thread),
                await owner_says(fixture, gold, thread, "Resume your gold watch"),
            ):
                assert (
                    await refused(context, "watch_resume", watch_id=watch_id)
                    == "work_paused_by_owner"
                ), action
            # The owner's own Resume lifts it.
            response = await fixture.client.post(
                f"/api/watches/{watch_id}/control", json={"action": "resume"}
            )
            assert response.is_success and response.json()["payload"]["enabled"] is True
        await fixture.request(
            "PUT",
            f"/routines/{routine_id}",
            {"prompt": "Scan gold", "interval_seconds": 3600, "enabled": False},
        )
        assert (
            await refused(
                await wake(fixture, gold, thread),
                "routine_toggle",
                routine_id=routine_id,
                enabled=True,
            )
            == "work_paused_by_owner"
        )
        async with fixture.runtime.db.sessions() as session:
            routine_row = await session.get(RoutineRow, routine_id)
            assert routine_row is not None and routine_row.enabled is False
            hold = await session.scalar(
                select(SupervisionHoldRow).where(
                    SupervisionHoldRow.target_id == routine_id,
                    SupervisionHoldRow.released_at.is_(None),
                )
            )
            assert hold is not None and hold.source == "owner" and hold.holder_agent_id is None
        await fixture.request(
            "PUT",
            f"/routines/{routine_id}",
            {"prompt": "Scan gold", "interval_seconds": 3600, "enabled": True},
        )
        async with fixture.runtime.db.sessions() as session:
            assert (await session.get(SupervisionHoldRow, hold.id)).released_at is not None  # type: ignore[union-attr]
        # A Task the owner paused stays paused for the agent.
        async with fixture.runtime.db.sessions() as session, session.begin():
            task = await create_task(
                session,
                fixture.owner,
                gold["id"],
                thread["id"],
                TaskCreate(title="Watch gold after the stop"),
            )
            task_id = task.id
        async with fixture.runtime.db.sessions() as session, session.begin():
            row = await get_task(session, fixture.owner, task_id)
            await control_task(
                session,
                fixture.owner,
                TaskControl(task_id=task_id, action="pause", expected_version=row.version),
            )
        async with fixture.runtime.db.sessions() as session:
            row = await get_task(session, fixture.owner, task_id)
            version = row.version
        assert (
            await refused(
                await wake(fixture, gold, thread),
                "task_control",
                task_id=task_id,
                action="resume",
                expected_version=version,
            )
            == "work_paused_by_owner"
        )
    finally:
        await fixture.close()


@pytest.mark.asyncio
async def test_deleting_a_supervisor_keeps_its_pauses_as_the_owners():
    """A deleted supervisor's pauses stay in force as the owner's: the work stays paused,
    its card keeps offering Resume, and the paused agent still cannot lift them."""
    database()
    from check_streaming import Fixture
    from lonora_contracts.routines import RoutineCreate
    from lonora_db.owner_actions import stale_reason
    from lonora_db.routines import create_routine
    from lonora_db.schema import AgentRow, OwnerActionRow, RoutineRow, SupervisionHoldRow
    from sqlalchemy import select

    fixture = await Fixture().open()
    try:
        lead, gold = await fixture.agent("Lead deleted"), await fixture.agent("Gold held")
        await grant(fixture, lead, gold)
        lead_thread, gold_thread = (
            await fixture.conversation(lead),
            await fixture.conversation(gold),
        )
        async with fixture.runtime.db.sessions() as session, session.begin():
            routine = await create_routine(
                session,
                fixture.owner,
                gold["id"],
                RoutineCreate(prompt="Review gold", interval_seconds=3600),
            )
            routine_id = routine.id
        lead_context = await wake(fixture, lead, lead_thread)
        await call(lead_context, "agent_control", agent_id=gold["id"], action="pause")
        await call(
            lead_context,
            "agent_control",
            agent_id=gold["id"],
            action="pause",
            target="routine",
            target_id=routine_id,
        )
        async with fixture.runtime.db.sessions() as session:
            holds = list(
                await session.scalars(
                    select(SupervisionHoldRow).where(SupervisionHoldRow.agent_id == gold["id"])
                )
            )
            cards = list(
                await session.scalars(
                    select(OwnerActionRow).where(
                        OwnerActionRow.kind == "supervision_paused",
                        OwnerActionRow.agent_id == gold["id"],
                    )
                )
            )
        assert len(holds) == 2 and len(cards) == 2
        await fixture.request("DELETE", f"/agents/{lead['id']}")
        fixture.agents.remove(lead["id"])
        async with fixture.runtime.db.sessions() as session:
            agent = await session.get(AgentRow, gold["id"])
            assert agent is not None and agent.paused
            for hold in holds:
                kept = await session.get(SupervisionHoldRow, hold.id)
                assert kept is not None and kept.released_at is None
                assert kept.source == "owner" and kept.holder_agent_id is None
            for card in cards:
                assert await stale_reason(session, fixture.owner, card.kind, card.payload) is None
        # The paused agent cannot lift them; the owner's Resume on the card does.
        await fixture.request("PATCH", f"/agents/{gold['id']}", {"paused": False})
        assert (
            await refused(
                await wake(fixture, gold, gold_thread),
                "routine_toggle",
                routine_id=routine_id,
                enabled=True,
            )
            == "work_paused_by_owner"
        )
        routine_card = next(
            card
            for card in cards
            if card.payload["hold_id"] in {h.id for h in holds if h.target_kind == "routine"}
        )
        decided = await fixture.request(
            "POST", f"/owner-actions/{routine_card.id}/decision", {"decision": "confirm"}
        )
        assert decided["status"] == "confirmed", decided
        async with fixture.runtime.db.sessions() as session:
            row = await session.get(RoutineRow, routine_id)
            assert row is not None and row.enabled
    finally:
        await fixture.close()


@pytest.mark.asyncio
async def test_a_hold_is_the_owners_or_an_agents_and_nothing_else():
    """4.7.2 after migration 0155: a pause the owner asked for is stored as the owner's;
    no hold can carry the old ``owner_message`` source."""
    database()
    from check_streaming import Fixture
    from lonora_contracts.domain import utcnow
    from lonora_db.schema import SupervisionHoldRow
    from sqlalchemy.exc import IntegrityError

    fixture = await Fixture().open()
    try:
        gold = await fixture.agent("Gold source")
        with pytest.raises(IntegrityError):
            async with fixture.runtime.db.sessions() as session, session.begin():
                session.add(
                    SupervisionHoldRow(
                        owner_id=fixture.owner,
                        holder_agent_id=None,
                        agent_id=gold["id"],
                        target_kind="agent",
                        target_id=gold["id"],
                        source="owner_message",
                        created_at=utcnow(),
                    )
                )
    finally:
        await fixture.close()


@pytest.mark.asyncio
async def test_a_pause_the_owner_asked_for_stays_the_owners():
    """4.7.2: a pause made from the owner's untainted message is the owner's; a run that
    read other content never speaks for the owner (6.10); asking to pause work already
    paused makes that pause the owner's; the owner lifts it by asking in chat (P5);
    Lonora never lifts a pause it did not make, even from the owner's words."""
    database()
    from check_streaming import Fixture
    from lonora_contracts.routines import RoutineCreate
    from lonora_db.pauses import refuse_held
    from lonora_db.personal_agent import ensure_personal_agent
    from lonora_db.routines import create_routine
    from lonora_db.supervision import control_work

    fixture = await Fixture().open()
    try:
        lead, gold = await fixture.agent("Lead words"), await fixture.agent("Gold words")
        await grant(fixture, lead, gold)
        async with fixture.runtime.db.sessions() as session, session.begin():
            lonora_id = (await ensure_personal_agent(session, fixture.owner)).id
        await grant(fixture, lead, {"id": lonora_id})
        async with fixture.runtime.db.sessions() as session, session.begin():
            gold_routine = await create_routine(
                session, fixture.owner, gold["id"], RoutineCreate(prompt="A", interval_seconds=3600)
            )
            lonora_routine = await create_routine(
                session, fixture.owner, lonora_id, RoutineCreate(prompt="B", interval_seconds=3600)
            )
            gold_routine_id, lonora_routine_id = gold_routine.id, lonora_routine.id

        gold_thread = await fixture.conversation(gold)
        await add_messages(
            fixture,
            gold_thread["id"],
            [("user", None, "Pause Gold"), ("user", None, "Pause it"), ("user", None, "Stop it")],
        )
        async with fixture.runtime.db.sessions() as session:
            words_1, words_2, words_3 = list(
                await session.scalars(
                    select(MessageRow.id)
                    .where(MessageRow.thread_id == gold_thread["id"])
                    .order_by(MessageRow.seq)
                )
            )

        async def control(action: str, *, words: str | None, kind: str = "agent", **ids: Any):
            """``words``: the run's untainted owner message (None once it read others')."""
            async with fixture.runtime.db.sessions() as session, session.begin():
                return await control_work(
                    session,
                    fixture.owner,
                    actor_id=ids.get("actor", lead["id"]),
                    agent_id=ids.get("agent", gold["id"]),
                    kind=kind,  # type: ignore[arg-type]
                    target_id=ids.get("target"),
                    action=action,  # type: ignore[arg-type]
                    owner_message_id=words,
                    run_id=None,
                )

        # A run that read other content has no owner message: its pause is the agent's.
        await control("pause", words=None)
        assert (await held(fixture, gold["id"])).source == "agent"
        await control("resume", words=None)

        # From the owner's untainted words, the pause is the owner's: the agent that made
        # it never lifts it on its own; the owner's words in chat lift it.
        await control("pause", words=words_1)
        made = await held(fixture, gold["id"])
        assert made.source == "owner" and made.source_message_id == words_1
        with pytest.raises(LonoraError, match="supervision_resume_not_yours"):
            await control("resume", words=None)
        assert (await control("resume", words=words_2))["changed"] is True
        assert (await held(fixture, gold["id"])).released_by == "owner"

        # Lead pauses on its own; the owner then asks for the same pause: it is the owner's.
        await control("pause", words=None)
        assert (await held(fixture, gold["id"])).source == "agent"
        again = await control("pause", words=words_2)
        assert again["changed"] is False and again["paused_by"] == "owner"
        assert (await held(fixture, gold["id"])).source == "owner"
        with pytest.raises(LonoraError, match="supervision_resume_not_yours"):
            await control("resume", words=None)
        await fixture.request("PATCH", f"/agents/{gold['id']}", {"paused": False})

        # Work the agent paused itself (no hold) becomes the owner's when the owner asks;
        # the agent's own tools lift it only from the owner's words.
        async with fixture.runtime.db.sessions() as session, session.begin():
            from lonora_db.schema import RoutineRow

            row = await session.get(RoutineRow, gold_routine_id)
            assert row is not None
            row.enabled = False
        await control("pause", words=words_3, kind="routine", target=gold_routine_id)
        hold = await held(fixture, gold_routine_id)
        assert hold.source == "owner" and hold.released_at is None
        with pytest.raises(LonoraError, match="work_paused_by_owner"):
            async with fixture.runtime.db.sessions() as session, session.begin():
                await refuse_held(session, fixture.owner, "routine", gold_routine_id, gold["id"])
        async with fixture.runtime.db.sessions() as session, session.begin():
            await refuse_held(
                session, fixture.owner, "routine", gold_routine_id, gold["id"], owner_message=True
            )
        assert (await held(fixture, gold_routine_id)).released_by == "owner"

        # Lead pauses Lonora's routine; Lonora cannot lift it, even from the owner's words.
        await control(
            "pause", words=None, kind="routine", agent=lonora_id, target=lonora_routine_id
        )
        with pytest.raises(LonoraError, match="work_paused_by_supervisor"):
            async with fixture.runtime.db.sessions() as session, session.begin():
                await refuse_held(
                    session,
                    fixture.owner,
                    "routine",
                    lonora_routine_id,
                    lonora_id,
                    owner_message=True,
                )
        await control(
            "resume", words=None, kind="routine", agent=lonora_id, target=lonora_routine_id
        )
    finally:
        await fixture.close()


@pytest.mark.asyncio
async def test_pausing_an_agent_ends_its_full_task_and_resuming_starts_it_again():
    """4.5.2: pausing a Full agent ends its continuous account-management task, through
    every pause entry point (Lonora's agent_control here; the owner's switch and Undo in
    check_management_task.py). 4.7.1: a paused agent's task is not restarted and its
    Runs are held. Resuming it, by Lonora or by the owner's Resume on the pause card,
    starts the task again (4.5.1)."""
    database()
    from check_streaming import Fixture
    from lonora_db.management_task import ensure_management_task, live_management_task
    from lonora_db.pauses import owner_resumes, runs_while_paused
    from lonora_db.personal_agent import ensure_personal_agent
    from lonora_db.schema import RunRow
    from lonora_db.trading_mode import set_trading_mode

    fixture = await Fixture().open()
    gold: dict[str, Any] = {}
    try:
        gold = await fixture.agent("Full gold task")
        async with fixture.runtime.db.sessions() as session, session.begin():
            lonora = {"id": (await ensure_personal_agent(session, fixture.owner)).id}
            await set_trading_mode(session, fixture.owner, gold["id"], "full", by="owner_tap")

        async def live_task() -> Any:
            async with fixture.runtime.db.sessions() as session:
                return await live_management_task(session, fixture.owner, gold["id"])

        assert await live_task() is not None
        # Lonora holds its default grant over the new agent.
        lonora_woke = await wake(fixture, lonora, await fixture.conversation(lonora))
        paused = await call(lonora_woke, "agent_control", agent_id=gold["id"], action="pause")
        assert paused["changed"] is True
        assert await live_task() is None
        async with fixture.runtime.db.sessions() as session, session.begin():
            # A paused agent's task is never started again while it is paused (4.7.1).
            assert await ensure_management_task(session, fixture.owner, gold["id"]) is None
            queued = list(
                await session.scalars(
                    select(RunRow).where(RunRow.agent_id == gold["id"], RunRow.status == "queued")
                )
            )
            assert all(not runs_while_paused(r.trigger, r.model_metadata) for r in queued)

        resumed = await call(lonora_woke, "agent_control", agent_id=gold["id"], action="resume")
        assert resumed["changed"] is True
        assert await live_task() is not None

        # Paused again; the owner's Resume on the pause card starts the task again.
        await call(lonora_woke, "agent_control", agent_id=gold["id"], action="pause")
        assert await live_task() is None
        hold = await held(fixture, gold["id"])
        async with fixture.runtime.db.sessions() as session, session.begin():
            assert await owner_resumes(session, fixture.owner, hold.id) == "agent"
        assert await live_task() is not None
    finally:
        if gold:
            async with fixture.runtime.db.sessions() as session, session.begin():
                await set_trading_mode(session, fixture.owner, gold["id"], "ask", by="agent")
        await fixture.close()
