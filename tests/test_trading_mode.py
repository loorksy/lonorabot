"""The agent's trading mode at the execution door (mandate 4.1, 4.2.3, 6.7). Offline."""

from decimal import Decimal
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest
from lonora_contracts.account import Position
from lonora_contracts.trading import TradeRequest
from lonora_core.user_error import LonoraError
from lonora_db import trading_mode as mode_store
from lonora_db.schema import AgentRow, MessageRow, RunRow, TradeApprovalRow
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


TICKET = Position(id="1", symbol="XAUUSD", side="buy", volume=Decimal("0.1"), open_price=Decimal(1))


def gate(
    monkeypatch: pytest.MonkeyPatch,
    mode: str,
    level: str = "supervised",
    owner: str | None = "agent",
    role: str = "specialist",
    manages_all: bool = False,
    holder_mode: str = "ask",
) -> AsyncMock:
    acting = AgentRow(
        id="agent",
        owner_id="owner",
        role=role,
        trading_mode=mode,
        manages_all_positions=manages_all,
    )
    monkeypatch.setattr(agent_permission, "acting_agent", AsyncMock(return_value=acting))
    # Whose journaled order opened the ticket: this agent's own by default.
    monkeypatch.setattr(agent_permission, "ticket_agent", AsyncMock(return_value=owner))
    monkeypatch.setattr(agent_permission, "effective_permission", AsyncMock(return_value=level))
    monkeypatch.setattr(agent_permission, "owner_typed_message", AsyncMock(return_value=None))
    session = AsyncMock()
    session.scalars.return_value = []
    session.get.return_value = AgentRow(id=owner or "x", owner_id="owner", trading_mode=holder_mode)
    return session


async def door(session: AsyncMock, item: TradeRequest, **flags: Any) -> None:
    await agent_permission.require_operation_permission(
        session, "owner", origin(), item, None, **flags
    )


@pytest.mark.asyncio
async def test_full_mode_sends_without_any_approval(monkeypatch: pytest.MonkeyPatch):
    session = gate(monkeypatch, "full")
    for item in (request(), close()):
        for reducing in (None, False, True):
            await door(session, item, reducing=reducing, target=TICKET)
    session.scalars.assert_not_called()


@pytest.mark.asyncio
async def test_ask_mode_needs_the_exact_approved_request_for_new_risk(
    monkeypatch: pytest.MonkeyPatch,
):
    session = gate(monkeypatch, "ask")
    for reducing in (None, False):
        with pytest.raises(LonoraError, match="trade_approval_required"):
            await door(session, request(), reducing=reducing)
    session.scalars.return_value = [TradeApprovalRow(requests=[request().model_dump(mode="json")])]
    await door(session, request(), reducing=False)
    # The exact match is unchanged: another id or another fingerprint is not approved.
    for changed in (request(operation_id="retry"), request(volume="0.3")):
        with pytest.raises(LonoraError, match="trade_approval_required"):
            await door(session, changed, reducing=False)


@pytest.mark.asyncio
async def test_ask_mode_lets_a_risk_reducing_request_through(monkeypatch: pytest.MonkeyPatch):
    session = gate(monkeypatch, "ask")
    await door(session, close(), reducing=True, target=TICKET)
    # Before the broker target is read, a request that may reduce risk is left to the
    # decisive check at send, which classifies it against the fresh ticket.
    await door(session, close(), reducing=None)
    # Classified as adding risk on the fresh ticket: it needs the exact approval.
    with pytest.raises(LonoraError, match="trade_approval_required"):
        await door(session, close(), reducing=False, target=TICKET)
    # Only the door's own classification counts: an entry is never risk-reducing.
    with pytest.raises(LonoraError, match="trade_approval_required"):
        await door(session, request(), reducing=None)


@pytest.mark.asyncio
@pytest.mark.parametrize("mode", ["full", "ask"])
@pytest.mark.parametrize("holder", [None, "another-agent"])
async def test_a_ticket_the_agent_does_not_own_is_refused(
    monkeypatch: pytest.MonkeyPatch, mode: str, holder: str | None
):
    """3.3.4: the owner's own ticket, or another agent's, is ticket_not_owned, even with an
    approved card for it."""
    session = gate(monkeypatch, mode, owner=holder)
    session.scalars.return_value = [TradeApprovalRow(requests=[close().model_dump(mode="json")])]
    for target in (TICKET, None):
        with pytest.raises(LonoraError, match="ticket_not_owned"):
            await door(session, close(), reducing=True, target=target)


@pytest.mark.asyncio
@pytest.mark.parametrize("mode", ["full", "ask"])
async def test_the_three_exceptions_of_ticket_ownership(monkeypatch: pytest.MonkeyPatch, mode: str):
    # The owner's standing instruction to manage every position.
    session = gate(monkeypatch, mode, owner=None, manages_all=True)
    await door(session, close(), reducing=True, target=TICKET)
    # The run carries the owner's typed message asking for it.
    session = gate(monkeypatch, mode, owner=None)
    monkeypatch.setattr(
        agent_permission, "owner_typed_message", AsyncMock(return_value=MessageRow(id="m1"))
    )
    await door(session, close(), reducing=True, target=TICKET, owner_message_id="m1")
    with pytest.raises(LonoraError, match="ticket_not_owned"):
        await door(session, close(), reducing=True, target=TICKET, owner_message_id="other")
    # Lonora acts on any ticket.
    session = gate(monkeypatch, mode, owner=None, role="personal")
    await door(session, close(), reducing=True, target=TICKET)


@pytest.mark.asyncio
async def test_lonora_asks_for_new_risk_on_an_ask_agents_ticket_even_in_full(
    monkeypatch: pytest.MonkeyPatch,
):
    """3.1.3: a risk-increasing request Lonora sends on a ticket owned by an agent in Ask
    becomes a Trade Approval card, even when Lonora is in Full."""
    widen = request(action="modify_position", position_id="1", volume=None, stop_loss="0.5")
    session = gate(monkeypatch, "full", owner="team-agent", role="personal", holder_mode="ask")
    with pytest.raises(LonoraError, match="trade_approval_required"):
        await door(session, widen, reducing=False, target=TICKET)
    await door(session, close(), reducing=True, target=TICKET)
    # The same request on a team agent in Full: Lonora's own mode governs it.
    session = gate(monkeypatch, "full", owner="team-agent", role="personal", holder_mode="full")
    await door(session, widen, reducing=False, target=TICKET)


@pytest.mark.asyncio
@pytest.mark.parametrize("mode", ["full", "ask"])
async def test_the_ladder_keeps_refusing_until_it_is_deleted(
    monkeypatch: pytest.MonkeyPatch, mode: str
):
    """0.4, 14.1.1: "No trading" is the old path, unchanged until its deletion step."""
    session = gate(monkeypatch, mode, "analysis")
    with pytest.raises(LonoraError, match="agent_analysis_only"):
        await door(session, close(), reducing=True, target=TICKET)


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
    # An observe-only wake reports the stored mode; its fields carry the restriction.
    observer = permission_guidance(state, mode="full", observe_only=True)
    assert snapshot(observer)["trading_mode"] == "full"
    assert snapshot(observer)["financial_mutations_prohibited"] is True
    # A No-trading agent is not told it trades on its own, whatever its mode.
    stopped = permission_guidance({**state, "effective_level": "analysis"}, mode="full")
    assert snapshot(stopped)["financial_mutations_prohibited"] is True
    assert "You are in Full" not in stopped
    # An active signed grant decides within its own terms in either mode.
    granted = permission_guidance(
        {**state, "effective_level": "autonomous", "active_authorities": [{"envelope": {}}]}
    )
    assert "in either mode until it is revoked" in granted
