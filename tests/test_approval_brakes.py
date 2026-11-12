"""Pauses come before approval cards (W15-ACC).

An agent at Ask me (or a trade outside an On its own grant) asks the owner with an
approval card. While a pause holds new risk, a card for a new entry
could only fail after the owner's tap, so the trade tool returns the boundary's own code
instead and no card is raised. Exits are still asked: the executor decides them against
the fresh broker target. Runs on the real migrated PostgreSQL schema and the simulation
broker (skipped without ``LONORA_DATABASE_URL``).
"""

from decimal import Decimal
from typing import Any

import pytest
from lonora_contracts.account import Position
from lonora_core.user_error import LonoraError
from test_proactive_wakes import call, database, retire, simulation


async def refused(context: Any, **arguments: Any) -> str:
    try:
        await call(context, "trade_execute", **arguments)
    except LonoraError as error:
        return error.code
    raise AssertionError("expected a refusal")


@pytest.mark.asyncio
async def test_pauses_refuse_new_entries_before_any_approval_card() -> None:
    database()
    from check_streaming import Fixture
    from lonora_db.schema import TradeApprovalRow
    from sqlalchemy import func, select

    fixture = await Fixture().open()
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

        # A pause the owner set on this market: the entry is refused, no card.
        pause = await fixture.request(
            "POST",
            "/trading/restrictions",
            {"account_id": connection, "symbol": "XAUUSD", "action_class": "no_new_entries"},
        )
        assert await refused(context, **entry) == "trading_restriction_active"
        assert await cards() == 0
        # An exit under the pause is still asked: closing is never held by a pause.
        close = await call(
            context,
            "trade_execute",
            action="close_position",
            account_id=connection,
            symbol="XAUUSD",
            position_id="held-ticket",
        )
        assert close.get("_runtime_wait") and close.get("approval_id"), close
        assert await cards() == 1
        # Lifted: the same entry is asked again with a card, as Ask me promises.
        await fixture.request("POST", f"/trading/restrictions/{pause['id']}/revoke", {"reason": ""})
        asked = await call(context, "trade_execute", **entry)
        assert asked.get("_runtime_wait") and asked.get("approval_id"), asked
        assert await cards() == 2
    finally:
        await retire(fixture, connection)
        await fixture.close()


@pytest.mark.asyncio
async def test_a_first_trade_on_a_fresh_install_is_asked_with_no_start_card() -> None:
    """Lonora has no Stop: a fresh install is never "not started". The first entry an
    agent in Ask is asked for becomes its approval card at once, and no Start card is
    raised."""
    database()
    from check_streaming import Fixture
    from lonora_db.schema import OwnerActionRow, SettingRow
    from sqlalchemy import func, select

    fixture = await Fixture().open()
    connection = ""
    try:
        connection = await simulation(fixture, [])
        async with fixture.runtime.db.sessions() as session:
            assert await session.get(SettingRow, "trading_control") is None
        agent = await fixture.agent("First run", supervised=True)
        context = await fixture.lease(await fixture.run(agent, await fixture.conversation(agent)))
        entry = {
            "action": "buy",
            "account_id": connection,
            "symbol": "XAUUSD",
            "volume": "0.1",
            "stop_loss": "95",
        }
        asked = await call(context, "trade_execute", **entry)
        assert asked.get("_runtime_wait") and asked.get("approval_id"), asked
        async with fixture.runtime.db.sessions() as session:
            cards = await session.scalar(
                select(func.count())
                .select_from(OwnerActionRow)
                .where(OwnerActionRow.run_id == context.lease.run_id)
            )
        assert cards == 0
    finally:
        await retire(fixture, connection)
        await fixture.close()
