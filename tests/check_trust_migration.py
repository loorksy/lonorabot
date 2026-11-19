"""0132 trusts sources on the owner's words and retires the trust card, on disposable PostgreSQL.

At head, make an owner, an agent and a conversation, and a source an agent trusted on the
owner's message (``added_via`` ``owner_message``). Step down below 0132: that row reads
``owner_card``, the old schema's nearest value. Seed what the old code stored: trust cards
(a pending one and a confirmed one) next to an unrelated pending card. Upgrade: the row is
``owner_message`` again, the pending trust card was settled ``superseded`` and both moved
out of ``ln_owner_actions``, the unrelated card untouched. The downgrade puts back what was
there (settled cards stay settled), and the upgrade runs again cleanly.
"""

import asyncio
import importlib.util
import json
import subprocess
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any
from uuid import uuid4

from check_streaming import Fixture, test_settings
from lonora_db.trusted_sources import trust_source
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection, create_async_engine

ROOT = Path(__file__).resolve().parents[1]
ALEMBIC = [sys.executable, "-m", "alembic", "-c", "packages/db/alembic.ini"]
PATH = ROOT / "packages/db/migrations/versions/0132_trust_from_owner_words.py"


def migration() -> Any:
    spec = importlib.util.spec_from_file_location("trust_migration", PATH)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def alembic(*arguments: str) -> None:
    subprocess.run([*ALEMBIC, *arguments], check=True, capture_output=True, text=True, cwd=ROOT)


async def added_via(connection: AsyncConnection, source_id: str) -> str:
    return await connection.scalar(
        text("SELECT added_via FROM ln_trusted_sources WHERE id = :id"), {"id": source_id}
    )


async def seed(connection: AsyncConnection, owner: str, ids: dict[str, str]) -> None:
    now = datetime.now(UTC)
    cards = {
        "pending": ("trust_source", "pending"),
        "confirmed": ("trust_source", "confirmed"),
        "other": ("resume_trading", "pending"),
    }
    for name, (kind, status) in cards.items():
        ids["card_" + name] = str(uuid4())
        await connection.execute(
            text(
                "INSERT INTO ln_owner_actions (id, owner_id, agent_id, thread_id, run_id, source,"
                " kind, subject, payload, payload_hash, status, result, expires_at, created_at,"
                " updated_at) VALUES (:id, :owner, :agent, :thread, NULL, 'agent', :kind,"
                " :subject, :payload, :hash, :status, '{}', :expires, :now, :now)"
            ),
            {
                "id": ids["card_" + name],
                "owner": owner,
                "agent": ids["agent"],
                "thread": ids["thread"],
                "kind": kind,
                "subject": "trusted-source:feed_domain:old.example"
                if kind == "trust_source"
                else "trading",
                "payload": json.dumps({"source_kind": "feed_domain", "identifier": "old.example"}),
                "hash": uuid4().hex,
                "status": status,
                "expires": now + timedelta(days=7),
                "now": now,
            },
        )


async def cards(connection: AsyncConnection, table: str, ids: dict[str, str]) -> dict[str, Any]:
    rows = await connection.execute(
        text(f"SELECT id, kind, status, status_reason FROM {table} WHERE id IN (:a, :b, :c)"),
        dict(
            zip("abc", (ids["card_" + n] for n in ("pending", "confirmed", "other")), strict=True)
        ),
    )
    return {row.id: (row.kind, row.status, row.status_reason) for row in rows}


async def main() -> None:
    module = migration()
    assert module.revision == "0132_trust_from_owner_words"
    before = module.down_revision
    assert before == "0110_closed_trades"
    fixture = await Fixture().open()
    try:
        agent = await fixture.agent("Trust migration")
        ids = {"agent": agent["id"], "thread": (await fixture.conversation(agent))["id"]}
        async with fixture.runtime.db.sessions() as session, session.begin():
            row, _ = await trust_source(
                session,
                fixture.owner,
                "feed_domain",
                "named-" + uuid4().hex[:8] + ".example",
                via="owner_message",
                agent_id=agent["id"],
            )
            ids["source"] = row.id
        owner = fixture.owner
    finally:
        await fixture.close(cleanup=False)
    engine = create_async_engine(test_settings().database_url)
    try:
        await asyncio.to_thread(alembic, "downgrade", before)
        async with engine.begin() as connection:
            # The old schema has no owner_message: the nearest value, remembered.
            assert await added_via(connection, ids["source"]) == "owner_card"
            await seed(connection, owner, ids)
        await engine.dispose()
        print("PASS the downgrade reads an owner_message entry as owner_card")

        await asyncio.to_thread(alembic, "upgrade", "head")
        async with engine.connect() as connection:
            assert await added_via(connection, ids["source"]) == "owner_message"
            marker = await connection.scalar(
                text("SELECT count(*) FROM ln_settings WHERE key = :k"), {"k": module.MARKER}
            )
            assert marker == 0
            live = await cards(connection, "ln_owner_actions", ids)
            assert live == {ids["card_other"]: ("resume_trading", "pending", None)}, live
            retired = await cards(connection, module.RETIRED, ids)
            assert retired == {
                ids["card_pending"]: ("trust_source", "superseded", "trust_cards_removed"),
                ids["card_confirmed"]: ("trust_source", "confirmed", None),
            }, retired
        await engine.dispose()
        print("PASS the upgrade restores owner_message and settles and retires trust cards")

        await asyncio.to_thread(alembic, "downgrade", before)
        async with engine.connect() as connection:
            back = await cards(connection, "ln_owner_actions", ids)
            assert back[ids["card_pending"]] == (
                "trust_source",
                "superseded",
                "trust_cards_removed",
            )
            assert back[ids["card_confirmed"]] == ("trust_source", "confirmed", None)
            assert len(back) == 3
            assert await added_via(connection, ids["source"]) == "owner_card"
        await engine.dispose()
        await asyncio.to_thread(alembic, "upgrade", "head")
        async with engine.connect() as connection:
            assert len(await cards(connection, "ln_owner_actions", ids)) == 1
            assert await added_via(connection, ids["source"]) == "owner_message"
        print("PASS the downgrade puts back what was there; the upgrade runs again")
    finally:
        await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
