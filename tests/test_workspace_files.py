"""14.1: each agent's analytical-workspace files are copied once into its home in the
owner's persistent workspace (7.1), before the old store is deleted."""

import base64
import json
from typing import Any

import httpx
import pytest
from lonora_agent.workspace_move import DESTINATION, move_snapshots
from lonora_db.schema import AnalyticalWorkspaceRow
from lonora_workspace.client import WorkspaceClient
from test_task_runtime import task_db as task_db
from workspace_fake import FakeWorkspace


def encode_snapshot(files: dict[str, bytes]) -> bytes:
    """The former analytical workspace's stored form."""
    return json.dumps(
        {name: base64.b64encode(body).decode() for name, body in files.items()}
    ).encode()


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

    assert await move_snapshots(db, WorkspaceClient(transport=httpx.MockTransport(full))) == 0
    async with db.sessions() as session:
        row = await session.get(AnalyticalWorkspaceRow, agent)
        assert row is not None and row.moved_at is None
    workspace = FakeWorkspace()
    assert await move_snapshots(db, workspace.client()) == 1
    assert workspace.files == {(agent, DESTINATION + "a.txt"): b"a"}


@pytest.mark.asyncio
async def test_an_agent_whose_copy_fails_does_not_hold_up_the_others(task_db: Any) -> None:
    db, _, agent, _ = task_db
    from lonora_db.schema import AgentRow

    async with db.sessions() as session, session.begin():
        template = await session.get(AgentRow, agent)
        assert template is not None
        others: list[str] = []
        for index in range(6):
            other = AgentRow(
                **{
                    column.key: getattr(template, column.key)
                    for column in AgentRow.__table__.columns
                    if column.key not in {"id"}
                }
            )
            other.id = f"{index:08d}-0000-4000-8000-000000000000"
            other.name = f"{template.name} {index}"
            session.add(other)
            others.append(other.id)
        await session.flush()
        for agent_id in [*others, agent]:
            session.add(
                AnalyticalWorkspaceRow(
                    agent_id=agent_id, revision=1, snapshot=encode_snapshot({"a.txt": b"a"})
                )
            )
    stuck = others[0]
    workspace = FakeWorkspace()

    def handle(request: httpx.Request) -> httpx.Response:
        if stuck.encode() in request.content:
            return httpx.Response(200, json={"boot_id": "b", "ok": False, "error": "mkdir"})
        return workspace.handle(request)

    client = WorkspaceClient(transport=httpx.MockTransport(handle))
    moved = 0
    for _ in range(3):
        moved += await move_snapshots(db, client)
    assert moved == 6
    assert (stuck, DESTINATION + "a.txt") not in workspace.files


@pytest.mark.parametrize(
    ("content", "code"),
    [
        (b'{"a.txt": "YQ==", "a.txt": "Yg=="}', "workspace_path_duplicate"),
        (b'{"a.txt": null}', "workspace_snapshot_invalid"),
        (b'{"a.txt": "not base64!"}', "workspace_snapshot_invalid"),
        (b"[]", "workspace_snapshot_invalid"),
        (b'{"../a.txt": "YQ=="}', "workspace_path_unsafe"),
        (b" " * (12 * 1024 * 1024 + 1), "workspace_snapshot_too_large"),
    ],
)
def test_a_stored_snapshot_is_checked_before_it_is_copied(content: bytes, code: str) -> None:
    from lonora_agent.workspace_move import read_snapshot
    from lonora_core.user_error import LonoraError

    with pytest.raises(LonoraError, match=code):
        read_snapshot(content)


@pytest.mark.asyncio
async def test_an_unreadable_snapshot_does_not_hold_up_the_others(task_db: Any) -> None:
    db, _, agent, _ = task_db
    async with db.sessions() as session, session.begin():
        session.add(AnalyticalWorkspaceRow(agent_id=agent, revision=1, snapshot=b'{"a": null}'))
    workspace = FakeWorkspace()
    assert await move_snapshots(db, workspace.client()) == 0
    assert workspace.files == {}
    async with db.sessions() as session:
        row = await session.get(AnalyticalWorkspaceRow, agent)
        assert row is not None and row.moved_at is None and row.move_tried_at is not None
