"""The agent's trading mode at the execution door (mandate 4.1, 4.2.3, 6.7). Offline; ticket
ownership (3.3.4) reads the journal on the shared ``task_db`` fixture."""

from datetime import datetime, timedelta
from decimal import Decimal
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from lonora_contracts.account import Position
from lonora_contracts.domain import utcnow
from lonora_contracts.trading import TradeRequest
from lonora_core.user_error import LonoraError
from lonora_db import trading_mode as mode_store
from lonora_db.client import Database
from lonora_db.schema import AgentRow, MessageRow, RunRow, TradeApprovalRow, TradingJournalRow
from lonora_session.idempotency import broker_operation_tag
from lonora_trading import agent_permission
from lonora_trading.account_authority import ticket_agent
from sqlalchemy.ext.asyncio import AsyncSession
from test_task_runtime import task_db as task_db

Fixture = tuple[Database, str, str, str]


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


def entry(
    owner: str,
    operation: str,
    agent: str | None,
    at: datetime,
    *,
    action: str = "buy",
    position: str | None = None,
    order: str | None = None,
) -> TradingJournalRow:
    """A confirmed entry journaled as the MetaApi adapter writes it: the broker's order and
    position ids in ``details``, the sending agent in ``details.execution``."""
    return TradingJournalRow(
        operation_id=operation,
        owner_id=owner,
        account_id="account",
        request_hash="0" * 64,
        request={"symbol": "XAUUSD", "action": action},
        status="confirmed",
        result={
            "broker_id": order or position,
            "details": {
                "order_id": order,
                "position_id": position,
                "execution": {"agent_id": agent},
            },
        },
        submitted_at=at,
        updated_at=at,
    )


async def two_agents(db: Database, owner: str) -> tuple[str, str]:
    async with db.sessions() as session, session.begin():
        rows = [AgentRow(owner_id=owner, name=name, role="specialist") for name in "AB"]
        session.add_all(rows)
        await session.flush()
        return rows[0].id, rows[1].id


def closing(position: str) -> TradeRequest:
    return request(action="close_position", position_id=position, volume=None)


async def closes(session: AsyncSession, owner: str, agent: str, ticket: Position) -> None:
    """The agent's close of this ticket at the door, with the real journal attribution."""
    run = RunRow(id="run", agent_id=agent, thread_id="chat", trigger="user", model_metadata={})
    level = AsyncMock(return_value="supervised")
    with patch.object(agent_permission, "effective_permission", level):
        await agent_permission.require_operation_permission(
            session, owner, run, closing(ticket.id), None, reducing=True, target=ticket
        )


@pytest.mark.asyncio
@pytest.mark.parametrize("tagged", [True, False])
async def test_a_netting_fill_never_takes_the_position_from_the_agent_that_opened_it(
    task_db: Fixture, tagged: bool
):
    """3.3.4: on a netting account the symbol's one position belongs to the agent whose order
    opened it from flat. B's later fill carries the same position id; the broker's tag of
    A's order names A, and without a tag the oldest entry on that position does."""
    db, owner, _, _ = task_db
    a, b = await two_agents(db, owner)
    now = utcnow()
    async with db.sessions() as session, session.begin():
        session.add_all(
            [
                entry(owner, "open-a", a, now - timedelta(minutes=5), position="P1", order="O1"),
                entry(owner, "fill-b", b, now, position="P1", order="O2"),
            ]
        )
    ticket = TICKET.model_copy(
        update={"id": "P1", "operation_id": broker_operation_tag("open-a") if tagged else None}
    )
    async with db.sessions() as session:
        assert await ticket_agent(session, owner, closing("P1"), ticket) == a
        await closes(session, owner, a, ticket)
        with pytest.raises(LonoraError, match="ticket_not_owned"):
            await closes(session, owner, b, ticket)
    # A later receipt on A's entry (a verification recheck) touches it last: the order
    # it was sent in, not its last update, decides.
    async with db.sessions() as session, session.begin():
        opened = await session.get(TradingJournalRow, "open-a")
        assert opened is not None
        opened.updated_at = now + timedelta(minutes=1)
    async with db.sessions() as session:
        assert await ticket_agent(session, owner, closing("P1"), ticket) == a


@pytest.mark.asyncio
async def test_a_pending_orders_fill_belongs_to_the_agent_that_placed_it(task_db: Fixture):
    """3.3.4: A's buy limit fills into a position that carries the order's ticket and tag,
    and is still A's after B's later fill nets into it."""
    db, owner, _, _ = task_db
    a, b = await two_agents(db, owner)
    now = utcnow()
    async with db.sessions() as session, session.begin():
        session.add_all(
            [
                entry(
                    owner, "limit-a", a, now - timedelta(hours=1), action="buy_limit", order="O7"
                ),
                entry(owner, "fill-b", b, now, position="O7", order="O8"),
            ]
        )
    ticket = TICKET.model_copy(update={"id": "O7", "operation_id": broker_operation_tag("limit-a")})
    async with db.sessions() as session:
        assert await ticket_agent(session, owner, closing("O7"), ticket) == a
        await closes(session, owner, a, ticket)
        with pytest.raises(LonoraError, match="ticket_not_owned"):
            await closes(session, owner, b, ticket)


@pytest.mark.asyncio
@pytest.mark.parametrize("tagged", [True, False])
async def test_an_opening_order_deep_in_the_history_still_names_its_agent(
    task_db: Fixture, tagged: bool
):
    """3.3.4: the agent's opening entry is older than a thousand later entries on the same
    account and symbol (the owner's own orders); the position is still the agent's."""
    db, owner, _, _ = task_db
    a, _ = await two_agents(db, owner)
    start = utcnow() - timedelta(days=30)
    async with db.sessions() as session, session.begin():
        session.add(entry(owner, "open-a", a, start, position="P1", order="O1"))
        session.add_all(
            entry(owner, f"own-{i}", None, start + timedelta(minutes=i + 1), position=f"Q{i}")
            for i in range(1000)
        )
    ticket = TICKET.model_copy(
        update={"id": "P1", "operation_id": broker_operation_tag("open-a") if tagged else None}
    )
    async with db.sessions() as session:
        assert await ticket_agent(session, owner, closing("P1"), ticket) == a
        await closes(session, owner, a, ticket)


@pytest.mark.asyncio
@pytest.mark.parametrize("tagged", [True, False])
async def test_an_opening_order_behind_a_thousand_older_entries_still_names_its_agent(
    task_db: Fixture, tagged: bool
):
    """3.3.4: a thousand entries on the same account and symbol (the owner's own orders) are
    older than the agent's opening entry, so the oldest-first read meets them first; no cap
    cuts the journal short and the position is still the agent's."""
    db, owner, _, _ = task_db
    a, _ = await two_agents(db, owner)
    start = utcnow() - timedelta(days=30)
    async with db.sessions() as session, session.begin():
        session.add_all(
            entry(owner, f"own-{i}", None, start + timedelta(minutes=i), position=f"Q{i}")
            for i in range(1000)
        )
        opened = start + timedelta(minutes=1000)
        session.add(entry(owner, "open-a", a, opened, position="P1", order="O1"))
    ticket = TICKET.model_copy(
        update={"id": "P1", "operation_id": broker_operation_tag("open-a") if tagged else None}
    )
    async with db.sessions() as session:
        assert await ticket_agent(session, owner, closing("P1"), ticket) == a
        await closes(session, owner, a, ticket)


@pytest.mark.asyncio
@pytest.mark.parametrize("tagged", [True, False])
async def test_the_operation_the_broker_names_outranks_an_older_entry_on_the_ticket(
    task_db: Fixture, tagged: bool
):
    """3.3.4: A sent first but B's order filled first and opened the position; A's fill
    netted into it, so A's older entry carries the same position id. The broker reports B's
    operation (its tag, or its raw id) on the ticket, and that decides before any entry that
    only carries the ticket id: B owns it, and A's close is ticket_not_owned."""
    db, owner, _, _ = task_db
    a, b = await two_agents(db, owner)
    now = utcnow()
    async with db.sessions() as session, session.begin():
        session.add_all(
            [
                entry(owner, "fill-a", a, now - timedelta(minutes=5), position="P1", order="O1"),
                entry(owner, "open-b", b, now, position="P1", order="O2"),
            ]
        )
    operation = broker_operation_tag("open-b") if tagged else "open-b"
    ticket = TICKET.model_copy(update={"id": "P1", "operation_id": operation})
    async with db.sessions() as session:
        assert await ticket_agent(session, owner, closing("P1"), ticket) == b
        await closes(session, owner, b, ticket)
        with pytest.raises(LonoraError, match="ticket_not_owned"):
            await closes(session, owner, a, ticket)


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
    ensure, end = management_task(monkeypatch)
    session = AsyncMock()
    session.add = MagicMock()
    session.get.return_value = row
    with pytest.raises(LonoraError, match="trading_mode_full_owner_only"):
        await mode_store.set_trading_mode(session, "owner", "agent", "full", by="agent")
    assert row.trading_mode == "ask"
    ensure.assert_not_awaited()
    await mode_store.set_trading_mode(session, "owner", "agent", "full", by="owner_tap")
    assert row.trading_mode == "full"
    mode_store.authority_lock.assert_awaited_with(session, "agent")  # type: ignore[attr-defined]
    # Full starts the agent's continuous account-management task (4.5.1).
    ensure.assert_awaited_once_with(session, "owner", "agent")
    end.assert_not_awaited()


@pytest.mark.asyncio
async def test_any_agent_may_switch_itself_to_ask(monkeypatch: pytest.MonkeyPatch):
    row = agent("full")
    monkeypatch.setattr(mode_store, "authority_lock", AsyncMock())
    ensure, end = management_task(monkeypatch)
    session = AsyncMock()
    session.add = MagicMock()
    session.get.return_value = row
    assert await mode_store.set_trading_mode(session, "owner", "agent", "ask", by="agent") == "ask"
    assert row.trading_mode == "ask"
    # Ask ends it (4.5.2).
    end.assert_awaited_once_with(session, "owner", "agent")
    ensure.assert_not_awaited()


def management_task(monkeypatch: pytest.MonkeyPatch) -> tuple[AsyncMock, AsyncMock]:
    from lonora_db import management_task as task_store

    ensure, end = AsyncMock(), AsyncMock()
    monkeypatch.setattr(task_store, "ensure_management_task", ensure)
    monkeypatch.setattr(task_store, "end_management_task", end)
    return ensure, end


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
