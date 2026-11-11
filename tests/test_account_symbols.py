"""What a read learned about an account's symbols is kept with the account and shown
before the next Run's first call."""

from datetime import timedelta
from typing import Any

import pytest
from lonora_agent.context.account_symbols import NOTE, account_symbols_context
from lonora_contracts.domain import utcnow
from lonora_db.broker_sessions import (
    SYMBOL_MAP_ENTRIES,
    account_symbols,
    learn_symbol,
)
from lonora_db.client import Database
from lonora_db.schema import AgentRow, BrokerSessionRow
from lonora_tools.symbols import remember_resolution
from test_task_runtime import task_db as task_db

Fixture = tuple[Database, str, str, str]
IDENTITY = {"login": "12345", "server": "Exness-MT5Trial16", "platform": "mt5"}


async def account(db: Database, owner: str, **identity: str) -> str:
    async with db.sessions() as session, session.begin():
        row = BrokerSessionRow(owner_id=owner, payload={"provider": "metaapi"})
        session.add(row)
        await session.flush()
        row.state = {
            "market_health": {"state": "healthy"},
            **(
                {"broker_identity": {**identity, "connection_version": row.version}}
                if identity
                else {}
            ),
        }
        return row.id


async def stored(db: Database, account_id: str) -> BrokerSessionRow:
    async with db.sessions() as session:
        row = await session.get(BrokerSessionRow, account_id)
        assert row is not None
        return row


async def learn(db: Database, owner: str, account_id: str, *args: Any) -> None:
    async with db.sessions() as session, session.begin():
        await learn_symbol(session, owner, account_id, *args)


@pytest.mark.asyncio
async def test_a_confirmed_name_is_kept_with_the_account_and_nothing_else_is_touched(
    task_db: Fixture,
) -> None:
    db, owner, _agent, _thread = task_db
    gold = await account(db, owner, **IDENTITY, broker="Exness Technologies Ltd")
    version = (await stored(db, gold)).version
    await learn(db, owner, gold, "الذَّهب", "XAUUSDm", "Gold vs US Dollar")
    await learn(db, owner, gold, "Gold", "XAUUSDm")
    row = await stored(db, gold)
    # Folded as the owner's search folds, so one word is one entry.
    assert {word: entry["symbol"] for word, entry in account_symbols(row).items()} == {
        "الذهب": "XAUUSDm",
        "gold": "XAUUSDm",
    }
    assert account_symbols(row)["الذهب"]["description"] == "Gold vs US Dollar"
    # A note: the connection is not reconnected, no send is fenced out, nothing else is lost.
    assert row.version == version and row.state["market_health"] == {"state": "healthy"}
    assert row.state["broker_identity"]["login"] == "12345"
    first = account_symbols(row)["gold"]["at"]
    await learn(db, owner, gold, "gold", "XAUUSDm")
    assert account_symbols(await stored(db, gold))["gold"]["at"] == first
    # A read that later finds several contracts for the word makes the account forget it.
    await learn(db, owner, gold, "gold", None)
    assert set(account_symbols(await stored(db, gold))) == {"الذهب"}


@pytest.mark.asyncio
async def test_the_map_is_not_shown_for_another_account_an_old_read_or_an_unread_account(
    task_db: Fixture,
) -> None:
    db, owner, _agent, _thread = task_db
    gold = await account(db, owner, **IDENTITY)
    unread = await account(db, owner)
    await learn(db, owner, gold, "gold", "XAUUSDm")
    await learn(db, owner, unread, "gold", "XAUUSDm")
    await learn(db, owner, "no-such-account", "gold", "XAUUSDm")
    # An account the broker has not reported has no identity to keep a map under.
    assert "symbol_map" not in (await stored(db, unread)).state
    row = await stored(db, gold)
    assert account_symbols(row, utcnow() + timedelta(days=29)) != {}
    assert account_symbols(row, utcnow() + timedelta(days=31)) == {}
    async with db.sessions() as session, session.begin():
        moved = await session.get(BrokerSessionRow, gold)
        assert moved is not None
        # The connection now points at another login: what the old account listed is gone.
        moved.state = {
            **moved.state,
            "broker_identity": {**moved.state["broker_identity"], "login": "999"},
        }
    assert account_symbols(await stored(db, gold)) == {}
    await learn(db, owner, gold, "eurusd", "EURUSDm")
    assert set(account_symbols(await stored(db, gold))) == {"eurusd"}
    for index in range(SYMBOL_MAP_ENTRIES + 5):
        await learn(db, owner, gold, f"pair{index}", f"PAIR{index}m")
    kept = account_symbols(await stored(db, gold))
    assert len(kept) == SYMBOL_MAP_ENTRIES and "eurusd" not in kept


@pytest.mark.asyncio
async def test_only_a_single_confirmed_read_is_remembered(task_db: Fixture) -> None:
    db, owner, _agent, _thread = task_db
    gold = await account(db, owner, **IDENTITY)
    arguments = {"account_id": gold}
    resolution = {"requested": "gold", "symbol": "XAUUSDm", "description": "Gold vs US Dollar"}
    await remember_resolution(db, owner, arguments, {"symbol_resolution": resolution})
    assert account_symbols(await stored(db, gold)) == {}
    confirmed = {"symbol_resolution": {**resolution, "confirmed": True}}
    await remember_resolution(db, owner, arguments, confirmed)
    assert account_symbols(await stored(db, gold))["gold"]["symbol"] == "XAUUSDm"
    several = {**resolution, "confirmed": True, "other_matches": [{"symbol": "XAUUSDc"}]}
    await remember_resolution(db, owner, arguments, {"symbol_resolution": several})
    assert account_symbols(await stored(db, gold)) == {}
    # A result that states nothing, or names no account, writes nothing and fails nothing.
    await remember_resolution(db, owner, arguments, {"bid": "4100"})
    await remember_resolution(db, owner, {}, confirmed)
    await remember_resolution(db, owner, {"account_id": "no-such-account"}, confirmed)


@pytest.mark.asyncio
async def test_the_agent_is_shown_what_its_accounts_list_before_its_first_call(
    task_db: Fixture,
) -> None:
    db, owner, agent, _thread = task_db
    gold = await account(db, owner, **IDENTITY, broker="Exness Technologies Ltd")
    other = await account(db, owner, login="777", server="Other-Live", platform="mt5")
    async with db.sessions() as session:
        row = await session.get(AgentRow, agent)
        assert row is not None
        assert await account_symbols_context(session, owner, row) == ""
    await learn(db, owner, gold, "gold", "XAUUSDm")
    await learn(db, owner, gold, "الذهب", "XAUUSDm")
    await learn(db, owner, other, "eurusd", "EURUSD.r")
    async with db.sessions() as session:
        row = await session.get(AgentRow, agent)
        assert row is not None
        text = await account_symbols_context(session, owner, row)
        assert text.startswith(NOTE) and "Before an order" in NOTE
        assert f"account {gold} (Exness Technologies Ltd): الذهب = XAUUSDm; gold = XAUUSDm" in text
        assert f"account {other}: eurusd = EURUSD.r" in text
        # An agent with a market of its own is shown that account only.
        row.trading_account_id = other
        focused = await account_symbols_context(session, owner, row)
        assert "EURUSD.r" in focused and "XAUUSDm" not in focused
