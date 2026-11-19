"""0121 removes ``activation.intents`` from every stored skill manifest, on PostgreSQL.

At head, make an owner, an agent and a run. Step below 0121 and store what earlier code
wrote, each manifest carrying ``intents``: an owner skill, a package skill whose state
holds a package version, two saved skill versions, and a run whose ``skill_snapshot``
pins a manifest. Upgrade: every copy reads with today's ``SkillManifest`` (``extra="forbid"``)
and the snapshot reader, nothing else in those rows changed. The downgrade leaves the
rows readable by the earlier contract (a missing key is []), and the upgrade runs again.
"""

import asyncio
import importlib.util
import json
import subprocess
import sys
from pathlib import Path
from typing import Any, cast
from uuid import uuid4

from check_streaming import Fixture, test_settings
from lonora_agent.skills.snapshot import read_snapshot
from lonora_contracts.skills import AgentSkill, SkillManifest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection, create_async_engine

ROOT = Path(__file__).resolve().parents[1]
ALEMBIC = [sys.executable, "-m", "alembic", "-c", "packages/db/alembic.ini"]
PATH = ROOT / "packages/db/migrations/versions/0121_skill_intents_removed.py"


def migration() -> Any:
    spec = importlib.util.spec_from_file_location("skill_intents_migration", PATH)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def alembic(*arguments: str) -> None:
    subprocess.run([*ALEMBIC, *arguments], check=True, capture_output=True, text=True, cwd=ROOT)


def as_dict(value: Any) -> Any:
    return json.loads(value) if isinstance(value, str) else value


def manifest(identity: str) -> dict[str, Any]:
    return {
        "id": identity,
        "version": "1.0.0",
        "title": identity,
        "description": "Stored before 0121.",
        "source": "owner",
        "activation": {"mode": "automatic", "intents": ["trade", "market"], "triggers": []},
    }


def skill(identity: str) -> dict[str, Any]:
    return {
        "name": identity,
        "content": "Instructions.",
        "enabled": True,
        "manifest": manifest(identity),
    }


async def seed(connection: AsyncConnection, owner: str, agent: str, run: str) -> dict[str, str]:
    ids = {"owner_skill": str(uuid4()), "package_skill": str(uuid4())}
    package_state = {
        "package": {"kind": "skill-package-v1", "versions": [{"payload": skill("pkg"), "x": 1}]},
        "kept": "unchanged",
    }
    for key, name, state in (
        ("owner_skill", "owned", {}),
        ("package_skill", "pkg", package_state),
    ):
        await connection.execute(
            text(
                "INSERT INTO ln_skills (id, owner_id, agent_id, payload, state, version, "
                "created_at, updated_at) VALUES (:id, :owner, :agent, CAST(:payload AS JSON), "
                "CAST(:state AS JSON), 1, now(), now())"
            ),
            {
                "id": ids[key],
                "owner": owner,
                "agent": agent,
                "payload": json.dumps(skill(name)),
                "state": json.dumps(state),
            },
        )
    for version in (1, 2):
        await connection.execute(
            text(
                "INSERT INTO ln_skill_versions (skill_id, version, owner_id, agent_id, package, "
                "payload, created_at) VALUES (:skill, :version, :owner, :agent, false, "
                "CAST(:payload AS JSON), now())"
            ),
            {
                "skill": ids["owner_skill"],
                "version": version,
                "owner": owner,
                "agent": agent,
                "payload": json.dumps(skill("owned")),
            },
        )
    metadata = as_dict(
        await connection.scalar(
            text("SELECT model_metadata FROM ln_runs WHERE id = :id"), {"id": run}
        )
    )
    metadata["skill_snapshot"] = {
        "version": 1,
        "skills": {"owned": {"manifest": manifest("owned"), "content": "Instructions."}},
    }
    metadata["kept"] = "unchanged"
    await connection.execute(
        text("UPDATE ln_runs SET model_metadata = CAST(:m AS JSON) WHERE id = :id"),
        {"m": json.dumps(metadata), "id": run},
    )
    return ids


async def verify(connection: AsyncConnection, ids: dict[str, str], run: str) -> None:
    for key in ("owner_skill", "package_skill"):
        row = (
            await connection.execute(
                text("SELECT payload, state FROM ln_skills WHERE id = :id"), {"id": ids[key]}
            )
        ).one()
        payload, state = as_dict(row[0]), as_dict(row[1])
        AgentSkill.model_validate(payload)
        assert "intents" not in payload["manifest"]["activation"]
        assert payload["manifest"]["activation"]["mode"] == "automatic"
        package: dict[str, Any] = state.get("package") or {}
        for entry in cast(list[dict[str, Any]], package.get("versions", [])):
            AgentSkill.model_validate(entry["payload"])
            assert entry["x"] == 1
        if key == "package_skill":
            assert state["kept"] == "unchanged"
    versions = (
        await connection.execute(
            text("SELECT payload FROM ln_skill_versions WHERE skill_id = :id"),
            {"id": ids["owner_skill"]},
        )
    ).all()
    assert len(versions) == 2
    for (payload,) in versions:
        SkillManifest.model_validate(as_dict(payload)["manifest"])
    metadata = as_dict(
        await connection.scalar(
            text("SELECT model_metadata FROM ln_runs WHERE id = :id"), {"id": run}
        )
    )
    assert read_snapshot(metadata["skill_snapshot"])["owned"].manifest.id == "owned"
    assert metadata["kept"] == "unchanged"


async def main() -> None:
    module = migration()
    assert module.revision == "0121_skill_intents_removed"
    before = module.down_revision
    fixture = await Fixture().open()
    try:
        agent = await fixture.agent("Intents migration")
        thread = await fixture.conversation(agent)
        run = (await fixture.run(agent, thread))["id"]
        owner = fixture.owner
    finally:
        await fixture.close(cleanup=False)
    engine = create_async_engine(test_settings().database_url)
    try:
        await asyncio.to_thread(alembic, "downgrade", before)
        async with engine.begin() as connection:
            ids = await seed(connection, owner, agent["id"], run)
        await engine.dispose()
        await asyncio.to_thread(alembic, "upgrade", module.revision)
        async with engine.connect() as connection:
            await verify(connection, ids, run)
        await engine.dispose()
        print("PASS every stored manifest reads with today's contract; nothing else changed")
        await asyncio.to_thread(alembic, "downgrade", before)
        await asyncio.to_thread(alembic, "upgrade", "head")
        async with engine.connect() as connection:
            await verify(connection, ids, run)
        print("PASS the downgrade keeps the rows readable and the upgrade runs again")
    finally:
        await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
