"""Q57 removes Shadow trading: a former paper agent never wakes up with live authority.

On a disposable PostgreSQL already at head: step down below 0053, seed Shadow-era rows
(a Shadow agent with an active and a pending grant, its management Task, an "On its
own"-capable stored level, Shadow goals, virtual journal entries, a virtual position and
a Shadow approval card) next to an ordinary live agent, then upgrade and check that
the Shadow agent ends with no active grant and the "No trading" level, Shadow work is
settled, and nothing of the live agent changed. The downgrade is structural (columns back
at 'live', an empty ln_shadow_trades) and the upgrade runs again cleanly.
"""

import asyncio
import json
import subprocess
import sys
from datetime import UTC, datetime, timedelta
from hashlib import sha256
from typing import Any
from uuid import NAMESPACE_URL, uuid4, uuid5

from check_streaming import test_settings
from sqlalchemy import inspect, text
from sqlalchemy.ext.asyncio import AsyncConnection, create_async_engine

ALEMBIC = [sys.executable, "-m", "alembic", "-c", "packages/db/alembic.ini"]
REVISION = "0053_remove_shadow_trading"
BEFORE = REVISION + "-1"


def alembic(*arguments: str) -> None:
    subprocess.run([*ALEMBIC, *arguments], check=True, capture_output=True, text=True)


def permission_key(owner_id: str, agent_id: str) -> str:
    return "agent-permission:" + sha256((owner_id + ":" + agent_id).encode()).hexdigest()


def as_dict(value: Any) -> dict[str, Any]:
    return json.loads(value) if isinstance(value, str) else value


async def columns(connection: AsyncConnection, table: str) -> set[str]:
    return {
        column["name"]
        for column in await connection.run_sync(lambda conn: inspect(conn).get_columns(table))
    }


async def tables(connection: AsyncConnection) -> set[str]:
    return set(await connection.run_sync(lambda conn: inspect(conn).get_table_names()))


async def seed(connection: AsyncConnection) -> dict[str, str]:
    now = datetime.now(UTC)
    owner = await connection.scalar(text("SELECT id FROM ln_owners LIMIT 1"))
    created = owner is None
    if owner is None:
        owner = str(uuid4())
        await connection.execute(
            text(
                "INSERT INTO ln_owners (id, singleton, email, password_hash, created_at) "
                "VALUES (:id, 1, 'shadow-removal@example.com', 'x', :now)"
            ),
            {"id": owner, "now": now},
        )
    ids = {name: str(uuid4()) for name in ("shadow", "unset", "live", "thread_task")}
    ids["owner"] = owner
    ids["created_owner"] = "yes" if created else ""
    for name, mode in (("shadow", "shadow"), ("unset", "shadow"), ("live", "live")):
        await connection.execute(
            text(
                "INSERT INTO ln_agents (id, owner_id, name, avatar, color, instructions, paused,"
                " created_at, role, execution_mode) VALUES (:id, :owner, :name, '', '', '',"
                " false, :now, 'legacy', :mode)"
            ),
            {"id": ids[name], "owner": owner, "name": name, "now": now, "mode": mode},
        )
    for agent, level, revision in (("shadow", "supervised", 3), ("live", "supervised", 2)):
        record = {
            "owner_id": owner,
            "agent_id": ids[agent],
            "revision": revision,
            "fallback_level": level,
            "customization": None,
        }
        await connection.execute(
            text("INSERT INTO ln_settings (key, payload, updated_at) VALUES (:k, :p, :now)"),
            {"k": permission_key(owner, ids[agent]), "p": json.dumps(record), "now": now},
        )
    grants = {
        "shadow_active": ("shadow", "active", "acct-1"),
        "shadow_pending": ("shadow", "pending", "acct-2"),
        "live_active": ("live", "active", "acct-1"),
    }
    for name, (agent, status, account) in grants.items():
        ids[name] = str(uuid4())
        await connection.execute(
            text(
                "INSERT INTO ln_account_authorities (id, owner_id, agent_id, account_id, status,"
                " envelope, envelope_hash, activation_expires_at, created_at, updated_at)"
                " VALUES (:id, :owner, :agent, :account, :status, '{}', 'h', :expires, :now, :now)"
            ),
            {
                "id": ids[name],
                "owner": owner,
                "agent": ids[agent],
                "account": account,
                "status": status,
                "expires": now + timedelta(hours=1),
                "now": now,
            },
        )
    for grant in ("shadow_active", "live_active"):
        task_id = str(uuid5(NAMESPACE_URL, ids[grant] + ":account-management-task"))
        ids[grant + "_task"] = task_id
        agent = ids["shadow" if grant.startswith("shadow") else "live"]
        state = {
            "task": {
                "schema_version": 1,
                "origin_thread_id": ids["thread_task"],
                "completion_mode": "continuous",
                "status": "running",
                "phase": "running",
                "control_requested": None,
            }
        }
        await connection.execute(
            text(
                "INSERT INTO ln_tickets (id, owner_id, agent_id, payload, state, version,"
                " created_at, updated_at) VALUES (:id, :owner, :agent, :payload, :state, 1,"
                " :now, :now)"
            ),
            {
                "id": task_id,
                "owner": owner,
                "agent": agent,
                "payload": json.dumps({"status": "working"}),
                "state": json.dumps(state),
                "now": now,
            },
        )
    goals = {
        "goal_shadow_active": ("shadow", {"status": "active", "execution_mode": "shadow"}),
        "goal_shadow_paused": ("live", {"status": "paused", "execution_mode": "shadow"}),
        "goal_shadow_done": ("live", {"status": "completed", "execution_mode": "shadow"}),
        "goal_live_active": ("live", {"status": "active", "execution_mode": "live"}),
        "goal_legacy_live": ("shadow", {"status": "paused", "code": "execution_mode_changed"}),
    }
    for name, (agent, state) in goals.items():
        ids[name] = str(uuid4())
        await connection.execute(
            text(
                "INSERT INTO ln_trading_goals (id, owner_id, agent_id, payload, state, version,"
                " created_at, updated_at) VALUES (:id, :owner, :agent, '{}', :state, 1, :now, :now)"
            ),
            {
                "id": ids[name],
                "owner": owner,
                "agent": ids[agent],
                "state": json.dumps(state),
                "now": now,
            },
        )
    for name, mode in (("journal_shadow", "shadow"), ("journal_live", "live")):
        ids[name] = "op-" + uuid4().hex
        await connection.execute(
            text(
                "INSERT INTO ln_trading_journal (operation_id, owner_id, account_id, request_hash,"
                " request, status, result, updated_at, execution_mode) VALUES (:id, :owner,"
                " 'acct-1', 'h', '{}', 'confirmed', '{}', :now, :mode)"
            ),
            {"id": ids[name], "owner": owner, "now": now, "mode": mode},
        )
    await connection.execute(
        text(
            "INSERT INTO ln_shadow_trades (id, owner_id, agent_id, payload, state, version,"
            " created_at, updated_at, account_id, symbol, status) VALUES (:id, :owner, :agent,"
            " '{}', '{}', 1, :now, :now, 'acct-1', 'XAUUSD', 'open')"
        ),
        {"id": str(uuid4()), "owner": owner, "agent": ids["shadow"], "now": now},
    )
    for name, mode in (("approval_shadow", "shadow"), ("approval_live", "live")):
        ids[name] = str(uuid4())
        await connection.execute(
            text(
                "INSERT INTO ln_trade_approvals (id, owner_id, agent_id, call_id, requests, status,"
                " results, created_at, updated_at, broker_snapshot) VALUES (:id, :owner, :agent,"
                " 'call', '[]', 'pending', '[]', :now, :now, :snapshot)"
            ),
            {
                "id": ids[name],
                "owner": owner,
                "agent": ids["shadow" if mode == "shadow" else "live"],
                "now": now,
                "snapshot": json.dumps({"execution_mode": {"value": mode}}),
            },
        )
    return ids


async def verify_upgraded(connection: AsyncConnection, ids: dict[str, str]) -> None:
    owner = ids["owner"]
    statuses = dict(
        (
            await connection.execute(
                text("SELECT id, status FROM ln_account_authorities WHERE id IN (:a, :b, :c)"),
                {"a": ids["shadow_active"], "b": ids["shadow_pending"], "c": ids["live_active"]},
            )
        ).all()
    )
    assert statuses[ids["shadow_active"]] == "revoked", statuses
    assert statuses[ids["shadow_pending"]] == "revoked", statuses
    assert statuses[ids["live_active"]] == "active", statuses
    active = await connection.scalar(
        text(
            "SELECT count(*) FROM ln_account_authorities WHERE agent_id IN (:a, :b)"
            " AND status IN ('active','pending')"
        ),
        {"a": ids["shadow"], "b": ids["unset"]},
    )
    assert active == 0, active
    print("PASS a former Shadow agent ends with no active or pending grant")

    async def level(agent: str) -> dict[str, Any]:
        value = await connection.scalar(
            text("SELECT payload FROM ln_settings WHERE key = :k"),
            {"k": permission_key(owner, ids[agent])},
        )
        assert value is not None, agent
        return as_dict(value)

    shadow, unset, live = await level("shadow"), await level("unset"), await level("live")
    assert shadow["fallback_level"] == "analysis" and shadow["revision"] == 4, shadow
    assert unset["fallback_level"] == "analysis", unset
    assert live["fallback_level"] == "supervised" and live["revision"] == 2, live
    print("PASS a former Shadow agent's level is No trading; the live agent's level is kept")

    tasks = {
        key: as_dict(state)
        for key, state in (
            await connection.execute(
                text("SELECT id, state FROM ln_tickets WHERE id IN (:a, :b)"),
                {"a": ids["shadow_active_task"], "b": ids["live_active_task"]},
            )
        ).all()
    }
    assert tasks[ids["shadow_active_task"]]["task"]["status"] == "cancelled", tasks
    assert tasks[ids["live_active_task"]]["task"]["status"] == "running", tasks
    print("PASS the revoked grant's management Task is cancelled; the live one keeps running")

    goals = {
        key: as_dict(state)
        for key, state in (
            await connection.execute(
                text("SELECT id, state FROM ln_trading_goals WHERE owner_id = :o"), {"o": owner}
            )
        ).all()
    }
    for name in ("goal_shadow_active", "goal_shadow_paused"):
        state = goals[ids[name]]
        assert state["status"] == "cancelled" and state["code"] == "shadow_trading_removed", state
    assert goals[ids["goal_shadow_done"]]["status"] == "completed"
    assert goals[ids["goal_live_active"]] == {"status": "active", "execution_mode": "live"}
    assert goals[ids["goal_legacy_live"]]["status"] == "paused"
    print("PASS Shadow goals are cancelled (finished ones stay history); live goals are untouched")

    journal = set(
        (
            await connection.execute(
                text("SELECT operation_id FROM ln_trading_journal WHERE owner_id = :o"),
                {"o": owner},
            )
        ).scalars()
    )
    assert ids["journal_live"] in journal and ids["journal_shadow"] not in journal, journal
    approvals = dict(
        (
            await connection.execute(
                text("SELECT id, status FROM ln_trade_approvals WHERE id IN (:a, :b)"),
                {"a": ids["approval_shadow"], "b": ids["approval_live"]},
            )
        ).all()
    )
    assert approvals == {ids["approval_shadow"]: "cancelled", ids["approval_live"]: "pending"}
    assert "execution_mode" not in await columns(connection, "ln_agents")
    assert "execution_mode" not in await columns(connection, "ln_trading_journal")
    assert "ln_shadow_trades" not in await tables(connection)
    print("PASS virtual receipts, the virtual book and both execution_mode columns are gone")


async def main() -> None:
    url = test_settings().database_url
    engine = create_async_engine(url)
    try:
        await asyncio.to_thread(alembic, "downgrade", BEFORE)
        async with engine.begin() as connection:
            ids = await seed(connection)
        await engine.dispose()
        await asyncio.to_thread(alembic, "upgrade", "heads")
        async with engine.connect() as connection:
            await verify_upgraded(connection, ids)
        await engine.dispose()

        await asyncio.to_thread(alembic, "downgrade", BEFORE)
        async with engine.connect() as connection:
            assert "execution_mode" in await columns(connection, "ln_agents")
            assert "execution_mode" in await columns(connection, "ln_trading_journal")
            assert "ln_shadow_trades" in await tables(connection)
            modes = set(
                (
                    await connection.execute(text("SELECT DISTINCT execution_mode FROM ln_agents"))
                ).scalars()
            )
            assert modes <= {"live"}, modes
            assert await connection.scalar(text("SELECT count(*) FROM ln_shadow_trades")) == 0
        await engine.dispose()
        await asyncio.to_thread(alembic, "upgrade", "heads")
        print("PASS the downgrade restores the columns at 'live' and an empty virtual book")
        async with engine.begin() as connection:
            # Leave no fixture identity behind for a later check on the same database.
            for agent in ("shadow", "unset", "live"):
                await connection.execute(
                    text("DELETE FROM ln_settings WHERE key = :k"),
                    {"k": permission_key(ids["owner"], ids[agent])},
                )
            await connection.execute(
                text("DELETE FROM ln_agents WHERE id IN (:a, :b, :c)"),
                {"a": ids["shadow"], "b": ids["unset"], "c": ids["live"]},
            )
            if ids["created_owner"]:
                await connection.execute(
                    text("DELETE FROM ln_owners WHERE id = :o"), {"o": ids["owner"]}
                )
    finally:
        await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
