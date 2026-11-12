"""Browser acceptance fixture for the canonical alert card (docs/genui.md): real Runs,
a scripted model, the simulation broker quoting the screenshot's prices.

``setup``   an agent, its conversation and a simulation account (XAUUSD 2368.40, XAGUSD
            28.92, EURUSD 1.0842); prints ids and the owner's cookies.
``stream``  the owner's message «نبّهني إذا صعد الذهب فوق 2400», then its Run: three
            market_quote calls in one message (c1-c3), then the A01 reply streamed in
            chunks, as a model would (lead first, then one card line at a time).
``receipt`` the card submission's queued Run: watch_create on the card's account, then the
            receipt card, interface only.
``parity``  the parity calculator (tests/test_genui_parity.py): every catalog node and every
            local, copy, open and go action, streamed through the real compiler, so each
            client's journey checks that it draws every node type the server accepts.
``records`` a pending Trade Approval and a resolve card for an uncertain operation in the
            conversation, as their own paths raise them; prints their ids.
``slots``   the agent's reply that embeds a fixed card (``card``, default the approval) as a
            trusted slot (mandate 10.2), with words, a hide condition and a tone it tries
            to give the slot.
"""

import asyncio
import json
import sys
from collections.abc import Callable
from pathlib import Path
from typing import Any
from unittest.mock import patch
from uuid import uuid4

from check_streaming import Fixture
from lonora_adapter_kit.types import ModelMessage, ModelReply, ToolCall
from lonora_agent.executor import execute_run
from lonora_contracts.domain import utcnow
from lonora_contracts.model_routing import ModelSelection
from lonora_tools.loader import load_tools

A01 = (Path(__file__).parent / "fixtures/genui/documents/valid/a01-alert.lonora-ui").read_text()
PARITY = (Path(__file__).parent / "fixtures/genui/documents/valid/parity.lonora-ui").read_text()
PARITY_OWNER = "احسب حجم الصفقة لرصيد 10000 كما في https://example.com/position-size"
LEAD = "جهّزت التنبيه من رسالتك؛ راجع الشرط ثم أنشئه.\n"
QUOTES = {"XAUUSD": "2368.40", "XAGUSD": "28.92", "EURUSD": "1.0842"}
SELECTION = ModelSelection(provider="openai", model="scripted-genui-browser")


def instrument(symbol: str) -> dict[str, Any]:
    digits = 4 if symbol == "EURUSD" else 2
    return {
        "symbol": symbol,
        "digits": digits,
        "tick_size": "0.0001" if digits == 4 else "0.01",
        "volume_min": "0.01",
        "volume_max": "100",
        "volume_step": "0.01",
    }


async def setup(_: dict[str, Any]) -> dict[str, Any]:
    fixture = await Fixture().open()
    try:
        agent = await fixture.agent("Genui browser")
        thread = await fixture.conversation(agent)
        connection = (
            await fixture.request(
                "POST",
                "/trading/connections",
                {"provider": "simulation", "account_id": uuid4().hex, "enabled": True},
            )
        )["id"]
        await fixture.request(
            "POST",
            f"/trading/connections/{connection}/simulation",
            {
                "snapshot": {
                    "currency": "USD",
                    "balance": "10000",
                    "instruments": [instrument(symbol) for symbol in QUOTES],
                    "quotes": {
                        symbol: {
                            "symbol": symbol,
                            "bid": bid,
                            "ask": bid,
                            "observed_at": utcnow().isoformat(),
                            "source": "genui-browser",
                        }
                        for symbol, bid in QUOTES.items()
                    },
                }
            },
        )
        # A verified broker identity, as a real connection has after its first read: with
        # several accounts the server names this one in the alert's bubble (§8.3).
        from lonora_db.schema import BrokerSessionRow

        async with fixture.runtime.db.sessions() as session, session.begin():
            row = await session.get(BrokerSessionRow, connection, with_for_update=True)
            assert row is not None
            row.state = {
                **row.state,
                "broker_identity": {
                    "broker": "Simulation",
                    "login": str(uuid4().int % 10**8),
                    "server": "Demo",
                    "platform": "mt5",
                    "connection_version": row.version,
                },
            }
        return {
            "agent": agent,
            "thread": thread,
            "connection": connection,
            "cookies": [
                {"name": cookie.name, "value": cookie.value}
                for cookie in fixture.client.cookies.jar
            ],
        }
    finally:
        await fixture.close(cleanup=False)


def scripted(first: list[ToolCall], text: Callable[[list[ModelMessage]], str], delay: float):
    """Round one asks for ``first``; round two streams ``text(messages)`` in chunks."""

    async def complete(*args: Any, **kwargs: Any):
        messages: list[ModelMessage] = args[1]
        on_delta = kwargs.get("on_delta")
        if not any(m.role == "tool" for m in messages[-len(first) - 2 :]) and not any(
            m.role == "tool" and m.tool_call_id == first[0].id for m in messages
        ):
            return ModelReply(tool_calls=first), SELECTION
        reply = text(messages)
        if on_delta is not None:
            lines = reply.split("\n")
            for index, line in enumerate(lines):
                # A real provider splits mid-line: never publish a partial line.
                piece = line + ("\n" if index < len(lines) - 1 else "")
                half = len(piece) // 2
                for chunk in (piece[:half], piece[half:]):
                    if chunk:
                        await on_delta(chunk)
                        await asyncio.sleep(delay)
        return ModelReply(text=reply), SELECTION

    return complete


async def stream(data: dict[str, Any]) -> dict[str, Any]:
    fixture = await Fixture().open()
    try:
        thread_id, connection = data["thread_id"], data["connection"]
        sent = await fixture.request(
            "POST", f"/threads/{thread_id}/messages", {"content": "نبّهني إذا صعد الذهب فوق 2400"}
        )
        run = sent["runs"][0]
        context = await fixture.lease(run)
        calls = [
            ToolCall(
                id=f"c{index + 1}",
                name="market_quote",
                arguments={"account_id": connection, "symbol": symbol},
            )
            for index, symbol in enumerate(QUOTES)
        ]
        reply = LEAD + "```lonora-ui\n" + A01.rstrip("\n") + "\n```"
        with patch.object(
            context.router, "complete", scripted(calls, lambda _: reply, data.get("delay", 0.12))
        ):
            await execute_run(context, load_tools(), 120, 6)
        current = await fixture.request("GET", "/runs/" + run["id"])
        return {"run": current}
    finally:
        await fixture.close(cleanup=False)


async def receipt(data: dict[str, Any]) -> dict[str, Any]:
    from lonora_db.schema import RunRow
    from sqlalchemy import select

    fixture = await Fixture().open()
    try:
        async with fixture.runtime.db.sessions() as session:
            rows = list(
                await session.scalars(
                    select(RunRow).where(
                        RunRow.thread_id == data["thread_id"], RunRow.status == "queued"
                    )
                )
            )
        run = next(row for row in rows if row.model_metadata.get("ui_submit_origin"))
        context = await fixture.lease(
            {"id": run.id, "agent_id": run.agent_id, "thread_id": run.thread_id}
        )
        call = ToolCall(
            id="w1",
            name="watch_create",
            arguments={
                "account_id": data["connection"],
                "symbol": "XAUUSD",
                "condition": "above",
                "level": "2400",
                "prompt": "Tell the owner gold rose above 2400.",
            },
        )

        def text(messages: list[ModelMessage]) -> str:
            result = next(m for m in messages if m.role == "tool" and m.tool_call_id == "w1")
            watch = json.loads(result.content)["id"]
            lines = [
                '{"v":2,"kind":"receipt","title":"تنبيه فعّال","sub":"الذهب فوق 2,400","icon":"check"}',
                '{"type":"KeyValue","rows":[["الأصل","الذهب"],["الشرط","يصعد فوق 2,400"],["الإشعار","داخل التطبيق"]]}',
                '{"type":"Row","children":[{"type":"Button","label":"عرض التنبيهات","icon":"bell","action":{"do":"go","route":"market"}},'
                '{"type":"Button","label":"إيقاف التنبيه","icon":"bellOff","action":{"do":"send","intent":"alert.off","data":{"watch_id":"'
                + watch
                + '"}}}]}',
                '{"why":"تأكيد مختصر بالتفاصيل مع زر للخطوة التالية؛ أوضح من فقرة.","fallback":"التنبيه فعّال: الذهب فوق 2,400."}',
            ]
            return "التنبيه فعّال.\n```lonora-ui\n" + "\n".join(lines) + "\n```"

        with patch.object(context.router, "complete", scripted([call], text, 0.02)):
            await execute_run(context, load_tools(), 120, 6)
        return {"run": await fixture.request("GET", "/runs/" + run.id)}
    finally:
        await fixture.close(cleanup=False)


async def parity(data: dict[str, Any]) -> dict[str, Any]:
    fixture = await Fixture().open()
    try:
        sent = await fixture.request(
            "POST", f"/threads/{data['thread_id']}/messages", {"content": PARITY_OWNER}
        )
        run = sent["runs"][0]
        context = await fixture.lease(run)
        reply = "جهّزت لك حاسبة الحجم.\n```lonora-ui\n" + PARITY.rstrip("\n") + "\n```"

        async def complete(*args: Any, **kwargs: Any):
            on_delta = kwargs.get("on_delta")
            if on_delta is not None:
                for line in reply.split("\n"):
                    await on_delta(line + "\n")
            return ModelReply(text=reply), SELECTION

        with patch.object(context.router, "complete", complete):
            await execute_run(context, load_tools(), 120, 6)
        return {"run": await fixture.request("GET", "/runs/" + run["id"])}
    finally:
        await fixture.close(cleanup=False)


async def records(data: dict[str, Any]) -> dict[str, Any]:
    from lonora_db.owner_actions import create_card
    from lonora_db.schema import RunRow, ThreadRow, TradeApprovalRow, TradingJournalRow

    fixture = await Fixture().open()
    try:
        async with fixture.runtime.db.sessions() as session, session.begin():
            thread = await session.get(ThreadRow, data["thread_id"])
            assert thread is not None and thread.agent_id is not None
            # The approval's waiting Run sits in its own conversation, so the owner's next
            # message here starts a new Run instead of answering it.
            waiting_thread = ThreadRow(owner_id=thread.owner_id, agent_id=thread.agent_id)
            session.add(waiting_thread)
            await session.flush()
            run = RunRow(
                thread_id=waiting_thread.id, agent_id=thread.agent_id, status="waiting_input"
            )
            session.add(run)
            await session.flush()
            approval = TradeApprovalRow(
                id=uuid4().hex,
                owner_id=thread.owner_id,
                run_id=run.id,
                thread_id=thread.id,
                agent_id=thread.agent_id,
                call_id="call-slot",
                timeline_seq=thread.next_seq,
                requests=[
                    {
                        "account_id": data["connection"],
                        "symbol": "XAUUSD",
                        "action": "buy",
                        "volume": "0.10",
                        "stop_loss": "2350.00",
                        "take_profit": "2420.00",
                    }
                ],
                status="pending",
                results=[],
                broker_snapshot={},
                created_at=utcnow(),
                updated_at=utcnow(),
            )
            session.add(approval)
            operation = uuid4().hex
            session.add(
                TradingJournalRow(
                    operation_id=operation,
                    owner_id=thread.owner_id,
                    account_id=data["connection"],
                    request_hash="h",
                    request={"symbol": "XAGUSD", "action": "sell", "volume": "1"},
                    status="ambiguous",
                    result={},
                )
            )
            await session.flush()
            settle = await create_card(
                session,
                thread.owner_id,
                card_id=uuid4().hex,
                agent_id=thread.agent_id,
                thread=thread,
                run_id=None,
                source="system",
                kind="resolve_operation",
                subject="operation:" + operation,
                payload={"operation_id": operation},
            )
            return {"approval": approval.id, "settle": settle.id}
    finally:
        await fixture.close(cleanup=False)


async def slots(data: dict[str, Any]) -> dict[str, Any]:
    fixture = await Fixture().open()
    try:
        sent = await fixture.request(
            "POST", f"/threads/{data['thread_id']}/messages", {"content": "ما الذي ينتظر قراري؟"}
        )
        run = sent["runs"][0]
        context = await fixture.lease(run)
        slot = {
            "type": "Slot",
            "card": data.get("card", "trade_approval"),
            "record": data["record"],
            # Never drawn: the server keeps only where the slot sits (mandate 10.2.1).
            "label": "صفقة مضمونة",
            "text": "0.50 لوت",
            "when": "false",
            "tone": "good",
        }
        lines = [
            '{"v":2,"kind":"receipt","title":"ينتظر قرارك","sub":"طلب معلّق","icon":"check"}',
            '{"type":"Text","text":"الذهب عند المقاومة؛ الطلب أدناه بانتظار قرارك."}',
            json.dumps(slot, ensure_ascii=False),
            '{"why":"الطلب في مكانه من الشرح.","fallback":"طلب موافقة بانتظار قرارك."}',
        ]
        reply = "قبل أن تقرر:\n```lonora-ui\n" + "\n".join(lines) + "\n```"

        async def complete(*args: Any, **kwargs: Any):
            on_delta = kwargs.get("on_delta")
            if on_delta is not None:
                for line in reply.split("\n"):
                    await on_delta(line + "\n")
            return ModelReply(text=reply), SELECTION

        with patch.object(context.router, "complete", complete):
            await execute_run(context, load_tools(), 120, 6)
        return {"run": await fixture.request("GET", "/runs/" + run["id"])}
    finally:
        await fixture.close(cleanup=False)


if __name__ == "__main__":
    command = sys.argv[1]
    payload = json.loads(sys.stdin.read() or "{}")
    action = {
        "setup": setup,
        "stream": stream,
        "receipt": receipt,
        "parity": parity,
        "records": records,
        "slots": slots,
    }[command]
    print(json.dumps(asyncio.run(action(payload))))
