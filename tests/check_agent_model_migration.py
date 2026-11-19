"""0131 removes the model modes, the allowed list and the model cards, on disposable PostgreSQL.

At head, make an owner, two agents and a conversation; step down below 0131 and seed what
the old code stored: a Fixed record whose ``previous`` is ``{mode, preference}``, a record
an agent switched itself (``chosen_by`` ``agent``, no owner message on its event), one an
agent applied on the owner's message, the owner's allowed list, and model cards (a pending
request, a pending Undo and a confirmed one) next to an unrelated pending card. Upgrade:
the records read with today's contract (no mode, ``previous`` a preference, the honest
``chosen_by``), the allowed list is gone, pending model cards were settled ``superseded``
and every model card moved out of ``ln_owner_actions``, the unrelated card untouched.
The downgrade puts back exactly what was there, and the upgrade runs again cleanly.
"""

import asyncio
import importlib.util
import json
import subprocess
import sys
from datetime import UTC, datetime, timedelta
from hashlib import sha256
from pathlib import Path
from typing import Any
from uuid import uuid4

from check_streaming import Fixture, test_settings
from lonora_contracts.model_routing import AgentModelPreference, AgentModelRecord
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection, create_async_engine

ROOT = Path(__file__).resolve().parents[1]
ALEMBIC = [sys.executable, "-m", "alembic", "-c", "packages/db/alembic.ini"]
PATH = ROOT / "packages/db/migrations/versions/0131_agent_model_owner_only.py"
OPUS = {"provider": "anthropic", "model": "claude-opus-test"}
SONNET = {"provider": "anthropic", "model": "claude-sonnet-test"}


def migration() -> Any:
    spec = importlib.util.spec_from_file_location("agent_model_migration", PATH)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def alembic(*arguments: str) -> None:
    subprocess.run([*ALEMBIC, *arguments], check=True, capture_output=True, text=True, cwd=ROOT)


def model_key(owner_id: str, agent_id: str) -> str:
    """Frozen copy of lonora_db.agent_models.agent_model_key."""
    return "agent-model:" + sha256((owner_id + ":" + agent_id).encode()).hexdigest()


def as_dict(value: Any) -> dict[str, Any]:
    return json.loads(value) if isinstance(value, str) else value


async def setting(connection: AsyncConnection, key: str) -> dict[str, Any] | None:
    value = await connection.scalar(
        text("SELECT payload FROM ln_settings WHERE key = :k"), {"k": key}
    )
    return None if value is None else as_dict(value)


async def seed(connection: AsyncConnection, owner: str, ids: dict[str, str]) -> dict[str, Any]:
    now = datetime.now(UTC)
    records: dict[str, dict[str, Any]] = {
        # Fixed by the owner, changed once before: previous is the old {mode, preference}.
        "fixed": {
            "owner_id": owner,
            "agent_id": ids["fixed"],
            "revision": 2,
            "mode": "fixed",
            "preference": {"primary": OPUS, "fallbacks": []},
            "chosen_by": "owner",
            "chosen_by_agent_id": None,
            "previous": {"mode": "automatic", "preference": {"primary": None, "fallbacks": []}},
            "changed_at": now.isoformat(),
        },
        # An Automatic agent switched itself: nobody's choice under today's rule.
        "self": {
            "owner_id": owner,
            "agent_id": ids["self"],
            "revision": 1,
            "mode": "automatic",
            "preference": {"primary": SONNET, "fallbacks": []},
            "chosen_by": "agent",
            "chosen_by_agent_id": ids["self"],
            "previous": {"mode": "automatic", "preference": {"primary": None, "fallbacks": []}},
            "changed_at": now.isoformat(),
        },
        # Applied by an agent on the owner's message: the owner's choice.
        "named": {
            "owner_id": owner,
            "agent_id": ids["named"],
            "revision": 1,
            "mode": "fixed",
            "preference": {"primary": OPUS, "fallbacks": []},
            "chosen_by": "agent",
            "chosen_by_agent_id": ids["named"],
            "previous": None,
            "changed_at": now.isoformat(),
        },
    }
    for name, record in records.items():
        await connection.execute(
            text("INSERT INTO ln_settings (key, payload, updated_at) VALUES (:k, :p, :now)"),
            {"k": model_key(owner, ids[name]), "p": json.dumps(record), "now": now},
        )
    for name, message in (("self", None), ("named", str(uuid4()))):
        await connection.execute(
            text(
                "INSERT INTO ln_events (owner_id, agent_id, kind, payload, created_at)"
                " VALUES (:owner, :agent, 'agent.model.updated', :payload, :now)"
            ),
            {
                "owner": owner,
                "agent": ids[name],
                "payload": json.dumps(
                    {"agent_id": ids[name], "revision": 1, "source_message_id": message}
                ),
                "now": now,
            },
        )
    allowed = {"added": [SONNET]}
    await connection.execute(
        text(
            "INSERT INTO ln_settings (key, payload, updated_at) VALUES ('model_allowed', :p, :now)"
        ),
        {"p": json.dumps(allowed), "now": now},
    )
    cards = {
        "request": ("agent_model", "pending"),
        "undo": ("agent_model_changed", "pending"),
        "confirmed": ("agent_model", "confirmed"),
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
                "agent": ids["self"],
                "thread": ids["thread"],
                "kind": kind,
                "subject": "agent-model:" + ids["self"] if kind != "resume_trading" else "trading",
                "payload": json.dumps({"agent_id": ids["self"], "mode": "fixed"}),
                "hash": uuid4().hex,
                "status": status,
                "expires": now + timedelta(hours=1),
                "now": now,
            },
        )
    return {"records": records, "allowed": allowed}


async def cards(connection: AsyncConnection, table: str, ids: dict[str, str]) -> dict[str, Any]:
    names = ("request", "undo", "confirmed", "other")
    rows = await connection.execute(
        text(f"SELECT id, kind, status, status_reason FROM {table} WHERE id IN (:a, :b, :c, :d)"),
        dict(zip("abcd", (ids["card_" + name] for name in names), strict=True)),
    )
    return {row.id: (row.kind, row.status, row.status_reason) for row in rows}


async def main() -> None:
    module = migration()
    assert module.revision == "0131_agent_model_owner_only"
    before = module.down_revision
    fixture = await Fixture().open()
    try:
        ids = {
            name: (await fixture.agent("Migration " + name))["id"]
            for name in ("fixed", "self", "named")
        }
        ids["thread"] = (await fixture.conversation({"id": ids["self"]}))["id"]
        owner = fixture.owner
    finally:
        await fixture.close(cleanup=False)
    engine = create_async_engine(test_settings().database_url)
    try:
        await asyncio.to_thread(alembic, "downgrade", before)
        async with engine.begin() as connection:
            seeded = await seed(connection, owner, ids)
        await engine.dispose()

        await asyncio.to_thread(alembic, "upgrade", module.revision)
        async with engine.connect() as connection:
            read = {
                name: AgentModelRecord.model_validate(
                    await setting(connection, model_key(owner, ids[name]))
                )
                for name in ("fixed", "self", "named")
            }
            stored = await setting(connection, model_key(owner, ids["fixed"]))
            assert stored is not None and "mode" not in stored
            assert read["fixed"].previous == AgentModelPreference()
            assert read["fixed"].preference.primary is not None
            assert read["fixed"].chosen_by == "owner"
            # The model stays; only who chose it reads honestly.
            assert read["self"].preference.primary is not None
            assert read["self"].chosen_by is None and read["self"].chosen_by_agent_id is None
            assert read["named"].chosen_by == "owner"
            assert read["named"].chosen_by_agent_id == ids["named"]
            assert await setting(connection, "model_allowed") is None
            live = await cards(connection, "ln_owner_actions", ids)
            assert live == {ids["card_other"]: ("resume_trading", "pending", None)}, live
            retired = await cards(connection, module.RETIRED, ids)
            assert retired == {
                ids["card_request"]: ("agent_model", "superseded", "model_cards_removed"),
                ids["card_undo"]: ("agent_model_changed", "superseded", "model_cards_removed"),
                ids["card_confirmed"]: ("agent_model", "confirmed", None),
            }, retired
        await engine.dispose()
        print("PASS the upgrade strips the mode, drops the allowed list and settles model cards")

        await asyncio.to_thread(alembic, "downgrade", before)
        async with engine.connect() as connection:
            for name, record in seeded["records"].items():
                assert await setting(connection, model_key(owner, ids[name])) == record, name
            assert await setting(connection, "model_allowed") == seeded["allowed"]
            back = await cards(connection, "ln_owner_actions", ids)
            assert back[ids["card_request"]] == ("agent_model", "superseded", "model_cards_removed")
            assert back[ids["card_confirmed"]] == ("agent_model", "confirmed", None)
            assert len(back) == 4
        await engine.dispose()
        await asyncio.to_thread(alembic, "upgrade", module.revision)
        async with engine.connect() as connection:
            assert len(await cards(connection, "ln_owner_actions", ids)) == 1
        print("PASS the downgrade puts back exactly what was there; the upgrade runs again")
        # Later migrations (for example 0150, which settles the Stop card seeded above as
        # the other kind) are theirs to check; the chain still runs to head from here.
        await asyncio.to_thread(alembic, "upgrade", "head")
    finally:
        await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
