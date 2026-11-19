"""Card lifetimes (WP-F cards): the newer card, «طلب جديد», trade approval expiry and the
notice cards' pure rules.

These cases run on the in-memory schema, those marked ``postgres`` only on
``LONORA_TASK_TEST_DATABASE_URL``. The
journeys through the tools, the passkey and the routes are in
``tests/test_card_journeys.py`` (skipped without ``LONORA_DATABASE_URL``).
"""

import os
from datetime import timedelta
from typing import Any

import pytest
from lonora_auth.identity import OwnerIdentity
from lonora_contracts.domain import utcnow
from lonora_contracts.owner_actions import (
    AccountAuthorityDraft,
    OwnerActionDecision,
    OwnerActionProposal,
)
from lonora_core.user_error import LonoraError
from lonora_db.client import Database
from lonora_db.owner_actions import (
    create_card,
    owner_action_data,
    propose,
    renew_card,
)
from lonora_db.schema import (
    BrokerSessionRow,
    EventRow,
    OwnerActionRow,
    RunRow,
    ThreadRow,
    TradeApprovalRow,
    TradingJournalRow,
)
from lonora_db.trade_approvals import (
    APPROVAL_LIFETIME,
    MAXIMUM_APPROVAL_LIFETIME,
    MINIMUM_APPROVAL_LIFETIME,
    approval_data,
    approval_expiry,
    decide,
    expire_if_due,
)
from pydantic import ValidationError
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from test_task_runtime import task_db as task_db

Fixture = tuple[Database, str, str, str]
# Cases that read a card back in a later transaction compare stored times, which only
# PostgreSQL returns with their zone: they run there (LONORA_TASK_TEST_DATABASE_URL).
postgres = pytest.mark.skipif(
    not os.environ.get("LONORA_TASK_TEST_DATABASE_URL"),
    reason="needs LONORA_TASK_TEST_DATABASE_URL (a disposable *_test PostgreSQL database)",
)


async def owned_account(session: AsyncSession, owner: str) -> str:
    row = BrokerSessionRow(owner_id=owner, payload={"provider": "simulation"})
    session.add(row)
    await session.flush()
    return row.id


async def uncertain(session: AsyncSession, owner: str, account: str, identifier: str) -> None:
    session.add(
        TradingJournalRow(
            operation_id=identifier,
            owner_id=owner,
            account_id=account,
            request_hash="h",
            request={"symbol": "XAUUSD", "action": "buy", "volume": "0.1"},
            status="ambiguous",
            result={},
        )
    )
    await session.flush()


async def resolve_card(
    session: AsyncSession, owner: str, agent: str, thread_id: str, identifier: str
) -> OwnerActionRow:
    thread = await session.get(ThreadRow, thread_id)
    assert thread is not None
    return await create_card(
        session,
        owner,
        card_id="resolve-" + identifier,
        agent_id=agent,
        thread=thread,
        run_id=None,
        source="system",
        kind="resolve_operation",
        subject="operation:" + identifier,
        payload={"operation_id": identifier},
    )


async def updates(session: AsyncSession, card_id: str) -> int:
    rows = await session.scalars(select(EventRow).where(EventRow.kind == "owner_action.updated"))
    return sum(1 for row in rows if row.payload.get("id") == card_id)


@pytest.mark.asyncio
async def test_a_newer_card_names_the_card_that_replaced_it(task_db: Fixture) -> None:
    db, owner, agent, thread = task_db
    async with db.sessions() as session, session.begin():
        change = OwnerActionProposal(kind="connect_credential", target="news_feed")
        first, _ = await propose(
            session, owner, change, card_id="old", agent_id=agent, thread_id=thread, run_id=None
        )
        assert (await owner_action_data(session, first))["superseded_by"] is None
        first.expires_at = utcnow() - timedelta(seconds=1)
        newer, created = await propose(
            session, owner, change, card_id="new", agent_id=agent, thread_id=thread, run_id=None
        )
        assert created and newer.id == "new"
        assert first.status == "expired" and first.superseded_by == "new"
        assert (await owner_action_data(session, first))["superseded_by"] == "new"
        assert (await owner_action_data(session, newer))["superseded_by"] is None


@postgres
@pytest.mark.asyncio
async def test_renew_raises_a_fresh_card_only_while_the_subject_still_needs_a_decision(
    task_db: Fixture,
) -> None:
    db, owner, agent, thread = task_db
    async with db.sessions() as session, session.begin():
        account = await owned_account(session, owner)
        await uncertain(session, owner, account, "op-still")
        old = await resolve_card(session, owner, agent, thread, "op-still")
        # A card still waiting is not renewed: it is the one to answer.
        with pytest.raises(LonoraError) as error:
            await renew_card(session, owner, old.id)
        assert (error.value.code, error.value.status) == ("owner_action_not_renewable", 409)
        old.expires_at = utcnow() - timedelta(minutes=1)  # Lazily expired, still pending.
        before = await updates(session, old.id)
        fresh = await renew_card(session, owner, old.id)
        assert fresh.id != old.id and fresh.status == "pending"
        assert (fresh.kind, fresh.subject, fresh.payload) == (old.kind, old.subject, old.payload)
        assert fresh.thread_id == old.thread_id and fresh.agent_id == old.agent_id
        # A fresh server lifetime (7 days for a resolve card), nothing set by the client.
        assert fresh.expires_at > utcnow() + timedelta(days=6)
        assert (old.status, old.superseded_by) == ("expired", fresh.id)
        assert await updates(session, old.id) == before + 1
        assert await updates(session, fresh.id) == 1
        # The old card is used up; renewing it again is refused (the fresh one is shown).
        with pytest.raises(LonoraError) as error:
            await renew_card(session, owner, old.id)
        assert error.value.code == "owner_action_not_renewable"
        # Settled meanwhile: the subject needs no decision, nothing is raised.
        fresh.expires_at = utcnow() - timedelta(minutes=1)
        operation = await session.get(TradingJournalRow, "op-still")
        assert operation is not None
        operation.status = "resolved"
        with pytest.raises(LonoraError) as error:
            await renew_card(session, owner, fresh.id)
        assert error.value.code == "owner_action_not_renewable"
        cards = await session.scalar(
            select(func.count())
            .select_from(OwnerActionRow)
            .where(OwnerActionRow.kind == "resolve_operation")
        )
        assert cards == 2


@pytest.mark.asyncio
async def test_undo_and_notice_cards_are_never_renewed(task_db: Fixture) -> None:
    db, owner, agent, thread_id = task_db
    async with db.sessions() as session, session.begin():
        thread = await session.get(ThreadRow, thread_id)
        assert thread is not None
        undo = await create_card(
            session,
            owner,
            card_id="created-undo",
            agent_id=agent,
            thread=thread,
            run_id=None,
            source="system",
            kind="agent_created",
            subject="agent:" + agent,
            payload={"agent_id": agent},
        )
        undo.expires_at = utcnow() - timedelta(minutes=1)
        with pytest.raises(LonoraError) as error:
            await renew_card(session, owner, undo.id)
        assert error.value.code == "owner_action_not_renewable"
        with pytest.raises(LonoraError) as error:
            await renew_card(session, "someone-else", undo.id)
        assert error.value.code == "owner_action_not_found"


async def answer(
    db: Database, owner: str, card_id: str, body: OwnerActionDecision
) -> dict[str, Any]:
    from lonora_api.routes.owner_actions import decide as decide_card
    from lonora_db.owner_actions import lock_owner_actions, owned_card

    identity = OwnerIdentity(id=owner, email="task@example.test", token_hash="0" * 64)
    async with db.sessions() as session, session.begin():
        await lock_owner_actions(session, owner)
        row = await owned_card(session, owner, card_id, lock=True)
        await decide_card(session, None, identity, row, body)  # type: ignore[arg-type]
        return await owner_action_data(session, row)


def test_an_approval_lives_between_thirty_and_sixty_minutes() -> None:
    assert MINIMUM_APPROVAL_LIFETIME == timedelta(minutes=30)
    assert MAXIMUM_APPROVAL_LIFETIME == timedelta(minutes=60)
    assert APPROVAL_LIFETIME == timedelta(minutes=45)
    now = utcnow()
    assert approval_expiry(now) == now + APPROVAL_LIFETIME


async def waiting_approval(
    session: AsyncSession, owner: str, agent: str, thread: str, identifier: str
) -> tuple[TradeApprovalRow, RunRow]:
    run = RunRow(
        thread_id=thread,
        agent_id=agent,
        status="waiting_input",
        execution_state={"pending": [{"id": "call-" + identifier}]},
    )
    session.add(run)
    await session.flush()
    created = utcnow() - timedelta(minutes=50)
    row = TradeApprovalRow(
        id=identifier,
        owner_id=owner,
        run_id=run.id,
        thread_id=thread,
        agent_id=agent,
        call_id="call-" + identifier,
        requests=[{"operation_id": "op-" + identifier, "action": "buy", "symbol": "XAUUSD"}],
        status="pending",
        results=[],
        created_at=created,
        expires_at=approval_expiry(created),
    )
    session.add(row)
    await session.flush()
    return row, run


@postgres
@pytest.mark.asyncio
async def test_an_expired_approval_can_never_be_approved(task_db: Fixture) -> None:
    db, owner, agent, thread = task_db
    async with db.sessions() as session, session.begin():
        row, run = await waiting_approval(session, owner, agent, thread, "late")
        # Read lazily: the card says expired before anything settles it.
        data = approval_data(row)
        assert row.expires_at is not None
        assert data["status"] == "expired" and data["expires_at"] == row.expires_at.isoformat()
        with pytest.raises(LonoraError) as error:
            await decide(session, owner, row.id, "approve")
        assert (error.value.code, error.value.status) == ("trade_approval_expired", 409)
        assert row.status == "pending"  # The refusal changed nothing by itself.
    async with db.sessions() as session, session.begin():
        row = await session.get(TradeApprovalRow, "late")
        assert row is not None
        assert await expire_if_due(session, row) is True
        assert row.status == "expired"
        # The waiting run continues and its trade call learns the card expired.
        waiting = await session.get(RunRow, run.id)
        assert waiting is not None and waiting.status == "queued"
        assert await expire_if_due(session, row) is False
        settled = list(
            await session.scalars(
                select(EventRow).where(EventRow.kind == "trading.approval.updated")
            )
        )
        assert [event.payload["status"] for event in settled] == ["expired"]
    async with db.sessions() as session, session.begin():
        for decision in ("approve", "reject"):
            with pytest.raises(LonoraError) as error:
                await decide(session, owner, "late", decision)
            assert error.value.code == "trade_approval_expired"
        stored = await session.get(TradeApprovalRow, "late")
        assert stored is not None and stored.status == "expired"


@pytest.mark.asyncio
async def test_an_old_approval_without_an_expiry_still_decides(task_db: Fixture) -> None:
    db, owner, agent, thread = task_db
    async with db.sessions() as session, session.begin():
        row, _ = await waiting_approval(session, owner, agent, thread, "legacy")
        row.expires_at = None
        assert approval_data(row)["status"] == "pending"
        assert await expire_if_due(session, row) is False
        decided = await decide(session, owner, row.id, "approve")
        assert decided["status"] == "approved" and decided["expires_at"] is None


def test_a_full_draft_takes_no_terms_of_its_own() -> None:
    assert AccountAuthorityDraft(mode="full").proposal("gold").kind == "grant_authority"
    for terms in (
        {"symbols": ["XAUUSD"]},
        {"all_pairs": True},
        {"actions": ["buy"]},
        {"duration": "24h"},
        {"allow_manual_positions": False},
    ):
        with pytest.raises(ValidationError):
            AccountAuthorityDraft.model_validate({"mode": "full", **terms})
    custom = AccountAuthorityDraft.model_validate(
        {"symbols": ["XAUUSD"], "actions": ["buy", "close_position"]}
    ).proposal("gold")
    assert custom.symbols == ["XAUUSD"] and custom.agent_id == "gold"
