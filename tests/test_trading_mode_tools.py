"""The trade tools under the trading mode (mandate 4.1, 3.3.4, 6.2, 6.3).

Full and the Ask risk-reducing path execute without a card; a ticket the agent's own
journaled order did not open still waits for the owner's card in either mode; a close-all
freezes the set it read, so a replay never extends it. Runs on the real migrated
PostgreSQL schema and the simulation broker (skipped without ``LONORA_DATABASE_URL``).
"""

from decimal import Decimal
from typing import Any

import pytest
from lonora_adapter_kit.types import ToolCall
from lonora_contracts.account import Position
from lonora_contracts.trading import TradingControl
from lonora_tools.loader import load_tools
from test_proactive_wakes import call, database, retire, simulation


async def same_call(context: Any, identity: str, name: str, **arguments: Any) -> dict[str, Any]:
    """A replay of one call: the same call id, as the runtime replays it."""
    return await load_tools().execute(
        ToolCall(id=identity, name=name, arguments=arguments), context
    )


@pytest.mark.asyncio
async def test_full_closes_its_own_positions_without_a_card_and_never_extends_a_replay() -> None:
    database()
    from check_streaming import Fixture
    from lonora_db.schema import TradeApprovalRow
    from lonora_db.trading_mode import set_trading_mode
    from lonora_trading.controls import read_controls, save_controls
    from sqlalchemy import func, select

    fixture = await Fixture().open()
    original = await read_controls(fixture.runtime.db)
    connection = ""
    try:
        connection = await simulation(fixture, [])
        await save_controls(fixture.runtime.db, TradingControl(enabled=True))
        agent = await fixture.agent("Full", supervised=True)
        async with fixture.runtime.db.sessions() as session, session.begin():
            await set_trading_mode(session, fixture.owner, agent["id"], "full", by="owner_tap")
        context = await fixture.lease(await fixture.run(agent, await fixture.conversation(agent)))
        entry = {"action": "buy", "account_id": connection, "symbol": "XAUUSD", "stop_loss": "95"}
        for volume in ("0.1", "0.2"):
            opened = await call(context, "trade_execute", **entry, volume=volume)
            assert opened.get("status") == "confirmed" and "approval_id" not in opened, opened
        broker = await fixture.runtime.services(fixture.owner).brokers.get(
            fixture.owner, connection
        )
        own = sorted(position.id for position in await broker.positions())
        assert len(own) == 2
        closed = await same_call(
            context, "close-all", "trade_close_positions", account_id=connection
        )
        assert "approval_id" not in closed, closed
        assert [item["status"] for item in closed["results"]] == ["confirmed", "confirmed"]
        later = await call(context, "trade_execute", **entry, volume="0.3")
        assert later.get("status") == "confirmed", later
        # The same call replayed answers from its frozen set: nothing new is closed.
        replayed = await same_call(
            context, "close-all", "trade_close_positions", account_id=connection
        )
        assert replayed["results"] == closed["results"]
        assert [position.id for position in await broker.positions()] == [later["broker_id"]]
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
@pytest.mark.parametrize("mode", ["full", "ask"])
async def test_the_owners_own_ticket_is_not_the_agents_unless_an_exception_holds(
    mode: str,
) -> None:
    """3.3.4: ticket_not_owned in either mode, never a card; the owner's standing
    instruction and Lonora are exceptions."""
    database()
    from check_streaming import Fixture
    from lonora_core.user_error import LonoraError
    from lonora_db.schema import AgentRow
    from lonora_db.trading_mode import set_trading_mode
    from lonora_trading.controls import read_controls, save_controls
    from sqlalchemy import select

    fixture = await Fixture().open()
    original = await read_controls(fixture.runtime.db)
    connection = ""
    try:
        manual = Position(
            id="owner-terminal-ticket",
            symbol="XAUUSD",
            side="buy",
            volume=Decimal("0.2"),
            open_price=Decimal(100),
            stop_loss=Decimal(90),
        )
        connection = await simulation(fixture, [manual])
        await save_controls(fixture.runtime.db, TradingControl(enabled=True))
        agent = await fixture.agent("Owner ticket " + mode, supervised=True)
        if mode == "full":
            async with fixture.runtime.db.sessions() as session, session.begin():
                await set_trading_mode(session, fixture.owner, agent["id"], "full", by="owner_tap")
        context = await fixture.lease(await fixture.run(agent, await fixture.conversation(agent)))
        for arguments in (
            {"action": "close_position", "position_id": manual.id},
            {"action": "modify_position", "position_id": manual.id, "stop_loss": "95"},
        ):
            with pytest.raises(LonoraError, match="ticket_not_owned"):
                await call(
                    context, "trade_execute", account_id=connection, symbol="XAUUSD", **arguments
                )
        # A close-all reaches only the agent's own tickets: the owner's is refused alone.
        batch = await call(context, "trade_close_positions", account_id=connection)
        assert "approval_id" not in batch, batch
        assert [item["code"] for item in batch["results"]] == ["ticket_not_owned"]
        # The standing instruction is recorded only from the owner's typed words.
        with pytest.raises(LonoraError, match="owner_message_required"):
            await call(context, "positions_manage_all", enabled=True)
        async with fixture.runtime.db.sessions() as session, session.begin():
            row = await session.get(AgentRow, agent["id"])
            assert row is not None
            row.manages_all_positions = True
        partial = await call(
            context,
            "trade_execute",
            account_id=connection,
            symbol="XAUUSD",
            action="close_position",
            position_id=manual.id,
            volume="0.1",
        )
        assert partial.get("status") == "confirmed" and "approval_id" not in partial, partial
        # Lonora acts on any ticket.
        async with fixture.runtime.db.sessions() as session:
            lonora = await session.scalar(
                select(AgentRow).where(
                    AgentRow.owner_id == fixture.owner, AgentRow.role == "personal"
                )
            )
        assert lonora is not None
        personal = {"id": lonora.id}
        lead = await fixture.lease(
            await fixture.run(personal, await fixture.conversation(personal))
        )
        closed = await call(
            lead,
            "trade_execute",
            account_id=connection,
            symbol="XAUUSD",
            action="close_position",
            position_id=manual.id,
        )
        assert closed.get("status") == "confirmed", closed
    finally:
        await save_controls(fixture.runtime.db, original)
        await retire(fixture, connection)
        await fixture.close()
