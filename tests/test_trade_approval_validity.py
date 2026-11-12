"""Trade Approval validity (mandate 10.3, 10.3.1, 14.3.9).

A card shows the agent's reason (labelled as the agent's words) and a tolerance; a
risk-increasing request in Ask without a tolerance is refused (`tolerance_required`). The
reference price is the executable side when the card is created; the first quote outside
reference ± tolerance marks the card `drifted` and wakes the agent with fixed text. A card
has no time limit. Reason, tolerance and judgment label are stored beside the request and
never change the operation id or the fingerprint. Runs on the real migrated PostgreSQL
schema and the simulation broker (skipped without ``LONORA_DATABASE_URL``).
"""

from typing import Any

import pytest
from lonora_adapter_kit.types import ToolCall
from lonora_contracts.domain import utcnow
from lonora_contracts.trading import TradingControl
from lonora_core.user_error import LonoraError, ToolRefusal
from lonora_tools.loader import load_tools
from test_proactive_wakes import call, database, retire, simulation


async def same_call(context: Any, identity: str, **arguments: Any) -> dict[str, Any]:
    return await load_tools().execute(
        ToolCall(id=identity, name="trade_execute", arguments=arguments), context
    )


async def set_quote(fixture: Any, connection: str, bid: str, ask: str) -> None:
    from lonora_db.schema import TradingAccountRow

    async with fixture.runtime.db.sessions() as session, session.begin():
        account = await session.get(TradingAccountRow, connection, with_for_update=True)
        assert account is not None
        account.payload = {
            **account.payload,
            "quotes": {
                "XAUUSD": {
                    "symbol": "XAUUSD",
                    "bid": bid,
                    "ask": ask,
                    "observed_at": utcnow().isoformat(),
                    "source": "drift-fixture",
                }
            },
        }


ENTRY = {"action": "buy", "symbol": "XAUUSD", "volume": "0.1", "stop_loss": "95"}


@pytest.mark.asyncio
async def test_a_card_carries_reason_and_tolerance_and_drifts_once_outside() -> None:
    database()
    from check_streaming import Fixture
    from lonora_db.schema import RunRow, TradeApprovalRow
    from lonora_trading.approval_drift import check_drift
    from lonora_trading.controls import read_controls, save_controls

    fixture = await Fixture().open()
    original = await read_controls(fixture.runtime.db)
    connection = ""
    try:
        connection = await simulation(fixture, [])
        await save_controls(fixture.runtime.db, TradingControl(enabled=True))
        agent = await fixture.agent("Validity", supervised=True)
        context = await fixture.lease(await fixture.run(agent, await fixture.conversation(agent)))
        entry = {**ENTRY, "account_id": connection}
        # Ask without a tolerance: refused before any card, with what to add.
        with pytest.raises(ToolRefusal, match="tolerance_required"):
            await same_call(context, "no-tolerance", **entry, reason="Breakout above 100")
        asked = await same_call(
            context,
            "with-tolerance",
            **entry,
            reason="Breakout above 100",
            tolerance="1.5",
        )
        assert asked.get("_runtime_wait") and asked.get("approval_id"), asked
        shown = await fixture.request("GET", f"/trading/approvals?thread_id={context.thread_id}")
        card = next(row for row in shown if row["id"] == asked["approval_id"])  # type: ignore[union-attr]
        assert card["reason"] == "Breakout above 100"
        assert card["tolerance"] == "1.5"
        # The executable side of a buy when the card was made: the ask.
        assert card["reference_price"] == "101"
        assert card["expires_at"] is None, "A card has no time limit"
        # Reason, tolerance and label are not part of the request or its identity.
        assert set(card["requests"][0]) >= {"operation_id", "symbol"}
        assert "reason" not in card["requests"][0] and "tolerance" not in card["requests"][0]
        async with fixture.runtime.db.sessions() as session, session.begin():
            waiting = await session.get(RunRow, context.lease.run_id, with_for_update=True)
            assert waiting is not None
            waiting.status = "waiting_input"
        brokers = fixture.runtime.services(fixture.owner).brokers
        # Inside reference ± tolerance: nothing happens.
        await set_quote(fixture, connection, "101.5", "102.5")
        assert await check_drift(fixture.runtime.db, brokers, fixture.owner) == 0
        # The first quote outside it marks the card drifted and wakes the agent.
        await set_quote(fixture, connection, "102", "103")
        assert await check_drift(fixture.runtime.db, brokers, fixture.owner) == 1
        assert await check_drift(fixture.runtime.db, brokers, fixture.owner) == 0
        async with fixture.runtime.db.sessions() as session:
            row = await session.get(TradeApprovalRow, asked["approval_id"])
            assert row is not None and row.status == "drifted"
            run = await session.get(RunRow, context.lease.run_id)
            assert run is not None and run.status == "queued"
        late = await fixture.client.post(
            f"/api/trading/approvals/{asked['approval_id']}/decision",
            json={"decision": "approve"},
        )
        assert late.status_code == 409, late.text
        context = await fixture.lease(
            {"id": context.lease.run_id, "agent_id": agent["id"], "thread_id": context.thread_id}
        )
        answer = await same_call(
            context,
            "with-tolerance",
            **entry,
            reason="Breakout above 100",
            tolerance="1.5",
        )
        assert answer["status"] == "drifted" and answer["code"] == "trade_approval_drifted"
        assert "outside" in answer["recovery"] and asked["approval_id"] in answer["recovery"]
    finally:
        await save_controls(fixture.runtime.db, original)
        await retire(fixture, connection)
        await fixture.close()


@pytest.mark.asyncio
async def test_approve_reads_the_quote_and_refuses_a_card_outside_its_band() -> None:
    """10.3.1.2: a drifted card cannot be approved, even before the watcher's next tick."""
    database()
    from check_streaming import Fixture
    from lonora_db.schema import RunRow, TradeApprovalRow
    from lonora_trading.controls import read_controls, save_controls

    fixture = await Fixture().open()
    original = await read_controls(fixture.runtime.db)
    connection = ""
    try:
        connection = await simulation(fixture, [])
        await save_controls(fixture.runtime.db, TradingControl(enabled=True))
        agent = await fixture.agent("Validity at approve", supervised=True)
        context = await fixture.lease(await fixture.run(agent, await fixture.conversation(agent)))
        asked = await same_call(
            context, "band", **ENTRY, account_id=connection, reason="Retest", tolerance="10"
        )
        assert asked.get("approval_id"), asked
        shown = await fixture.request("GET", f"/trading/approvals?thread_id={context.thread_id}")
        card = next(row for row in shown if row["id"] == asked["approval_id"])  # type: ignore[union-attr]
        # Plain decimals, never an exponent ("1E+1").
        assert card["tolerance"] == "10", card
        async with fixture.runtime.db.sessions() as session, session.begin():
            waiting = await session.get(RunRow, context.lease.run_id, with_for_update=True)
            assert waiting is not None
            waiting.status = "waiting_input"
        await set_quote(fixture, connection, "120", "121")
        tapped = await fixture.client.post(
            f"/api/trading/approvals/{asked['approval_id']}/decision",
            json={"decision": "approve"},
        )
        assert tapped.status_code == 409 and "trade_approval_drifted" in tapped.text, tapped.text
        async with fixture.runtime.db.sessions() as session:
            row = await session.get(TradeApprovalRow, asked["approval_id"])
            assert row is not None and row.status == "drifted"
    finally:
        await save_controls(fixture.runtime.db, original)
        await retire(fixture, connection)
        await fixture.close()


@pytest.mark.asyncio
async def test_a_reused_card_that_ended_is_decided_again_with_its_tolerance(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """10.3.1.1: the card the same request reused drifted before the locked read; the
    request is decided from the start, so it never parks on a card without validity."""
    database()
    from check_streaming import Fixture
    from lonora_tools import trade
    from lonora_trading.controls import read_controls, save_controls

    fixture = await Fixture().open()
    original = await read_controls(fixture.runtime.db)
    connection = ""
    try:
        connection = await simulation(fixture, [])
        await save_controls(fixture.runtime.db, TradingControl(enabled=True))
        agent = await fixture.agent("Validity reuse", supervised=True)
        context = await fixture.lease(await fixture.run(agent, await fixture.conversation(agent)))
        answers = iter([True])
        real = trade.reused_card

        async def ended(context: Any, requests: Any) -> bool:
            return next(answers, None) or await real(context, requests)

        monkeypatch.setattr(trade, "reused_card", ended)
        with pytest.raises(ToolRefusal, match="tolerance_required"):
            await same_call(context, "reuse", **ENTRY, account_id=connection, reason="Retest")
    finally:
        await save_controls(fixture.runtime.db, original)
        await retire(fixture, connection)
        await fixture.close()


@pytest.mark.asyncio
async def test_the_reason_never_changes_the_operation_and_the_journal_keeps_it() -> None:
    database()
    from check_streaming import Fixture
    from lonora_db.schema import TradingJournalRow
    from lonora_db.trading_mode import set_trading_mode
    from lonora_trading.controls import read_controls, save_controls

    fixture = await Fixture().open()
    original = await read_controls(fixture.runtime.db)
    connection = ""
    try:
        connection = await simulation(fixture, [])
        await save_controls(fixture.runtime.db, TradingControl(enabled=True))
        agent = await fixture.agent("Annotated", supervised=True)
        async with fixture.runtime.db.sessions() as session, session.begin():
            await set_trading_mode(session, fixture.owner, agent["id"], "full", by="owner_tap")
        context = await fixture.lease(await fixture.run(agent, await fixture.conversation(agent)))
        entry = {**ENTRY, "account_id": connection}
        first = await call(context, "trade_execute", **entry, reason="First")
        assert first["status"] == "confirmed", first
        # Only the reason differs: the same operation, answered from its receipt.
        again = await call(context, "trade_execute", **entry, reason="Second wording")
        assert again["operation_id"] == first["operation_id"]
        async with fixture.runtime.db.sessions() as session:
            row = await session.get(TradingJournalRow, first["operation_id"])
            assert row is not None
            assert row.annotation == {"reason": "First", "label": None, "tolerance": None}
            assert "reason" not in row.request
    finally:
        await save_controls(fixture.runtime.db, original)
        await retire(fixture, connection)
        await fixture.close()


@pytest.mark.asyncio
async def test_the_agent_withdraws_its_own_card() -> None:
    database()
    from check_streaming import Fixture
    from lonora_db.schema import RunRow, TradeApprovalRow
    from sqlalchemy import func, select
    from lonora_trading.controls import read_controls, save_controls

    fixture = await Fixture().open()
    original = await read_controls(fixture.runtime.db)
    connection = ""
    try:
        connection = await simulation(fixture, [])
        await save_controls(fixture.runtime.db, TradingControl(enabled=True))
        agent = await fixture.agent("Withdraws", supervised=True)
        context = await fixture.lease(await fixture.run(agent, await fixture.conversation(agent)))
        asked = await call(
            context,
            "trade_execute",
            **{**ENTRY, "account_id": connection},
            reason="Range low",
            tolerance="2",
        )
        assert asked.get("approval_id"), asked
        other = await fixture.agent("Other", supervised=True)
        stranger = await fixture.lease(await fixture.run(other, await fixture.conversation(other)))
        with pytest.raises(LonoraError, match="trade_approval_not_found"):
            await call(stranger, "trade_approval_withdraw", approval_id=asked["approval_id"])
        # A later run withdraws the card its ended run raised: no wake for what it knows.
        async with fixture.runtime.db.sessions() as session, session.begin():
            ended = await session.get(RunRow, context.lease.run_id, with_for_update=True)
            assert ended is not None
            ended.status = "completed"
        later = await fixture.lease(await fixture.run(agent, {"id": context.thread_id}))
        runs = select(func.count()).select_from(RunRow).where(RunRow.agent_id == agent["id"])
        async with fixture.runtime.db.sessions() as session:
            before = await session.scalar(runs)
        done = await call(later, "trade_approval_withdraw", approval_id=asked["approval_id"])
        assert done["status"] == "withdrawn"
        async with fixture.runtime.db.sessions() as session:
            assert await session.scalar(runs) == before, "A self-withdrawal woke the agent"
        async with fixture.runtime.db.sessions() as session:
            row = await session.get(TradeApprovalRow, asked["approval_id"])
            assert row is not None and row.status == "withdrawn"
        late = await fixture.client.post(
            f"/api/trading/approvals/{asked['approval_id']}/decision",
            json={"decision": "approve"},
        )
        assert late.status_code == 409
    finally:
        await save_controls(fixture.runtime.db, original)
        await retire(fixture, connection)
        await fixture.close()
