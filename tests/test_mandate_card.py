"""The fixed Mandate card (mandate 10.3, 4.2.1, 4.2.3).

It shows the agent's mode read live and one button for the other mode; the owner's tap
applies the mode the button showed. Switching to Full withdraws the agent's pending
Trade Approval cards and wakes it with fixed text; a card is never executed because of a
mode change. Runs on the real migrated PostgreSQL schema and the simulation broker
(skipped without ``LONORA_DATABASE_URL``).
"""

from decimal import Decimal
from typing import Any, cast

import pytest
from lonora_contracts.account import Position
from lonora_contracts.trading import TradingControl
from lonora_core.user_error import LonoraError
from test_proactive_wakes import call, database, retire, simulation


async def tap(fixture: Any, card_id: str, mode: str | None) -> Any:
    body: dict[str, Any] = {"decision": "confirm"}
    if mode is not None:
        body["trading_mode"] = mode
    return await fixture.client.post(f"/api/owner-actions/{card_id}/decision", json=body)


async def mode_of(fixture: Any, agent_id: str) -> str:
    from lonora_db.trading_mode import trading_mode

    async with fixture.runtime.db.sessions() as session:
        return await trading_mode(session, fixture.owner, agent_id)


@pytest.mark.asyncio
async def test_the_mandate_card_switches_the_mode_the_button_showed() -> None:
    database()
    from check_streaming import Fixture

    fixture = await Fixture().open()
    try:
        agent = await fixture.agent("Mandate", supervised=True)
        context = await fixture.lease(await fixture.run(agent, await fixture.conversation(agent)))
        card = (await call(context, "owner_action_propose", kind="trading_mode"))["owner_action"]
        assert card["kind"] == "trading_mode" and card["status"] == "pending", card
        # A repeated proposal returns the card already shown.
        repeat = await call(context, "owner_action_propose", kind="trading_mode")
        assert repeat["owner_action"]["id"] == card["id"] and repeat["already_shown"], repeat
        shown = cast(
            list[dict[str, Any]],
            await fixture.request("GET", f"/owner-actions?thread_id={context.thread_id}"),
        )
        row = next(item for item in shown if item["id"] == card["id"])
        # Read live: the agent's current mode and its name, never the agent's words.
        assert row["facts"]["trading_mode"] == "ask"
        assert row["facts"]["agent"]["id"] == agent["id"]
        # The decision must carry the mode the button showed.
        missing = await tap(fixture, card["id"], None)
        assert missing.status_code == 422, missing.text
        assert await mode_of(fixture, agent["id"]) == "ask"
        full = await tap(fixture, card["id"], "full")
        assert full.status_code == 200, full.text
        assert full.json()["facts"]["trading_mode"] == "full"
        assert full.json()["result"]["trading_mode"] == "full"
        assert await mode_of(fixture, agent["id"]) == "full"
        # The same card stays the switch: the next tap shows Ask and applies Ask.
        ask = await tap(fixture, card["id"], "ask")
        assert ask.status_code == 200, ask.text
        assert await mode_of(fixture, agent["id"]) == "ask"
        assert ask.json()["facts"]["trading_mode"] == "ask"
        # A stale second tap applies what its button showed, never a toggle.
        again = await tap(fixture, card["id"], "ask")
        assert again.status_code == 200 and await mode_of(fixture, agent["id"]) == "ask"
        # Tapped, it no longer waits for the owner, and it is still the agent's switch.
        assert again.json()["status"] == "confirmed"
    finally:
        await fixture.close()


@pytest.mark.asyncio
async def test_only_lonora_raises_the_card_for_another_agent() -> None:
    database()
    from check_streaming import Fixture

    fixture = await Fixture().open()
    try:
        first = await fixture.agent("First", supervised=True)
        second = await fixture.agent("Second", supervised=True)
        context = await fixture.lease(await fixture.run(first, await fixture.conversation(first)))
        with pytest.raises(LonoraError, match="owner_action_trading_mode_agent_forbidden"):
            await call(context, "owner_action_propose", kind="trading_mode", agent_id=second["id"])
    finally:
        await fixture.close()


@pytest.mark.asyncio
async def test_switching_to_full_withdraws_pending_approvals_and_never_executes_them() -> None:
    database()
    from check_streaming import Fixture
    from lonora_db.schema import RunRow, TradeApprovalRow, TradingJournalRow
    from lonora_trading.controls import read_controls, save_controls
    from sqlalchemy import select

    fixture = await Fixture().open()
    original = await read_controls(fixture.runtime.db)
    connection = ""
    try:
        held = Position(
            id="mandate-ticket",
            symbol="XAUUSD",
            side="buy",
            volume=Decimal("0.1"),
            open_price=Decimal(100),
        )
        connection = await simulation(fixture, [held])
        await save_controls(fixture.runtime.db, TradingControl(enabled=True))
        agent = await fixture.agent("Withdraw", supervised=True)
        context = await fixture.lease(await fixture.run(agent, await fixture.conversation(agent)))
        entry = {
            "action": "buy",
            "account_id": connection,
            "symbol": "XAUUSD",
            "volume": "0.1",
            "tolerance": "2",
        }
        asked = await same_call(context, entry)
        assert asked.get("_runtime_wait") and asked.get("approval_id"), asked
        async with fixture.runtime.db.sessions() as session, session.begin():
            # The runtime parks a run that waits on a card.
            waiting = await session.get(RunRow, context.lease.run_id, with_for_update=True)
            assert waiting is not None
            waiting.status = "waiting_input"
        # A second card of the same agent whose run has ended: no run waits on it.
        other = await fixture.lease(await fixture.run(agent, await fixture.conversation(agent)))
        card = (await call(other, "owner_action_propose", kind="trading_mode"))["owner_action"]
        idle = await call(other, "trade_execute", **{**entry, "volume": "0.2"})
        assert idle.get("_runtime_wait") and idle.get("approval_id"), idle
        # A third whose run is still working: it reads the withdrawal itself.
        busy_run = await fixture.lease(await fixture.run(agent, await fixture.conversation(agent)))
        busy = await call(busy_run, "trade_execute", **{**entry, "volume": "0.3"})
        assert busy.get("_runtime_wait") and busy.get("approval_id"), busy
        async with fixture.runtime.db.sessions() as session, session.begin():
            ended = await session.get(RunRow, other.lease.run_id, with_for_update=True)
            assert ended is not None
            ended.status = "completed"
        full = await tap(fixture, card["id"], "full")
        assert full.status_code == 200, full.text
        async with fixture.runtime.db.sessions() as session:
            approval = await session.get(TradeApprovalRow, asked["approval_id"])
            assert approval is not None and approval.status == "withdrawn"
            run = await session.get(RunRow, context.lease.run_id)
            assert run is not None and run.status == "queued"
            # The card no run waited on wakes its agent with fixed server text.
            idle_card = await session.get(TradeApprovalRow, idle["approval_id"])
            assert idle_card is not None and idle_card.status == "withdrawn"
            wake = await session.scalar(
                select(RunRow).where(
                    RunRow.model_metadata["withdrawn_trade_approval_id"].as_string()
                    == idle["approval_id"]
                )
            )
            assert wake is not None and wake.agent_id == agent["id"]
            assert "Your trading mode is now Full" in (wake.prompt or ""), wake.prompt
            # A run still working is never woken a second time for the same request.
            busy_card = await session.get(TradeApprovalRow, busy["approval_id"])
            assert busy_card is not None and busy_card.status == "withdrawn"
            second = await session.scalar(
                select(RunRow).where(
                    RunRow.model_metadata["withdrawn_trade_approval_id"].as_string()
                    == busy["approval_id"]
                )
            )
            assert second is None
            sent = await session.scalar(
                select(TradingJournalRow.operation_id).where(
                    TradingJournalRow.owner_id == fixture.owner,
                    TradingJournalRow.account_id == connection,
                )
            )
            assert sent is None, "A mode change executed a pending card"
        # The waiting call reads fixed server text and decides again under Full.
        context = await fixture.lease({"id": context.lease.run_id, **agent_run(context)})
        answer = await same_call(context, entry)
        assert answer.get("status") == "withdrawn", answer
        assert answer.get("code") == "trade_approval_withdrawn"
        assert "Full" in answer.get("recovery", "")
        # The owner can never approve a withdrawn card.
        late = await fixture.client.post(
            f"/api/trading/approvals/{asked['approval_id']}/decision", json={"decision": "approve"}
        )
        assert late.status_code == 409, late.text
    finally:
        await save_controls(fixture.runtime.db, original)
        await retire(fixture, connection)
        await fixture.close()


async def same_call(context: Any, arguments: dict[str, Any]) -> dict[str, Any]:
    """The runtime resumes a waiting call with the same call id."""
    from lonora_adapter_kit.types import ToolCall
    from lonora_tools.loader import load_tools

    return await load_tools().execute(
        ToolCall(id="mandate-trade-call", name="trade_execute", arguments=arguments), context
    )


def agent_run(context: Any) -> dict[str, Any]:
    return {"agent_id": context.agent_id, "thread_id": context.thread_id}


@pytest.mark.asyncio
async def test_a_switch_to_full_while_a_card_is_prepared_decides_under_full(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The card insert re-reads the mode under the authority lock: a card raised after
    the switch would never be withdrawn, so the request is decided under Full."""
    database()
    from check_streaming import Fixture
    from lonora_db.schema import TradeApprovalRow
    from lonora_db.trading_mode import set_trading_mode
    from lonora_tools import trade
    from lonora_trading.controls import read_controls, save_controls
    from sqlalchemy import func, select

    fixture = await Fixture().open()
    original = await read_controls(fixture.runtime.db)
    connection = ""
    try:
        connection = await simulation(fixture, [])
        await save_controls(fixture.runtime.db, TradingControl(enabled=True))
        agent = await fixture.agent("Race", supervised=True)
        context = await fixture.lease(await fixture.run(agent, await fixture.conversation(agent)))
        prepare = trade.reviewed_contracts

        async def owner_taps_full_meanwhile(*args: Any) -> Any:
            async with fixture.runtime.db.sessions() as session, session.begin():
                await set_trading_mode(session, fixture.owner, agent["id"], "full", by="owner_tap")
            return await prepare(*args)

        monkeypatch.setattr(trade, "reviewed_contracts", owner_taps_full_meanwhile)
        entry = {
            "action": "buy",
            "account_id": connection,
            "symbol": "XAUUSD",
            "volume": "0.1",
            "tolerance": "2",
        }
        result = await call(context, "trade_execute", **entry)
        assert result.get("status") == "confirmed" and "approval_id" not in result, result
        async with fixture.runtime.db.sessions() as session:
            cards = await session.scalar(
                select(func.count())
                .select_from(TradeApprovalRow)
                .where(TradeApprovalRow.run_id == context.lease.run_id)
            )
        assert cards == 0
    finally:
        await save_controls(fixture.runtime.db, original)
        await retire(fixture, connection)
        await fixture.close()


@pytest.mark.asyncio
async def test_the_card_is_refreshed_when_the_mode_changes_elsewhere() -> None:
    database()
    from check_streaming import Fixture
    from lonora_db.schema import EventRow
    from sqlalchemy import select

    fixture = await Fixture().open()
    try:
        agent = await fixture.agent("Live", supervised=True)
        context = await fixture.lease(await fixture.run(agent, await fixture.conversation(agent)))
        card = (await call(context, "owner_action_propose", kind="trading_mode"))["owner_action"]
        assert (await tap(fixture, card["id"], "full")).status_code == 200
        async with fixture.runtime.db.sessions() as session:
            before = await session.scalar(select(EventRow.cursor).order_by(EventRow.cursor.desc()))
        # The agent switches itself to Ask: its card's conversation hears of it.
        assert (await call(context, "trading_mode_ask"))["trading_mode"] == "ask"
        async with fixture.runtime.db.sessions() as session:
            events = list(
                await session.scalars(
                    select(EventRow).where(
                        EventRow.cursor > (before or 0), EventRow.kind == "owner_action.updated"
                    )
                )
            )
        assert any(event.payload.get("id") == card["id"] for event in events), events
        shown = cast(
            list[dict[str, Any]],
            await fixture.request("GET", f"/owner-actions?thread_id={context.thread_id}"),
        )
        assert next(row for row in shown if row["id"] == card["id"])["facts"]["trading_mode"] == (
            "ask"
        )
    finally:
        await fixture.close()


@pytest.mark.asyncio
async def test_lonoras_card_for_a_deleted_agent_ends_with_it() -> None:
    database()
    from check_streaming import Fixture
    from lonora_db.schema import AgentRow
    from sqlalchemy import select

    fixture = await Fixture().open()
    try:
        async with fixture.runtime.db.sessions() as session:
            lonora = await session.scalar(
                select(AgentRow).where(
                    AgentRow.owner_id == fixture.owner, AgentRow.role == "personal"
                )
            )
        assert lonora is not None
        team = await fixture.agent("Team", supervised=True)
        personal = {"id": lonora.id}
        context = await fixture.lease(
            await fixture.run(personal, await fixture.conversation(personal))
        )
        card = (
            await call(context, "owner_action_propose", kind="trading_mode", agent_id=team["id"])
        )["owner_action"]
        await fixture.request("DELETE", "/agents/" + team["id"])
        fixture.agents.remove(team["id"])
        shown = cast(
            list[dict[str, Any]],
            await fixture.request("GET", f"/owner-actions?thread_id={context.thread_id}"),
        )
        row = next(item for item in shown if item["id"] == card["id"])
        assert row["status"] != "pending", row
    finally:
        await fixture.close()


@pytest.mark.asyncio
async def test_lonora_offers_its_own_mandate_card_at_onboarding() -> None:
    """4.3.1: Lonora starts in Ask and offers its Mandate card during onboarding."""
    database()
    from check_streaming import Fixture
    from lonora_db.personal_agent import ensure_personal_agent
    from lonora_db.schema import OwnerActionRow
    from lonora_db.threads import conversation_thread
    from sqlalchemy import select

    fixture = await Fixture().open()
    try:
        async with fixture.runtime.db.sessions() as session, session.begin():
            lonora = await ensure_personal_agent(session, fixture.owner)
            thread = await conversation_thread(session, fixture.owner, lonora.id)
            cards = list(
                await session.scalars(
                    select(OwnerActionRow).where(
                        OwnerActionRow.owner_id == fixture.owner,
                        OwnerActionRow.kind == "trading_mode",
                        OwnerActionRow.subject == "trading_mode:" + lonora.id,
                    )
                )
            )
            # Asked again, no second card.
            await ensure_personal_agent(session, fixture.owner)
        assert [(c.subject, c.thread_id, c.status) for c in cards] == [
            ("trading_mode:" + lonora.id, thread.id, "pending")
        ], cards
        assert await mode_of(fixture, lonora.id) == "ask"
        tapped = await tap(fixture, cards[0].id, "full")
        assert tapped.status_code == 200, tapped.text
        assert await mode_of(fixture, lonora.id) == "full"
    finally:
        await fixture.close()
