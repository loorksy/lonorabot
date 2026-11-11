"""Lonora sees everything: supervision grants on a fresh migrated PostgreSQL database.

1. Migration 0041 gives the Personal Agent a default grant over every other agent;
   running its seed again adds nothing; a downgrade drops both tables and a re-upgrade
   seeds again. A Personal Agent created after other agents supervises each of them,
   and every agent created later is supervised from its creation.
2. The owner asks Lonora what the gold agent did and why it skipped the London entry.
   A real Run with a scripted model answers from the gold agent's records through
   agent_inspect and session_search, offered natively; nothing of the gold agent was
   in Lonora's context before it asked. After the owner revokes the grant, the same
   question is refused at once.

No live broker, model provider or real order is involved.
"""

import asyncio
import importlib.util
import json
import subprocess
import sys
from pathlib import Path
from typing import Any, cast
from unittest.mock import patch
from uuid import uuid4

from check_streaming import Fixture
from lonora_adapter_kit.types import ModelMessage, ModelReply, ToolCall, ToolDefinition
from lonora_agent.executor import execute_run
from lonora_contracts.model_routing import ModelSelection
from lonora_db.events import emit
from lonora_db.personal_agent import ensure_personal_agent
from lonora_db.schema import (
    AgentRow,
    MemoryRow,
    MessageRow,
    RunRow,
    SupervisionGrantRow,
    ThreadRow,
)
from lonora_db.supervision import supervises
from lonora_db.trading_decisions import DECISION_KIND
from lonora_tools.loader import load_tools
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import create_async_engine

ROOT = Path(__file__).resolve().parents[1]
MIGRATION = ROOT / "packages/db/migrations/versions/0041_supervision_grants.py"
PREVIOUS = "0040_retire_super_bot_requests"
SENTINEL = "goldsentinel-" + uuid4().hex[:8]


def migration() -> Any:
    spec = importlib.util.spec_from_file_location("supervision_migration", MIGRATION)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


async def alembic(action: str, revision: str) -> None:
    await asyncio.to_thread(
        subprocess.run,
        [sys.executable, "-m", "alembic", "-c", "packages/db/alembic.ini", action, revision],
        check=True,
        cwd=ROOT,
        stdout=subprocess.DEVNULL,
    )


async def defaults(fixture: Fixture, personal: str) -> set[str]:
    async with fixture.runtime.db.sessions() as session:
        rows = await session.scalars(
            select(SupervisionGrantRow).where(
                SupervisionGrantRow.supervisor_agent_id == personal,
                SupervisionGrantRow.revoked_at.is_(None),
            )
        )
        found = list(rows)
    assert all(row.created_via == "default" for row in found), found
    return {row.supervised_agent_id for row in found}


async def grants_by_default(fixture: Fixture, url: str) -> tuple[str, dict[str, Any]]:
    gold = await fixture.agent("Gold")
    silver = await fixture.agent("Silver")
    async with fixture.runtime.db.sessions() as session, session.begin():
        personal = await ensure_personal_agent(session, fixture.owner)
        personal_id = personal.id
    async with fixture.runtime.db.sessions() as session:
        everyone = set(
            await session.scalars(
                select(AgentRow.id).where(
                    AgentRow.owner_id == fixture.owner, AgentRow.id != personal_id
                )
            )
        )
    # Created after the other agents, Lonora supervises each of them at once.
    assert await defaults(fixture, personal_id) == everyone, everyone
    assert {gold["id"], silver["id"]} <= everyone
    print("PASS a Personal Agent created after other agents supervises every one by default")

    engine = create_async_engine(url)
    try:
        await alembic("downgrade", PREVIOUS)
        async with engine.connect() as connection:
            for table in ("ln_supervision_grants", "ln_supervision_holds"):
                found = await connection.scalar(text(f"SELECT to_regclass('{table}')"))
                assert found is None, table
        await alembic("upgrade", "head")
        assert await defaults(fixture, personal_id) == everyone
        module = migration()
        async with engine.begin() as connection:
            assert await connection.run_sync(module.seed_default_grants) == 0
        assert await defaults(fixture, personal_id) == everyone
    finally:
        await engine.dispose()
    print("PASS migration 0041 seeds one default grant per agent, re-runs add none, round trip")

    later = await fixture.agent("Later")
    async with fixture.runtime.db.sessions() as session:
        assert await supervises(session, fixture.owner, personal_id, later["id"])
        assert not await supervises(session, fixture.owner, gold["id"], silver["id"])
    print("PASS an agent created later is supervised by Lonora from its creation, peers are not")
    return personal_id, gold


def scripted(script: list[Any], seen: list[tuple[list[ModelMessage], list[str]]]) -> Any:
    async def complete(_: Any, messages: list[ModelMessage], tools: Any, **kwargs: Any):
        offered = cast(list[ToolDefinition], tools or [])
        seen.append((list(messages), [tool.name for tool in offered]))
        step = script.pop(0)
        if isinstance(step, ToolCall):
            reply = ModelReply(tool_calls=[step], text="")
        else:
            reply = ModelReply(tool_calls=[], text=str(step))
        return reply, ModelSelection(provider="openai", model="scripted-supervision")

    return complete


def result_of(messages: list[ModelMessage], call_id: str) -> dict[str, Any]:
    return json.loads(
        next(
            message.content
            for message in reversed(messages)
            if message.role == "tool" and message.tool_call_id == call_id
        )
    )


async def ask(
    fixture: Fixture, personal: dict[str, Any], words: str, script: list[Any]
) -> list[tuple[list[ModelMessage], list[str]]]:
    thread = await fixture.conversation(personal)
    sent = await fixture.request(
        "POST",
        f"/threads/{thread['id']}/messages",
        {"content": words, "client_nonce": "supervision-" + uuid4().hex},
    )
    context = await fixture.lease(
        {"id": sent["run_ids"][0], "agent_id": personal["id"], "thread_id": thread["id"]}
    )
    seen: list[tuple[list[ModelMessage], list[str]]] = []
    with patch.object(context.router, "complete", scripted(script, seen)):
        await execute_run(context, load_tools(), 120, 8)
    assert not script, script
    async with context.db.sessions() as session:
        run = await session.get(RunRow, context.lease.run_id)
        assert run is not None and run.status == "completed", run and run.status
    return seen


async def lonora_answers_from_the_records(
    fixture: Fixture, personal_id: str, gold: dict[str, Any]
) -> None:
    thread = await fixture.conversation(gold)
    async with fixture.runtime.db.sessions() as session, session.begin():
        row = await session.get(ThreadRow, thread["id"], with_for_update=True)
        assert row is not None
        session.add(
            MessageRow(
                thread_id=row.id,
                seq=row.next_seq,
                role="assistant",
                agent_id=gold["id"],
                content=f"{SENTINEL} London open: spread 4.1 above my 2.5 limit, no entry.",
            )
        )
        row.next_seq += 1
        memory = await session.get(MemoryRow, gold["id"])
        assert memory is not None
        memory.content = f"# MEMORY.md\n- {SENTINEL} skip entries when the spread is wide\n"
        emit(
            session,
            fixture.owner,
            DECISION_KIND,
            thread_id=row.id,
            agent_id=gold["id"],
            payload={
                "decision": {
                    "id": "decision-" + SENTINEL,
                    "symbol": "XAUUSD",
                    "account_id": "acct",
                    "timeframe": "M15",
                    "action": "WAIT",
                    "summary": f"{SENTINEL} London entry skipped: spread too wide",
                    "recorded_at": "2026-11-08T08:05:00+00:00",
                    "run_id": "run-" + SENTINEL,
                }
            },
        )
    personal = {"id": personal_id}
    question = "ماذا فعل وكيل الذهب اليوم، ولماذا لم يدخل في جلسة لندن؟"
    seen = await ask(
        fixture,
        personal,
        question,
        [
            ToolCall(id="look", name="agent_inspect", arguments={"agent_id": gold["id"]}),
            ToolCall(
                id="why",
                name="agent_inspect",
                arguments={"agent_id": gold["id"], "section": "decisions"},
            ),
            ToolCall(id="said", name="session_search", arguments={"query": SENTINEL}),
            "لم يدخل لأن السبريد كان أوسع من حده.",
        ],
    )
    first_messages, offered = seen[0]
    # Read on demand, never injected: nothing of the gold agent's records before asking.
    assert SENTINEL not in "\n".join(message.content for message in first_messages)
    assert {"agent_inspect", "peer_send"} <= set(offered), offered
    last = seen[-1][0]
    overview = result_of(last, "look")
    assert overview["ok"] is True and overview["authority"] == "supervised_read", overview
    decisions = result_of(last, "why")
    assert [item["id"] for item in decisions["decisions"]] == ["decision-" + SENTINEL]
    said = result_of(last, "said")
    assert said["results"] and all(item["untrusted"] for item in said["results"])
    assert said["results"][0]["supervised_agent"]["id"] == gold["id"]
    print("PASS Lonora answers what the gold agent did and why from its records, on demand")

    view = await fixture.request("GET", f"/supervision?agent_id={gold['id']}")
    grant = next(item for item in view["supervised_by"] if item["supervisor"]["id"] == personal_id)
    await fixture.request("POST", f"/supervision/{grant['id']}/revoke")
    seen = await ask(
        fixture,
        personal,
        question,
        [
            ToolCall(id="look", name="agent_inspect", arguments={"agent_id": gold["id"]}),
            ToolCall(id="said", name="session_search", arguments={"query": SENTINEL}),
            "لا أستطيع قراءة عمله الآن.",
        ],
    )
    last = seen[-1][0]
    refused = result_of(last, "look")
    assert refused["ok"] is False and refused["reason"] == "supervision required", refused
    said = result_of(last, "said")
    assert said["results"] == [] and said["decisions"] == [], said
    print("PASS after the owner revokes the grant, Lonora cannot read the gold agent's work")


async def main() -> None:
    fixture = await Fixture().open()
    try:
        url = fixture.settings.database_url
        personal_id, gold = await grants_by_default(fixture, url)
        await lonora_answers_from_the_records(fixture, personal_id, gold)
    finally:
        await fixture.close()


if __name__ == "__main__":
    asyncio.run(main())
