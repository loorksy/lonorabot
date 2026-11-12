"""Trading readiness: one presentation-only line of "can it trade now, what stops it".

Runs on the shared ``task_db`` fixture (a disposable PostgreSQL schema when
``LONORA_TASK_TEST_DATABASE_URL`` is set, otherwise in-memory SQLite). Signed grants are
injected through ``permission_state``: the signature path itself is covered by
``check_account_authority``. The projection must never be consulted for enforcement.
"""

import ast
from datetime import timedelta
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock

import pytest
from lonora_contracts.domain import utcnow
from lonora_db.agent_state import agent_live_state
from lonora_db.client import Database
from lonora_db.schema import (
    AgentRow,
    BrokerSessionRow,
    OwnerActionRow,
    TradingJournalRow,
)
from lonora_db.trading_readiness import trading_readiness
from lonora_db.transactions import execution_policy_key
from lonora_trading.execution_quality import policy_key
from test_task_runtime import task_db as task_db

Fixture = tuple[Database, str, str, str]
ROOT = Path(__file__).resolve().parents[1]


def grant(account: str, **envelope: Any) -> dict[str, Any]:
    return {
        "account_id": account,
        "valid_until": None,
        "envelope": {
            "account_id": account,
            "symbol_scope": "selected",
            "symbols": ["XAUUSD"],
            "actions": ["buy", "sell", "close_position"],
            "allow_manual_positions": False,
            **envelope,
        },
    }


def level(monkeypatch: pytest.MonkeyPatch, effective: str, *grants: dict[str, Any]) -> None:
    monkeypatch.setattr(
        "lonora_db.trading_readiness.permission_state",
        AsyncMock(return_value={"effective_level": effective, "active_authorities": list(grants)}),
    )


async def account(db: Database, owner: str) -> str:
    async with db.sessions() as session, session.begin():
        row = BrokerSessionRow(owner_id=owner, payload={"provider": "simulation"})
        session.add(row)
        await session.flush()
        return row.id


async def readiness(db: Database, owner: str, agent: str) -> dict[str, Any]:
    async with db.sessions() as session:
        row = await session.get(AgentRow, agent)
        assert row is not None
        return await trading_readiness(session, owner, row)


@pytest.mark.asyncio
async def test_no_grant_reads_as_no_trading(task_db: Fixture) -> None:
    db, owner, agent, _ = task_db
    await account(db, owner)
    result = await readiness(db, owner, agent)
    assert result["presentation_only"] is True
    # The per-agent default is analysis: the one line says it does not trade.
    assert result["level"] == "analysis" and result["state"] == "no_trading"
    assert result["grants"] == []
    # Lonora has no Stop: the projection carries no global trading state.
    assert "global_trading" not in result
    assert result["unresolved_operations"] == []
    assert "restrictions" not in result and "exits_allowed" not in result


@pytest.mark.asyncio
async def test_ask_me_and_signed_grant_lines(
    task_db: Fixture, monkeypatch: pytest.MonkeyPatch
) -> None:
    db, owner, agent, _ = task_db
    acct = await account(db, owner)
    level(monkeypatch, "supervised")
    asked = await readiness(db, owner, agent)
    assert asked["state"] == "ask_me" and asked["params"] == {}

    level(monkeypatch, "autonomous", grant(acct, valid_until="2026-12-01T00:00:00+00:00"))
    signed = await readiness(db, owner, agent)
    assert signed["state"] == "on_its_own"
    assert signed["params"]["symbols"] == ["XAUUSD"]
    assert signed["params"]["symbol_scope"] == "selected"
    assert signed["grants"][0]["actions"] == ["buy", "sell", "close_position"]
    assert signed["grants"][0]["allow_manual_positions"] is False
    # The executor reads the account's stored policy (its freshness bounds) at this key.
    assert policy_key(owner, acct) == execution_policy_key(owner, acct)


@pytest.mark.asyncio
async def test_a_granted_account_is_read_whatever_the_owner_s_other_accounts(
    task_db: Fixture, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The line reads the account the grant signs for (its unresolved operations), even
    when the owner has more accounts than the projection lists by default."""
    db, owner, agent, _ = task_db
    for _ in range(12):
        await account(db, owner)
    granted = await account(db, owner)  # Created last: beyond the first ten.
    async with db.sessions() as session, session.begin():
        session.add(
            TradingJournalRow(
                operation_id="op-granted",
                owner_id=owner,
                account_id=granted,
                request_hash="hash",
                request={"symbol": "XAUUSD", "action": "buy"},
                status="ambiguous",
                result={},
            )
        )
    level(monkeypatch, "autonomous", grant(granted))
    signed = await readiness(db, owner, agent)
    assert signed["state"] == "uncertain", signed
    assert signed["params"] == {"count": 1, "symbol": "XAUUSD"}


@pytest.mark.asyncio
async def test_ambiguous_operation_reads_as_uncertain_with_its_scoped_block(
    task_db: Fixture, monkeypatch: pytest.MonkeyPatch
) -> None:
    db, owner, agent, thread = task_db
    acct = await account(db, owner)
    level(monkeypatch, "autonomous", grant(acct))
    rows: list[tuple[str, str, dict[str, Any]]] = [
        ("op-ambiguous", "ambiguous", {"execution": {"agent_id": agent}}),
        ("op-submitted", "submitted", {}),
        ("op-confirmed", "confirmed", {}),
    ]
    async with db.sessions() as session, session.begin():
        for index, (operation, status, details) in enumerate(rows):
            session.add(
                TradingJournalRow(
                    operation_id=operation,
                    owner_id=owner,
                    account_id=acct,
                    request_hash="hash",
                    request={"symbol": "XAUUSD", "action": "buy", "volume": "0.1"},
                    status=status,
                    result={"details": details},
                    submitted_at=utcnow() - timedelta(minutes=10 - index),
                )
            )
    uncertain = await readiness(db, owner, agent)
    assert uncertain["state"] == "uncertain"
    assert uncertain["params"] == {"count": 2, "symbol": "XAUUSD"}
    operations = uncertain["unresolved_operations"]
    assert [item["operation_id"] for item in operations] == ["op-ambiguous", "op-submitted"]
    assert operations[0]["this_agent"] is True and operations[1]["this_agent"] is False
    assert {item["blocks"] for item in operations} == {"new_risk_on_this_symbol_or_ticket"}
    # «حسم» opens that operation's own resolve card, never another pending card.
    assert [item["resolve_card"] for item in operations] == [None, None]
    async with db.sessions() as session, session.begin():
        card = OwnerActionRow(
            owner_id=owner,
            agent_id=agent,
            # The card lives in a conversation (here the agent's own chat; another agent's or
            # Lonora's likewise): «حسم» opens that conversation and jumps to it.
            thread_id=thread,
            timeline_seq=7,
            source="system",
            kind="resolve_operation",
            subject="operation:op-ambiguous",
            payload={"operation_id": "op-ambiguous"},
            payload_hash="resolve",
            status="pending",
            result={},
            expires_at=utcnow() + timedelta(days=1),
        )
        session.add(card)
        session.add(
            OwnerActionRow(
                owner_id=owner,
                agent_id=agent,
                source="system",
                kind="resolve_operation",
                subject="operation:op-submitted",
                payload={"operation_id": "op-submitted"},
                payload_hash="expired",
                status="pending",
                result={},
                expires_at=utcnow() - timedelta(minutes=1),
            )
        )
    linked = (await readiness(db, owner, agent))["unresolved_operations"]
    assert linked[0]["resolve_card"] == {
        "id": card.id,
        "thread_id": thread,
        "agent_id": agent,
        "group_id": None,
        "timeline_seq": 7,
    }
    assert linked[1]["resolve_card"] is None
    # A pause is the stronger line; the operation stays listed for the sheet.
    async with db.sessions() as session, session.begin():
        row = await session.get(AgentRow, agent)
        assert row is not None
        row.paused = True
    held = await readiness(db, owner, agent)
    assert held["state"] == "agent_paused" and held["unresolved_count"] == 2


@pytest.mark.asyncio
async def test_paused_agent_and_market_bound_scope(
    task_db: Fixture, monkeypatch: pytest.MonkeyPatch
) -> None:
    db, owner, agent, _ = task_db
    bound, other = await account(db, owner), await account(db, owner)
    level(monkeypatch, "supervised")
    async with db.sessions() as session, session.begin():
        row = await session.get(AgentRow, agent)
        assert row is not None
        row.trading_account_id, row.trading_symbol = bound, "XAUUSD"
        row.paused = True
        for operation, acct, symbol in (
            ("op-bound", bound, "xauusd"),
            ("op-other-symbol", bound, "EURUSD"),
            ("op-other-account", other, "XAUUSD"),
        ):
            session.add(
                TradingJournalRow(
                    operation_id=operation,
                    owner_id=owner,
                    account_id=acct,
                    request_hash="hash",
                    request={"symbol": symbol, "action": "buy"},
                    status="ambiguous",
                    result={},
                )
            )
    assert (await readiness(db, owner, agent))["state"] == "agent_paused"
    async with db.sessions() as session, session.begin():
        row = await session.get(AgentRow, agent)
        assert row is not None
        row.paused = False
    scoped = await readiness(db, owner, agent)
    # A market-bound agent sees only its own account and market.
    assert [item["operation_id"] for item in scoped["unresolved_operations"]] == ["op-bound"]
    assert scoped["state"] == "uncertain"


@pytest.mark.asyncio
async def test_operations_count_only_on_the_accounts_the_agent_acts_on(
    task_db: Fixture, monkeypatch: pytest.MonkeyPatch
) -> None:
    db, owner, agent, _ = task_db
    granted, other = await account(db, owner), await account(db, owner)
    level(monkeypatch, "autonomous", grant(granted))
    async with db.sessions() as session, session.begin():
        session.add(
            TradingJournalRow(
                operation_id="op-elsewhere",
                owner_id=owner,
                account_id=other,
                request_hash="hash",
                request={"symbol": "EURUSD", "action": "buy"},
                status="ambiguous",
                result={},
            )
        )
    elsewhere = await readiness(db, owner, agent)
    # An uncertain operation on another account does not stop this agent trading on its
    # own on its granted account; the sheet still lists it.
    assert elsewhere["state"] == "on_its_own"
    assert [item["operation_id"] for item in elsewhere["unresolved_operations"]] == ["op-elsewhere"]
    assert elsewhere["unresolved_count"] == 1
    # An agent that asks before each trade may ask on any account: the operation counts.
    level(monkeypatch, "supervised")
    assert (await readiness(db, owner, agent))["state"] == "uncertain"


@pytest.mark.asyncio
async def test_live_state_carries_readiness_only_for_the_owner_view(task_db: Fixture) -> None:
    db, owner, agent, _ = task_db
    async with db.sessions() as session:
        plain = await agent_live_state(session, owner, agent)
        owner_view = await agent_live_state(session, owner, agent, readiness=True)
    assert plain.trading_readiness is None
    assert owner_view.trading_readiness is not None
    assert owner_view.trading_readiness["state"] == "no_trading"


@pytest.mark.asyncio
async def test_the_status_line_waits_for_the_owner_or_the_broker_like_the_pill(
    task_db: Fixture,
) -> None:
    """A decision card in the agent's conversation, or its own operation the broker has
    not settled, is never "Idle": the line says what the card and the pill say."""

    db, owner, agent, thread = task_db
    acct = await account(db, owner)
    async with db.sessions() as session:
        idle = await agent_live_state(session, owner, agent)
    assert idle.state == "idle"
    async with db.sessions() as session, session.begin():
        session.add(
            OwnerActionRow(
                owner_id=owner,
                agent_id=agent,
                thread_id=thread,
                timeline_seq=1,
                source="agent",
                kind="trust_source",
                subject="probe",
                payload={},
                payload_hash="probe",
                status="pending",
                result={},
                expires_at=utcnow() + timedelta(days=1),
            )
        )
    async with db.sessions() as session:
        waiting = await agent_live_state(session, owner, agent)
    assert waiting.state == "action_required" and waiting.reason_code == "owner_card_required"
    async with db.sessions() as session, session.begin():
        session.add(
            TradingJournalRow(
                operation_id="op-mine-" + agent,
                owner_id=owner,
                account_id=acct,
                request_hash="hash",
                request={"symbol": "XAUUSD", "action": "buy", "volume": "0.1"},
                status="ambiguous",
                result={"details": {"execution": {"agent_id": agent}}},
                submitted_at=utcnow(),
            )
        )
    async with db.sessions() as session:
        uncertain = await agent_live_state(session, owner, agent)
    assert uncertain.state == "action_required" and uncertain.phase == "uncertain"
    assert uncertain.reason_code == "operation_uncertain"


def test_readiness_is_presentation_only_and_never_read_by_enforcement() -> None:
    """The executor, admission and permission checks must never import the projection."""
    for package in ("trading", "tools"):
        for path in (ROOT / "packages" / package / "src").rglob("*.py"):
            tree = ast.parse(path.read_text())
            for node in ast.walk(tree):
                names = (
                    [alias.name for alias in node.names]
                    if isinstance(node, ast.ImportFrom | ast.Import)
                    else []
                )
                module = node.module if isinstance(node, ast.ImportFrom) else None
                assert "trading_readiness" not in (module or ""), path
                assert "trading_readiness" not in names, path
    routing = (ROOT / "packages/agent-runtime/src/lonora_agent/context/team.py").read_text()
    assert "readiness=True" not in routing
