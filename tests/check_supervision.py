"""Lonora sees everything, by its role: no supervision grant, on a fresh migrated database.

1. No grant table exists. Lonora reaches every team agent, those created before it and
   after it; a team agent reaches no one.
2. A team agent is refused another agent's reads and control.
3. The owner asks Lonora what the gold agent did and why it skipped the London entry.
   A real Run with a scripted model answers from the gold agent's records through
   agent_inspect and session_search, offered natively; nothing of the gold agent was
   in Lonora's context before it asked. No grant row was ever written.
4. Migration 0127 drops ``ln_supervision_grants`` and deletes the cards of the three
   grant kinds; ``supervision_paused`` cards and pause holds stay. Its downgrade brings
   the table back empty.

No live broker, model provider or real order is involved.
"""

import asyncio
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
from lonora_contracts.runs import RunRequest
from lonora_core.user_error import LonoraError
from lonora_db.events import emit
from lonora_db.lead import reaches
from lonora_db.owner_actions import raise_supervision_pause_card
from lonora_db.personal_agent import ensure_personal_agent
from lonora_db.runs import create_run
from lonora_db.schema import (
    AgentRow,
    MemoryRow,
    MessageRow,
    OwnerActionRow,
    RunRow,
    SupervisionHoldRow,
    ThreadRow,
)
from lonora_db.trading_decisions import DECISION_KIND
from lonora_tools.loader import load_tools
from sqlalchemy import insert, select, text
from sqlalchemy.ext.asyncio import create_async_engine

ROOT = Path(__file__).resolve().parents[1]
PREVIOUS = "0126_team_heads_merge"
GRANT_KINDS = ("supervise", "supervision_created", "supervision_stopped")
SENTINEL = "goldsentinel-" + uuid4().hex[:8]


async def alembic(action: str, revision: str) -> None:
    await asyncio.to_thread(
        subprocess.run,
        [sys.executable, "-m", "alembic", "-c", "packages/db/alembic.ini", action, revision],
        check=True,
        cwd=ROOT,
        stdout=subprocess.DEVNULL,
    )


async def table_exists(url: str, table: str) -> bool:
    engine = create_async_engine(url)
    try:
        async with engine.connect() as connection:
            return await connection.scalar(text(f"SELECT to_regclass('{table}')")) is not None
    finally:
        await engine.dispose()


async def call(context: Any, name: str, **arguments: Any) -> dict[str, Any]:
    return await load_tools().execute(
        ToolCall(id="call-" + uuid4().hex, name=name, arguments=arguments), context
    )


async def refused(context: Any, name: str, **arguments: Any) -> str:
    try:
        await call(context, name, **arguments)
    except LonoraError as error:
        return error.code
    raise AssertionError("expected a refusal from " + name)


async def wake(fixture: Fixture, agent: dict[str, Any]) -> Any:
    """A Run no owner message started: a routine wake in the agent's own conversation."""
    thread = await fixture.conversation(agent)
    async with fixture.runtime.db.sessions() as session, session.begin():
        run = await create_run(
            session,
            fixture.owner,
            RunRequest(
                thread_id=thread["id"], agent_id=agent["id"], trigger="routine", prompt="Check"
            ),
        )
        data = {"id": run.id, "agent_id": agent["id"], "thread_id": thread["id"]}
    return await fixture.lease(data)


async def lonora_leads_by_its_role(fixture: Fixture, url: str) -> tuple[str, dict[str, Any]]:
    assert not await table_exists(url, "ln_supervision_grants")
    gold = await fixture.agent("Gold")
    silver = await fixture.agent("Silver")
    async with fixture.runtime.db.sessions() as session, session.begin():
        personal_id = (await ensure_personal_agent(session, fixture.owner)).id
    later = await fixture.agent("Later")
    async with fixture.runtime.db.sessions() as session:
        team = set(
            await session.scalars(
                select(AgentRow.id).where(
                    AgentRow.owner_id == fixture.owner, AgentRow.id != personal_id
                )
            )
        )
        assert {gold["id"], silver["id"], later["id"]} <= team
        for agent_id in team:
            assert await reaches(session, fixture.owner, personal_id, agent_id), agent_id
            assert not await reaches(session, fixture.owner, agent_id, personal_id), agent_id
        assert not await reaches(session, fixture.owner, gold["id"], silver["id"])
        assert not await reaches(session, fixture.owner, later["id"], gold["id"])
    print("PASS no grant table exists; Lonora reaches every team agent, before and after it")
    print("PASS a team agent reaches no other agent, Lonora included")

    silver_context = await wake(fixture, silver)
    gold_thread = await fixture.conversation(gold)
    assert (
        await refused(silver_context, "session_search", thread_id=gold_thread["id"])
        == "thread_not_found"
    )
    for agent_id in (gold["id"], personal_id):
        assert (
            await refused(silver_context, "agent_inspect", agent_id=agent_id)
            == "supervision_required"
        )
        assert (
            await refused(silver_context, "agent_control", agent_id=agent_id, action="pause")
            == "supervision_required"
        )
    for action in ("cancel_run", "set_ask"):
        assert (
            await refused(silver_context, "agent_control", agent_id=gold["id"], action=action)
            == "agent_control_lead_only"
        )
    print("PASS a team agent is refused another agent's reads and control")
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
    assert "supervision_change" not in offered, offered
    last = seen[-1][0]
    overview = result_of(last, "look")
    assert overview["ok"] is True and overview["authority"] == "supervised_read", overview
    decisions = result_of(last, "why")
    assert [item["id"] for item in decisions["decisions"]] == ["decision-" + SENTINEL]
    said = result_of(last, "said")
    assert said["results"] and all(item["untrusted"] for item in said["results"])
    assert said["results"][0]["supervised_agent"]["id"] == gold["id"]
    # Mandate 3.1.6, 3.3.3: the lead's reads are built in, no grant gives or ends them.
    print("PASS Lonora answers what the gold agent did and why from its records, with no grant")


async def migration_drops_grants_and_keeps_pauses(
    fixture: Fixture, url: str, personal_id: str, gold: dict[str, Any]
) -> None:
    context = await wake(fixture, {"id": personal_id})
    paused = await call(context, "agent_control", agent_id=gold["id"], action="pause")
    assert paused["changed"] is True, paused
    async with fixture.runtime.db.sessions() as session, session.begin():
        hold = await session.scalar(
            select(SupervisionHoldRow).where(
                SupervisionHoldRow.target_id == gold["id"],
                SupervisionHoldRow.released_at.is_(None),
            )
        )
        assert hold is not None
        hold_id = hold.id
        # Lonora's pause raises no card; a card stored before 0127 is kept and rendered.
        paused_card = (await raise_supervision_pause_card(session, hold, run_id=None)).id
        stored = await session.get(OwnerActionRow, paused_card)
        assert stored is not None
        template = {
            column.key: getattr(stored, column.key) for column in OwnerActionRow.__table__.columns
        }

    await alembic("downgrade", PREVIOUS)
    assert await table_exists(url, "ln_supervision_grants")
    engine = create_async_engine(url)
    try:
        async with engine.begin() as connection:
            # The downgrade brings the table back empty: no agent regains a grant.
            assert await connection.scalar(text("SELECT count(*) FROM ln_supervision_grants")) == 0
            await connection.execute(
                text(
                    "INSERT INTO ln_supervision_grants (id, owner_id, supervisor_agent_id,"
                    " supervised_agent_id, created_via, created_at)"
                    " VALUES (:id, :owner, :supervisor, :supervised, 'owner_ui', now())"
                ),
                {
                    "id": str(uuid4()),
                    "owner": fixture.owner,
                    "supervisor": gold["id"],
                    "supervised": personal_id,
                },
            )
            for kind in GRANT_KINDS:
                await connection.execute(
                    insert(OwnerActionRow).values(
                        **{**template, "id": str(uuid4()), "kind": kind, "payload": {}}
                    )
                )
    finally:
        await engine.dispose()
    await alembic("upgrade", "head")
    assert not await table_exists(url, "ln_supervision_grants")
    async with fixture.runtime.db.sessions() as session:
        kinds = list(
            await session.scalars(
                select(OwnerActionRow.kind).where(OwnerActionRow.owner_id == fixture.owner)
            )
        )
        assert not set(GRANT_KINDS) & set(kinds), kinds
        assert await session.get(OwnerActionRow, paused_card) is not None
        kept = await session.get(SupervisionHoldRow, hold_id)
        assert kept is not None and kept.released_at is None
        agent = await session.get(AgentRow, gold["id"])
        assert agent is not None and agent.paused
    print("PASS migration 0127 drops the grant table and the three grant card kinds")
    print("PASS supervision_paused cards and pause holds survive 0127; its downgrade is empty")
    # The owner's Resume on the kept card still lifts the pause.
    decided = await fixture.request(
        "POST", f"/owner-actions/{paused_card}/decision", {"decision": "confirm"}
    )
    assert decided["status"] == "confirmed", decided
    async with fixture.runtime.db.sessions() as session:
        agent = await session.get(AgentRow, gold["id"])
        assert agent is not None and not agent.paused
    print("PASS the owner's Resume on a kept pause card lifts Lonora's pause")


async def main() -> None:
    fixture = await Fixture().open()
    try:
        url = fixture.settings.database_url
        personal_id, gold = await lonora_leads_by_its_role(fixture, url)
        await lonora_answers_from_the_records(fixture, personal_id, gold)
        await migration_drops_grants_and_keeps_pauses(fixture, url, personal_id, gold)
    finally:
        await fixture.close()


if __name__ == "__main__":
    asyncio.run(main())
