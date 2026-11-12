"""Card lifetimes (WP-F cards): the newer card, «طلب جديد», «غير معروف» with a pause,
trade approval expiry and the notice cards' pure rules.

These cases run on the in-memory schema, those marked ``postgres`` only on
``LONORA_TASK_TEST_DATABASE_URL``. The
journeys through the tools, the passkey and the routes are in
``tests/test_card_journeys.py`` (skipped without ``LONORA_DATABASE_URL``).
"""

import os
from datetime import datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo

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
    TradingRestrictionRow,
)
from lonora_db.trade_approvals import (
    approval_data,
    decide,
    expire_if_due,
)
from lonora_db.transactions import SettingsRepository, execution_policy_key
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
        kind="settle_operation",
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
        account = await owned_account(session, owner)
        change = OwnerActionProposal(
            kind="set_account_limits",
            account_id=account,
            set_limits={"max_daily_loss": 250},  # type: ignore[dict-item]
            currency="USD",
        )
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
            .where(OwnerActionRow.kind == "settle_operation")
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


def test_the_pause_switch_goes_only_with_unknown() -> None:
    assert OwnerActionDecision(decision="confirm", outcome="unknown", pause_new_today=True)
    assert not OwnerActionDecision(decision="confirm", outcome="unknown").pause_new_today
    for outcome in ("executed", "not_executed", None):
        with pytest.raises(ValidationError):
            OwnerActionDecision(decision="confirm", outcome=outcome, pause_new_today=True)
    with pytest.raises(ValidationError):
        OwnerActionDecision(decision="cancel", pause_new_today=True)


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


async def restrictions(db: Database, owner: str) -> list[TradingRestrictionRow]:
    async with db.sessions() as session:
        return list(
            await session.scalars(
                select(TradingRestrictionRow).where(TradingRestrictionRow.owner_id == owner)
            )
        )


@postgres
@pytest.mark.asyncio
async def test_unknown_with_the_switch_pauses_new_trades_on_the_account_until_day_end(
    task_db: Fixture,
) -> None:
    db, owner, agent, thread = task_db
    async with db.sessions() as session, session.begin():
        account = await owned_account(session, owner)
        await SettingsRepository().put(
            session,
            execution_policy_key(owner, account),
            {"risk": {"currency": "USD", "trading_day_timezone": "Asia/Riyadh"}},
        )
        for identifier in ("op-paused", "op-plain", "op-done"):
            await uncertain(session, owner, account, identifier)
            await resolve_card(session, owner, agent, thread, identifier)
    paused = await answer(
        db,
        owner,
        "resolve-op-paused",
        OwnerActionDecision(decision="confirm", outcome="unknown", pause_new_today=True),
    )
    assert paused["status"] == "confirmed" and paused["result"]["outcome"] == "unknown"
    rows = await restrictions(db, owner)
    assert len(rows) == 1
    pause = rows[0]
    assert (pause.account_id, pause.agent_id, pause.symbol) == (account, None, None)
    assert (pause.action_class, pause.source, pause.created_by) == (
        "no_new_entries",
        "owner_ui",
        "owner",
    )
    assert pause.created_by_agent_id is None and not pause.applies_to_owner_manual
    assert paused["result"]["restriction_id"] == pause.id
    # Until the end of the trading day in the account's own trading-day zone.
    zone = ZoneInfo("Asia/Riyadh")
    assert pause.valid_until is not None
    local = pause.valid_until.astimezone(zone)
    assert (local.hour, local.minute, local.second) == (0, 0, 0)
    today = utcnow().astimezone(zone).date()
    assert local.date() == today + timedelta(days=1)
    assert datetime.combine(today, datetime.min.time(), zone) < pause.valid_until
    # The same answer again changes nothing: still one restriction.
    again = await answer(
        db,
        owner,
        "resolve-op-paused",
        OwnerActionDecision(decision="confirm", outcome="unknown", pause_new_today=True),
    )
    assert again["status"] == "confirmed" and len(await restrictions(db, owner)) == 1
    # «غير معروف» without the switch pauses nothing.
    plain = await answer(
        db, owner, "resolve-op-plain", OwnerActionDecision(decision="confirm", outcome="unknown")
    )
    assert plain["status"] == "confirmed" and len(await restrictions(db, owner)) == 1
    assert "restriction_id" not in plain["result"]


@postgres
@pytest.mark.asyncio
async def test_the_pause_switch_is_refused_on_any_other_card(task_db: Fixture) -> None:
    db, owner, agent, thread_id = task_db
    async with db.sessions() as session, session.begin():
        thread = await session.get(ThreadRow, thread_id)
        assert thread is not None
        await create_card(
            session,
            owner,
            card_id="resume",
            agent_id=agent,
            thread=thread,
            run_id=None,
            source="system",
            kind="resume_trading",
            subject="trading",
            payload={"enabled": True, "emergency_stop": False},
        )
    with pytest.raises(LonoraError) as error:
        await answer(
            db,
            owner,
            "resume",
            OwnerActionDecision(decision="confirm", outcome="unknown", pause_new_today=True),
        )
    assert (error.value.code, error.value.status) == ("owner_action_pause_unsupported", 422)
    assert await restrictions(db, owner) == []


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
        # A card stored before the fixed lifetime was removed keeps its stored expiry.
        expires_at=created + timedelta(minutes=45),
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
        {"daily_loss_amount": "100"},
        {"daily_loss_percent": "2"},
    ):
        with pytest.raises(ValidationError):
            AccountAuthorityDraft.model_validate({"mode": "full", **terms})
    custom = AccountAuthorityDraft.model_validate(
        {"symbols": ["XAUUSD"], "actions": ["buy", "close_position"], "daily_loss_amount": "150"}
    ).proposal("gold")
    assert custom.symbols == ["XAUUSD"] and custom.agent_id == "gold"
    with pytest.raises(ValidationError):
        AccountAuthorityDraft.model_validate({"daily_loss_amount": "1", "daily_loss_percent": "1"})
