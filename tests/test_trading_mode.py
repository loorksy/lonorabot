"""The agent's trading mode at the execution door (mandate 4.1, 4.2.3, 6.7). Offline."""

from decimal import Decimal
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest
from lonora_contracts.account import Position
from lonora_contracts.trading import TradeRequest
from lonora_core.user_error import LonoraError
from lonora_db import trading_mode as mode_store
from lonora_db.schema import AgentRow, RunRow, TradeApprovalRow
from lonora_trading import agent_permission


def origin() -> RunRow:
    return RunRow(id="run", agent_id="agent", thread_id="chat", trigger="user", model_metadata={})


def request(**changes: Any) -> TradeRequest:
    return TradeRequest.model_validate(
        {
            "account_id": "account",
            "symbol": "XAUUSD",
            "action": "buy",
            "volume": "0.1",
            "operation_id": "operation",
            **changes,
        }
    )


def close() -> TradeRequest:
    return request(action="close_position", position_id="1", volume=None)


TICKET = Position(id="1", symbol="XAUUSD", side="buy", volume=Decimal("0.1"), open_price=1)


def gate(
    monkeypatch: pytest.MonkeyPatch, mode: str, level: str = "supervised", owner: str = "agent"
) -> AsyncMock:
    monkeypatch.setattr(agent_permission, "trading_mode", AsyncMock(return_value=mode))
    # Whose journaled order opened the ticket: this agent's own by default.
    monkeypatch.setattr(agent_permission, "ticket_agent", AsyncMock(return_value=owner))
    monkeypatch.setattr(agent_permission, "effective_permission", AsyncMock(return_value=level))
    session = AsyncMock()
    session.scalars.return_value = []
    return session


@pytest.mark.asyncio
@pytest.mark.parametrize("level", ["analysis", "supervised", "autonomous"])
async def test_full_mode_sends_without_any_approval(monkeypatch: pytest.MonkeyPatch, level: str):
    session = gate(monkeypatch, "full", level)
    for item in (request(), close()):
        for reducing in (None, False, True):
            await agent_permission.require_operation_permission(
                session, "owner", origin(), item, None, reducing=reducing, target=TICKET
            )
    session.scalars.assert_not_called()


@pytest.mark.asyncio
async def test_ask_mode_needs_the_exact_approved_request_for_new_risk(
    monkeypatch: pytest.MonkeyPatch,
):
    session = gate(monkeypatch, "ask")
    for reducing in (None, False):
        with pytest.raises(LonoraError, match="trade_approval_required"):
            await agent_permission.require_operation_permission(
                session, "owner", origin(), request(), None, reducing=reducing
            )
    session.scalars.return_value = [TradeApprovalRow(requests=[request().model_dump(mode="json")])]
    await agent_permission.require_operation_permission(
        session, "owner", origin(), request(), None, reducing=False
    )
    # The exact match is unchanged: another id or another fingerprint is not approved.
    for changed in (request(operation_id="retry"), request(volume="0.3")):
        with pytest.raises(LonoraError, match="trade_approval_required"):
            await agent_permission.require_operation_permission(
                session, "owner", origin(), changed, None, reducing=False
            )


@pytest.mark.asyncio
async def test_ask_mode_lets_a_risk_reducing_request_through(monkeypatch: pytest.MonkeyPatch):
    session = gate(monkeypatch, "ask")
    await agent_permission.require_operation_permission(
        session, "owner", origin(), close(), None, reducing=True, target=TICKET
    )
    # Before the broker target is read, a request that may reduce risk is left to the
    # decisive check at send, which classifies it against the fresh ticket.
    await agent_permission.require_operation_permission(
        session, "owner", origin(), close(), None, reducing=None
    )
    # Classified as adding risk on the fresh ticket: it needs the exact approval.
    with pytest.raises(LonoraError, match="trade_approval_required"):
        await agent_permission.require_operation_permission(
            session, "owner", origin(), close(), None, reducing=False, target=TICKET
        )
    # Only the door's own classification counts: an entry is never risk-reducing.
    with pytest.raises(LonoraError, match="trade_approval_required"):
        await agent_permission.require_operation_permission(
            session, "owner", origin(), request(), None, reducing=None
        )


@pytest.mark.asyncio
@pytest.mark.parametrize("mode", ["full", "ask"])
@pytest.mark.parametrize("owner", [None, "another-agent"])
async def test_a_ticket_the_agent_did_not_open_needs_the_exact_approval(
    monkeypatch: pytest.MonkeyPatch, mode: str, owner: str | None
):
    """The owner's own position, or another agent's: never without the owner's card."""
    session = gate(monkeypatch, mode, owner=owner)  # type: ignore[arg-type]
    for target in (TICKET, None):
        with pytest.raises(LonoraError, match="trade_approval_required"):
            await agent_permission.require_operation_permission(
                session, "owner", origin(), close(), None, reducing=True, target=target
            )
    session.scalars.return_value = [TradeApprovalRow(requests=[close().model_dump(mode="json")])]
    await agent_permission.require_operation_permission(
        session, "owner", origin(), close(), None, reducing=True, target=TICKET
    )


@pytest.mark.asyncio
async def test_ask_mode_keeps_the_ladder_until_it_is_removed(monkeypatch: pytest.MonkeyPatch):
    session = gate(monkeypatch, "ask", "analysis")
    with pytest.raises(LonoraError, match="agent_analysis_only"):
        await agent_permission.require_operation_permission(
            session, "owner", origin(), close(), None, reducing=True, target=TICKET
        )


def agent(mode: str = "ask", role: str = "specialist") -> AgentRow:
    return AgentRow(id="agent", owner_id="owner", name="Gold", role=role, trading_mode=mode)


@pytest.mark.asyncio
async def test_only_the_owner_tap_sets_full(monkeypatch: pytest.MonkeyPatch):
    row = agent()
    monkeypatch.setattr(mode_store, "authority_lock", AsyncMock())
    session = AsyncMock()
    session.add = MagicMock()
    session.get.return_value = row
    with pytest.raises(LonoraError, match="trading_mode_full_owner_only"):
        await mode_store.set_trading_mode(session, "owner", "agent", "full", by="agent")
    assert row.trading_mode == "ask"
    await mode_store.set_trading_mode(session, "owner", "agent", "full", by="owner_tap")
    assert row.trading_mode == "full"
    mode_store.authority_lock.assert_awaited_with(session, "agent")  # type: ignore[attr-defined]


@pytest.mark.asyncio
async def test_any_agent_may_switch_itself_to_ask(monkeypatch: pytest.MonkeyPatch):
    row = agent("full")
    monkeypatch.setattr(mode_store, "authority_lock", AsyncMock())
    session = AsyncMock()
    session.add = MagicMock()
    session.get.return_value = row
    assert await mode_store.set_trading_mode(session, "owner", "agent", "ask", by="agent") == "ask"
    assert row.trading_mode == "ask"


@pytest.mark.asyncio
async def test_a_foreign_agent_is_not_found(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(mode_store, "authority_lock", AsyncMock())
    session = AsyncMock()
    session.get.return_value = AgentRow(id="agent", owner_id="other", name="x", trading_mode="ask")
    with pytest.raises(LonoraError, match="agent_not_found"):
        await mode_store.trading_mode(session, "owner", "agent")


def test_the_frame_gives_the_agent_its_mode_every_turn():
    import json

    from lonora_agent.context.permissions import permission_guidance

    state: dict[str, Any] = {"effective_level": "supervised", "active_authorities": []}

    def snapshot(text: str) -> dict[str, Any]:
        start = text.index("<current_financial_permission>") + len("<current_financial_permission>")
        return json.loads(text[start : text.index("</current_financial_permission>")])

    ask = permission_guidance(state)
    assert snapshot(ask)["trading_mode"] == "ask" and "You are in Ask" in ask
    full = permission_guidance(state, mode="full")
    assert snapshot(full)["trading_mode"] == "full" and "You are in Full" in full
    assert snapshot(full)["owner_approval_required"] is False
    # An observe-only wake never inherits the agent's Full mode.
    observer = permission_guidance(state, mode="full", observe_only=True)
    assert snapshot(observer)["trading_mode"] == "ask"
    assert snapshot(observer)["financial_mutations_prohibited"] is True
