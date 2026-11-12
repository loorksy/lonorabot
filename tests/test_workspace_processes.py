"""7.1.2: "on its next wake, the agent that started a process is told which of its
processes ended." Background processes are recorded when started, closed from the
supervisor's listing (exit, stop, a workspace restart), and told once, in one run."""

import pytest
from lonora_db.client import Database
from lonora_db.schema import WorkspaceProcessRow
from lonora_db.workspace_processes import ended_notice, reconcile, started
from test_task_runtime import task_db as task_db

Fixture = tuple[Database, str, str, str]


def listing(boot: str, *jobs: dict[str, object]) -> dict[str, object]:
    return {"boot_id": boot, "jobs": list(jobs), "processes": []}


def job(
    job_id: str, ended: bool, code: int | None = None, stopped: bool = False
) -> dict[str, object]:
    return {"id": job_id, "ended_at": 1.0 if ended else None, "exit_code": code, "stopped": stopped}


@pytest.mark.asyncio
async def test_an_agent_is_told_once_which_of_its_processes_ended(task_db: Fixture) -> None:
    db, owner, agent, _ = task_db
    async with db.sessions() as session, session.begin():
        for job_id, pid, command in (
            ("a" * 32, 101, "python bot.py"),
            ("b" * 32, 102, "node server.js"),
            ("c" * 32, 103, "sleep 999"),
            ("d" * 32, 104, "tail -f log"),
        ):
            await started(session, owner, agent, job_id, "boot-1", pid, command)
    async with db.sessions() as session, session.begin():
        closed = await reconcile(
            session,
            listing(
                "boot-1",
                job("a" * 32, True, 1),
                job("b" * 32, True, -15, stopped=True),
                job("c" * 32, False),
            ),
        )
    assert closed == 3  # d is gone from the listing: lost
    first = await ended_notice(db, agent, "run-1")
    assert "pid 101 `python bot.py` exited with code 1." in first
    assert "pid 102 `node server.js` was stopped" in first
    assert "pid 104 `tail -f log` ended (no exit status is known)." in first
    assert "sleep 999" not in first
    # The same run sees it again on every turn; the next run does not.
    assert await ended_notice(db, agent, "run-1") == first
    assert await ended_notice(db, agent, "run-2") == ""


@pytest.mark.asyncio
async def test_a_workspace_restart_ends_every_open_process(task_db: Fixture) -> None:
    db, owner, agent, _ = task_db
    async with db.sessions() as session, session.begin():
        await started(session, owner, agent, "e" * 32, "boot-1", 201, "python listener.py")
    async with db.sessions() as session, session.begin():
        assert await reconcile(session, listing("boot-2")) == 1
        row = await session.get(WorkspaceProcessRow, "e" * 32)
        assert row is not None and row.outcome == "restarted"
    notice = await ended_notice(db, agent, "run-1")
    assert "ended when the workspace restarted" in notice


@pytest.mark.asyncio
async def test_a_running_process_is_never_reported(task_db: Fixture) -> None:
    db, owner, agent, _ = task_db
    async with db.sessions() as session, session.begin():
        await started(session, owner, agent, "f" * 32, "boot-1", 301, "python bot.py")
        assert await reconcile(session, listing("boot-1", job("f" * 32, False))) == 0
    assert await ended_notice(db, agent, "run-1") == ""
