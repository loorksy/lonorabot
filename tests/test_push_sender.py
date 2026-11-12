"""The push sender (VISION 11.4, map R3/R4) against a fake Expo transport.

One push per record and phone at creation, fixed catalog text under the agent's name, a
receipt written before any network call, never a second send, per-item isolation, no push
for other attention codes. Needs PostgreSQL (LONORA_TASK_TEST_DATABASE_URL): the cursor reads
the published event order and two gateways race on an advisory lock.
"""

import asyncio
import os
from datetime import timedelta
from typing import Any
from uuid import uuid4

import httpx
import pytest
from lonora_adapters.channels.expo_push import EXPO_PUSH_URL, ExpoPushTransport
from lonora_auth.sessions import issue_session, token_hash
from lonora_bus.attention import attention_text
from lonora_contracts.domain import utcnow
from lonora_contracts.push import PushDeviceRegistration
from lonora_core.user_error import LonoraError
from lonora_db.attention import publish_ready
from lonora_db.client import Database
from lonora_db.push_devices import register_device
from lonora_db.schema import (
    AgentRow,
    AttentionRow,
    BrokerSessionRow,
    EffectReceiptRow,
    OwnerActionRow,
    OwnerRow,
    PushDeviceRow,
    SessionRow,
    ThreadRow,
    TradeApprovalRow,
    TradingJournalRow,
)
from lonora_db.transactions import SettingsRepository
from lonora_gateway.push import PUSHES_PER_TICK, cursor_key, dispatch_push
from lonora_security.secrets import SecretCipher
from pydantic import SecretStr
from sqlalchemy import select
from test_task_runtime import task_db as task_db

pytestmark = pytest.mark.skipif(
    not os.environ.get("LONORA_TASK_TEST_DATABASE_URL"),
    reason="needs LONORA_TASK_TEST_DATABASE_URL (a disposable *_test PostgreSQL database)",
)
CIPHER = SecretCipher("MDAwMDAwMDAwMDAwMDAwMDAwMDAwMDAwMDAwMDAwMDA=")
PHONE, TABLET = "0f4c1b52-7c2e-4f53-9e64-1d1d6c0f4a21", "b5d0e9c4-2a8f-4c11-8e1b-77a6c3d2e910"
Fixture = tuple[Database, str, str, str]


class FakeExpo:
    """Records every message; answers with tickets, a failure or a hang."""

    def __init__(self, db: Database, answer: Any = None, before: Any = None) -> None:
        self.db, self.answer, self.sent = db, answer, list[dict[str, Any]]()
        self.before = before
        self.receipts_before_send: list[list[str]] = []

    async def send(self, messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
        async with self.db.sessions() as session:
            stored = await session.scalars(select(EffectReceiptRow))
            self.receipts_before_send.append(sorted(row.result["status"] for row in stored))
        self.sent.extend(messages)
        if self.before is not None:
            await self.before()
        if isinstance(self.answer, BaseException):
            raise self.answer
        if self.answer == "hang":
            await asyncio.sleep(3600)
        if callable(self.answer):
            reply: Any = self.answer
            return [reply(message) for message in messages]
        return [{"status": "ok", "id": "ticket-" + str(index)} for index in range(len(messages))]


async def phone(db: Database, owner_id: str, device: str, token: str) -> str:
    async with db.sessions() as session, session.begin():
        owner = await session.get(OwnerRow, owner_id)
        assert owner
        bearer, _ = await issue_session(session, owner, 3600)
        await register_device(
            session,
            owner_id,
            token_hash(bearer),
            device,
            PushDeviceRegistration(token=SecretStr(token), platform="android"),
            CIPHER,
        )
    return bearer


async def card(
    db: Database,
    owner_id: str,
    agent_id: str,
    thread_id: str,
    code: str,
    record_thread: str | None = None,
) -> str:
    """A pending Trade Approval, an uncertain operation, or another attention item, made
    ready the way the attention loop does it."""
    approval_id = str(uuid4())
    async with db.sessions() as session, session.begin():
        if code == "operation_uncertain":
            account = BrokerSessionRow(owner_id=owner_id, payload={"provider": "simulation"})
            session.add(account)
            await session.flush()
            session.add(
                TradingJournalRow(
                    operation_id=approval_id,
                    owner_id=owner_id,
                    account_id=account.id,
                    request_hash="h",
                    request={"symbol": "XAUUSD", "action": "buy", "volume": "0.1"},
                    status="ambiguous",
                    thread_id=record_thread or thread_id,
                    timeline_seq=9,
                )
            )
        if code == "approval_required":
            session.add(
                TradeApprovalRow(
                    id=approval_id,
                    owner_id=owner_id,
                    thread_id=record_thread or thread_id,
                    agent_id=agent_id,
                    call_id="call-" + approval_id,
                    requests=[{"symbol": "XAUUSD", "action": "buy", "volume": "0.1"}],
                    status="pending",
                    timeline_seq=7,
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
            parameters={"approval_id": approval_id, "operation_id": approval_id},
            due_at=utcnow(),
        )
        session.add(item)
        await session.flush()
        publish_ready(session, item, None)
    return approval_id


async def started(db: Database, owner_id: str, expo: FakeExpo) -> None:
    """The first run only places the cursor at the end of the stream."""
    assert await dispatch_push(db, owner_id, CIPHER, expo) == 0


async def receipts(db: Database) -> list[dict[str, Any]]:
    async with db.sessions() as session:
        return [row.result for row in await session.scalars(select(EffectReceiptRow))]


@pytest.mark.asyncio
async def test_a_pending_approval_pushes_once_per_phone_with_catalog_text(
    task_db: Fixture,
) -> None:
    db, owner_id, agent_id, thread_id = task_db
    async with db.sessions() as session, session.begin():
        agent = await session.get(AgentRow, agent_id)
        assert agent
        agent.name = "ذهب"
    expo = FakeExpo(db)
    await phone(db, owner_id, PHONE, "ExponentPushToken[phone000000000001]")
    await phone(db, owner_id, TABLET, "ExponentPushToken[tablet00000000002]")
    await started(db, owner_id, expo)
    approval = await card(db, owner_id, agent_id, thread_id, "approval_required")
    assert await dispatch_push(db, owner_id, CIPHER, expo) == 2
    assert await dispatch_push(db, owner_id, CIPHER, expo) == 0
    assert sorted(message["to"] for message in expo.sent) == [
        "ExponentPushToken[phone000000000001]",
        "ExponentPushToken[tablet00000000002]",
    ]
    for message in expo.sent:
        assert message["title"] == "ذهب"
        assert message["body"] == attention_text("approval_required", "ar")
        # Only where to open: no price, volume, symbol, account or record of the request.
        assert message["data"] == {"thread_id": thread_id, "around": 7}
        assert "XAUUSD" not in str(message) and "0.1" not in str(message)
        assert approval not in str(message) and "categoryId" not in message
    # Every receipt was written before the first network call, and confirmed after its own.
    assert expo.receipts_before_send[0] == ["submitted", "submitted"]
    stored = await receipts(db)
    assert [row["status"] for row in stored] == ["confirmed", "confirmed"]
    assert all("ExponentPushToken" not in str(row) for row in stored)


@pytest.mark.asyncio
async def test_an_unconfirmed_send_is_never_repeated(task_db: Fixture) -> None:
    db, owner_id, agent_id, thread_id = task_db
    await phone(db, owner_id, PHONE, "ExponentPushToken[phone000000000001]")
    await started(db, owner_id, FakeExpo(db))
    for answer in (httpx.ReadTimeout("sent, no answer"), LonoraError("push_request_failed", 502)):
        expo = FakeExpo(db, answer)
        await card(db, owner_id, agent_id, thread_id, "approval_required")
        await dispatch_push(db, owner_id, CIPHER, expo)
        assert len(expo.sent) == 1
    assert [row["status"] for row in await receipts(db)] == ["ambiguous", "ambiguous"]
    # A later tick (or a restart) sends nothing for either record.
    quiet = FakeExpo(db)
    assert await dispatch_push(db, owner_id, CIPHER, quiet) == 0 and quiet.sent == []


@pytest.mark.asyncio
async def test_a_refused_request_is_rejected_and_not_repeated(task_db: Fixture) -> None:
    db, owner_id, agent_id, thread_id = task_db
    await phone(db, owner_id, PHONE, "ExponentPushToken[phone000000000001]")
    expo = FakeExpo(db, LonoraError("push_request_refused", 502))
    await started(db, owner_id, expo)
    await card(db, owner_id, agent_id, thread_id, "approval_required")
    await dispatch_push(db, owner_id, CIPHER, expo)
    assert [row["status"] for row in await receipts(db)] == ["rejected"]
    assert await dispatch_push(db, owner_id, CIPHER, FakeExpo(db)) == 0


@pytest.mark.asyncio
async def test_two_gateways_push_one_record_once(task_db: Fixture) -> None:
    db, owner_id, agent_id, thread_id = task_db
    await phone(db, owner_id, PHONE, "ExponentPushToken[phone000000000001]")
    first, second = FakeExpo(db), FakeExpo(db)
    await started(db, owner_id, first)
    await card(db, owner_id, agent_id, thread_id, "approval_required")
    await asyncio.gather(
        dispatch_push(db, owner_id, CIPHER, first), dispatch_push(db, owner_id, CIPHER, second)
    )
    assert len(first.sent) + len(second.sent) == 1


@pytest.mark.asyncio
async def test_one_phone_gone_does_not_stop_the_other(task_db: Fixture) -> None:
    db, owner_id, agent_id, thread_id = task_db
    await phone(db, owner_id, PHONE, "ExponentPushToken[phone000000000001]")
    await phone(db, owner_id, TABLET, "ExponentPushToken[tablet00000000002]")

    def answer(message: dict[str, Any]) -> dict[str, Any]:
        if "tablet" in message["to"]:
            return {"status": "error", "details": {"error": "DeviceNotRegistered"}}
        return {"status": "ok", "id": "ticket"}

    expo = FakeExpo(db, answer)
    await started(db, owner_id, expo)
    await card(db, owner_id, agent_id, thread_id, "approval_required")
    await dispatch_push(db, owner_id, CIPHER, expo)
    assert sorted(row["status"] for row in await receipts(db)) == ["confirmed", "rejected"]
    async with db.sessions() as session:
        left = [row.device_id for row in await session.scalars(select(PushDeviceRow))]
    assert left == [PHONE]


@pytest.mark.asyncio
async def test_other_items_and_settled_cards_never_push(task_db: Fixture) -> None:
    db, owner_id, agent_id, thread_id = task_db
    await phone(db, owner_id, PHONE, "ExponentPushToken[phone000000000001]")
    expo = FakeExpo(db)
    await started(db, owner_id, expo)
    for code in ("task_review", "external_broker_activity", "agent_notification"):
        await card(db, owner_id, agent_id, thread_id, code)
    approval = await card(db, owner_id, agent_id, thread_id, "approval_required")
    async with db.sessions() as session, session.begin():
        row = await session.get(TradeApprovalRow, approval)
        assert row
        row.status = "rejected"
    assert await dispatch_push(db, owner_id, CIPHER, expo) == 0 and expo.sent == []


@pytest.mark.asyncio
async def test_a_signed_out_phone_gets_nothing_and_an_expired_session_still_does(
    task_db: Fixture,
) -> None:
    # A mobile session has an absolute lifetime; the phone stays reachable until it signs
    # out (R-SEC M1 on #142).
    db, owner_id, agent_id, thread_id = task_db
    expired = await phone(db, owner_id, PHONE, "ExponentPushToken[phone000000000001]")
    revoked = await phone(db, owner_id, TABLET, "ExponentPushToken[tablet00000000002]")
    async with db.sessions() as session, session.begin():
        for row in await session.scalars(select(SessionRow)):
            if row.token_hash == token_hash(expired):
                row.expires_at = utcnow() - timedelta(seconds=1)
            if row.token_hash == token_hash(revoked):
                row.revoked = True
    expo = FakeExpo(db)
    await started(db, owner_id, expo)
    await card(db, owner_id, agent_id, thread_id, "approval_required")
    assert await dispatch_push(db, owner_id, CIPHER, expo) == 1
    assert [message["to"] for message in expo.sent] == ["ExponentPushToken[phone000000000001]"]
    async with db.sessions() as session:
        left = [row.device_id for row in await session.scalars(select(PushDeviceRow))]
    assert left == [PHONE]


@pytest.mark.asyncio
async def test_cards_waiting_before_push_was_installed_do_not_push(task_db: Fixture) -> None:
    db, owner_id, agent_id, thread_id = task_db
    await phone(db, owner_id, PHONE, "ExponentPushToken[phone000000000001]")
    await card(db, owner_id, agent_id, thread_id, "approval_required")
    expo = FakeExpo(db)
    await started(db, owner_id, expo)
    assert await dispatch_push(db, owner_id, CIPHER, expo) == 0 and expo.sent == []


@pytest.mark.asyncio
async def test_a_hanging_expo_call_ends_as_unconfirmed(
    task_db: Fixture, monkeypatch: pytest.MonkeyPatch
) -> None:
    import lonora_gateway.push as push

    monkeypatch.setattr(push, "SEND_TIMEOUT_SECONDS", 0.2)
    db, owner_id, agent_id, thread_id = task_db
    await phone(db, owner_id, PHONE, "ExponentPushToken[phone000000000001]")
    expo = FakeExpo(db, "hang")
    await started(db, owner_id, expo)
    await card(db, owner_id, agent_id, thread_id, "approval_required")
    await dispatch_push(db, owner_id, CIPHER, expo)
    assert [row["status"] for row in await receipts(db)] == ["ambiguous"]


@pytest.mark.asyncio
async def test_the_expo_adapter_request_and_its_failures() -> None:
    seen: list[httpx.Request] = []

    def answer(status: int, body: Any):
        def handler(request: httpx.Request) -> httpx.Response:
            seen.append(request)
            return httpx.Response(status, json=body)

        return httpx.MockTransport(handler)

    message = {"to": "ExponentPushToken[phone000000000001]", "title": "t", "body": "b"}
    ok = ExpoPushTransport("access", answer(200, {"data": [{"status": "ok", "id": "x"}]}))
    assert await ok.send([message]) == [{"status": "ok", "id": "x"}]
    assert str(seen[0].url) == EXPO_PUSH_URL
    assert seen[0].headers["authorization"] == "Bearer access"
    await ExpoPushTransport(None, answer(200, {"data": [{}]})).send([message])
    assert "authorization" not in seen[-1].headers
    failures: list[tuple[int, dict[str, Any], str]] = [
        (400, {"errors": []}, "push_request_refused"),
        (429, {"errors": []}, "push_rate_limited"),
        (503, {}, "push_request_failed"),
        (200, {"data": []}, "push_response_invalid"),
    ]
    for status, body, code in failures:
        with pytest.raises(LonoraError) as failed:
            await ExpoPushTransport(None, answer(status, body)).send([message])
        assert failed.value.code == code


@pytest.mark.asyncio
async def test_an_uncertain_operation_pushes_once(task_db: Fixture) -> None:
    db, owner_id, agent_id, thread_id = task_db
    await phone(db, owner_id, PHONE, "ExponentPushToken[phone000000000001]")
    expo = FakeExpo(db)
    await started(db, owner_id, expo)
    await card(db, owner_id, agent_id, thread_id, "operation_uncertain")
    assert await dispatch_push(db, owner_id, CIPHER, expo) == 1
    assert expo.sent[0]["body"] == attention_text("operation_uncertain", "ar")
    assert expo.sent[0]["data"] == {"thread_id": thread_id, "around": 9}
    assert await dispatch_push(db, owner_id, CIPHER, expo) == 0


@pytest.mark.asyncio
async def test_the_receipt_alone_stops_a_second_send(task_db: Fixture) -> None:
    # Even with the cursor moved back (a restored setting, a stale read), a record that has
    # a receipt for a phone is never sent to it again.
    db, owner_id, agent_id, thread_id = task_db
    await phone(db, owner_id, PHONE, "ExponentPushToken[phone000000000001]")
    expo = FakeExpo(db, httpx.ReadTimeout("lost"))
    await started(db, owner_id, expo)
    async with db.sessions() as session:
        start = dict(await SettingsRepository().get(session, cursor_key(owner_id)))
    await card(db, owner_id, agent_id, thread_id, "approval_required")
    await dispatch_push(db, owner_id, CIPHER, expo)
    async with db.sessions() as session, session.begin():
        await SettingsRepository().put(session, cursor_key(owner_id), start)
    again = FakeExpo(db)
    assert await dispatch_push(db, owner_id, CIPHER, again) == 0 and again.sent == []


@pytest.mark.asyncio
async def test_a_refused_phone_does_not_cost_the_other_its_push(task_db: Fixture) -> None:
    db, owner_id, agent_id, thread_id = task_db
    await phone(db, owner_id, PHONE, "ExponentPushToken[phone000000000001]")
    await phone(db, owner_id, TABLET, "ExponentPushToken[tablet00000000002]")

    def answer(message: dict[str, Any]) -> dict[str, Any]:
        if "tablet" in message["to"]:
            raise LonoraError("push_request_refused", 502)
        return {"status": "ok", "id": "ticket"}

    expo = FakeExpo(db, answer)
    await started(db, owner_id, expo)
    await card(db, owner_id, agent_id, thread_id, "approval_required")
    await dispatch_push(db, owner_id, CIPHER, expo)
    assert sorted(row["status"] for row in await receipts(db)) == ["confirmed", "rejected"]


@pytest.mark.asyncio
async def test_a_tick_starts_at_most_a_few_sends_and_the_rest_follow(task_db: Fixture) -> None:
    db, owner_id, agent_id, thread_id = task_db
    await phone(db, owner_id, PHONE, "ExponentPushToken[phone000000000001]")
    expo = FakeExpo(db)
    await started(db, owner_id, expo)
    for _ in range(PUSHES_PER_TICK + 2):
        await card(db, owner_id, agent_id, thread_id, "approval_required")
    assert await dispatch_push(db, owner_id, CIPHER, expo) == PUSHES_PER_TICK
    assert await dispatch_push(db, owner_id, CIPHER, expo) == 2
    assert await dispatch_push(db, owner_id, CIPHER, expo) == 0


@pytest.mark.asyncio
async def test_an_unreadable_phone_or_a_failing_item_stops_nothing_else(
    task_db: Fixture, monkeypatch: pytest.MonkeyPatch
) -> None:
    import lonora_gateway.push as push

    db, owner_id, agent_id, thread_id = task_db
    await phone(db, owner_id, PHONE, "ExponentPushToken[phone000000000001]")
    await phone(db, owner_id, TABLET, "ExponentPushToken[tablet00000000002]")
    async with db.sessions() as session, session.begin():
        for row in await session.scalars(select(PushDeviceRow)):
            if row.device_id == TABLET:
                row.token_ciphertext = "written-with-another-key"
    expo = FakeExpo(db)
    await started(db, owner_id, expo)
    broken = await card(db, owner_id, agent_id, thread_id, "approval_required")
    await card(db, owner_id, agent_id, thread_id, "approval_required")
    current = push.mandatory_current

    async def failing(session: Any, item: AttentionRow) -> bool:
        if item.parameters.get("approval_id") == broken:
            raise RuntimeError("item broken")
        return await current(session, item)

    monkeypatch.setattr(push, "mandatory_current", failing)
    assert await dispatch_push(db, owner_id, CIPHER, expo) == 1
    assert [message["to"] for message in expo.sent] == ["ExponentPushToken[phone000000000001]"]


@pytest.mark.asyncio
async def test_around_is_sent_only_for_the_conversation_the_push_opens(task_db: Fixture) -> None:
    db, owner_id, agent_id, thread_id = task_db
    async with db.sessions() as session, session.begin():
        work = ThreadRow(owner_id=owner_id, agent_id=agent_id)
        session.add(work)
        await session.flush()
        work_id = work.id
    await phone(db, owner_id, PHONE, "ExponentPushToken[phone000000000001]")
    expo = FakeExpo(db)
    await started(db, owner_id, expo)
    await card(db, owner_id, agent_id, thread_id, "approval_required", record_thread=work_id)
    await dispatch_push(db, owner_id, CIPHER, expo)
    assert expo.sent[0]["data"] == {"thread_id": thread_id}


@pytest.mark.asyncio
async def test_a_phone_that_registered_a_new_token_is_kept(task_db: Fixture) -> None:
    # DeviceNotRegistered names the old token; the phone registered a new one meanwhile.
    db, owner_id, agent_id, thread_id = task_db
    await phone(db, owner_id, PHONE, "ExponentPushToken[phone000000000001]")

    async def rotate() -> None:
        await phone(db, owner_id, PHONE, "ExponentPushToken[phone000000000099]")

    def gone(_: dict[str, Any]) -> dict[str, Any]:
        return {"status": "error", "details": {"error": "DeviceNotRegistered"}}

    expo = FakeExpo(db, gone, rotate)
    await started(db, owner_id, expo)
    await card(db, owner_id, agent_id, thread_id, "approval_required")
    await dispatch_push(db, owner_id, CIPHER, expo)
    async with db.sessions() as session:
        assert [row.device_id for row in await session.scalars(select(PushDeviceRow))] == [PHONE]


async def make_due(db: Database) -> None:
    async with db.sessions() as session, session.begin():
        for row in await session.scalars(select(EffectReceiptRow)):
            if row.result.get("status") == "retry":
                row.result = {**row.result, "retry_at": utcnow().isoformat()}


@pytest.mark.asyncio
async def test_a_send_that_never_reached_expo_is_tried_again_until_a_limit(
    task_db: Fixture,
) -> None:
    # R-SEC M2 on #142: no connection or a 429 means nothing was sent, so it is retried with
    # backoff; it gives up after MAX_ATTEMPTS. A send that may have arrived never is.
    db, owner_id, agent_id, thread_id = task_db
    await phone(db, owner_id, PHONE, "ExponentPushToken[phone000000000001]")
    down = FakeExpo(db, LonoraError("push_not_sent", 502))
    await started(db, owner_id, down)
    await card(db, owner_id, agent_id, thread_id, "approval_required")
    await dispatch_push(db, owner_id, CIPHER, down)
    [receipt] = await receipts(db)
    assert receipt["status"] == "retry" and receipt["attempts"] == 1
    # Not yet due: nothing is sent.
    assert await dispatch_push(db, owner_id, CIPHER, down) == 0
    await make_due(db)
    limited = FakeExpo(db, LonoraError("push_rate_limited", 502))
    assert await dispatch_push(db, owner_id, CIPHER, limited) == 1
    await make_due(db)
    up = FakeExpo(db)
    assert await dispatch_push(db, owner_id, CIPHER, up) == 1
    assert up.sent[0]["to"] == "ExponentPushToken[phone000000000001]"
    assert up.sent[0]["body"] == attention_text("approval_required", "ar")
    [receipt] = await receipts(db)
    assert receipt["status"] == "confirmed" and receipt["attempts"] == 2
    assert await dispatch_push(db, owner_id, CIPHER, up) == 0


@pytest.mark.asyncio
async def test_retries_stop_at_the_limit(task_db: Fixture) -> None:
    import lonora_gateway.push as push

    db, owner_id, agent_id, thread_id = task_db
    await phone(db, owner_id, PHONE, "ExponentPushToken[phone000000000001]")
    down = FakeExpo(db, LonoraError("push_not_sent", 502))
    await started(db, owner_id, down)
    await card(db, owner_id, agent_id, thread_id, "approval_required")
    for _ in range(push.MAX_ATTEMPTS):
        await dispatch_push(db, owner_id, CIPHER, down)
        await make_due(db)
    assert len(down.sent) == push.MAX_ATTEMPTS
    [receipt] = await receipts(db)
    assert receipt["status"] == "rejected" and receipt["code"] == "push_not_sent"
    assert await dispatch_push(db, owner_id, CIPHER, down) == 0


@pytest.mark.asyncio
async def test_the_adapter_reports_a_connection_that_was_never_made() -> None:
    def refuse(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("refused", request=request)

    message = {"to": "ExponentPushToken[phone000000000001]"}
    with pytest.raises(LonoraError) as failed:
        await ExpoPushTransport(None, httpx.MockTransport(refuse)).send([message])
    assert failed.value.code == "push_not_sent"


@pytest.mark.asyncio
async def test_a_retry_is_dropped_once_its_card_has_ended(task_db: Fixture) -> None:
    db, owner_id, agent_id, thread_id = task_db
    await phone(db, owner_id, PHONE, "ExponentPushToken[phone000000000001]")
    down = FakeExpo(db, LonoraError("push_not_sent", 502))
    await started(db, owner_id, down)
    approval = await card(db, owner_id, agent_id, thread_id, "approval_required")
    await dispatch_push(db, owner_id, CIPHER, down)
    async with db.sessions() as session, session.begin():
        row = await session.get(TradeApprovalRow, approval)
        assert row
        row.status = "rejected"
    await make_due(db)
    up = FakeExpo(db)
    assert await dispatch_push(db, owner_id, CIPHER, up) == 0 and up.sent == []
    [receipt] = await receipts(db)
    assert receipt["status"] == "withdrawn"


async def secret_card(
    db: Database, owner_id: str, agent_id: str, thread_id: str, source: str
) -> str:
    async with db.sessions() as session, session.begin():
        card_row = OwnerActionRow(
            owner_id=owner_id,
            agent_id=agent_id,
            thread_id=thread_id,
            run_id=str(uuid4()) if source == "agent" else None,
            source=source,
            kind="connect_credential",
            subject="secret:" + uuid4().hex,
            payload={},
            payload_hash=uuid4().hex,
            status="pending",
            timeline_seq=11,
            expires_at=utcnow() + timedelta(days=7),
        )
        session.add(card_row)
        await session.flush()
        item = AttentionRow(
            owner_id=owner_id,
            agent_id=agent_id,
            thread_id=thread_id,
            logical_key=uuid4().hex,
            coalesce_key=uuid4().hex,
            importance="action_required",
            code="secret_requested",
            parameters={"owner_action_id": card_row.id},
            due_at=utcnow(),
        )
        session.add(item)
        await session.flush()
        publish_ready(session, item, None)
        return card_row.id


async def outage(
    db: Database, owner_id: str, agent_id: str, thread_id: str, account: str | None, code: str
) -> str:
    """A disconnected account and its health item, as W-ATTN raises it."""
    since = (utcnow() - timedelta(minutes=3)).isoformat()
    async with db.sessions() as session, session.begin():
        if account is None:
            row = BrokerSessionRow(owner_id=owner_id, payload={"enabled": True})
            session.add(row)
            await session.flush()
            account = row.id
        broker = await session.get(BrokerSessionRow, account)
        assert broker
        recovery = dict(broker.state.get("broker_recovery") or {})
        if recovery.get("status") != "disconnected":
            recovery = {"status": "disconnected", "since": since}
        recovery["reason_code"] = (
            "broker_credentials_rejected" if code == "broker_token_rejected" else "timeout"
        )
        broker.state = {**broker.state, "broker_recovery": recovery}
        item = AttentionRow(
            owner_id=owner_id,
            agent_id=agent_id,
            thread_id=thread_id,
            logical_key=uuid4().hex,
            coalesce_key=uuid4().hex,
            importance="action_required",
            code=code,
            parameters={"account_id": account, "since": recovery["since"]},
            due_at=utcnow(),
        )
        session.add(item)
        await session.flush()
        publish_ready(session, item, None)
    return account


@pytest.mark.asyncio
async def test_a_secret_card_an_agent_waits_on_pushes_and_a_system_one_does_not(
    task_db: Fixture,
) -> None:
    db, owner_id, agent_id, thread_id = task_db
    await phone(db, owner_id, PHONE, "ExponentPushToken[phone000000000001]")
    expo = FakeExpo(db)
    await started(db, owner_id, expo)
    await secret_card(db, owner_id, agent_id, thread_id, "system")
    await secret_card(db, owner_id, agent_id, thread_id, "agent")
    assert await dispatch_push(db, owner_id, CIPHER, expo) == 1
    assert expo.sent[0]["body"] == attention_text("secret_requested", "ar")
    assert expo.sent[0]["data"] == {"thread_id": thread_id, "around": 11}
    assert await dispatch_push(db, owner_id, CIPHER, expo) == 0


@pytest.mark.asyncio
async def test_a_broker_problem_pushes_once_per_account_and_outage(task_db: Fixture) -> None:
    db, owner_id, agent_id, thread_id = task_db
    await phone(db, owner_id, PHONE, "ExponentPushToken[phone000000000001]")
    expo = FakeExpo(db)
    await started(db, owner_id, expo)
    account = await outage(db, owner_id, agent_id, thread_id, None, "broker_token_rejected")
    assert await dispatch_push(db, owner_id, CIPHER, expo) == 1
    assert expo.sent[0]["body"] == attention_text("broker_token_rejected", "ar")
    assert expo.sent[0]["data"] == {"thread_id": thread_id}
    # The same outage named again by another health item (the reason flapped): no push.
    await outage(db, owner_id, agent_id, thread_id, account, "broker_connection_lost")
    assert await dispatch_push(db, owner_id, CIPHER, expo) == 0
    # A new outage of the same account is a new problem.
    async with db.sessions() as session, session.begin():
        broker = await session.get(BrokerSessionRow, account)
        assert broker
        broker.state = {"broker_recovery": {"status": "connected"}}
    await outage(db, owner_id, agent_id, thread_id, account, "broker_connection_lost")
    assert await dispatch_push(db, owner_id, CIPHER, expo) == 1
