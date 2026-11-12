"""Owner amendment 1 removes Stop: migration 0150 settles every stored Stop record.

On a disposable PostgreSQL already at head: step down below 0150, seed the Stop-era rows
(the stored trading_control setting, resume_trading cards in both states, an
emergency_stop attention item) next to rows of the same tables that are not Stop, then
upgrade and check that only the Stop rows are gone. The downgrade writes the control back
as running (and never overwrites one already there) and the upgrade runs again cleanly.
"""

import asyncio
import subprocess
import sys
from datetime import UTC, datetime, timedelta
from uuid import uuid4

from check_streaming import test_settings
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection, create_async_engine

ALEMBIC = [sys.executable, "-m", "alembic", "-c", "packages/db/alembic.ini"]
REVISION = "0150_remove_stop"
BEFORE = REVISION + "-1"


def alembic(*arguments: str) -> None:
    subprocess.run([*ALEMBIC, *arguments], check=True, capture_output=True, text=True)


async def seed(connection: AsyncConnection) -> dict[str, str]:
    now = datetime.now(UTC)
    ids = {name: str(uuid4()) for name in ("owner", "agent", "thread")}
    ids["owner"] = await connection.scalar(text("SELECT id FROM ln_owners LIMIT 1")) or ids["owner"]
    await connection.execute(
        text(
            "INSERT INTO ln_owners (id, singleton, email, password_hash, created_at) "
            "VALUES (:id, 1, 'stop-removal@example.com', 'x', :now) ON CONFLICT DO NOTHING"
        ),
        {"id": ids["owner"], "now": now},
    )
    await connection.execute(
        text(
            "INSERT INTO ln_agents (id, owner_id, name, avatar, color, instructions, paused,"
            " created_at) VALUES (:id, :owner, 'stop-removal', '', '', '', false, :now)"
        ),
        {"id": ids["agent"], "owner": ids["owner"], "now": now},
    )
    await connection.execute(
        text(
            "INSERT INTO ln_threads (id, owner_id, title, next_seq, created_at, context_summary,"
            " summary_seq) VALUES (:id, :owner, 'stop-removal', 1, :now, '', 0)"
        ),
        {"id": ids["thread"], "owner": ids["owner"], "now": now},
    )
    await connection.execute(
        text(
            "INSERT INTO ln_settings (key, payload, updated_at) VALUES"
            " ('trading_control', '{\"enabled\": false, \"emergency_stop\": true}', :now),"
            " ('stop_removal_other', '{\"kept\": true}', :now)"
            " ON CONFLICT (key) DO UPDATE SET payload = EXCLUDED.payload"
        ),
        {"now": now},
    )
    for kind, status in (
        ("resume_trading", "pending"),
        ("resume_trading", "confirmed"),
        ("lift_restriction", "pending"),
    ):
        ids[f"{kind}:{status}"] = str(uuid4())
        await connection.execute(
            text(
                "INSERT INTO ln_owner_actions (id, owner_id, agent_id, thread_id, source, kind,"
                " subject, payload, payload_hash, status, result, expires_at, created_at,"
                " updated_at) VALUES (:id, :owner, :agent, :thread, 'agent', :kind, :subject,"
                " '{}', 'h', :status, '{}', :expires, :now, :now)"
            ),
            {
                "id": ids[f"{kind}:{status}"],
                "owner": ids["owner"],
                "agent": ids["agent"],
                "thread": ids["thread"],
                "kind": kind,
                "subject": "trading" if kind == "resume_trading" else "restriction:r1",
                "status": status,
                "expires": now + timedelta(hours=1),
                "now": now,
            },
        )
    for code in ("emergency_stop", "approval_required"):
        ids[code] = str(uuid4())
        await connection.execute(
            text(
                "INSERT INTO ln_attention (id, owner_id, agent_id, thread_id, logical_key,"
                " coalesce_key, importance, code, status, parameters, source_events,"
                " source_count, version, due_at, created_at, updated_at) VALUES (:id, :owner,"
                " :agent, :thread, :id, :id, 'critical', :code, 'ready', '{}', '[]', 1, 1,"
                " :now, :now, :now)"
            ),
            {
                "id": ids[code],
                "owner": ids["owner"],
                "agent": ids["agent"],
                "thread": ids["thread"],
                "code": code,
                "now": now,
            },
        )
    return ids


async def remaining(connection: AsyncConnection, ids: dict[str, str]) -> dict[str, object]:
    return {
        "settings": set(
            await connection.scalars(
                text(
                    "SELECT key FROM ln_settings WHERE key IN ('trading_control', 'stop_removal_other')"
                )
            )
        ),
        "cards": set(
            await connection.scalars(
                text("SELECT kind || ':' || status FROM ln_owner_actions WHERE thread_id = :t"),
                {"t": ids["thread"]},
            )
        ),
        "attention": set(
            await connection.scalars(
                text("SELECT code FROM ln_attention WHERE thread_id = :t"), {"t": ids["thread"]}
            )
        ),
    }


async def main() -> None:
    url = test_settings().database_url
    alembic("upgrade", "head")
    alembic("downgrade", BEFORE)
    engine = create_async_engine(url)
    try:
        async with engine.begin() as connection:
            ids = await seed(connection)
        alembic("upgrade", REVISION)
        async with engine.connect() as connection:
            left = await remaining(connection, ids)
        assert left == {
            "settings": {"stop_removal_other"},
            "cards": {"lift_restriction:pending"},
            "attention": {"approval_required"},
        }, left
        print(
            "PASS the upgrade removes the stored control, resume_trading cards and emergency_stop items, and nothing else"
        )

        alembic("downgrade", BEFORE)
        async with engine.connect() as connection:
            restored = await connection.scalar(
                text("SELECT payload::text FROM ln_settings WHERE key = 'trading_control'")
            )
        assert restored is not None and '"enabled": true' in restored, restored
        assert '"emergency_stop": false' in restored, restored
        async with engine.begin() as connection:
            await connection.execute(
                text(
                    "UPDATE ln_settings SET payload = '{\"enabled\": false}' WHERE key = 'trading_control'"
                )
            )
        alembic("upgrade", REVISION)
        alembic("downgrade", BEFORE)
        async with engine.connect() as connection:
            again = await connection.scalar(
                text("SELECT payload::text FROM ln_settings WHERE key = 'trading_control'")
            )
        assert '"enabled": true' in (again or ""), again
        alembic("upgrade", "head")
        async with engine.connect() as connection:
            final = await remaining(connection, ids)
        assert final["settings"] == {"stop_removal_other"}, final
        print(
            "PASS the downgrade writes the control back as running, and the upgrade runs again cleanly"
        )
        async with engine.begin() as connection:
            await connection.execute(
                text("DELETE FROM ln_settings WHERE key = 'stop_removal_other'")
            )
            await connection.execute(
                text("DELETE FROM ln_owner_actions WHERE thread_id = :t"), {"t": ids["thread"]}
            )
            await connection.execute(
                text("DELETE FROM ln_attention WHERE thread_id = :t"), {"t": ids["thread"]}
            )
    finally:
        await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
