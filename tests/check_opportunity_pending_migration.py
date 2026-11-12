"""0085: an opportunity's two pending operation keys become one list, and back.

On a disposable PostgreSQL already at head: step down below 0085, seed a thesis whose
state holds a pending entry and a pending management operation (with their journal
rows), upgrade and check the list, downgrade and check the two keys come back by each
operation's journal action.
"""

import asyncio
import json
import subprocess
import sys
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import uuid4

from check_streaming import test_settings
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

ALEMBIC = [sys.executable, "-m", "alembic", "-c", "packages/db/alembic.ini"]
BEFORE = "0068_end_trading_goals"


def alembic(*arguments: str) -> None:
    subprocess.run([*ALEMBIC, *arguments], check=True, capture_output=True, text=True)


def as_dict(value: Any) -> dict[str, Any]:
    return json.loads(value) if isinstance(value, str) else value


async def main() -> None:
    engine = create_async_engine(test_settings().database_url)
    now = datetime.now(UTC)
    ids = {name: str(uuid4()) for name in ("owner", "agent", "thread", "thesis", "account")}
    entry, management = "op-entry-" + uuid4().hex, "op-exit-" + uuid4().hex
    try:
        await asyncio.to_thread(alembic, "downgrade", BEFORE)
        async with engine.begin() as connection:
            statements = [
                "INSERT INTO ln_owners (id, singleton, email, password_hash, created_at)"
                " VALUES (:owner, 1, 'pending-migration@example.com', 'x', :now)",
                "INSERT INTO ln_agents (id, owner_id, name, avatar, color, instructions, paused,"
                " created_at) VALUES (:agent, :owner, 'Gold', '', '', '', false, :now)",
                "INSERT INTO ln_threads (id, owner_id, agent_id, title, context_summary,"
                " summary_seq, next_seq, created_at) VALUES (:thread, :owner, :agent, 'Gold',"
                " '', 0, 1, :now)",
            ]
            for statement in statements:
                await connection.execute(text(statement), {**ids, "now": now})
            columns = {
                row[0]
                for row in await connection.execute(
                    text(
                        "SELECT column_name FROM information_schema.columns"
                        " WHERE table_name = 'ln_trading_opportunities'"
                    )
                )
            }
            assert {"account_id", "symbol", "timeframe", "setup_key"} <= columns, columns
            await connection.execute(
                text(
                    "INSERT INTO ln_trading_opportunities (id, owner_id, agent_id, thread_id,"
                    " account_id, symbol, timeframe, setup_key, status, payload, state, version,"
                    " expires_at, created_at, updated_at) VALUES (:thesis, :owner, :agent,"
                    " :thread, :account, 'XAUUSD', '1h', 'fixture', 'acted_on', '{}',"
                    " CAST(:state AS json), 1, :expires, :now, :now)"
                ),
                {
                    **ids,
                    "now": now,
                    "expires": now + timedelta(hours=1),
                    "state": json.dumps(
                        {
                            "pending_entry_operation_id": entry,
                            "pending_management_operation_id": management,
                            "reason_code": "thesis_entry_confirmed",
                        }
                    ),
                },
            )
            for operation, action in ((entry, "buy"), (management, "close_position")):
                await connection.execute(
                    text(
                        "INSERT INTO ln_trading_journal (operation_id, owner_id, account_id,"
                        " request_hash, request, status, result, updated_at) VALUES (:op,"
                        " :owner, :account, 'h', CAST(:request AS json), 'ambiguous', '{}', :now)"
                    ),
                    {
                        **ids,
                        "op": operation,
                        "now": now,
                        "request": json.dumps({"action": action, "symbol": "XAUUSD"}),
                    },
                )
        await engine.dispose()

        async def state() -> dict[str, Any]:
            async with engine.connect() as connection:
                value = await connection.scalar(
                    text("SELECT state FROM ln_trading_opportunities WHERE id = :t"),
                    {"t": ids["thesis"]},
                )
            await engine.dispose()
            return as_dict(value)

        await asyncio.to_thread(alembic, "upgrade", "heads")
        upgraded = await state()
        assert upgraded["pending_operation_ids"] == [entry, management], upgraded
        assert not {"pending_entry_operation_id", "pending_management_operation_id"} & set(upgraded)
        assert upgraded["reason_code"] == "thesis_entry_confirmed"
        print("PASS the two pending keys become one list; the rest of the state is kept")
        await asyncio.to_thread(alembic, "downgrade", BEFORE)
        downgraded = await state()
        assert downgraded["pending_entry_operation_id"] == entry, downgraded
        assert downgraded["pending_management_operation_id"] == management, downgraded
        assert "pending_operation_ids" not in downgraded
        await asyncio.to_thread(alembic, "upgrade", "heads")
        assert (await state())["pending_operation_ids"] == [entry, management]
        async with engine.begin() as connection:
            await connection.execute(
                text("DELETE FROM ln_trading_journal WHERE operation_id IN (:a, :b)"),
                {"a": entry, "b": management},
            )
            await connection.execute(text("DELETE FROM ln_owners WHERE id = :owner"), ids)
        print("PASS the downgrade splits the list by journal action; the upgrade repeats")
    finally:
        await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
