"""14.1: each agent's analytical-workspace files are copied once into its home in the
owner's persistent workspace (7.1), before the old store is deleted."""

from typing import Any

import httpx
import pytest
from lonora_agent.workspace import encode_snapshot
from lonora_agent.workspace_move import DESTINATION, move_snapshots
from lonora_core.user_error import LonoraError
from lonora_db.schema import AnalyticalWorkspaceRow
from lonora_workspace.client import WorkspaceClient
from test_task_runtime import task_db as task_db
from workspace_fake import FakeWorkspace


@pytest.mark.asyncio
async def test_an_agents_files_are_copied_once_into_its_home(task_db: Any) -> None:
    db, _, agent, _ = task_db
    files = {"analysis.py": b"print(1)\n", "market/EURUSD_1h.csv": b"time,close\n"}
    async with db.sessions() as session, session.begin():
        session.add(
            AnalyticalWorkspaceRow(agent_id=agent, revision=3, snapshot=encode_snapshot(files))
        )
    workspace = FakeWorkspace()
    assert await move_snapshots(db, workspace.client()) == 1
    assert workspace.files == {(agent, DESTINATION + path): data for path, data in files.items()}
    async with db.sessions() as session:
        row = await session.get(AnalyticalWorkspaceRow, agent)
        assert row is not None and row.moved_at is not None
    # Once moved, never copied again (the agent may have changed the copies since).
    workspace.files.clear()
    assert await move_snapshots(db, workspace.client()) == 0
    assert workspace.files == {}


@pytest.mark.asyncio
async def test_a_copy_that_did_not_finish_is_tried_again(task_db: Any) -> None:
    db, _, agent, _ = task_db
    async with db.sessions() as session, session.begin():
        session.add(
            AnalyticalWorkspaceRow(
                agent_id=agent, revision=1, snapshot=encode_snapshot({"a.txt": b"a"})
            )
        )

    def full(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"boot_id": "b", "ok": False, "error": "no space"})

    with pytest.raises(LonoraError) as refused:
        await move_snapshots(db, WorkspaceClient(transport=httpx.MockTransport(full)))
    assert refused.value.code == "workspace_snapshot_move_failed"
    async with db.sessions() as session:
        row = await session.get(AnalyticalWorkspaceRow, agent)
        assert row is not None and row.moved_at is None
    workspace = FakeWorkspace()
    assert await move_snapshots(db, workspace.client()) == 1
    assert workspace.files == {(agent, DESTINATION + "a.txt"): b"a"}
