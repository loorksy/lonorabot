"""An enabled package's utilities run from skills/<id>/<version>/ in the agent's home
(7.1). Validation and activation write that copy; a version enabled before the store
existed, or whose copy is gone, gets it from the store once per Gateway start."""

import shlex
from typing import Any

import httpx
import pytest
from lonora_agent.skills.run_copies import restore_run_copies
from lonora_agent.skills.store import store_files
from lonora_db.schema import SkillRow
from lonora_workspace.client import WorkspaceClient
from test_task_runtime import task_db as task_db
from workspace_fake import FakeWorkspace

PACKAGE = {
    "skills/stats/1.0.0/SKILL.md": "---\nname: stats\n---\nUse it.\n",
    "skills/stats/1.0.0/mean.py": "print(1)\n",
}


def workspace() -> FakeWorkspace:
    """`test -f PATH` answers from the fake's files, as the agent's shell would."""

    def shell(agent: str, command: str) -> dict[str, Any]:
        words = shlex.split(command)
        assert words[:2] == ["test", "-f"], command
        return {"exit_code": 0 if (agent, words[2]) in fake.files else 1}

    fake = FakeWorkspace(shell)
    return fake


async def package(db: Any, owner: str, agent: str, name: str, enabled: bool) -> None:
    async with db.sessions() as session, session.begin():
        session.add(
            SkillRow(
                owner_id=owner,
                agent_id=agent,
                payload={"name": name, "enabled": enabled, "manifest": {"version": "1.0.0"}},
                state={"package": {"versions": []}},
            )
        )
        await store_files(
            session,
            agent,
            {path.replace("stats", name, 1): body for path, body in PACKAGE.items()},
        )


@pytest.mark.asyncio
async def test_an_enabled_version_without_its_copy_gets_it_once(task_db: Any) -> None:
    db, owner, agent, _ = task_db
    await package(db, owner, agent, "stats", True)
    # A disabled package is run from nowhere: no copy is written for it.
    await package(db, owner, agent, "draft", False)
    fake, checked = workspace(), dict[tuple[str, str, str], bool]()
    assert await restore_run_copies(db, fake.client(), checked) == 1
    assert fake.files == {(agent, path): body.encode() for path, body in PACKAGE.items()}
    # Checked once per Gateway start: the agent's later edits to its copy are left alone.
    fake.files[(agent, "skills/stats/1.0.0/mean.py")] = b"edited\n"
    fake.ran.clear()
    assert await restore_run_copies(db, fake.client(), checked) == 0
    assert fake.ran == [] and fake.files[(agent, "skills/stats/1.0.0/mean.py")] == b"edited\n"


@pytest.mark.asyncio
async def test_a_present_copy_is_not_rewritten(task_db: Any) -> None:
    db, owner, agent, _ = task_db
    await package(db, owner, agent, "stats", True)
    fake = workspace()
    fake.files[(agent, "skills/stats/1.0.0/SKILL.md")] = b"present"
    fake.files[(agent, "skills/stats/1.0.0/data.csv")] = b"the agent's"
    assert await restore_run_copies(db, fake.client(), {}) == 0
    assert fake.files[(agent, "skills/stats/1.0.0/data.csv")] == b"the agent's"


@pytest.mark.asyncio
async def test_the_store_has_a_quota_per_agent(
    task_db: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    from lonora_agent.skills import store
    from lonora_core.user_error import LonoraError
    from lonora_db.schema import SkillPackageFileRow
    from sqlalchemy import select

    db, _, agent, _ = task_db
    monkeypatch.setattr(store, "STORE_BYTES", 10)
    async with db.sessions() as session, session.begin():
        await store_files(session, agent, {"skills/a/1.0.0/SKILL.md": "x" * 10})
    # Over the quota: refused in the caller's transaction, so nothing of it is kept.
    with pytest.raises(LonoraError, match="skill_package_store_full"):
        async with db.sessions() as session, session.begin():
            await store_files(session, agent, {"skills/b/1.0.0/SKILL.md": "y"})
    async with db.sessions() as session:
        paths = (await session.scalars(select(SkillPackageFileRow.path))).all()
    assert paths == ["skills/a/1.0.0/SKILL.md"]


@pytest.mark.asyncio
async def test_a_copy_that_keeps_failing_does_not_hold_up_the_others(task_db: Any) -> None:
    db, owner, agent, _ = task_db
    await package(db, owner, agent, "aaa", True)
    await package(db, owner, agent, "bbb", True)
    fake, checked = workspace(), dict[tuple[str, str, str], bool]()
    handle = fake.handle

    def full(request: Any) -> Any:
        # The first package's directory cannot be written (a full disk, say).
        if b"skills/aaa/" in request.content and request.url.path == "/v1/files/write":
            return httpx.Response(200, json={"boot_id": "b", "ok": False, "error": "no space"})
        return handle(request)

    client = WorkspaceClient(transport=httpx.MockTransport(full))
    assert await restore_run_copies(db, client, checked) == 1
    assert checked == {(agent, "aaa", "1.0.0"): False, (agent, "bbb", "1.0.0"): True}
    # Tried again on the next tick, after any version not yet tried; it succeeds once it can.
    assert await restore_run_copies(db, fake.client(), checked) == 1
    assert checked[(agent, "aaa", "1.0.0")] is True
