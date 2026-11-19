"""Migration 0200 on real rows, in an empty disposable PostgreSQL database (Lonora has one
owner, so it runs once per database): stored skill
manifests that require a removed workspace tool name its replacement, saved stdio MCP
servers are deleted and the others lose `transport` and `command`, and the old tools'
receipts table is dropped (14.3.9)."""

import asyncio
import subprocess
import sys
from typing import Any
from uuid import uuid4

from check_streaming import test_settings
from lonora_db.client import Database
from lonora_db.schema import (
    AgentRow,
    McpConnectionRow,
    OwnerRow,
    SkillRow,
    SkillVersionRow,
    TrustedSourceRow,
)
from sqlalchemy import inspect, select

ALEMBIC = [sys.executable, "-m", "alembic", "-c", "packages/db/alembic.ini"]
OLD = ["workspace_read", "workspace_execute", "market_quote"]


def manifest(tools: list[str]) -> dict[str, Any]:
    return {"version": "1.0.0", "required_tools": tools, "source": "installed"}


async def alembic(*arguments: str) -> None:
    await asyncio.to_thread(
        subprocess.run, [*ALEMBIC, *arguments], check=True, stdout=subprocess.DEVNULL
    )


async def main() -> None:
    db = Database.connect(test_settings().database_url)
    try:
        await alembic("downgrade", "0087_end_money_limits")
        async with db.sessions() as session, session.begin():
            owner = OwnerRow(
                email=f"old-workspace-{uuid4().hex[:8]}@example.test", password_hash="fixture"
            )
            session.add(owner)
            await session.flush()
            agent = AgentRow(owner_id=owner.id, name="Old packages")
            session.add(agent)
            await session.flush()
            skill = SkillRow(
                owner_id=owner.id,
                agent_id=agent.id,
                payload={"name": "stats", "enabled": True, "manifest": manifest(OLD)},
                state={
                    "package": {
                        "versions": [
                            {"payload": {"name": "stats", "manifest": manifest(OLD)}},
                            # No removed name: left exactly as it was, duplicate included.
                            {
                                "payload": {
                                    "name": "stats",
                                    "manifest": manifest(["web_search", "web_search"]),
                                }
                            },
                            # A non-string entry stays as it is beside a renamed one.
                            {"payload": {"manifest": {"required_tools": [7, "workspace_update"]}}},
                        ]
                    }
                },
            )
            session.add(skill)
            await session.flush()
            session.add(
                SkillVersionRow(
                    skill_id=skill.id,
                    version=1,
                    owner_id=owner.id,
                    agent_id=agent.id,
                    package=True,
                    payload={"name": "stats", "manifest": manifest(["workspace_inspect"])},
                )
            )
            remote = McpConnectionRow(
                owner_id=owner.id,
                payload={
                    "name": "Remote",
                    "transport": "http",
                    "url": "https://mcp.example.com/mcp",
                    "command": [],
                    "enabled": True,
                },
            )
            local = McpConnectionRow(
                owner_id=owner.id,
                payload={"name": "Local", "transport": "stdio", "command": ["server"]},
            )
            session.add_all([remote, local])
            await session.flush()
            # Trust on the stdio server (an http server trusted, then edited to stdio while
            # disabled): it goes with the server.
            trusted = TrustedSourceRow(
                owner_id=owner.id, kind="mcp_server", identifier=local.id, added_via="owner_ui"
            )
            session.add(trusted)
            await session.flush()
            ids = (skill.id, remote.id, local.id, trusted.id)
        await db.close()
        await alembic("upgrade", "head")
        async with db.sessions() as session:
            skill = await session.get(SkillRow, ids[0])
            assert skill is not None
            replaced = ["workspace_file_read", "workspace_run", "market_quote"]
            assert skill.payload["manifest"]["required_tools"] == replaced
            versions = skill.state["package"]["versions"]
            assert versions[0]["payload"]["manifest"]["required_tools"] == replaced
            # A manifest without a removed tool is left exactly as it was.
            assert versions[1]["payload"]["manifest"]["required_tools"] == [
                "web_search",
                "web_search",
            ]
            assert versions[2]["payload"]["manifest"]["required_tools"] == [
                7,
                "workspace_file_write",
            ]
            saved = await session.get(SkillVersionRow, (ids[0], 1))
            assert saved is not None
            assert saved.payload["manifest"]["required_tools"] == ["workspace_run"]
            remote_row = await session.get(McpConnectionRow, ids[1])
            assert remote_row is not None
            assert remote_row.payload == {
                "name": "Remote",
                "url": "https://mcp.example.com/mcp",
                "enabled": True,
            }
            assert await session.get(McpConnectionRow, ids[2]) is None
            # The remaining payload validates against the contract without the removed fields.
            from lonora_contracts.mcp import McpConnection

            McpConnection.model_validate(remote_row.payload)
            owned = select(McpConnectionRow.id).where(
                McpConnectionRow.owner_id == remote_row.owner_id
            )
            assert (await session.scalars(owned)).all() == [ids[1]]
            trust = await session.get(TrustedSourceRow, ids[3])
            assert trust is not None and trust.revoked_at is not None
            assert trust.revoked_via == "owner_ui"
        async with db.engine.connect() as connection:
            tables = await connection.run_sync(lambda conn: inspect(conn).get_table_names())
        assert "ln_workspace_operations" not in tables
        assert "ln_analytical_workspaces" in tables
        # Down and up again: the receipts table comes back empty, then goes.
        await db.close()
        await alembic("downgrade", "0087_end_money_limits")
        async with db.engine.connect() as connection:
            tables = await connection.run_sync(lambda conn: inspect(conn).get_table_names())
        assert "ln_workspace_operations" in tables
        await db.close()
        await alembic("upgrade", "head")
        print(
            "PASS: 0200 renames removed workspace tools in stored manifests, deletes saved "
            "stdio MCP servers, strips transport/command, drops the old receipts; round-trips"
        )
    finally:
        await db.close()


if __name__ == "__main__":
    asyncio.run(main())
