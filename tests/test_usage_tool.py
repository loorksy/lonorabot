"""P5 and 13.1: the owner's usage reaches chat through ``usage_read``.

Usage per agent and per model had a server capability (``lonora_db.usage``) and a Web
page, but no agent could read it, so "what did my agents cost this month?" had no
answer in chat. The tool reads the same services as the page; it is a view, never a
cap (owner decision D4, mandate P1).
"""

from datetime import timedelta
from pathlib import Path
from typing import Any, cast
from uuid import uuid4

import pytest
from lonora_contracts.domain import utcnow
from lonora_db.client import Database
from lonora_db.schema import AgentRow, UsageRow
from lonora_tools.context import ToolContext
from lonora_tools.loader import load_tools
from test_task_runtime import task_db as task_db

Fixture = tuple[Database, str, str, str]


def context(fixture: Fixture) -> ToolContext:
    db, owner, agent, thread = fixture
    return ToolContext(
        db,
        owner,
        agent,
        thread,
        cast(Any, None),
        cast(Any, None),
        cast(Any, None),
        cast(Any, None),
        cast(Any, None),
        Path("/tmp/usage-tool-fixture"),
    )


async def seed(db: Database, owner: str, agent: str, model: str, tokens: int) -> None:
    async with db.sessions() as session, session.begin():
        now = utcnow() - timedelta(minutes=5)
        session.add(
            UsageRow(
                owner_id=owner,
                agent_id=agent,
                payload={
                    "run_id": uuid4().hex,
                    "provider": "anthropic",
                    "model": model,
                    "input_tokens": tokens,
                    "output_tokens": tokens // 10,
                    "cached_tokens": 0,
                },
                created_at=now,
                updated_at=now,
            )
        )


def test_usage_read_is_a_read_tool_in_the_intelligence_chapter() -> None:
    tool = load_tools().tools["usage_read"]
    assert tool.read_only and not tool.financial
    assert tool.toolset == "intelligence"
    # A view, never a cap: the description sets no limit and asks for no approval.
    assert "limit" not in tool.description.lower() and "cap" not in tool.description.lower()


@pytest.mark.asyncio
async def test_usage_read_ranks_this_months_usage_per_agent_and_model(task_db: Fixture) -> None:
    db, owner, agent, _ = task_db
    async with db.sessions() as session, session.begin():
        other = AgentRow(owner_id=owner, name="Gold desk")
        session.add(other)
        await session.flush()
        other_id = other.id
    await seed(db, owner, agent, "claude-sonnet-4-5", 1000)
    await seed(db, owner, other_id, "claude-sonnet-4-5", 4000)
    await seed(db, owner, other_id, "claude-sonnet-4-5", 4000)
    tool = load_tools().tools["usage_read"]

    everyone = await tool.handler(context(task_db), {"period": "month"})
    assert everyone["ok"] is True and everyone["period"] == "month"
    assert everyone["totals"]["requests"] == 3
    assert [row["agent_id"] for row in everyone["agents"]] == [other_id, agent]
    assert everyone["agents"][0]["agent_name"] == "Gold desk"
    assert everyone["agents"][0]["requests"] == 2
    assert everyone["models"][0]["model"] == "claude-sonnet-4-5"
    assert everyone["totals"]["cost_usd"] > 0
    # The month so far and its projection, as on the usage page.
    assert everyone["month"]["spent_usd"] > 0 and "projected_usd" in everyone["month"]

    one = await tool.handler(context(task_db), {"period": "day", "agent_id": agent})
    assert one["agent_id"] == agent and one["totals"]["requests"] == 1
    assert [row["agent_id"] for row in one["agents"]] == [agent]


@pytest.mark.asyncio
async def test_usage_read_refuses_an_agent_the_owner_does_not_have(task_db: Fixture) -> None:
    tool = load_tools().tools["usage_read"]
    refused = await tool.handler(context(task_db), {"agent_id": uuid4().hex})
    assert refused == {"ok": False, "code": "agent_not_found"}
