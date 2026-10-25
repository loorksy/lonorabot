"""Actual PostgreSQL delivery plans, late commits and concurrent migration recovery."""

import asyncio
import subprocess
import sys
from datetime import timedelta
from typing import Any, cast
from uuid import uuid4

from check_streaming import Fixture
from lonora_contracts.domain import utcnow
from lonora_db.events import (
    PUBLIC_CURSOR,
    current_event_cursor,
    events_after,
    public_cursor_expression,
)
from lonora_db.schema import EventRow, SettingRow
from sqlalchemy import func, select, text
from sqlalchemy.dialects import postgresql
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.sql import Select

INDEXES = {
    "ln_events_owner_public_cursor",
    "ln_events_unpublished_cursor",
    "ln_events_run_cursor",
    "ln_events_owner_agent_kind_cursor",
}


def index_names(plan: dict[str, Any]) -> set[str]:
    result = {str(plan["Index Name"])} if plan.get("Index Name") else set[str]()
    for child in plan.get("Plans", []):
        result.update(index_names(child))
    return result


async def check_plan(session: AsyncSession, query: Select[Any], expected: str) -> None:
    sql = str(query.compile(dialect=postgresql.dialect(), compile_kwargs={"literal_binds": True}))
    raw: Any = await session.scalar(text("EXPLAIN (ANALYZE, FORMAT JSON) " + sql))
    assert expected in index_names(raw[0]["Plan"]), (expected, raw[0]["Plan"])
    print("PASS indexed PostgreSQL query", expected, "execution_ms=", raw[0]["Execution Time"])


async def migrate(revision: str, action: str) -> None:
    await asyncio.to_thread(
        subprocess.run,
        [sys.executable, "-m", "alembic", "-c", "packages/db/alembic.ini", action, revision],
        check=True,
        stdout=subprocess.DEVNULL,
    )


async def main() -> None:
    fixture = await Fixture().open()
    db = fixture.runtime.db
    try:
        agent = await fixture.agent("Indexed event reads")
        agent_id, run_id = str(agent["id"]), str(uuid4())
        # Enough quote history to distinguish an indexed read from a table/PK
        # scan. No planner toggles force index use for these four actual queries.
        async with db.sessions() as session, session.begin():
            await session.execute(
                text(
                    "INSERT INTO ln_events(owner_id,agent_id,run_id,kind,payload,created_at) "
                    "SELECT :owner, CASE WHEN n % 100 = 0 THEN :agent ELSE NULL END, "
                    "CASE WHEN n % 1000 = 0 THEN :run ELSE NULL END, "
                    "CASE WHEN n % 100 = 0 THEN 'tool.completed' ELSE 'market.quote_updated' END, "
                    "json_build_object('_ln_public_cursor',1000000+n,'padding',repeat('x',180)), "
                    "now() FROM generate_series(1,60000) AS n"
                ),
                {"owner": fixture.owner, "agent": agent_id, "run": run_id},
            )
            maximum = await session.scalar(select(func.max(EventRow.cursor)))
            counter = await session.get(SettingRow, "event_publication")
            if counter is None:
                counter = SettingRow(key="event_publication", payload={})
                session.add(counter)
            counter.payload = {"last": 1060000, "primary_max": maximum, "scan_at": 0}
            await session.execute(text("ANALYZE ln_events"))
        public = public_cursor_expression()
        async with db.sessions() as session:
            await check_plan(
                session,
                select(EventRow)
                .where(EventRow.owner_id == fixture.owner, public > 1059900)
                .order_by(public)
                .limit(200),
                "ln_events_owner_public_cursor",
            )
            await check_plan(
                session,
                select(EventRow)
                .where(public.is_(None))
                .order_by(EventRow.cursor)
                .limit(1000)
                .with_for_update(skip_locked=True),
                "ln_events_unpublished_cursor",
            )
            await check_plan(
                session,
                select(EventRow)
                .where(EventRow.run_id == run_id)
                .order_by(EventRow.cursor.desc())
                .limit(20),
                "ln_events_run_cursor",
            )
            await check_plan(
                session,
                select(EventRow)
                .where(
                    EventRow.owner_id == fixture.owner,
                    EventRow.agent_id == agent_id,
                    EventRow.kind == "tool.completed",
                    EventRow.created_at >= utcnow() - timedelta(days=1),
                )
                .order_by(EventRow.cursor.desc())
                .limit(40),
                "ln_events_owner_agent_kind_cursor",
            )
        # A generic prepared plan still sees the trusted JSON key literally;
        # only owner/cursor vary. It must not lose its expression index after
        # PostgreSQL switches from custom to generic plans.
        async with db.sessions() as session:
            await session.execute(text("SET LOCAL plan_cache_mode=force_generic_plan"))
            await session.execute(
                text(
                    "PREPARE ln_event_replay(varchar,integer) AS SELECT cursor FROM ln_events "
                    "WHERE owner_id=$1 AND CAST(payload->>'_ln_public_cursor' AS INTEGER)>$2 "
                    "ORDER BY CAST(payload->>'_ln_public_cursor' AS INTEGER) LIMIT 200"
                )
            )
            owner_literal = str(
                text(":owner")
                .bindparams(owner=fixture.owner)
                .compile(dialect=postgresql.dialect(), compile_kwargs={"literal_binds": True})
            )
            raw: Any = await session.scalar(
                text("EXPLAIN (FORMAT JSON) EXECUTE ln_event_replay(" + owner_literal + ",1059900)")
            )
            assert "ln_events_owner_public_cursor" in index_names(raw[0]["Plan"])
            await session.execute(text("DEALLOCATE ln_event_replay"))
        print("PASS generic prepared replay plan retains the public cursor index")
        async with db.sessions() as session:
            baseline = await current_event_cursor(session, fixture.owner)
        async with db.sessions() as delayed, db.sessions() as immediate:
            late = EventRow(owner_id=fixture.owner, kind="test.late", payload={})
            early = EventRow(owner_id=fixture.owner, kind="test.early", payload={})
            delayed.add(late)
            await delayed.flush()
            immediate.add(early)
            await immediate.commit()
            async with db.sessions() as session:
                first = await events_after(session, fixture.owner, baseline)
                assert [event.kind for event in first] == ["test.early"]
                first_cursor = int(first[0].payload[PUBLIC_CURSOR])
            await delayed.commit()
            async with db.sessions() as session:
                after = await events_after(session, fixture.owner, first_cursor)
                assert [event.kind for event in after] == ["test.late"]
                assert int(after[0].payload[PUBLIC_CURSOR]) > first_cursor
                assert late.cursor < early.cursor
        print("PASS indexed delivery retains late-commit publication order without losing events")
        async with db.sessions() as session:
            count = await session.scalar(select(func.count()).select_from(EventRow))
        await db.close()
        await migrate("0030_full_account_management", "downgrade")
        async with db.engine.connect() as connection:
            remaining = set(
                (
                    await connection.execute(
                        text("SELECT indexname FROM pg_indexes WHERE tablename='ln_events'")
                    )
                )
                .scalars()
                .all()
            )
            assert not INDEXES.intersection(remaining)
            assert await connection.scalar(select(func.count()).select_from(EventRow)) == count
        # A failed concurrent build leaves an INVALID name in PostgreSQL. The
        # migration must repair it instead of allowing IF NOT EXISTS to skip it.
        async with db.engine.connect() as connection:
            connection = await connection.execution_options(isolation_level="AUTOCOMMIT")
            try:
                await connection.execute(
                    text(
                        "CREATE UNIQUE INDEX CONCURRENTLY ln_events_run_cursor ON ln_events(owner_id)"
                    )
                )
            except IntegrityError:
                pass
            else:
                raise AssertionError(
                    "duplicate-owner fixture did not leave an invalid concurrent index"
                )
            assert (
                await connection.scalar(
                    text(
                        "SELECT indisvalid FROM pg_index WHERE indexrelid='ln_events_run_cursor'::regclass"
                    )
                )
                is False
            )
        await db.close()
        await migrate("head", "upgrade")
        async with db.engine.connect() as connection:
            actual = cast(
                list[tuple[str, bool]],
                (
                    await connection.execute(
                        text(
                            "SELECT c.relname,i.indisvalid AND i.indisready FROM pg_index i "
                            "JOIN pg_class c ON c.oid=i.indexrelid WHERE c.relname IN "
                            "('ln_events_owner_public_cursor','ln_events_unpublished_cursor',"
                            "'ln_events_run_cursor','ln_events_owner_agent_kind_cursor')"
                        )
                    )
                ).all(),
            )
            assert {name for name, valid in actual if valid} == INDEXES
            assert await connection.scalar(select(func.count()).select_from(EventRow)) == count
        print("PASS concurrent migration roundtrip and invalid-index retry preserve all event rows")
    finally:
        await fixture.close()


if __name__ == "__main__":
    asyncio.run(main())
