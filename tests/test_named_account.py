"""An account named in the owner's words: used by a read, refused with it by a change."""

from types import SimpleNamespace
from typing import Any, cast

import pytest
from lonora_contracts.domain import Contract
from lonora_db.client import Database
from lonora_db.schema import BrokerSessionRow
from lonora_tools.context import ToolContext
from lonora_tools.market_binding import named_account, prepare_market_arguments
from lonora_tools.resolve import NotResolved
from test_task_runtime import task_db as task_db

Fixture = tuple[Database, str, str, str]


class NeedsAccount(Contract):
    account_id: str


async def account(db: Database, owner: str, **identity: str) -> str:
    """An account whose identity the broker reported, unless none is given."""
    async with db.sessions() as session, session.begin():
        row = BrokerSessionRow(owner_id=owner, payload={"provider": "metaapi"})
        session.add(row)
        await session.flush()
        if identity:
            row.state = {"broker_identity": {**identity, "connection_version": row.version}}
        return row.id


async def named(db: Database, owner: str, requested: str, *, read: bool) -> Any:
    async with db.sessions() as session:
        return await named_account(session, owner, {"account_id": requested}, read=read)


@pytest.mark.asyncio
async def test_a_read_takes_the_one_account_a_name_or_number_fits(task_db: Fixture) -> None:
    db, owner, _agent, _thread = task_db
    gold = await account(db, owner, login="12345", broker="Exness Technologies Ltd", name="Ahmed")
    await account(db, owner, login="777", broker="Other Markets", name="Second")
    for requested in ("0012345", " 12345 ", "exness", "Ahmed"):
        args, note = await named(db, owner, requested, read=True)
        assert args == {"account_id": gold} and note["id"] == gold, requested
    assert note == {"argument": "account_id", "requested": "Ahmed", "id": gold, "label": "Ahmed"}
    # The id itself, whatever its letter case, is the account and nothing is stated.
    assert await named(db, owner, gold.upper(), read=False) == ({"account_id": gold}, None)
    assert await named(db, owner, gold, read=True) == ({"account_id": gold}, None)


@pytest.mark.asyncio
async def test_a_change_is_never_pointed_at_an_account_it_did_not_name(task_db: Fixture) -> None:
    db, owner, _agent, _thread = task_db
    gold = await account(db, owner, login="12345", broker="Exness Technologies Ltd", name="Ahmed")
    with pytest.raises(NotResolved) as one:
        await named(db, owner, "12345", read=False)
    assert one.value.code == "broker_sessions_not_found" and one.value.details["retryable"]
    assert one.value.details["candidates"] == [
        {"id": gold, "label": "12345", "broker": "Exness Technologies Ltd", "login": "12345"}
    ]
    assert one.value.details["next_actions"] == [{"repeat_with": {"account_id": gold}}]


@pytest.mark.asyncio
async def test_two_accounts_are_never_chosen_between_and_an_unknown_one_lists_what_exists(
    task_db: Fixture,
) -> None:
    db, owner, _agent, _thread = task_db
    first = await account(db, owner, login="1", broker="Exness Technologies Ltd", name="A")
    second = await account(db, owner, login="2", broker="Exness Technologies Ltd", name="B")
    # An account the broker has not reported yet has no name to match, only its id.
    unread = await account(db, owner)
    with pytest.raises(NotResolved) as several:
        await named(db, owner, "Exness", read=True)
    assert several.value.code == "broker_sessions_ambiguous"
    assert {item["id"] for item in several.value.details["candidates"]} == {first, second}
    with pytest.raises(NotResolved) as missing:
        await named(db, owner, "no-such-account", read=True)
    assert missing.value.code == "broker_sessions_not_found"
    assert {item["id"] for item in missing.value.details["existing"]} == {first, second, unread}
    assert missing.value.details["next_actions"] == [{"tool": "list_accounts"}]


@pytest.mark.asyncio
async def test_a_call_that_names_no_account_means_the_only_one_or_asks_which(
    task_db: Fixture,
) -> None:
    db, owner, agent, _thread = task_db
    context = cast(ToolContext, SimpleNamespace(db=db, owner_id=owner, agent_id=agent))
    only = await account(db, owner, login="1", broker="Exness Technologies Ltd", name="A")
    assert await prepare_market_arguments(context, "market_quote", {}, NeedsAccount, read=True) == (
        {"account_id": only},
        None,
    )
    second = await account(db, owner, login="2", broker="Other Markets", name="B")
    with pytest.raises(NotResolved) as which:
        await prepare_market_arguments(context, "market_quote", {}, NeedsAccount, read=True)
    assert which.value.code == "broker_sessions_ambiguous"
    assert which.value.details["retryable"] is False
    assert [item["id"] for item in which.value.details["candidates"]] == [second, only]
    # A read that names one of them is that account, stated for the model to say.
    args, note = await prepare_market_arguments(
        context, "market_quote", {"account_id": "other markets"}, NeedsAccount, read=True
    )
    assert args == {"account_id": second} and note is not None and note["label"] == "Other Markets"
    # A tool that is not about a market is not touched.
    assert await prepare_market_arguments(
        context, "task_inspect", {"account_id": "x"}, NeedsAccount
    ) == ({"account_id": "x"}, None)
