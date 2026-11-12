"""Brakes come before approval cards (W15-ACC).

An agent in Ask (or a trade outside an On its own grant) asks the owner with an
approval card. While Stop new trading or a pause holds new risk, a card for a new entry
could only fail after the owner's tap, so the trade tool returns the boundary's own code
instead and no card is raised. Exits are still asked: the executor decides them against
the fresh broker target. Runs on the real migrated PostgreSQL schema and the simulation
broker (skipped without ``LONORA_DATABASE_URL``).
"""

from decimal import Decimal
from typing import Any

import pytest
from lonora_contracts.account import Position
from lonora_contracts.trading import TradingControl
from lonora_core.user_error import LonoraError
from test_proactive_wakes import call, database, retire, simulation


async def refused(context: Any, **arguments: Any) -> str:
    try:
        await call(context, "trade_execute", **arguments)
    except LonoraError as error:
        return error.code
    raise AssertionError("expected a refusal")


@pytest.mark.asyncio
async def test_stop_and_pauses_refuse_new_entries_before_any_approval_card() -> None:
    database()
    from check_streaming import Fixture
    from lonora_db.schema import TradeApprovalRow
    from lonora_trading.controls import read_controls, save_controls
    from sqlalchemy import func, select

    fixture = await Fixture().open()
    original = await read_controls(fixture.runtime.db)
    connection = ""
    try:
        held = Position(
            id="held-ticket",
            symbol="XAUUSD",
            side="buy",
            volume=Decimal("0.1"),
            open_price=Decimal(100),
            stop_loss=Decimal(95),
        )
        connection = await simulation(fixture, [held])
        agent = await fixture.agent("Ask me", supervised=True)
        context = await fixture.lease(await fixture.run(agent, await fixture.conversation(agent)))
        entry = {
            "action": "buy",
            "account_id": connection,
            "symbol": "XAUUSD",
            "volume": "0.1",
            "stop_loss": "95",
        }

        async def cards() -> int:
            async with fixture.runtime.db.sessions() as session:
                return int(
                    await session.scalar(
                        select(func.count())
                        .select_from(TradeApprovalRow)
                        .where(TradeApprovalRow.run_id == context.lease.run_id)
                    )
                    or 0
                )

        # The owner's own Stop new trading refuses the entry, no card. (Saving the stopped
        # default on an install that never started stores nothing: that case offers the
        # Start trading card, below.)
        await save_controls(fixture.runtime.db, TradingControl(enabled=True))
        await save_controls(fixture.runtime.db, TradingControl(enabled=False))
        assert await refused(context, **entry) == "trading_disabled"
        await save_controls(fixture.runtime.db, TradingControl(enabled=True, emergency_stop=True))
        assert await refused(context, **entry) == "emergency_stop"
        assert await cards() == 0
        # A pause the owner set on this market: the entry is refused, no card.
        await save_controls(fixture.runtime.db, TradingControl(enabled=True))
        pause = await fixture.request(
            "POST",
            "/trading/restrictions",
            {"account_id": connection, "symbol": "XAUUSD", "action_class": "no_new_entries"},
        )
        assert await refused(context, **entry) == "trading_restriction_active"
        assert await cards() == 0
        # An exit under the pause is never held by a pause. This ticket was opened outside
        # Lonora (the owner's own), so the agent may not act on it at all (3.3.4).
        close = {
            "action": "close_position",
            "account_id": connection,
            "symbol": "XAUUSD",
            "position_id": "held-ticket",
        }
        assert await refused(context, **close) == "ticket_not_owned"
        assert await cards() == 0
        # Lifted: the same entry is asked again with a card, as Ask me promises.
        await fixture.request("POST", f"/trading/restrictions/{pause['id']}/revoke", {"reason": ""})
        asked = await call(context, "trade_execute", **entry)
        assert asked.get("_runtime_wait") and asked.get("approval_id"), asked
        assert await cards() == 1
    finally:
        await save_controls(fixture.runtime.db, original)
        await retire(fixture, connection)
        await fixture.close()


@pytest.mark.asyncio
async def test_a_first_trade_on_a_fresh_install_raises_the_start_trading_card() -> None:
    """Trading starts stopped by default, not by the owner's Stop: the first entry an
    agent is asked for is not sent and not asked as an approval, but the one-tap Start
    trading card appears in the conversation at once (once per request)."""
    database()
    from check_streaming import Fixture
    from lonora_db.schema import OwnerActionRow, SettingRow, TradeApprovalRow
    from lonora_trading.controls import read_controls, save_controls
    from sqlalchemy import func, select

    fixture = await Fixture().open()
    original = await read_controls(fixture.runtime.db)
    connection = ""
    try:
        connection = await simulation(fixture, [])
        async with fixture.runtime.db.sessions() as session, session.begin():
            # A fresh install: no stored control at all.
            stored = await session.get(SettingRow, "trading_control")
            if stored is not None:
                await session.delete(stored)
        agent = await fixture.agent("First run", supervised=True)
        context = await fixture.lease(await fixture.run(agent, await fixture.conversation(agent)))
        entry = {
            "action": "buy",
            "account_id": connection,
            "symbol": "XAUUSD",
            "volume": "0.1",
            "stop_loss": "95",
        }
        first = await call(context, "trade_execute", **entry)
        assert first["code"] == "trading_not_started", first
        assert first["owner_action"]["kind"] == "resume_trading", first
        again = await call(context, "trade_execute", **entry)
        assert again["owner_action"]["id"] == first["owner_action"]["id"], again
        async with fixture.runtime.db.sessions() as session:
            approvals = await session.scalar(
                select(func.count())
                .select_from(TradeApprovalRow)
                .where(TradeApprovalRow.run_id == context.lease.run_id)
            )
            card = await session.get(OwnerActionRow, first["owner_action"]["id"])
        assert approvals == 0 and card is not None and card.status == "pending"
        # One tap starts trading; the same entry is then asked as Ask me promises.
        decided = await fixture.request(
            "POST", f"/owner-actions/{card.id}/decision", {"decision": "confirm"}
        )
        assert decided["result"]["started"] is True, decided
        asked = await call(context, "trade_execute", **entry)
        assert asked.get("_runtime_wait") and asked.get("approval_id"), asked
        # After the owner's own Stop it stays the owner's brake: the refusal, no card.
        await save_controls(fixture.runtime.db, TradingControl(enabled=False))
        assert await refused(context, **{**entry, "volume": "0.2"}) == "trading_disabled"
    finally:
        await save_controls(fixture.runtime.db, original)
        await retire(fixture, connection)
        await fixture.close()
