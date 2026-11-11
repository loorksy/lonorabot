"""Behaviour case: «كيف وضع الذهب؟» on an account whose symbols carry a broker suffix.

Real API, database and tool loop; imported simulation and a scripted model that names
the instrument the way the incident's model did ("XAUUSD", «الذهب»), never the broker's
spelling. The reply must carry the price and its context, no internal code, and no
question about a symbol name. The same account then shows the order rules: an order
names the account's exact symbol or is refused with the real candidates and the next
call, two matching contracts are never chosen between, and the approval card carries
the broker's real symbol and contract specification.
"""

import asyncio
import json
import re
from datetime import timedelta
from typing import Any, cast
from unittest.mock import patch
from uuid import uuid4

from check_streaming import Fixture
from lonora_adapter_kit.types import ModelMessage, ModelReply, ToolCall
from lonora_agent.executor import execute_run
from lonora_contracts.domain import utcnow
from lonora_contracts.model_routing import ModelSelection
from lonora_db.schema import RunRow, TradingAccountRow
from lonora_tools.loader import load_tools
from lonora_tools.symbols import ASK_WHICH_CONTRACT, USE_THE_SYMBOL, SymbolNotResolved

QUESTION = "كيف وضع الذهب؟"
# A result code: lowercase words joined by underscores (symbol_not_found).
INTERNAL_CODE = re.compile(r"[a-z]+(?:_[a-z0-9]+)+")
SYMBOL_QUESTION = re.compile(r"[؟?]|رمز|symbol", re.IGNORECASE)
GOLD = "XAUUSDm"


def contract(symbol: str, base: str, description: str, size: str) -> dict[str, Any]:
    return {
        "symbol": symbol,
        "description": description,
        "path": "Forex\\Metals\\" + symbol if base.startswith("XA") else "Forex\\" + symbol,
        "digits": 2,
        "tick_size": "0.01",
        "volume_min": "0.01",
        "volume_max": "10",
        "volume_step": "0.01",
        "contract_size": size,
        "base_currency": base,
        "profit_currency": "USD",
    }


def snapshot(instruments: list[dict[str, Any]], login: str) -> dict[str, Any]:
    now = utcnow()
    bar = {"symbol": GOLD, "open": "4100", "high": "4112", "low": "4095", "close": "4108"}
    return {
        "snapshot": {
            "balance": "10000",
            "currency": "USD",
            "broker": "Explicit suffix-account fixture",
            "login": login,
            "server": "Fixture-MT5Trial",
            "instruments": instruments,
            "quotes": {
                GOLD: {
                    "symbol": GOLD,
                    "bid": "4108.20",
                    "ask": "4108.45",
                    "observed_at": now.isoformat(),
                    "source": "explicit-simulation-fixture",
                }
            },
            "candles": {
                GOLD + ":1h": [
                    {**bar, "timeframe": "1h", "time": (now - timedelta(hours=260 - i)).isoformat()}
                    for i in range(260)
                ],
                GOLD + ":1d": [
                    {**bar, "timeframe": "1d", "time": (now - timedelta(days=30 - i)).isoformat()}
                    for i in range(30)
                ],
            },
        }
    }


SUFFIXED = [
    contract("EURUSDm", "EUR", "Euro vs US Dollar", "100000"),
    contract(GOLD, "XAU", "Gold vs US Dollar", "100"),
    contract("XAGUSDm", "XAG", "Silver vs US Dollar", "5000"),
]


async def main() -> None:
    fixture = await Fixture().open()
    connection_id = None
    connections: list[str] = []
    try:
        agent = await fixture.agent("Suffix account fixture", supervised=True)
        thread = await fixture.conversation(agent)
        connection = await fixture.request(
            "POST",
            "/trading/connections",
            {"provider": "simulation", "account_id": uuid4().hex, "enabled": True},
        )
        connection_id = connection["id"]
        connections.append(connection_id)
        seed = f"/trading/connections/{connection_id}/simulation"
        await fixture.request("POST", seed, snapshot(SUFFIXED, "472790406"))
        # A second account that lists a standard and a cent gold contract.
        two_contracts = (
            await fixture.request(
                "POST",
                "/trading/connections",
                {"provider": "simulation", "account_id": uuid4().hex, "enabled": True},
            )
        )["id"]
        connections.append(two_contracts)
        await fixture.request(
            "POST",
            f"/trading/connections/{two_contracts}/simulation",
            snapshot([*SUFFIXED, contract("XAUUSDc", "XAU", "Gold cent", "1")], "472790407"),
        )
        await fixture.request(
            "PUT", "/trading/controls", {"enabled": True, "emergency_stop": False}
        )
        run = await fixture.request(
            "POST",
            "/runs",
            {"agent_id": agent["id"], "thread_id": thread["id"], "prompt": QUESTION},
        )
        context = await fixture.lease(run)
        phase = 0
        observations: list[dict[str, Any]] = []

        async def complete(
            capability: Any, messages: list[ModelMessage], tools: Any, **kwargs: Any
        ):
            nonlocal phase
            phase += 1
            if phase == 1:
                reply = ModelReply(
                    tool_calls=[ToolCall(id="accounts", name="list_accounts", arguments={})]
                )
            elif phase == 2:
                # The incident's two calls: the price by the usual code, the contract by
                # the owner's own word. Neither is this broker's spelling.
                reply = ModelReply(
                    tool_calls=[
                        ToolCall(
                            id="price",
                            name="market_snapshot",
                            arguments={
                                "account_id": connection_id,
                                "symbol": "XAUUSD",
                                "timeframes": ["1h"],
                            },
                        ),
                        ToolCall(
                            id="contract",
                            name="market_instrument",
                            arguments={"account_id": connection_id, "symbol": "الذهب"},
                        ),
                    ]
                )
            else:
                observations.extend(
                    json.loads(message.content) for message in messages if message.role == "tool"
                )
                price = next(item for item in observations if "quote" in item)
                trend = {"up": "صاعد", "down": "هابط"}.get(
                    price["timeframes"][0]["trend"]["label"], "عرضي"
                )
                reply = ModelReply(
                    text=(
                        f"الذهب الآن عند {price['quote']['bid']} على حسابك ({price['symbol']})، "
                        f"واتجاه الساعة {trend}."
                    )
                )
            return reply, ModelSelection(provider="openai", model="explicit-scripted-gold-fixture")

        with patch.object(context.router, "complete", complete):
            await execute_run(context, load_tools(), 120, 12)
        # Nothing the model was handed failed: it never saw a code or a reason to ask.
        assert len(observations) == 3 and all(item["ok"] is True for item in observations)
        assert not any("code" in item for item in observations)
        price, spec = (
            next(item for item in observations if "quote" in item),
            next(item for item in observations if "contract_size" in item),
        )
        assert price["symbol"] == GOLD and price["quote"]["bid"] == "4108.20"
        assert price["symbol_resolution"] == {
            "requested": "XAUUSD",
            "symbol": GOLD,
            "description": "Gold vs US Dollar",
        }
        assert spec["symbol"] == GOLD and spec["contract_size"] == "100"
        assert spec["symbol_resolution"] == {
            "requested": "الذهب",
            "symbol": GOLD,
            "description": "Gold vs US Dollar",
        }
        async with fixture.runtime.db.sessions() as session:
            row = await session.get(RunRow, run["id"])
            assert row and row.status == "completed" and row.result
            answer = row.result
        assert "4108.20" in answer and GOLD in answer and "اتجاه" in answer
        assert not INTERNAL_CODE.search(answer) and not SYMBOL_QUESTION.search(answer)
        messages = cast(
            list[dict[str, Any]], await fixture.request("GET", f"/threads/{thread['id']}/messages")
        )
        assert any(message["content"] == answer for message in messages)
        print(
            "PASS «كيف وضع الذهب؟» on a suffixed account: price and context from the account's "
            "own symbol, no internal code, no question about a symbol name"
        )

        order = {"account_id": connection_id, "action": "buy", "volume": "0.01"}
        buying = await fixture.request(
            "POST",
            "/runs",
            {"agent_id": agent["id"], "thread_id": thread["id"], "prompt": "اشتر ذهب"},
        )
        context = await fixture.lease(buying)
        approvals = f"/trading/approvals?thread_id={thread['id']}"

        # A standard and a cent contract on the account: an order never chooses.
        for requested in ("XAUUSD", "gold", "الذهب"):
            try:
                await load_tools().execute(
                    ToolCall(
                        id="two-" + uuid4().hex[:6],
                        name="trade_execute",
                        arguments={**order, "account_id": two_contracts, "symbol": requested},
                    ),
                    context,
                )
            except SymbolNotResolved as failure:
                assert failure.code == "symbol_ambiguous"
                assert failure.details["next"] == ASK_WHICH_CONTRACT
                assert [
                    (item["symbol"], item["contract_size"])
                    for item in failure.details["candidates"]
                ] == [("XAUUSDc", "1"), (GOLD, "100")]
            else:
                raise AssertionError("An order must never choose between two contracts")
        assert not await fixture.request("GET", approvals)
        print("PASS a standard and a cent contract: an order never chooses, no card is made")

        phase = 0
        refusal: dict[str, Any] = {}

        async def order_model(
            capability: Any, messages: list[ModelMessage], tools: Any, **kwargs: Any
        ):
            nonlocal phase
            phase += 1
            symbol = "XAUUSD"
            if phase > 1:
                # The refusal names the real symbol and the next call; the model follows it.
                refusal.update(
                    json.loads(
                        next(
                            m for m in messages if m.role == "tool" and m.tool_call_id == "o1"
                        ).content
                    )
                )
                symbol = refusal["candidates"][0]["symbol"]
            return ModelReply(
                tool_calls=[
                    ToolCall(
                        id="o" + str(min(phase, 2)),
                        name="trade_execute",
                        arguments={**order, "symbol": symbol},
                    )
                ]
            ), ModelSelection(provider="openai", model="explicit-scripted-gold-fixture")

        with patch.object(context.router, "complete", order_model):
            await execute_run(context, load_tools(), 120, 12)
        assert refusal["ok"] is False and refusal["code"] == "symbol_not_found"
        assert refusal["next"] == USE_THE_SYMBOL.format(symbol=GOLD)
        assert refusal["candidates"] == [
            {
                "symbol": GOLD,
                "description": "Gold vs US Dollar",
                "path": "Forex\\Metals\\" + GOLD,
                "volume_min": "0.01",
                "volume_step": "0.01",
                "contract_size": "100",
                "base_currency": "XAU",
                "profit_currency": "USD",
            }
        ]
        assert (await fixture.request("GET", "/runs/" + buying["id"]))["status"] == "waiting_input"
        cards = cast(list[dict[str, Any]], await fixture.request("GET", approvals))
        assert len(cards) == 1 and cards[0]["status"] == "pending"
        assert [item["symbol"] for item in cards[0]["requests"]] == [GOLD]
        assert [
            (item["symbol"], item["contract_size"], item["volume_min"], item["description"])
            for item in cards[0]["contracts"]
        ] == [(GOLD, "100", "0.01", "Gold vs US Dollar")]
        broker = await context.brokers.get(context.owner_id, connection_id)
        assert not await broker.positions()
        print(
            "PASS an order by a code the account does not list is refused with the real symbol "
            "and the next call; the model continues itself and the approval card names the "
            "broker's symbol and contract specification"
        )
    finally:
        for identifier in connections:
            async with fixture.runtime.db.sessions() as session, session.begin():
                row = await session.get(TradingAccountRow, identifier)
                if row:
                    await session.delete(row)
            await fixture.request("DELETE", "/trading/connections/" + identifier)
        await fixture.request(
            "PUT", "/trading/controls", {"enabled": False, "emergency_stop": False}
        )
        await fixture.close()


if __name__ == "__main__":
    asyncio.run(main())
