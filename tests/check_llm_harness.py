"""Scripted Agent harness acceptance on disposable PostgreSQL and a simulation broker.

These scenarios verify context, discovery, persistence and financial effects. The
scripted provider does not establish the reasoning quality of a live LLM.
"""

import asyncio
import json
from datetime import datetime, timedelta
from decimal import Decimal
from typing import Any
from unittest.mock import patch
from uuid import uuid4

from check_streaming import Fixture
from device_fixture import Device
from lonora_adapter_kit.types import ModelMessage, ModelReply, ToolCall, ToolDefinition
from lonora_agent.executor import execute_run
from lonora_contracts.domain import utcnow
from lonora_contracts.model_routing import ModelSelection
from lonora_contracts.trading import TradingControl
from lonora_core.user_error import LonoraError
from lonora_db.runs import require_lease
from lonora_db.schema import (
    MessageRow,
    RunRow,
    ThreadRow,
    TicketRow,
    TradeApprovalRow,
    TradingAccountRow,
)
from lonora_db.task_wait import resume_ready_waits
from lonora_db.trading_decisions import decision_history
from lonora_session.idempotency import stable_id
from lonora_tools.context import ToolContext
from lonora_tools.loader import load_tools
from lonora_trading.controls import read_controls, save_controls
from sqlalchemy import func, select


def response(call: ToolCall | None = None, text: str = "") -> tuple[ModelReply, ModelSelection]:
    return ModelReply(text=text, tool_calls=[call] if call else []), ModelSelection(
        provider="openai", model="scripted-llm-harness"
    )


def call(identity: str, name: str, **arguments: Any) -> ToolCall:
    return ToolCall(id=identity, name=name, arguments=arguments)


def inspect(identity: str, name: str) -> tuple[ModelReply, ModelSelection]:
    return response(call(identity, "tool_environment", tool_name=name))


def observation(messages: list[ModelMessage], identity: str) -> dict[str, Any]:
    row = next(
        message
        for message in reversed(messages)
        if message.role == "tool" and message.tool_call_id == identity
    )
    return json.loads(row.content)


async def simulation(f: Fixture, symbol: str = "EURUSD.suffix") -> tuple[str, str]:
    account = (
        await f.request(
            "POST",
            "/trading/connections",
            {"provider": "simulation", "account_id": uuid4().hex, "enabled": True},
        )
    )["id"]
    now = utcnow()
    await f.request(
        "POST",
        f"/trading/connections/{account}/simulation",
        {
            "snapshot": {
                "currency": "USD",
                "balance": "10000",
                "instruments": [
                    {
                        "symbol": symbol,
                        "digits": 2,
                        "tick_size": "0.01",
                        "volume_min": "0.1",
                        "volume_max": "100",
                        "volume_step": "0.1",
                    }
                ],
                "quotes": {
                    symbol: {
                        "symbol": symbol,
                        "bid": "100",
                        "ask": "101",
                        "observed_at": now.isoformat(),
                        "source": "harness-simulation",
                    }
                },
                "candles": {
                    symbol + ":1m": [
                        {
                            "symbol": symbol,
                            "timeframe": "1m",
                            "time": (now - timedelta(minutes=3 - index)).isoformat(),
                            "open": "99",
                            "high": "102",
                            "low": "98",
                            "close": "100",
                        }
                        for index in range(3)
                    ]
                },
            }
        },
    )
    return account, symbol


async def seed_context(f: Fixture, thread: dict[str, Any], symbol: str) -> None:
    """Seed prior owner facts; normal history_context must retain them on a short follow-up."""
    async with f.runtime.db.sessions() as session, session.begin():
        row = await session.get(ThreadRow, thread["id"], with_for_update=True)
        assert row
        session.add(
            MessageRow(
                thread_id=row.id,
                seq=row.next_seq,
                role="user",
                content=f"السوق المقصود {symbol}. اخترت الشراء، وحد المخاطرة الذي حددته 150 USD.",
            )
        )
        row.next_seq += 1


async def discovery_and_context(f: Fixture) -> None:
    account, symbol = await simulation(f)
    registry = load_tools()
    for index, prompt in enumerate(
        (
            "راجع السوق الحالي وفق ما اتفقنا عليه",
            "Review the market using our agreed context",
            "تابع",
        )
    ):
        agent = await f.agent("Harness context")
        thread = await f.conversation(agent)
        await seed_context(f, thread, symbol)
        run = await f.request(
            "POST", "/runs", {"agent_id": agent["id"], "thread_id": thread["id"], "prompt": prompt}
        )
        ctx = await f.lease(run)
        phase = 0

        async def model(
            _: Any,
            messages: list[ModelMessage],
            tools: list[ToolDefinition],
            *,
            expected_prompt: str = prompt,
            variant_index: int = index,
            **kwargs: Any,
        ) -> tuple[ModelReply, ModelSelection]:
            nonlocal phase
            names = {tool.name for tool in tools}
            contents = "\n".join(message.content for message in messages)
            assert expected_prompt in contents and symbol in contents and "150 USD" in contents
            assert "اخترت الشراء" in contents
            if phase == 0:
                assert (
                    "tool_environment" in names and "market_quote" not in names and len(names) <= 4
                )
                phase += 1
                return inspect("discover-quote", "market_quote")
            assert "market_quote" in names
            if phase == 1:
                phase += 1
                # Worker loss after discovery was durably observed, before the next request.
                if variant_index == 0:
                    raise asyncio.CancelledError()
            if phase == 2:
                phase += 1
                return response(call("quote", "market_quote", account_id=account, symbol=symbol))
            assert observation(messages, "quote")["ok"]
            phase += 1
            return response(text="راجعت السعر الحالي مع الاحتفاظ بالسوق والمخاطرة اللذين حددتهما.")

        with patch.object(ctx.router, "complete", model):
            if index == 0:
                try:
                    await execute_run(ctx, registry, 120, 12)
                except asyncio.CancelledError:
                    pass
                else:
                    raise AssertionError("scripted worker loss was not reached")
                old = ctx
                ctx = await f.lease(run)
                async with f.runtime.db.sessions() as session:
                    try:
                        await require_lease(session, old.lease)
                    except LonoraError as error:
                        assert error.code == "stale_lease"
                    else:
                        raise AssertionError("replaced worker retained authority")
            await execute_run(ctx, registry, 120, 12)
        async with f.runtime.db.sessions() as session:
            row = await session.get(RunRow, run["id"])
            assert row and row.status == "completed", row.error_code if row else None
            calls = [
                item
                for item in row.execution_state["messages"]
                if item["role"] == "tool" and item.get("tool_call_id") == "quote"
            ]
            assert len(calls) == 1 and phase == 4
    print(
        "PASS Arabic/English/short follow-up context, progressive discovery and worker replacement"
    )

    agent = await f.agent("Read-only harness")
    run = await f.run(agent, await f.conversation(agent))
    ctx = await f.lease(run)
    async with f.runtime.db.sessions() as session, session.begin():
        row = await session.get(RunRow, run["id"], with_for_update=True)
        assert row
        row.model_metadata = {**row.model_metadata, "authority": "observe_only"}
    phase = 0

    async def reader(
        _: Any, messages: list[ModelMessage], tools: list[ToolDefinition], **kwargs: Any
    ) -> tuple[ModelReply, ModelSelection]:
        nonlocal phase
        advertised = {tool.name for tool in tools}
        assert not advertised.intersection(
            name for name, tool in registry.tools.items() if tool.financial
        )
        phase += 1
        if phase == 1:
            return inspect("denied-discovery", "trade_execute")
        assert observation(messages, "denied-discovery")["code"] == "tool_not_allowed"
        return response(text="يمكنني مراجعة البيانات المتاحة ضمن الصلاحية الحالية.")

    with patch.object(ctx.router, "complete", reader):
        await execute_run(ctx, registry, 120, 8)
    assert phase == 2
    print("PASS read-only discovery never advertises or activates financial execution")


async def managed_task(f: Fixture, account: str) -> tuple[dict[str, Any], ToolContext]:
    agent = next(
        row for row in (await f.client.get("/api/agents")).json() if row["role"] == "personal"
    )
    thread = await f.conversation(agent)
    device = await Device.enroll(f)
    proposal = await f.request(
        "POST",
        f"/agents/{agent['id']}/account-authorities",
        {
            "thread_id": thread["id"],
            "account_id": account,
            "management_mode": "full",
            "symbol_scope": "account",
            "symbols": [],
            "actions": ["buy", "sell", "close_position", "modify_position"],
            "allow_manual_positions": True,
        },
    )
    challenge = await f.request("POST", f"/account-authorities/{proposal['id']}/challenge", {})
    grant = await f.request(
        "POST",
        "/account-authorities/verify",
        device.assertion(challenge, f.settings.allowed_origin),
    )
    async with f.runtime.db.sessions() as session:
        task = await session.get(TicketRow, stable_id(grant["id"], "account-management-task"))
        assert task
        run = await session.get(RunRow, task.payload["run_id"])
        assert run and run.model_metadata["account_management_id"] == grant["id"]
        data = {"id": run.id, "agent_id": run.agent_id, "thread_id": run.thread_id}
    return data, await f.lease(data)


async def conditional_mission(f: Fixture, valid: bool) -> None:
    account, symbol = await simulation(f, "XAUUSDm" if valid else "US500.cash")
    run, ctx = await managed_task(f, account)
    registry = load_tools()
    broker = await ctx.brokers.get(f.owner, account)
    phase = 0
    decided = ""
    verified = False
    conditional = {
        "direction": "BUY",
        "condition": "A retest holds the observed support and buyers regain control.",
        "invalidation": "The retest fails and the current evidence contradicts recovery.",
        "review_instruction": "Read fresh market evidence and reassess the retest; a timer is only a wake signal.",
    }
    params = {
        "account_id": account,
        "symbol": symbol,
        "timeframe": "1m",
        "summary": "Interpret the developing retest using current broker evidence.",
        "market_view": {"bias": "BULLISH"},
    }

    async def model(
        _: Any, messages: list[ModelMessage], tools: list[ToolDefinition], **kwargs: Any
    ) -> tuple[ModelReply, ModelSelection]:
        nonlocal phase, decided, verified
        phase += 1
        names = {tool.name for tool in tools}
        if phase == 1:
            assert "market_decision_record" not in names
            return inspect("discover-decision", "market_decision_record")
        if phase == 2:
            assert "market_decision_record" in names
            return response(
                call(
                    "conditional",
                    "market_decision_record",
                    **params,
                    action="CONDITIONAL_ENTRY",
                    conditional_entry=conditional,
                )
            )
        if phase == 3:
            saved = observation(messages, "conditional")
            assert saved["action"] == "CONDITIONAL_ENTRY" and not saved["execution_authorized"]
            assert saved["readiness"]["entry_readiness"]["state"] == "AWAITING_REASSESSMENT"
            return inspect("discover-wait", "task_wait")
        if phase == 4:
            return response(call("review-later", "task_wait", kind="timer", seconds=30))
        assert any("<runtime_wake>" in message.content for message in messages)
        if phase == 5:
            assert "market_decision_record" in names and "task_wait" in names
            return inspect("discover-live-quote", "market_quote")
        if phase == 6:
            return response(call("fresh-quote", "market_quote", account_id=account, symbol=symbol))
        if phase == 7:
            fresh = observation(messages, "fresh-quote")
            assert fresh["ok"]
            # Scripted decisions are fixture outcomes, not a production trading rule.
            quote = fresh.get("quote", fresh)
            decided = "BUY" if Decimal(str(quote["bid"])) > 102 else "WAIT"
            assert decided == ("BUY" if valid else "WAIT")
            return response(call("reassessed", "market_decision_record", **params, action=decided))
        if phase == 8:
            reassessed = observation(messages, "reassessed")
            assert reassessed["action"] == decided and not reassessed["execution_authorized"]
            if not valid:
                return response(text="أعدت التقييم، ولم يتحقق شرط الدخول؛ لم أفتح صفقة.")
            assert reassessed["readiness"]["market_assessment"]["bias"] == "BULLISH"
            assert reassessed["readiness"]["entry_readiness"]["state"] == "MODEL_SELECTED"
            assert (
                reassessed["readiness"]["execution_readiness"]["state"] == "REVALIDATION_REQUIRED"
            )
            return inspect("discover-trade", "trade_execute")
        if phase == 9:
            return response(
                call(
                    "entry",
                    "trade_execute",
                    account_id=account,
                    symbol=symbol,
                    action="buy",
                    volume="0.1",
                    stop_loss="90",
                    take_profit="110",
                )
            )
        result = observation(messages, "entry")
        assert result["status"] == "confirmed", result
        assert result["details"]["verification"]["status"] == "verified"
        verified = True
        return response(text="فُتحت الصفقة وتحققت من وجودها ومن مستويات الحماية.")

    with patch.object(ctx.router, "complete", model):
        await execute_run(ctx, registry, 120, 16)
    assert phase == 4 and not await broker.positions()
    async with f.runtime.db.sessions() as session:
        row = await session.get(RunRow, run["id"])
        assert row and row.status == "waiting_takeover"
        due = datetime.fromisoformat(row.execution_state["environment"]["wait"]["due_at"])
    assert await resume_ready_waits(f.runtime.db) == 0
    async with f.runtime.db.sessions() as session, session.begin():
        source = await session.get(TradingAccountRow, account, with_for_update=True)
        assert source
        bid = "103" if valid else "95"
        quote = {
            **source.payload["quotes"][symbol],
            "bid": bid,
            "ask": str(Decimal(bid) + 1),
            "observed_at": utcnow().isoformat(),
        }
        source.payload = {**source.payload, "quotes": {symbol: quote}}
    with patch("lonora_db.task_wait.utcnow", return_value=due + timedelta(seconds=1)):
        assert await resume_ready_waits(f.runtime.db) == 1
        assert await resume_ready_waits(f.runtime.db) == 0
    old = ctx
    ctx = await f.lease(run)
    async with f.runtime.db.sessions() as session:
        try:
            await require_lease(session, old.lease)
        except LonoraError as error:
            assert error.code == "stale_lease"
        else:
            raise AssertionError("old worker could act after wake")
    with patch.object(ctx.router, "complete", model):
        await execute_run(ctx, registry, 120, 16)
    async with f.runtime.db.sessions() as session:
        row = await session.get(RunRow, run["id"])
        assert row and row.status == "completed", row.error_code if row else None
        records = await decision_history(session, f.owner, account_id=account)
        assert len(records) == 2
        assert records[-1].action == "CONDITIONAL_ENTRY"
        assert (
            records[-1].conditional_entry
            and records[-1].conditional_entry.condition == conditional["condition"]
        )
        assert records[0].action == decided
        assert records[-1].evidence.quote and records[-1].evidence.quote.bid == 100
        assert records[0].evidence.quote and records[0].evidence.quote.bid == Decimal(bid)
        assert (
            await session.scalar(
                select(func.count())
                .select_from(TradeApprovalRow)
                .where(TradeApprovalRow.run_id == run["id"])
            )
            == 0
        )
    assert len(await broker.positions()) == int(valid) and verified is valid
    print(
        "PASS conditional intent -> durable wait -> same-Run fresh reassessment -> "
        + (
            "signed independently verified simulation entry"
            if valid
            else "invalidated condition with zero trades"
        )
    )


async def main() -> None:
    f = await Fixture().open()
    original = await read_controls(f.runtime.db)
    try:
        await save_controls(f.runtime.db, TradingControl(enabled=True))
        await discovery_and_context(f)
        await conditional_mission(f, True)
        await conditional_mission(f, False)
    finally:
        await save_controls(f.runtime.db, original)
        await f.close()


if __name__ == "__main__":
    asyncio.run(main())
