"""Trading goals are removed (mandate 14.2.4, 14.3.14, 14.3.9, 14.3.18.6).

On a disposable PostgreSQL already at head: step down to the revision before 0067, seed
a goal, a goal-armed watch and routine, a plain watch whose payload still stores the
null goal keys every older payload carried, a plain routine, a queued goal wake, a
finished goal wake, an ordinary queued run and a ``goal_changed`` attention item, then
upgrade and check that:

* the goal-armed watch and routine are deleted; the plain watch loses the three goal
  keys and validates against the ``Watch`` contract; the plain routine stays;
* the routine goal columns and the goal tables are gone;
* the queued goal wake is cancelled with ``goal_removed``; the finished one and the
  ordinary run are untouched;
* the ``goal_changed`` item is suppressed as ``internal_update``.

The downgrade restores the empty columns and tables and the upgrade runs again cleanly.
"""

import asyncio
import json
import subprocess
import sys
from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

from check_streaming import test_settings
from lonora_contracts.market_watch import Watch
from sqlalchemy import inspect, text
from sqlalchemy.ext.asyncio import AsyncConnection, create_async_engine

ALEMBIC = [sys.executable, "-m", "alembic", "-c", "packages/db/alembic.ini"]
BEFORE = "0050_genui_state_and_origin"


def alembic(*arguments: str) -> None:
    subprocess.run([*ALEMBIC, *arguments], check=True, capture_output=True, text=True)


def as_dict(value: Any) -> dict[str, Any]:
    return json.loads(value) if isinstance(value, str) else value


async def columns(connection: AsyncConnection, table: str) -> set[str]:
    return {
        column["name"]
        for column in await connection.run_sync(lambda conn: inspect(conn).get_columns(table))
    }


async def tables(connection: AsyncConnection) -> set[str]:
    return set(await connection.run_sync(lambda conn: inspect(conn).get_table_names()))


def watch_payload(**extra: Any) -> dict[str, Any]:
    return {
        "kind": "price",
        "account_id": "acct-1",
        "symbol": "XAUUSD",
        "condition": "above",
        "level": "2400",
        "prompt": "Gold above 2400",
        **extra,
    }


async def seed(connection: AsyncConnection) -> dict[str, str]:
    now = datetime.now(UTC)
    ids = {
        name: str(uuid4())
        for name in (
            "owner",
            "agent",
            "thread",
            "goal",
            "goal_watch",
            "plain_watch",
            "goal_routine",
            "plain_routine",
            "goal_run",
            "goal_run_done",
            "meta_run",
            "plain_run",
            "attention",
        )
    }
    statements: list[tuple[str, dict[str, Any]]] = [
        (
            "INSERT INTO ln_owners (id, singleton, email, password_hash, created_at)"
            " VALUES (:owner, 1, 'goal-removal@example.com', 'x', :now)",
            {},
        ),
        (
            "INSERT INTO ln_agents (id, owner_id, name, avatar, color, instructions, paused,"
            " created_at) VALUES (:agent, :owner, 'Gold', '', '', '', false, :now)",
            {},
        ),
        (
            "INSERT INTO ln_threads (id, owner_id, agent_id, title, context_summary,"
            " summary_seq, next_seq, created_at) VALUES (:thread, :owner, :agent, 'Gold', '',"
            " 0, 1, :now)",
            {},
        ),
        (
            "INSERT INTO ln_trading_goals (id, owner_id, agent_id, thread_id, payload, state,"
            " version, created_at, updated_at) VALUES (:goal, :owner, :agent, :thread, '{}',"
            ' \'{"status": "active"}\', 1, :now, :now)',
            {},
        ),
    ]
    for name, payload in (
        ("goal_watch", watch_payload(goal_id=ids["goal"], step_id="entry", goal_plan_version=1)),
        ("plain_watch", watch_payload(goal_id=None, step_id=None, goal_plan_version=None)),
    ):
        statements.append(
            (
                "INSERT INTO ln_market_watches (id, owner_id, agent_id, thread_id, payload,"
                " state, version, created_at, updated_at) VALUES (:" + name + ", :owner,"
                " :agent, :thread, CAST(:payload AS json), '{}', 1, :now, :now)",
                {"payload": json.dumps(payload)},
            )
        )
    for name, goal in (("goal_routine", "goal"), ("plain_routine", None)):
        statements.append(
            (
                "INSERT INTO ln_routines (id, owner_id, agent_id, thread_id, prompt, timezone,"
                " enabled, next_run_at, interval_seconds, goal_id, step_id) VALUES (:"
                + name
                + ", :owner, :agent, :thread, 'Review', 'UTC', true, :now, 900, :goal_link,"
                " :step_link)",
                {"goal_link": ids[goal] if goal else None, "step_link": "entry" if goal else None},
            )
        )
    for name, trigger, status, metadata in (
        ("goal_run", "goal", "queued", {}),
        ("goal_run_done", "goal", "completed", {}),
        ("meta_run", "watch", "queued", {"goal_id": ids["goal"], "step_id": "entry"}),
        ("plain_run", "watch", "queued", {}),
    ):
        statements.append(
            (
                "INSERT INTO ln_runs (id, thread_id, agent_id, trigger, prompt, status,"
                " input_seq, lease_fence, execution_state, model_metadata, created_at,"
                " updated_at) VALUES (:" + name + ", :thread, :agent, :trigger, 'Wake',"
                " :status, 0, 0, '{}', CAST(:metadata AS json), :now, :now)",
                {"trigger": trigger, "status": status, "metadata": json.dumps(metadata)},
            )
        )
    statements.append(
        (
            "INSERT INTO ln_attention (id, owner_id, agent_id, thread_id, logical_key,"
            " coalesce_key, importance, code, status, parameters, source_events, source_count,"
            " version, due_at, created_at, updated_at) VALUES (:attention, :owner, :agent,"
            " :thread, :attention, 'goal', 'important_change', 'goal_changed', 'ready', '{}',"
            " '[]', 1, 1, :now, :now, :now)",
            {},
        )
    )
    for statement, extra in statements:
        await connection.execute(text(statement), {**ids, "now": now, **extra})
    return ids


async def verify(connection: AsyncConnection, ids: dict[str, str]) -> None:
    watches = {
        identifier: as_dict(payload)
        for identifier, payload in (
            await connection.execute(
                text("SELECT id, payload FROM ln_market_watches WHERE owner_id = :o"),
                {"o": ids["owner"]},
            )
        ).all()
    }
    assert set(watches) == {ids["plain_watch"]}, watches
    plain = watches[ids["plain_watch"]]
    assert not {"goal_id", "step_id", "goal_plan_version"} & set(plain), plain
    Watch.model_validate(plain)
    routines = set(
        (
            await connection.execute(
                text("SELECT id FROM ln_routines WHERE owner_id = :o"), {"o": ids["owner"]}
            )
        ).scalars()
    )
    assert routines == {ids["plain_routine"]}, routines
    assert not {"goal_id", "step_id"} & await columns(connection, "ln_routines")
    assert not {"ln_trading_goals", "ln_goal_decisions"} & await tables(connection)
    print("PASS goal-armed watches and routines are deleted; other watches lose the goal keys")

    runs = {
        identifier: (status, code)
        for identifier, status, code in (
            await connection.execute(
                text("SELECT id, status, error_code FROM ln_runs WHERE thread_id = :t"),
                {"t": ids["thread"]},
            )
        ).all()
    }
    assert runs[ids["goal_run"]] == ("cancelled", "goal_removed"), runs
    assert runs[ids["meta_run"]] == ("cancelled", "goal_removed"), runs
    assert runs[ids["goal_run_done"]] == ("completed", None), runs
    assert runs[ids["plain_run"]] == ("queued", None), runs
    attention = (
        await connection.execute(
            text("SELECT code, status FROM ln_attention WHERE id = :a"), {"a": ids["attention"]}
        )
    ).one()
    assert tuple(attention) == ("internal_update", "suppressed"), attention
    print("PASS open goal wakes end; goal attention items are retired; goal tables are gone")


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
            await verify(connection, ids)
        await engine.dispose()

        await asyncio.to_thread(alembic, "downgrade", BEFORE)
        async with engine.connect() as connection:
            assert {"goal_id", "step_id"} <= await columns(connection, "ln_routines")
            assert {"ln_trading_goals", "ln_goal_decisions"} <= await tables(connection)
        await engine.dispose()
        await asyncio.to_thread(alembic, "upgrade", "heads")
        async with engine.begin() as connection:
            await verify(connection, ids)
            await connection.execute(
                text("DELETE FROM ln_owners WHERE id = :o"), {"o": ids["owner"]}
            )
        print("PASS the downgrade restores empty columns and tables; the upgrade repeats cleanly")
    finally:
        await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
