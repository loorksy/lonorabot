"""Upgrade/downgrade roundtrip, only in an empty disposable verification DB."""

import asyncio
import subprocess
import sys

from check_streaming import test_settings
from lonora_db.client import Database
from lonora_db.schema import AnalyticalWorkspaceRow, WorkspaceOperationRow
from sqlalchemy import func, inspect, select


async def main() -> None:
    db = Database.connect(test_settings().database_url)
    try:
        async with db.sessions() as session:
            assert not await session.scalar(
                select(func.count()).select_from(AnalyticalWorkspaceRow)
            )
            assert not await session.scalar(select(func.count()).select_from(WorkspaceOperationRow))
        await db.close()
        command = [sys.executable, "-m", "alembic", "-c", "packages/db/alembic.ini"]
        await asyncio.to_thread(
            subprocess.run,
            [*command, "downgrade", "0027_device_authority"],
            check=True,
            stdout=subprocess.DEVNULL,
        )
        async with db.engine.connect() as connection:
            tables = await connection.run_sync(lambda conn: inspect(conn).get_table_names())
            assert (
                "ln_analytical_workspaces" not in tables and "ln_workspace_operations" not in tables
            )
            assert "ln_agents" in tables and "ln_trading_journal" in tables
        await db.close()
        await asyncio.to_thread(
            subprocess.run, [*command, "upgrade", "head"], check=True, stdout=subprocess.DEVNULL
        )
        async with db.engine.connect() as connection:
            tables = await connection.run_sync(lambda conn: inspect(conn).get_table_names())
            assert "ln_analytical_workspaces" in tables and "ln_workspace_operations" in tables
        print(
            "PASS: empty disposable PostgreSQL workspace migration upgrade/downgrade/upgrade; existing tables preserved"
        )
    finally:
        await db.close()


if __name__ == "__main__":
    asyncio.run(main())
