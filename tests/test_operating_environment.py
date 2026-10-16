"""Self-directed tool observations stay on the existing Agent loop."""

import json
import os
from collections.abc import AsyncGenerator
from pathlib import Path
from typing import Any, cast
from unittest.mock import patch
from uuid import uuid4

import pytest
import pytest_asyncio
from lonora_adapter_kit.types import ModelMessage, ModelReply, ToolCall
from lonora_agent.tool_loop import execute_tool_loop
from lonora_contracts.domain import Contract, MessageCreate
from lonora_contracts.model_routing import ModelSelection
from lonora_contracts.runs import Lease
from lonora_core.operating import (
    argument_key,
    classify,
    financial_resend_blocked,
    observation,
    record_failure,
    route_repeated,
    select_activity,
)
from lonora_core.user_error import LonoraError
from lonora_db.client import Database
from lonora_db.messages import send_message
from lonora_db.runs import checkpoint, claim_next
from lonora_db.schema import AgentRow, Base, OwnerRow, RunRow, ScratchpadRow, ThreadRow
from lonora_tools.base import Tool
from lonora_tools.context import ToolContext
from lonora_tools.registry import ToolRegistry
from pydantic import Field
from sqlalchemy import select, text
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine


def test_classification_keeps_financial_mutation_on_reconcile():
    assert classify("tool_arguments_invalid", tool="goal_create", read_only=False)[:2] == (
        "invalid_tool_arguments",
        "repair",
    )
    assert classify("broker_connection_timeout", tool="market_candles", read_only=True)[:2] == (
        "connection_failure",
        "retry_read",
    )
    assert classify("broker_connection_timeout", tool="trade_execute", read_only=False)[:2] == (
        "ambiguous_mutation",
        "reconcile",
    )
    payload = observation(
        code="tool_arguments_invalid",
        tool="goal_create",
        read_only=False,
        issues=[{"path": ["limit"], "type": "missing"}],
    )
    assert payload["request_understood"] is True
    assert payload["owner_required"] is False
    assert payload["retryable"] is True
    assert "secret-value" not in json.dumps(payload)


def test_repeated_route_and_financial_resend_are_distinct():
    key = argument_key("market_candles", {"symbol": "XAUUSDm"})
    routes, count = record_failure(
        [],
        key=key,
        tool="market_candles",
        code="broker_connection_timeout",
        classification="connection_failure",
    )
    assert count == 1 and not route_repeated(routes, key)
    routes, count = record_failure(
        routes,
        key=key,
        tool="market_candles",
        code="broker_connection_timeout",
        classification="connection_failure",
    )
    assert count == 2 and route_repeated(routes, key)
    other = argument_key("market_candles", {"symbol": "XAUUSDm", "limit": 20})
    assert not route_repeated(routes, other)
    financial, _ = record_failure(
        [],
        key=argument_key("trade_execute", {"symbol": "XAUUSDm"}),
        tool="trade_execute",
        code="broker_connection_timeout",
        classification="ambiguous_mutation",
    )
    assert financial_resend_blocked(financial, "trade_execute")
    assert financial_resend_blocked(financial, "goal_step_execute")
    assert not financial_resend_blocked(financial, "market_quote")


def test_live_activity_follows_authoritative_state():
    assert (
        select_activity(
            paused=False,
            approvals=1,
            authorizations=0,
            broker_degraded=True,
            collaborating=True,
            watching=True,
            working=True,
            run_activity="gathering",
        )
        == "waiting_approval"
    )
    assert (
        select_activity(
            paused=False,
            approvals=0,
            authorizations=0,
            broker_degraded=False,
            collaborating=False,
            watching=False,
            working=True,
            run_activity="gathering",
        )
        == "gathering"
    )
    assert (
        select_activity(
            paused=False,
            approvals=0,
            authorizations=0,
            broker_degraded=False,
            collaborating=False,
            watching=True,
            working=False,
            run_activity=None,
        )
        == "waiting_market"
    )


class CandleRead(Contract):
    symbol: str = Field(min_length=1, max_length=32)


class RepairInput(Contract):
    title: str
    limit: int


@pytest_asyncio.fixture
async def operating_db() -> AsyncGenerator[tuple[Database, str, str, str]]:
    explicit = os.environ.get("LONORA_TASK_TEST_DATABASE_URL")
    schema = "operate_" + uuid4().hex
    if explicit:
        url = make_url(explicit)
        if not url.drivername.startswith("postgresql") or not (url.database or "").endswith(
            "_test"
        ):
            pytest.fail(
                "Operating checks require an explicit disposable *_test PostgreSQL database"
            )
        engine = create_async_engine(
            explicit, connect_args={"server_settings": {"search_path": schema}}
        )
        db = Database(engine, async_sessionmaker(engine, expire_on_commit=False))
        async with engine.begin() as connection:
            await connection.execute(text('CREATE SCHEMA "' + schema + '"'))
    else:
        db = Database.connect("sqlite+aiosqlite:///:memory:")
    async with db.engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    async with db.sessions() as session, session.begin():
        owner = OwnerRow(email="operate@example.test", password_hash="fixture")
        session.add(owner)
        await session.flush()
        agent = AgentRow(owner_id=owner.id, name="Operating fixture")
        session.add(agent)
        await session.flush()
        thread = ThreadRow(owner_id=owner.id, agent_id=agent.id)
        session.add(thread)
        await session.flush()
        owner_id, agent_id, thread_id = owner.id, agent.id, thread.id
    yield db, owner_id, agent_id, thread_id
    if explicit:
        async with db.engine.begin() as connection:
            await connection.execute(text('DROP SCHEMA "' + schema + '" CASCADE'))
    await db.close()


def _context(db: Database, owner: str, agent: str, thread: str, lease: Lease) -> ToolContext:
    return ToolContext(
        db=db,
        owner_id=owner,
        agent_id=agent,
        thread_id=thread,
        lease=lease,
        brokers=cast(Any, object()),
        trading=cast(Any, object()),
        secrets=cast(Any, object()),
        router=cast(Any, object()),
        artifact_root=Path("/tmp"),
    )


async def _lease(db: Database, owner: str, thread: str) -> Lease:
    async with db.sessions() as session, session.begin():
        await send_message(session, owner, thread, MessageCreate(content="Analyze gold."))
        run = await claim_next(session, "worker", 120, "conversation")
        assert run is not None
        lease = Lease(run_id=run.id, owner="worker", fence=run.lease_fence)
        await checkpoint(
            session,
            lease,
            {
                "rounds": 0,
                "messages": [ModelMessage(role="user", content="Analyze gold.").model_dump()],
            },
        )
        return lease


def _selection() -> ModelSelection:
    return ModelSelection(provider="openai", model="scripted")


@pytest.mark.asyncio
async def test_invalid_arguments_are_repaired_without_owner_help(
    operating_db: tuple[Database, str, str, str],
) -> None:
    db, owner, agent, thread = operating_db
    lease = await _lease(db, owner, thread)
    seen: list[dict[str, Any]] = []

    async def repair(context: ToolContext, args: dict[str, Any]) -> dict[str, Any]:
        seen.append(args)
        return {"accepted": args["limit"]}

    registry = ToolRegistry([Tool("goal_create", "Create a goal.", RepairInput, repair)])

    async def model(
        context: ToolContext, messages: list[ModelMessage], tools: Any, capability: Any
    ):
        if messages[-1].role != "tool":
            return ModelReply(
                tool_calls=[ToolCall(id="bad", name="goal_create", arguments={"title": "gold"})]
            ), _selection()
        body = json.loads(messages[-1].content)
        if body.get("ok"):
            return ModelReply(text="The gold review is prepared."), _selection()
        assert body["code"] == "tool_arguments_invalid"
        assert body["request_understood"] is True
        assert body["owner_required"] is False
        assert body["recovery"] == "repair"
        assert any(
            field["name"] == "limit" and field["required"] for field in body["schema_fields"]
        )
        assert "gold" not in json.dumps(body["issues"])
        return ModelReply(
            tool_calls=[
                ToolCall(id="fixed", name="goal_create", arguments={"title": "gold", "limit": 1})
            ]
        ), _selection()

    with patch("lonora_agent.tool_loop.model_turn", model):
        outcome = await execute_tool_loop(_context(db, owner, agent, thread, lease), registry, 6)
    assert seen == [{"title": "gold", "limit": 1}]
    assert outcome.text == "The gold review is prepared."


@pytest.mark.asyncio
async def test_repeated_read_failure_changes_route_and_survives_checkpoint(
    operating_db: tuple[Database, str, str, str],
) -> None:
    db, owner, agent, thread = operating_db
    lease = await _lease(db, owner, thread)
    calls = {"n": 0}

    async def candles(context: ToolContext, args: dict[str, Any]) -> dict[str, Any]:
        calls["n"] += 1
        raise LonoraError("broker_connection_timeout", 504)

    registry = ToolRegistry([Tool("market_candles", "Read candles.", CandleRead, candles, True)])

    async def model(
        context: ToolContext, messages: list[ModelMessage], tools: Any, capability: Any
    ):
        last = messages[-1]
        if last.role == "tool":
            body = json.loads(last.content)
            if body.get("route_repeated") or body.get("code") == "route_exhausted":
                return ModelReply(
                    text=(
                        "I understood the gold analysis request. Market data is currently "
                        "unavailable, and recovery attempts did not restore it yet."
                    )
                ), _selection()
            if body.get("recovery") == "change_strategy":
                return ModelReply(
                    tool_calls=[
                        ToolCall(id="again", name="market_candles", arguments={"symbol": "XAUUSDm"})
                    ]
                ), _selection()
        return ModelReply(
            tool_calls=[
                ToolCall(
                    id="read-" + str(calls["n"]),
                    name="market_candles",
                    arguments={"symbol": "XAUUSDm"},
                )
            ]
        ), _selection()

    with patch("lonora_agent.tool_loop.model_turn", model):
        outcome = await execute_tool_loop(_context(db, owner, agent, thread, lease), registry, 8)
    assert calls["n"] == 2
    assert "understood" in outcome.text
    assert "did not understand" not in outcome.text.lower()
    async with db.sessions() as session:
        run = await session.get(RunRow, lease.run_id)
        assert run is not None
        routes = run.execution_state["failure_routes"]
        assert routes[0]["code"] == "broker_connection_timeout"
        assert routes[0]["count"] == 2
        assert "symbol" not in json.dumps(routes)
        notes = list(
            (
                await session.scalars(select(ScratchpadRow).where(ScratchpadRow.agent_id == agent))
            ).all()
        )
    assert len(notes) == 1
    assert notes[0].state["provenance"] == "tool-observed"
    assert notes[0].state["authority"] == "none"
    assert "Emergency Stop" in notes[0].payload["content"]


@pytest.mark.asyncio
async def test_ambiguous_financial_call_is_not_resent(
    operating_db: tuple[Database, str, str, str],
) -> None:
    db, owner, agent, thread = operating_db
    lease = await _lease(db, owner, thread)
    calls = {"n": 0}

    async def execute(context: ToolContext, args: dict[str, Any]) -> dict[str, Any]:
        calls["n"] += 1
        raise LonoraError("broker_connection_timeout", 504)

    registry = ToolRegistry([Tool("trade_execute", "Send a trade.", CandleRead, execute)])

    async def model(
        context: ToolContext, messages: list[ModelMessage], tools: Any, capability: Any
    ):
        last = messages[-1]
        if last.role == "tool":
            body = json.loads(last.content)
            if body.get("code") == "financial_retry_blocked":
                return ModelReply(
                    text="I understood the request. The order needs reconciliation before any retry."
                ), _selection()
            assert body["recovery"] == "reconcile"
            assert body["owner_required"] is False
            return ModelReply(
                tool_calls=[
                    ToolCall(id="resend", name="trade_execute", arguments={"symbol": "XAUUSDm"})
                ]
            ), _selection()
        return ModelReply(
            tool_calls=[ToolCall(id="send", name="trade_execute", arguments={"symbol": "XAUUSDm"})]
        ), _selection()

    with patch("lonora_agent.tool_loop.model_turn", model):
        outcome = await execute_tool_loop(_context(db, owner, agent, thread, lease), registry, 6)
    assert calls["n"] == 1
    assert "reconciliation" in outcome.text


@pytest.mark.asyncio
async def test_restart_blocks_a_route_already_recorded(
    operating_db: tuple[Database, str, str, str],
) -> None:
    db, owner, agent, thread = operating_db
    lease = await _lease(db, owner, thread)
    key = argument_key("market_candles", {"symbol": "XAUUSDm"})
    async with db.sessions() as session, session.begin():
        await checkpoint(
            session,
            lease,
            {
                "rounds": 1,
                "failure_routes": [
                    {
                        "key": key,
                        "tool": "market_candles",
                        "code": "broker_connection_timeout",
                        "classification": "connection_failure",
                        "count": 2,
                    }
                ],
                "messages": [ModelMessage(role="user", content="Analyze gold.").model_dump()],
                "pending": [
                    ToolCall(
                        id="restored", name="market_candles", arguments={"symbol": "XAUUSDm"}
                    ).model_dump()
                ],
            },
        )
    calls = {"n": 0}

    async def candles(context: ToolContext, args: dict[str, Any]) -> dict[str, Any]:
        calls["n"] += 1
        return {"candles": []}

    registry = ToolRegistry([Tool("market_candles", "Read candles.", CandleRead, candles, True)])

    async def model(
        context: ToolContext, messages: list[ModelMessage], tools: Any, capability: Any
    ):
        body = json.loads(messages[-1].content)
        assert body["code"] == "route_exhausted"
        assert calls["n"] == 0
        return ModelReply(
            text="I understood the request. That candle route is exhausted."
        ), _selection()

    with patch("lonora_agent.tool_loop.model_turn", model):
        outcome = await execute_tool_loop(_context(db, owner, agent, thread, lease), registry, 4)
    assert calls["n"] == 0
    assert outcome.text.startswith("I understood")
