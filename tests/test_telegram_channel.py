"""Telegram as the owner's other channel (VISION 11.4, map Q17, R3).

The chat is paired by a one-time code; Telegram carries exactly the events that push, once
per record under the effect-receipt rule; an inbound "yes" is an owner message to the agent
and never decides a card. Needs PostgreSQL (LONORA_TASK_TEST_DATABASE_URL).
"""

import os
from datetime import timedelta
from types import SimpleNamespace
from typing import Any
from uuid import uuid4

import pytest
from lonora_bus.attention import attention_text
from lonora_contracts.domain import utcnow
from lonora_core.user_error import LonoraError
from lonora_db.attention import publish_ready
from lonora_db.client import Database
from lonora_db.events import publish_committed
from lonora_db.schema import (
    AgentRow,
    AttentionRow,
    EffectReceiptRow,
    IntegrationRow,
    MessageRow,
    TradeApprovalRow,
)
from lonora_db.telegram_pairing import pairing_status, start_pairing
from lonora_gateway import event_dispatch
from sqlalchemy import select
from test_task_runtime import task_db as task_db

pytestmark = pytest.mark.skipif(
    not os.environ.get("LONORA_TASK_TEST_DATABASE_URL"),
    reason="needs LONORA_TASK_TEST_DATABASE_URL (a disposable *_test PostgreSQL database)",
)
Fixture = tuple[Database, str, str, str]
CHAT = "424242"


class FakeTelegram:
    inbox: list[dict[str, Any]] = []
    sent: list[tuple[str, str]] = []
    fail = False
    next_id = 0

    def __init__(self, token: str) -> None:
        assert token == "bot-token"

    async def updates(self, offset: int) -> list[dict[str, Any]]:
        waiting = [update for update in FakeTelegram.inbox if update["update_id"] >= offset]
        FakeTelegram.inbox = []
        return waiting

    async def send(self, destination: str, content: str) -> dict[str, Any]:
        FakeTelegram.sent.append((destination, content))
        if FakeTelegram.fail:
            raise LonoraError("telegram_delivery_failed", 502)
        return {"message_id": len(FakeTelegram.sent)}


def update(text: str, chat: str = CHAT, kind: str = "private") -> None:
    FakeTelegram.next_id += 1
    FakeTelegram.inbox.append(
        {
            "update_id": FakeTelegram.next_id,
            "message": {"text": text, "chat": {"id": int(chat), "type": kind}},
        }
    )


@pytest.fixture(autouse=True)
def fake_telegram(monkeypatch: pytest.MonkeyPatch) -> None:
    FakeTelegram.inbox, FakeTelegram.sent, FakeTelegram.fail = [], [], False
    monkeypatch.setattr(event_dispatch, "TelegramAdapter", FakeTelegram)


async def linked(db: Database, owner_id: str, agent_id: str, thread_id: str) -> str:
    async with db.sessions() as session, session.begin():
        row = IntegrationRow(
            owner_id=owner_id,
            payload={
                "type": "telegram",
                "name": "Telegram",
                "secret_id": "secret",
                "enabled": True,
                "deliver_to_agent_id": agent_id,
                "thread_id": thread_id,
                "allowed_destinations": [],
            },
        )
        session.add(row)
        await session.flush()
        return row.id


async def tick(db: Database, owner_id: str, integration_id: str) -> None:
    async def read(_: str) -> str:
        return "bot-token"

    services: Any = SimpleNamespace(owner_id=owner_id, secrets=SimpleNamespace(read=read))
    async with db.sessions() as session:
        await publish_committed(session)
    async with db.sessions() as session:
        row = await session.get(IntegrationRow, integration_id)
        assert row
    await event_dispatch.dispatch_integration(db, services, row)


async def pair(db: Database, owner_id: str, integration_id: str) -> None:
    async with db.sessions() as session, session.begin():
        code = await start_pairing(session, owner_id, integration_id)
    update("/start " + code)
    await tick(db, owner_id, integration_id)


async def approval(db: Database, owner_id: str, agent_id: str, thread_id: str, code: str) -> str:
    record = str(uuid4())
    async with db.sessions() as session, session.begin():
        session.add(
            TradeApprovalRow(
                id=record,
                owner_id=owner_id,
                thread_id=thread_id,
                agent_id=agent_id,
                call_id="call-" + record,
                requests=[{"symbol": "XAUUSD", "action": "buy", "volume": "0.1"}],
                status="pending",
            )
        )
        item = AttentionRow(
            owner_id=owner_id,
            agent_id=agent_id,
            thread_id=thread_id,
            logical_key=uuid4().hex,
            coalesce_key=uuid4().hex,
            importance="action_required",
            code=code,
            parameters={"approval_id": record},
            due_at=utcnow(),
        )
        session.add(item)
        await session.flush()
        publish_ready(session, item, None)
    return record


async def payload(db: Database, integration_id: str) -> dict[str, Any]:
    async with db.sessions() as session:
        row = await session.get(IntegrationRow, integration_id)
        assert row
        return dict(row.payload)


@pytest.mark.asyncio
async def test_the_chat_is_paired_once_by_its_code_and_nothing_else(task_db: Fixture) -> None:
    db, owner_id, agent_id, thread_id = task_db
    integration = await linked(db, owner_id, agent_id, thread_id)
    async with db.sessions() as session, session.begin():
        code = await start_pairing(session, owner_id, integration)
    # A wrong code, a group chat and a bare code bind nothing.
    update("/start WRONGCOD")
    update("/start " + code, "777", "group")
    update(code)
    await tick(db, owner_id, integration)
    assert (await payload(db, integration))["allowed_destinations"] == []
    update("/start " + code.lower())
    await tick(db, owner_id, integration)
    assert (await payload(db, integration))["allowed_destinations"] == [CHAT]
    # The code works once: another chat cannot take the bot over with it.
    update("/start " + code, "999")
    await tick(db, owner_id, integration)
    assert (await payload(db, integration))["allowed_destinations"] == [CHAT]
    async with db.sessions() as session:
        row = await session.get(IntegrationRow, integration)
        assert row and pairing_status(row) == {"paired": True}
        # Neither the pairing nor the refused attempts reached the agent as messages.
        texts = [m.content for m in await session.scalars(select(MessageRow))]
    assert all(code not in str(text) for text in texts)


@pytest.mark.asyncio
async def test_an_expired_code_binds_nothing(task_db: Fixture) -> None:
    db, owner_id, agent_id, thread_id = task_db
    integration = await linked(db, owner_id, agent_id, thread_id)
    async with db.sessions() as session, session.begin():
        code = await start_pairing(session, owner_id, integration)
        row = await session.get(IntegrationRow, integration)
        assert row
        row.state = {
            **row.state,
            "pairing": {
                **row.state["pairing"],
                "expires_at": (utcnow() - timedelta(seconds=1)).isoformat(),
            },
        }
    update("/start " + code)
    await tick(db, owner_id, integration)
    assert (await payload(db, integration))["allowed_destinations"] == []


@pytest.mark.asyncio
async def test_telegram_carries_the_push_events_once_and_nothing_else(task_db: Fixture) -> None:
    db, owner_id, agent_id, thread_id = task_db
    async with db.sessions() as session, session.begin():
        agent = await session.get(AgentRow, agent_id)
        assert agent
        agent.name = "ذهب"
    integration = await linked(db, owner_id, agent_id, thread_id)
    await pair(db, owner_id, integration)
    await approval(db, owner_id, agent_id, thread_id, "task_review")
    await approval(db, owner_id, agent_id, thread_id, "approval_required")
    await tick(db, owner_id, integration)
    await tick(db, owner_id, integration)
    assert FakeTelegram.sent == [(CHAT, "ذهب: " + attention_text("approval_required", "ar"))]
    assert "XAUUSD" not in str(FakeTelegram.sent)


@pytest.mark.asyncio
async def test_an_unconfirmed_telegram_send_is_never_repeated(task_db: Fixture) -> None:
    db, owner_id, agent_id, thread_id = task_db
    integration = await linked(db, owner_id, agent_id, thread_id)
    await pair(db, owner_id, integration)
    FakeTelegram.fail = True
    await approval(db, owner_id, agent_id, thread_id, "approval_required")
    await tick(db, owner_id, integration)
    FakeTelegram.fail = False
    await tick(db, owner_id, integration)
    assert len(FakeTelegram.sent) == 1
    async with db.sessions() as session:
        statuses = [row.result["status"] for row in await session.scalars(select(EffectReceiptRow))]
    assert statuses == ["ambiguous"]


@pytest.mark.asyncio
async def test_an_inbound_yes_is_a_message_to_the_agent_never_an_approval(
    task_db: Fixture,
) -> None:
    db, owner_id, agent_id, thread_id = task_db
    integration = await linked(db, owner_id, agent_id, thread_id)
    await pair(db, owner_id, integration)
    record = await approval(db, owner_id, agent_id, thread_id, "approval_required")
    update("نعم")
    update("yes")
    await tick(db, owner_id, integration)
    async with db.sessions() as session:
        card = await session.get(TradeApprovalRow, record)
        assert card and card.status == "pending"
        owner_messages = [
            message.content
            for message in await session.scalars(
                select(MessageRow).where(MessageRow.thread_id == thread_id)
            )
            if message.role == "user"
        ]
    assert owner_messages == ["نعم", "yes"]


@pytest.mark.asyncio
async def test_only_a_telegram_integration_of_the_owner_pairs(task_db: Fixture) -> None:
    db, owner_id, _, _ = task_db
    async with db.sessions() as session, session.begin():
        feed = IntegrationRow(owner_id=owner_id, payload={"type": "news_feed", "name": "f"})
        session.add(feed)
        await session.flush()
        with pytest.raises(LonoraError) as refused:
            await start_pairing(session, owner_id, feed.id)
    assert refused.value.code == "integration_not_found"
