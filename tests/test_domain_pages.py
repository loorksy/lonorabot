"""Phase 4b domain pages (WP-H and the Task fields of WP-D).

Pure cases run everywhere: the routine schedule rule with a one-shot ``run_at``, the
Task's ``due_at`` and ``completion_criteria``, knowledge links, light goals. The
PostgreSQL cases (LONORA_DATABASE_URL) go through the owner API on the migrated schema:
routine titles and one-shot firing, «تحديد كمكتملة», light goals, «المعرفة», the
skills version history and restore, «تحديد الكل كمقروء» and the activity projection.
"""

import os
from datetime import UTC, datetime, timedelta
from typing import Any, cast

import pytest
from lonora_contracts.agent_goals import AgentGoal
from lonora_contracts.knowledge import KnowledgeLink
from lonora_contracts.routines import RoutineCreate
from lonora_contracts.tasks import TaskControl, TaskCreate
from pydantic import ValidationError

# --- Pure ---------------------------------------------------------------------------


def test_a_routine_has_exactly_one_schedule_and_a_one_shot_needs_a_zone():
    at = datetime(2030, 12, 1, 9, tzinfo=UTC)
    one_shot = RoutineCreate(prompt="Brief me", title="  موجز  ", run_at=at)
    assert one_shot.title == "موجز" and one_shot.run_at == at
    assert RoutineCreate(prompt="x", cron="0 9 * * *", title="   ").title is None
    for extra in ({"cron": "0 9 * * *"}, {"interval_seconds": 3600}):
        with pytest.raises(ValidationError, match="one_schedule_required"):
            RoutineCreate.model_validate({"prompt": "x", "run_at": at, **extra})
    with pytest.raises(ValidationError, match="one_schedule_required"):
        RoutineCreate(prompt="x")
    with pytest.raises(ValidationError, match="run_at_timezone_required"):
        RoutineCreate(prompt="x", run_at=datetime(2026, 12, 1, 9))


def test_task_fields_and_owner_completion_are_not_an_agent_control():
    task = TaskCreate.model_validate(
        {"title": "t", "due_at": "2026-12-01T18:00:00Z", "completion_criteria": "report sent"}
    )
    assert task.due_at is not None and task.completion_criteria == "report sent"
    # «تحديد كمكتملة» is the owner's own route; the agents' TaskControl cannot complete.
    with pytest.raises(ValidationError):
        TaskControl.model_validate({"task_id": "x", "action": "complete", "expected_version": 1})


def test_links_are_http_pages_and_goals_carry_no_schedule_or_authority():
    assert KnowledgeLink(title="t", url=" https://example.com/a ").url == "https://example.com/a"
    for url in ("javascript:alert(1)", "file:///etc/passwd", "https://", "example.com"):
        with pytest.raises(ValidationError):
            KnowledgeLink(title="t", url=url)
    assert set(AgentGoal.model_fields) == {"title", "description", "done"}
    with pytest.raises(ValidationError):
        AgentGoal.model_validate({"title": "t", "interval_seconds": 60})


# --- PostgreSQL: the owner API on the migrated schema -----------------------------------


def database() -> None:
    if not os.environ.get("LONORA_DATABASE_URL"):
        pytest.skip("The domain page cases use the real migrated PostgreSQL schema.")


async def status_of(fixture: Any, method: str, path: str, body: Any = None) -> tuple[int, Any]:
    response = await fixture.client.request(method, "/api" + path, json=body)
    return response.status_code, response.json()


@pytest.mark.asyncio
async def test_routines_keep_a_title_and_a_one_shot_fires_once():
    database()
    from check_streaming import Fixture
    from lonora_contracts.domain import utcnow
    from lonora_db.routines import enqueue_routine
    from lonora_db.schema import RoutineRow, RunRow
    from sqlalchemy import func, select

    fixture = await Fixture().open()
    try:
        agent = await fixture.agent("Scheduler")
        at = (utcnow() + timedelta(hours=2)).replace(microsecond=0)
        created = await fixture.request(
            "POST",
            f"/routines/{agent['id']}",
            {"title": "موجز الصباح", "prompt": "Prepare the brief", "run_at": at.isoformat()},
        )
        assert created["title"] == "موجز الصباح" and created["cron"] is None
        assert datetime.fromisoformat(created["run_at"]) == at
        assert datetime.fromisoformat(created["next_run_at"]) == at
        listed = cast(list[Any], await fixture.request("GET", f"/routines?agent_id={agent['id']}"))
        assert [row["title"] for row in listed] == ["موجز الصباح"]
        async with fixture.runtime.db.sessions() as session, session.begin():
            row = await session.get(RoutineRow, created["id"], with_for_update=True)
            assert row is not None
            assert await enqueue_routine(session, row, at + timedelta(seconds=1))
            assert row.enabled is False and row.next_run_at == at
        async with fixture.runtime.db.sessions() as session:
            runs = await session.scalar(
                select(func.count()).select_from(RunRow).where(RunRow.thread_id == row.thread_id)
            )
        assert runs == 1
        # Rescheduling with the switch on fires again once; a recurring one keeps its title.
        again = await fixture.request(
            "PUT",
            f"/routines/{created['id']}",
            {"title": "موجز", "prompt": "Prepare the brief", "cron": "0 9 * * *"},
        )
        assert again["title"] == "موجز" and again["run_at"] is None and again["enabled"]
    finally:
        await fixture.close()


@pytest.mark.asyncio
async def test_owner_completion_stops_the_work_and_reads_completed():
    database()
    from check_streaming import Fixture
    from lonora_db.schema import RunRow

    fixture = await Fixture().open()
    try:
        agent = await fixture.agent("Worker")
        thread = await fixture.conversation(agent)
        task = await fixture.request(
            "POST",
            f"/tasks?agent_id={agent['id']}&thread_id={thread['id']}",
            {
                "title": "Weekly report",
                "description": "Summarise the week",
                "due_at": "2026-12-01T18:00:00Z",
                "completion_criteria": "A report in the chat",
            },
        )
        assert task["due_at"] == "2026-12-01T18:00:00+00:00"
        assert task["completion_criteria"] == "A report in the chat"
        listed = cast(list[Any], await fixture.request("GET", "/tasks"))
        assert task["id"] in [row["id"] for row in listed]
        stale, _ = await status_of(
            fixture, "POST", f"/tasks/{task['id']}/complete", {"expected_version": 99}
        )
        assert stale == 409
        done = await fixture.request(
            "POST", f"/tasks/{task['id']}/complete", {"expected_version": task["version"]}
        )
        assert done["status"] == "completed" and not done["can_cancel"]
        async with fixture.runtime.db.sessions() as session:
            run = await session.get(RunRow, task["runs"][0]["id"])
        assert run is not None and run.status == "cancelled"
        again, body = await status_of(
            fixture, "POST", f"/tasks/{task['id']}/complete", {"expected_version": done["version"]}
        )
        assert again == 409 and body["code"] == "task_terminal"
    finally:
        await fixture.close()


@pytest.mark.asyncio
async def test_a_running_task_completes_at_its_next_checkpoint():
    database()
    from check_streaming import Fixture
    from lonora_contracts.domain import utcnow
    from lonora_contracts.runs import Lease
    from lonora_db.schema import RunRow
    from lonora_db.tasks import checkpoint_task

    fixture = await Fixture().open()
    try:
        agent = await fixture.agent("Runner")
        thread = await fixture.conversation(agent)
        task = await fixture.request(
            "POST",
            f"/tasks?agent_id={agent['id']}&thread_id={thread['id']}",
            {"title": "Long job"},
        )
        run_id = task["runs"][0]["id"]
        async with fixture.runtime.db.sessions() as session, session.begin():
            run = await session.get(RunRow, run_id, with_for_update=True)
            assert run is not None
            run.status, run.lease_owner = "running", "t7"
            run.lease_fence += 1
            run.lease_expires_at = utcnow() + timedelta(minutes=5)
            lease = Lease(run_id=run_id, owner="t7", fence=run.lease_fence)
        current = await fixture.request("GET", f"/tasks/{task['id']}")
        asked = await fixture.request(
            "POST", f"/tasks/{task['id']}/complete", {"expected_version": current["version"]}
        )
        assert asked["control_requested"] == "complete" and asked["status"] != "completed"
        async with fixture.runtime.db.sessions() as session, session.begin():
            assert await checkpoint_task(session, lease)
        finished = await fixture.request("GET", f"/tasks/{task['id']}")
        assert finished["status"] == "completed" and finished["control_requested"] is None
    finally:
        await fixture.close()


@pytest.mark.asyncio
async def test_light_goals_and_links_belong_to_one_agent():
    database()
    from check_streaming import Fixture

    fixture = await Fixture().open()
    try:
        agent = await fixture.agent("Researcher")
        code, _ = await status_of(fixture, "POST", "/agent-goals", {"payload": {"title": "x"}})
        assert code == 422
        goal = await fixture.request(
            "POST",
            "/agent-goals",
            {"agent_id": agent["id"], "payload": {"title": "تعلم السوق", "description": "d"}},
        )
        assert goal["payload"] == {"title": "تعلم السوق", "description": "d", "done": False}
        done = await fixture.request(
            "PUT",
            f"/agent-goals/{goal['id']}",
            {"version": goal["version"], "payload": {**goal["payload"], "done": True}},
        )
        assert done["payload"]["done"] is True
        goals = await fixture.request("GET", f"/agent-goals?agent_id={agent['id']}")
        assert [row["id"] for row in cast(list[Any], goals)] == [goal["id"]]
        code, _ = await status_of(
            fixture,
            "POST",
            "/knowledge-links",
            {"agent_id": agent["id"], "payload": {"title": "t", "url": "ftp://x"}},
        )
        assert code == 422
        link = await fixture.request(
            "POST",
            "/knowledge-links",
            {
                "agent_id": agent["id"],
                "payload": {"title": "Docs", "url": "https://example.com", "note": "API"},
            },
        )
        items = cast(list[Any], await fixture.request("GET", f"/agents/{agent['id']}/knowledge"))
        assert [(row["type"], row["title"], row["url"]) for row in items] == [
            ("link", "Docs", "https://example.com")
        ]
        assert items[0]["id"] == link["id"] and items[0]["content"] == "API"
    finally:
        await fixture.close()


@pytest.mark.asyncio
async def test_semantic_notes_list_by_title_and_need_the_semantic_model():
    database()
    from check_streaming import Fixture
    from lonora_db.schema import SemanticMemoryRow

    fixture = await Fixture().open()
    try:
        agent = await fixture.agent("Notes")
        code, body = await status_of(
            fixture,
            "POST",
            f"/agents/{agent['id']}/knowledge/notes",
            {"title": "t", "content": "c"},
        )
        assert code == 409 and body["code"] == "semantic_model_required"
        async with fixture.runtime.db.sessions() as session, session.begin():
            session.add(
                SemanticMemoryRow(
                    id="note-" + agent["id"][:20],
                    owner_id=fixture.owner,
                    agent_id=agent["id"],
                    payload={"text": "First line\nmore", "embedding": [], "model": "m"},
                )
            )
        items = cast(list[Any], await fixture.request("GET", f"/agents/{agent['id']}/knowledge"))
        assert [(row["type"], row["title"]) for row in items] == [("note", "First line")]
        other = await fixture.agent("Other")
        code, _ = await status_of(
            fixture, "DELETE", f"/agents/{other['id']}/knowledge/notes/{items[0]['id']}"
        )
        assert code == 404
        await fixture.request("DELETE", f"/agents/{agent['id']}/knowledge/notes/{items[0]['id']}")
        assert await fixture.request("GET", f"/agents/{agent['id']}/knowledge") == []
    finally:
        await fixture.close()


@pytest.mark.asyncio
async def test_skill_versions_list_every_save_and_restore_is_a_new_version():
    database()
    from check_streaming import Fixture

    fixture = await Fixture().open()
    try:
        agent = await fixture.agent("Skilled")
        skill = await fixture.request(
            "POST",
            "/skills",
            {"agent_id": agent["id"], "payload": {"name": "brief", "content": "First."}},
        )
        second = await fixture.request(
            "PUT",
            f"/skills/{skill['id']}",
            {"version": skill["version"], "payload": {"name": "brief", "content": "Second."}},
        )
        versions = cast(list[Any], await fixture.request("GET", f"/skills/{skill['id']}/versions"))
        assert [(row["version"], row["current"]) for row in versions] == [(2, True), (1, False)]
        restored = await fixture.request(
            "POST", f"/skills/{skill['id']}/restore", {"version": 1, "expected_version": 2}
        )
        assert restored["version"] == 3 and restored["payload"]["content"] == "First."
        # Undo is a restore of the version just left.
        undone = await fixture.request(
            "POST", f"/skills/{skill['id']}/restore", {"version": 2, "expected_version": 3}
        )
        assert undone["payload"]["content"] == second["payload"]["content"]
        code, _ = await status_of(
            fixture, "POST", f"/skills/{skill['id']}/restore", {"version": 1, "expected_version": 3}
        )
        assert code == 409
        code, body = await status_of(
            fixture, "POST", f"/skills/{skill['id']}/restore", {"version": 9, "expected_version": 4}
        )
        assert code == 404 and body["code"] == "skill_version_not_found"
        versions = cast(list[Any], await fixture.request("GET", f"/skills/{skill['id']}/versions"))
        assert [row["version"] for row in versions] == [4, 3, 2, 1]
    finally:
        await fixture.close()


@pytest.mark.asyncio
async def test_seen_all_keeps_action_items_and_activity_comes_from_events():
    database()
    from check_streaming import Fixture
    from lonora_contracts.domain import utcnow
    from lonora_db.schema import AttentionRow

    fixture = await Fixture().open()
    try:
        agent = await fixture.agent("Notifier")
        thread = await fixture.conversation(agent)
        async with fixture.runtime.db.sessions() as session, session.begin():
            for index, importance in enumerate(["informational", "important_change", "critical"]):
                session.add(
                    AttentionRow(
                        owner_id=fixture.owner,
                        agent_id=agent["id"],
                        thread_id=thread["id"],
                        logical_key=f"t7-{agent['id'][:8]}-{index}",
                        coalesce_key=f"t7-{index}",
                        importance=importance,
                        code="task_failed",
                        due_at=utcnow(),
                    )
                )
        seen = await fixture.request("POST", "/attention/seen-all")
        assert seen == {"seen": 2}
        open_items = [
            row
            for row in cast(list[Any], await fixture.request("GET", "/attention"))
            if row["agent_id"] == agent["id"]
        ]
        assert [row["importance"] for row in open_items] == ["critical"]
        task = await fixture.request(
            "POST",
            f"/tasks?agent_id={agent['id']}&thread_id={thread['id']}",
            {"title": "Close the books"},
        )
        await fixture.request(
            "POST", f"/tasks/{task['id']}/complete", {"expected_version": task["version"]}
        )
        feed = await fixture.request("GET", "/activity?limit=100")
        mine = [row for row in feed["items"] if row["agent_id"] == agent["id"]]
        assert [(row["code"], row["subject"]) for row in mine[:2]] == [
            ("task_completed", "Close the books"),
            ("task_created", "Close the books"),
        ]
        # One entry per durable event: no cancelled step before the owner's completion.
        assert "task_cancelled" not in [row["code"] for row in mine]
        older = await fixture.request("GET", f"/activity?limit=1&before={mine[0]['id']}")
        assert int(older["items"][0]["id"]) < int(mine[0]["id"])
    finally:
        await fixture.close()


@pytest.mark.asyncio
async def test_agent_text_files_upload_and_edit_but_other_files_do_not():
    database()
    from check_streaming import Fixture

    fixture = await Fixture().open()
    try:
        agent = await fixture.agent("Filer")
        uploaded = await fixture.client.post(
            "/api/artifacts/upload",
            files={"file": ("note.txt", b"first", "text/plain")},
            data={"agent_id": agent["id"]},
        )
        assert uploaded.status_code == 201
        text = uploaded.json()
        assert text["agent_id"] == agent["id"]
        listed = cast(list[Any], await fixture.request("GET", f"/artifacts?agent_id={agent['id']}"))
        assert [row["id"] for row in listed] == [text["id"]]
        saved = await fixture.request(
            "PUT", f"/artifacts/{text['id']}/text", {"name": "plan.md", "content": "second"}
        )
        assert saved["payload"]["name"] == "plan.md" and saved["payload"]["size"] == 6
        body = await fixture.client.get(f"/api/artifacts/{text['id']}/file")
        assert body.text == "second"
        image = await fixture.client.post(
            "/api/artifacts/upload", files={"file": ("a.png", b"\x89PNG", "image/png")}
        )
        code, problem = await status_of(
            fixture, "PUT", f"/artifacts/{image.json()['id']}/text", {"name": "a", "content": "x"}
        )
        assert code == 409 and problem["code"] == "artifact_not_text"
    finally:
        await fixture.close()


@pytest.mark.asyncio
async def test_completing_a_task_with_no_active_run_cancels_its_trade_approvals():
    database()
    from check_streaming import Fixture
    from lonora_db.schema import RunRow, TradeApprovalRow

    fixture = await Fixture().open()
    try:
        agent = await fixture.agent("Approver")
        thread = await fixture.conversation(agent)
        task = await fixture.request(
            "POST",
            f"/tasks?agent_id={agent['id']}&thread_id={thread['id']}",
            {"title": "Stale approval"},
        )
        run_id = task["runs"][0]["id"]
        async with fixture.runtime.db.sessions() as session, session.begin():
            run = await session.get(RunRow, run_id, with_for_update=True)
            assert run is not None
            run.status = "failed"
            for status in ("pending", "approved"):
                session.add(
                    TradeApprovalRow(
                        id=f"{status}-{run_id[:20]}",
                        owner_id=fixture.owner,
                        run_id=run_id,
                        thread_id=thread["id"],
                        agent_id=agent["id"],
                        call_id="call-" + status,
                        requests=[],
                        status=status,
                    )
                )
        current = await fixture.request("GET", f"/tasks/{task['id']}")
        done = await fixture.request(
            "POST", f"/tasks/{task['id']}/complete", {"expected_version": current["version"]}
        )
        assert done["status"] == "completed"
        async with fixture.runtime.db.sessions() as session:
            for status in ("pending", "approved"):
                row = await session.get(TradeApprovalRow, f"{status}-{run_id[:20]}")
                assert row is not None and row.status == "cancelled"
    finally:
        await fixture.close()


@pytest.mark.asyncio
async def test_a_one_shot_that_cannot_enqueue_stays_scheduled_and_past_times_are_refused():
    database()
    from check_streaming import Fixture
    from lonora_contracts.domain import utcnow
    from lonora_db.routines import enqueue_routine
    from lonora_db.schema import RoutineRow

    with pytest.raises(ValidationError, match="run_at_past"):
        RoutineCreate(prompt="x", run_at=datetime(2020, 1, 1, tzinfo=UTC))
    offset = datetime(2030, 1, 1, 12, tzinfo=UTC).astimezone(
        __import__("zoneinfo").ZoneInfo("Asia/Damascus")
    )
    assert RoutineCreate(prompt="x", run_at=offset).run_at == datetime(2030, 1, 1, 12, tzinfo=UTC)
    fixture = await Fixture().open()
    try:
        agent = await fixture.agent("Retry")
        at = (utcnow() + timedelta(hours=1)).replace(microsecond=0)
        created = await fixture.request(
            "POST", f"/routines/{agent['id']}", {"prompt": "Once", "run_at": at.isoformat()}
        )
        import lonora_db.routines as routines

        async def refused(*_: Any, **__: Any) -> None:
            from lonora_core.user_error import LonoraError

            raise LonoraError("goal_not_active", 409)

        original = routines.create_run
        routines.create_run = refused  # type: ignore[assignment]
        try:
            async with fixture.runtime.db.sessions() as session, session.begin():
                row = await session.get(RoutineRow, created["id"], with_for_update=True)
                assert row is not None
                now = at + timedelta(seconds=1)
                assert not await enqueue_routine(session, row, now)
                assert row.enabled is True and row.next_run_at > now
        finally:
            routines.create_run = original
    finally:
        await fixture.close()


@pytest.mark.asyncio
async def test_text_edit_never_deletes_outside_its_folder_and_untyped_text_is_text():
    database()
    from check_streaming import Fixture
    from lonora_security.runtime_storage import confined_path

    fixture = await Fixture().open()
    try:
        root = fixture.runtime.settings.artifact_root
        markdown = await fixture.client.post(
            "/api/artifacts/upload",
            files={"file": ("plan.md", b"# plan", "application/octet-stream")},
        )
        row = markdown.json()
        assert row["payload"]["media_type"] == "text/plain"
        victim = confined_path(root, "someone-else/secret.txt")
        victim.parent.mkdir(parents=True, exist_ok=True)
        victim.write_bytes(b"keep me")
        # A key retargeted through the generic resource update must not reach the unlink.
        moved = await fixture.request(
            "PUT",
            f"/artifacts/{row['id']}",
            {
                "version": row["version"],
                "payload": {**row["payload"], "key": "someone-else/secret.txt"},
            },
        )
        saved = await fixture.request(
            "PUT", f"/artifacts/{moved['id']}/text", {"name": "plan.md", "content": "# new"}
        )
        assert saved["payload"]["key"].startswith(row["id"] + "/")
        assert victim.read_bytes() == b"keep me"
        again = await fixture.request(
            "PUT", f"/artifacts/{row['id']}/text", {"name": "plan.md", "content": "# newer"}
        )
        assert not confined_path(root, saved["payload"]["key"]).exists()
        assert confined_path(root, again["payload"]["key"]).read_bytes() == b"# newer"
    finally:
        await fixture.close()
