"""Trading readiness: one presentation-only line of "can it trade now, what stops it".

Runs on the shared ``task_db`` fixture (a disposable PostgreSQL schema when
``LONORA_TASK_TEST_DATABASE_URL`` is set, otherwise in-memory SQLite). Signed grants are
injected through ``permission_state``: the signature path itself is covered by
``check_account_authority``. The projection must never be consulted for enforcement.
"""

import ast
import os
from datetime import timedelta
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock

import pytest
from lonora_contracts.domain import utcnow
from lonora_contracts.trading import TradingControl
from lonora_db.agent_state import agent_live_state
from lonora_db.client import Database
from lonora_db.schema import (
    AccountAuthorityRow,
    AgentRow,
    BrokerSessionRow,
    TradingJournalRow,
    TradingRestrictionRow,
)
from lonora_db.trading_readiness import global_trading, trading_readiness
from lonora_db.transactions import SettingsRepository, execution_policy_key
from lonora_trading.controls import save_controls
from lonora_trading.execution_quality import policy_key
from test_task_runtime import task_db as task_db

Fixture = tuple[Database, str, str, str]
POSTGRES = bool(os.environ.get("LONORA_TASK_TEST_DATABASE_URL"))
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


async def resume(db: Database) -> None:
    await save_controls(db, TradingControl(enabled=True))


@pytest.mark.asyncio
async def test_no_grant_reads_as_no_trading_with_default_stopped_and_unset_limits(
    task_db: Fixture,
) -> None:
    db, owner, agent, _ = task_db
    acct = await account(db, owner)
    result = await readiness(db, owner, agent)
    assert result["presentation_only"] is True
    # The per-agent default is analysis: the one line says it does not trade.
    assert result["level"] == "analysis" and result["state"] == "no_trading"
    assert result["grants"] == []
    # Trading starts stopped until the owner resumes it; nobody changed it yet.
    assert result["global_trading"] == {"state": "stopped", "since": None, "changed_by": "default"}
    assert result["money_limits"] == [
        {
            "account_id": acct,
            "configured": False,
            "currency": None,
            "limits": {},
            "not_configured": [
                "max_trade_risk",
                "max_trade_risk_equity_percent",
                "max_daily_loss",
                "max_open_risk",
                "max_open_risk_equity_percent",
                "min_free_margin",
            ],
        }
    ]
    assert result["restrictions"] == [] and result["unresolved_operations"] == []
    assert result["exits_allowed"] is True


@pytest.mark.asyncio
async def test_ask_me_and_signed_grant_lines_report_whether_a_money_limit_is_set(
    task_db: Fixture, monkeypatch: pytest.MonkeyPatch
) -> None:
    db, owner, agent, _ = task_db
    acct = await account(db, owner)
    await resume(db)
    level(monkeypatch, "supervised")
    asked = await readiness(db, owner, agent)
    assert asked["state"] == "ask_me" and asked["params"] == {"money_limit_set": False}
    assert asked["global_trading"]["state"] == "running"
    assert asked["global_trading"]["changed_by"] == "owner"

    level(monkeypatch, "autonomous", grant(acct, valid_until="2026-12-01T00:00:00+00:00"))
    signed = await readiness(db, owner, agent)
    assert signed["state"] == "on_its_own"
    assert signed["params"]["symbols"] == ["XAUUSD"]
    assert signed["params"]["symbol_scope"] == "selected"
    assert signed["params"]["money_limit_set"] is False
    assert signed["grants"][0]["actions"] == ["buy", "sell", "close_position"]
    assert signed["grants"][0]["allow_manual_positions"] is False

    async with db.sessions() as session, session.begin():
        await SettingsRepository().put(
            session,
            execution_policy_key(owner, acct),
            {"risk": {"currency": "USD", "max_daily_loss": "300"}},
        )
    limited = await readiness(db, owner, agent)
    assert limited["params"]["money_limit_set"] is True
    assert limited["money_limits"][0]["limits"] == {"max_daily_loss": "300"}
    assert limited["money_limits"][0]["trading_day_timezone"] == "UTC"
    # The executor and this projection read the same settings key.
    assert policy_key(owner, acct) == execution_policy_key(owner, acct)


@pytest.mark.asyncio
async def test_globally_stopped_wins_over_the_ladder_and_since_stays_true(
    task_db: Fixture, monkeypatch: pytest.MonkeyPatch
) -> None:
    db, owner, agent, _ = task_db
    acct = await account(db, owner)
    level(monkeypatch, "autonomous", grant(acct))
    await resume(db)
    await save_controls(db, TradingControl(enabled=False, emergency_stop=True))
    stopped = await readiness(db, owner, agent)
    assert stopped["state"] == "stopped"
    assert stopped["params"]["since"] == stopped["global_trading"]["since"] is not None
    # Repeating Stop is not a new change: "stopped since" does not move.
    await save_controls(db, TradingControl(enabled=False, emergency_stop=True))
    async with db.sessions() as session:
        assert (await global_trading(session))["since"] == stopped["global_trading"]["since"]
    # Plain Trading OFF is the same single brake.
    await save_controls(db, TradingControl(enabled=False))
    assert (await readiness(db, owner, agent))["state"] == "stopped"
    await resume(db)
    assert (await readiness(db, owner, agent))["state"] == "on_its_own"
    # No trading stays the truthful line for an agent that never trades.
    level(monkeypatch, "analysis")
    await save_controls(db, TradingControl(enabled=False))
    assert (await readiness(db, owner, agent))["state"] == "no_trading"


@pytest.mark.asyncio
@pytest.mark.skipif(not POSTGRES, reason="restriction windows need timezone-aware timestamps")
async def test_active_restriction_pauses_and_a_freeze_traps_no_exit_but_shows_it(
    task_db: Fixture, monkeypatch: pytest.MonkeyPatch
) -> None:
    db, owner, agent, _ = task_db
    acct = await account(db, owner)
    await resume(db)
    level(monkeypatch, "supervised")
    now = utcnow()
    async with db.sessions() as session, session.begin():
        session.add_all(
            [
                TradingRestrictionRow(
                    owner_id=owner,
                    account_id=acct,
                    agent_id=None,
                    action_class="no_new_entries",
                    valid_from=now - timedelta(minutes=1),
                    valid_until=now + timedelta(hours=3),
                    source="owner_message",
                    created_by="agent",
                    created_by_agent_id=agent,
                ),
                TradingRestrictionRow(
                    owner_id=owner,
                    account_id=acct,
                    agent_id=agent,
                    symbol="XAUUSD",
                    action_class="all_mutations",
                    valid_from=now + timedelta(hours=1),
                    valid_until=now + timedelta(hours=2),
                    source="owner_ui",
                    created_by="owner",
                ),
                TradingRestrictionRow(
                    owner_id=owner,
                    account_id=acct,
                    agent_id="another-agent",
                    action_class="all_mutations",
                    valid_from=now - timedelta(minutes=1),
                    source="owner_ui",
                    created_by="owner",
                ),
            ]
        )
    paused = await readiness(db, owner, agent)
    assert paused["state"] == "paused"
    assert paused["params"]["action_class"] == "no_new_entries"
    assert paused["params"]["count"] == 1 and paused["params"]["symbol"] is None
    # Active first; the scheduled one is listed; another agent's pause is not.
    assert [item["state"] for item in paused["restrictions"]] == ["active", "scheduled"]
    first = paused["restrictions"][0]
    assert first["applies_to"] == "all_agents" and first["source"] == "owner_message"
    assert first["created_by_agent_id"] == agent and "reason" not in first
    assert paused["restrictions"][1]["applies_to"] == "this_agent"
    assert paused["exits_allowed"] is True
    async with db.sessions() as session, session.begin():
        session.add(
            TradingRestrictionRow(
                owner_id=owner,
                account_id=acct,
                agent_id=agent,
                action_class="all_mutations",
                valid_from=now - timedelta(minutes=1),
                source="owner_ui",
                created_by="owner",
            )
        )
    frozen = await readiness(db, owner, agent)
    assert frozen["params"]["action_class"] == "all_mutations"
    assert frozen["exits_allowed"] is False


@pytest.mark.asyncio
async def test_ambiguous_operation_reads_as_uncertain_with_its_scoped_block(
    task_db: Fixture, monkeypatch: pytest.MonkeyPatch
) -> None:
    db, owner, agent, _ = task_db
    acct = await account(db, owner)
    await resume(db)
    level(monkeypatch, "autonomous", grant(acct))
    rows: list[tuple[str, str, str, dict[str, Any]]] = [
        ("op-ambiguous", "ambiguous", "live", {"execution": {"agent_id": agent}}),
        ("op-submitted", "submitted", "live", {}),
        ("op-confirmed", "confirmed", "live", {}),
        ("op-shadow", "ambiguous", "shadow", {}),
    ]
    async with db.sessions() as session, session.begin():
        for index, (operation, status, mode, details) in enumerate(rows):
            session.add(
                TradingJournalRow(
                    operation_id=operation,
                    owner_id=owner,
                    account_id=acct,
                    request_hash="hash",
                    request={"symbol": "XAUUSD", "action": "buy", "volume": "0.1"},
                    status=status,
                    execution_mode=mode,
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
    # A stop or pause is the stronger line; the operation stays listed for the sheet.
    await save_controls(db, TradingControl(enabled=False))
    stopped = await readiness(db, owner, agent)
    assert stopped["state"] == "stopped" and stopped["unresolved_count"] == 2


@pytest.mark.asyncio
async def test_paused_agent_and_market_bound_scope(
    task_db: Fixture, monkeypatch: pytest.MonkeyPatch
) -> None:
    db, owner, agent, _ = task_db
    bound, other = await account(db, owner), await account(db, owner)
    await resume(db)
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
    assert [item["account_id"] for item in scoped["money_limits"]] == [bound]
    assert [item["operation_id"] for item in scoped["unresolved_operations"]] == ["op-bound"]
    assert scoped["state"] == "uncertain"


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
@pytest.mark.skipif(not POSTGRES, reason="grant expiry needs timezone-aware timestamps")
async def test_owner_grant_summary_reports_money_limits_once(task_db: Fixture) -> None:
    db, owner, agent, thread = task_db
    acct = await account(db, owner)
    async with db.sessions() as session, session.begin():
        # A grant awaiting the owner's signature is listed; it is never authority.
        session.add(
            AccountAuthorityRow(
                owner_id=owner,
                agent_id=agent,
                thread_id=thread,
                account_id=acct,
                status="pending",
                envelope={"account_id": acct, "symbols": ["XAUUSD"], "actions": ["buy"]},
                envelope_hash="hash",
                activation_expires_at=utcnow() + timedelta(minutes=10),
            )
        )
    async with db.sessions() as session:
        plain = await agent_live_state(session, owner, agent)
        owner_view = await agent_live_state(session, owner, agent, readiness=True)
    # The owner's grant summary reports the account's money limits; the model's live
    # state does not repeat them (its permission frame carries them every turn), and
    # neither claims a monetary limit is "unavailable".
    assert owner_view.account_authorities[0]["money_limits"]["configured"] is False
    assert "money_limits" not in plain.account_authorities[0]
    assert "monetary_stop_risk" not in plain.account_authorities[0]


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
