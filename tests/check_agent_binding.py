"""Broker-native immutable new-bot binding with real PG and explicit simulation."""

import asyncio
from decimal import Decimal
from typing import Any, cast
from uuid import uuid4

from check_streaming import Fixture
from lonora_adapter_kit.types import ToolCall
from lonora_contracts.domain import AgentCreate, utcnow
from lonora_contracts.trading import TradeRequest
from lonora_core.user_error import LonoraError
from lonora_db.agent_binding import binding_context
from lonora_db.agents import agent_data, create_agent
from lonora_db.schema import AgentRow, RunRow, TradingAccountRow
from lonora_tools.loader import load_tools
from lonora_voice.context import voice_context


async def checks() -> None:
    fixture = await Fixture().open()
    connections: list[str] = []
    symbols = ["EURUSDm", "XAUUSD.pro", "US500.cash", "BTCUSD.a"]
    try:

        async def connection() -> str:
            row = await fixture.request(
                "POST",
                "/trading/connections",
                {"provider": "simulation", "account_id": uuid4().hex, "enabled": True},
            )
            identifier = str(row["id"])
            connections.append(identifier)
            await fixture.request(
                "POST",
                f"/trading/connections/{identifier}/simulation",
                {
                    "snapshot": {
                        "currency": "USD",
                        "balance": "10000",
                        "instruments": [
                            {
                                "symbol": s,
                                "digits": 2,
                                "tick_size": "0.01",
                                "volume_min": "0.1",
                                "volume_max": "100",
                                "volume_step": "0.1",
                            }
                            for s in symbols
                        ],
                        "quotes": {
                            s: {
                                "symbol": s,
                                "bid": "100",
                                "ask": "101",
                                "observed_at": utcnow().isoformat(),
                                "source": "explicit-binding-fixture",
                            }
                            for s in symbols
                        },
                    }
                },
            )
            return identifier

        primary, secondary = await connection(), await connection()
        missing = await fixture.client.post("/api/agents", json={"name": "Missing market"})
        assert (
            missing.status_code == 422
            and missing.json()["code"] == "agent_trading_binding_required"
        )
        unknown = await fixture.client.post(
            "/api/agents",
            json={
                "name": "Unknown market",
                "trading_account_id": primary,
                "trading_symbol": "XAUUSD",
            },
        )
        assert unknown.status_code == 404 and unknown.json()["code"] == "symbol_not_found"
        agents: list[dict[str, Any]] = []
        for symbol in symbols:
            agent = await fixture.request(
                "POST",
                "/agents",
                {
                    "name": "Bound " + symbol,
                    "trading_account_id": primary,
                    "trading_symbol": symbol,
                },
            )
            current = await fixture.request("GET", "/agents/" + agent["id"])
            assert current["trading_symbol"] == symbol and current["trading_account_id"] == primary
            fixture.agents.append(agent["id"])
            agents.append(agent)
            assert agent["trading_symbol"] == symbol and agent["trading_account_id"] == primary
            changed = await fixture.client.patch(
                "/api/agents/" + agent["id"], json={"trading_symbol": symbols[0]}
            )
            assert changed.status_code == 422
            renamed = await fixture.request(
                "PATCH", "/agents/" + agent["id"], {"name": "Renamed " + symbol}
            )
            assert renamed["trading_symbol"] == symbol
        print(
            "PASS new creation requires real broker selection; all asset suffixes exact; PATCH cannot alter binding"
        )
        agent = agents[0]
        thread = await fixture.conversation(agent)
        context = await fixture.lease(await fixture.run(agent, thread))
        registry = load_tools()

        async def denied(name: str, args: dict[str, Any], code: str) -> None:
            try:
                await registry.execute(ToolCall(id=uuid4().hex, name=name, arguments=args), context)
            except LonoraError as error:
                assert error.code == code, (name, error.code)
            else:
                raise AssertionError(name + " bypassed binding")

        for name in (
            "market_quote",
            "market_instrument",
            "market_candles",
            "chart_indicator",
            "chart_open",
            "chart_snapshot",
        ):
            args: dict[str, Any] = {"account_id": primary, "symbol": symbols[1]}
            if name in ("market_candles", "chart_indicator", "chart_snapshot"):
                args["timeframe"] = "1h"
            if name == "chart_indicator":
                args["name"] = "rsi"
            await denied(name, args, "agent_trading_symbol_mismatch")
        await denied(
            "market_quote",
            {"account_id": secondary, "symbol": symbols[0]},
            "agent_trading_account_mismatch",
        )
        await denied(
            "trade_execute",
            {"account_id": primary, "symbol": symbols[1], "action": "buy", "volume": "0.1"},
            "agent_trading_symbol_mismatch",
        )
        await denied(
            "trade_close_positions", {"account_id": secondary}, "agent_trading_account_mismatch"
        )
        await denied(
            "watch_create",
            {
                "account_id": primary,
                "symbol": symbols[1],
                "kind": "price",
                "condition": "above",
                "level": "120",
                "prompt": "Explicit binding fixture",
            },
            "agent_trading_symbol_mismatch",
        )
        await denied(
            "goal_create",
            {
                "title": "Wrong market",
                "objective": "Explicit invalid fixture",
                "account_id": primary,
                "symbol": symbols[0],
                "steps": [
                    {
                        "id": "entry",
                        "title": "Wrong step",
                        "kind": "trade",
                        "trade": {
                            "account_id": primary,
                            "symbol": symbols[1],
                            "action": "buy",
                            "volume": "0.1",
                        },
                    }
                ],
            },
            "tool_arguments_invalid",
        )
        allowed = await registry.execute(
            ToolCall(
                id="quote",
                name="market_quote",
                arguments={"account_id": primary, "symbol": symbols[0]},
            ),
            context,
        )
        assert allowed["symbol"] == symbols[0]
        catalog = await registry.execute(
            ToolCall(id="symbols", name="market_symbols", arguments={"account_id": primary}),
            context,
        )
        assert catalog["symbols"] == [symbols[0]]
        print(
            "PASS generic tool boundary rejects cross-pair/account quote/candle/chart/trade/watch and nested goal steps"
        )
        async with fixture.runtime.db.sessions() as session, session.begin():
            snapshot = await session.get(TradingAccountRow, primary, with_for_update=True)
            assert snapshot is not None
            snapshot.payload = {
                **snapshot.payload,
                "positions": [
                    {
                        "id": "manual-" + s,
                        "symbol": s,
                        "side": "buy",
                        "volume": "0.1",
                        "open_price": "90",
                    }
                    for s in symbols
                ],
            }
        account = await registry.execute(
            ToolCall(id="account", name="account_read", arguments={"account_id": primary}), context
        )
        assert [p["symbol"] for p in account["positions"]] == [symbols[0]]
        proposal = await registry.execute(
            ToolCall(id="close", name="trade_close_positions", arguments={"account_id": primary}),
            context,
        )
        cards = cast(
            list[dict[str, Any]],
            await fixture.request("GET", f"/trading/approvals?thread_id={thread['id']}"),
        )
        card = next(c for c in cards if c["id"] == proposal["approval_id"])
        assert len(card["requests"]) == 1 and card["requests"][0]["symbol"] == symbols[0]
        try:
            await context.trading.execute(
                fixture.owner,
                TradeRequest(
                    account_id=primary, symbol=symbols[1], action="buy", volume=Decimal("0.1")
                ),
                context.lease,
            )
        except LonoraError as error:
            assert error.code == "agent_trading_symbol_mismatch"
        else:
            raise AssertionError("Direct central execution bypass")
        print(
            "PASS broker manual ticket reads and close-all scoped; central execution independently rejects mismatch"
        )
        async with fixture.runtime.db.sessions() as session, session.begin():
            child = await create_agent(
                session, fixture.owner, AgentCreate(name="Inherited child"), agent["id"]
            )
            child_data = agent_data(child)
            fixture.agents.append(child.id)
            assert child.trading_account_id == primary and child.trading_symbol == symbols[0]
        child_thread = await fixture.conversation(child_data)
        child_context = await fixture.lease(await fixture.run(child_data, child_thread))
        async with fixture.runtime.db.sessions() as session, session.begin():
            row = await session.get(RunRow, child_context.lease.run_id)
            assert row is not None
            row.parent_run_id = context.lease.run_id
        await denied(
            "market_quote",
            {"account_id": primary, "symbol": symbols[1]},
            "agent_trading_symbol_mismatch",
        )
        async with fixture.runtime.db.sessions() as session:
            selected = await session.get(AgentRow, agent["id"])
            assert selected is not None
            assert symbols[0] in binding_context(selected)
            instructions, _ = await voice_context(
                session, fixture.owner, selected, thread["id"], "Voice authority fixture"
            )
            assert symbols[0] in instructions and "immutable_trading_market" in instructions
        legacy = await fixture.agent("Legacy unbound")
        assert legacy["trading_account_id"] is None and legacy["trading_symbol"] is None
        print(
            "PASS persistent child inheritance, voice/runtime identity context and unchanged migrated legacy agents"
        )
        other_thread = await fixture.conversation(agents[1])
        foreign_chart = await fixture.request(
            "POST",
            "/charts",
            {
                "agent_id": agents[1]["id"],
                "thread_id": other_thread["id"],
                "payload": {"account_id": primary, "symbol": symbols[1], "timeframe": "1h"},
            },
        )
        await denied(
            "chart_inspect", {"chart_id": foreign_chart["id"]}, "agent_trading_symbol_mismatch"
        )
        for association in ({"agent_id": agent["id"]}, {"thread_id": thread["id"]}):
            response = await fixture.client.post(
                "/api/charts",
                json={
                    **association,
                    "payload": {"account_id": primary, "symbol": symbols[1], "timeframe": "1h"},
                },
            )
            assert (
                response.status_code == 409
                and response.json()["code"] == "agent_trading_symbol_mismatch"
            )
        response = await fixture.client.post(
            "/api/trading/goals",
            json={
                "agent_id": agent["id"],
                "thread_id": thread["id"],
                "title": "Forbidden target",
                "objective": "Explicit invalid fixture",
                "account_id": primary,
                "symbol": symbols[1],
                "steps": [
                    {
                        "id": "entry",
                        "title": "Foreign entry",
                        "kind": "trade",
                        "trade": {
                            "account_id": primary,
                            "symbol": symbols[1],
                            "action": "buy",
                            "volume": "0.1",
                        },
                    }
                ],
            },
        )
        assert (
            response.status_code == 409
            and response.json()["code"] == "agent_trading_symbol_mismatch"
        )
        peer_context = await fixture.lease(await fixture.run(agents[1], other_thread))
        async with fixture.runtime.db.sessions() as session, session.begin():
            peer_run = await session.get(RunRow, peer_context.lease.run_id)
            assert peer_run is not None
            peer_run.parent_run_id = context.lease.run_id
        try:
            await peer_context.trading.execute(
                fixture.owner,
                TradeRequest(
                    account_id=primary, symbol=symbols[1], action="buy", volume=Decimal("0.1")
                ),
                peer_context.lease,
            )
        except LonoraError as error:
            assert error.code == "agent_trading_symbol_mismatch"
        else:
            raise AssertionError("Peer delegated trade bypassed parent binding")
        await fixture.request("DELETE", "/charts/" + foreign_chart["id"])
        print(
            "PASS persisted chart-ID/direct chart+goal APIs and peer financial ancestry cannot bypass binding"
        )
        from lonora_contracts.market_watch import Watch
        from lonora_db.schema import MarketWatchRow
        from lonora_market.watchers import observe

        watch = await fixture.request(
            "POST",
            "/watches",
            {
                "agent_id": agent["id"],
                "thread_id": thread["id"],
                "payload": {
                    "account_id": primary,
                    "kind": "position",
                    "position_id": "manual-" + symbols[1],
                    "condition": "opened",
                    "prompt": "Explicit forged foreign ticket fixture",
                },
            },
        )
        assert watch["payload"]["symbol"] == symbols[0]
        async with fixture.runtime.db.sessions() as session:
            saved = await session.get(MarketWatchRow, watch["id"])
            assert saved is not None
        try:
            await observe(
                fixture.runtime.db, context.brokers, saved, Watch.model_validate(saved.payload)
            )
        except LonoraError as error:
            assert error.code == "agent_trading_symbol_mismatch"
        else:
            raise AssertionError("Foreign position ticket bypassed watch binding")
        changed = await fixture.client.put(
            "/api/watches/" + watch["id"],
            json={
                "version": watch["version"],
                "payload": {**watch["payload"], "symbol": symbols[1]},
            },
        )
        assert (
            changed.status_code == 409 and changed.json()["code"] == "agent_trading_symbol_mismatch"
        )
        await fixture.request("DELETE", "/watches/" + watch["id"])
        print(
            "PASS symbol-less position watches inherit pair and actual broker ticket symbol is fenced"
        )

    finally:
        for identifier in connections:
            await fixture.request("DELETE", "/trading/connections/" + identifier)
        await fixture.close()


if __name__ == "__main__":
    asyncio.run(checks())
