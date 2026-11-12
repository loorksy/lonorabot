"""Broker-native immutable new-bot binding with real PG and explicit simulation."""

import asyncio
from decimal import Decimal
from typing import Any
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

# The refusals the door no longer makes for orders (3.1.2, 6.9).
BINDING = {"agent_trading_account_mismatch", "agent_trading_symbol_mismatch"}


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
        # This fixture tests scoped financial proposals. A new trading agent starts at
        # Ask me (W15-3); setting it again through the owner API keeps that level.
        permission = await fixture.request("GET", f"/agents/{agent['id']}/permissions")
        assert permission["effective_level"] == "supervised"
        await fixture.request(
            "PUT",
            f"/agents/{agent['id']}/permissions",
            {"level": "supervised", "expected_revision": permission["revision"]},
        )
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

        async def not_bound(name: str, args: dict[str, Any]) -> None:
            """Orders are never bound to the focus pair (3.1.2, 6.9): any refusal is
            another rule's (mode, approval), never the binding."""
            try:
                await registry.execute(ToolCall(id=uuid4().hex, name=name, arguments=args), context)
            except LonoraError as error:
                assert error.code not in BINDING, (name, error.code)

        # Reading is open: market data reads cover every owned account and symbol.
        # Persistent chart work, like every mutation, keeps the bound pair.
        for name in ("market_quote", "market_instrument", "market_candles", "chart_indicator"):
            args: dict[str, Any] = {"account_id": primary, "symbol": symbols[1]}
            if name in ("market_candles", "chart_indicator"):
                args["timeframe"] = "1h"
            if name == "chart_indicator":
                args["name"] = "rsi"
            try:
                await registry.execute(ToolCall(id=uuid4().hex, name=name, arguments=args), context)
            except LonoraError as error:
                # Simulation fixtures carry no bars for this pair; scope still passed.
                assert error.code != "agent_trading_symbol_mismatch", (name, error.code)
        related = await registry.execute(
            ToolCall(
                id=uuid4().hex,
                name="market_quote",
                arguments={"account_id": primary, "symbol": symbols[1]},
            ),
            context,
        )
        assert related["symbol"] == symbols[1]
        for name in ("chart_open", "chart_snapshot"):
            args = {"account_id": primary, "symbol": symbols[1]}
            if name == "chart_snapshot":
                args["timeframe"] = "1h"
            await denied(name, args, "agent_trading_symbol_mismatch")
        for name, args in (
            ("market_quote", {"account_id": secondary, "symbol": symbols[0]}),
            ("account_read", {"account_id": secondary}),
            ("list_accounts", {}),
        ):
            try:
                read = await registry.execute(
                    ToolCall(id=uuid4().hex, name=name, arguments=args), context
                )
            except LonoraError as error:
                # Another owned account is readable; only fixture data may be missing.
                assert error.code not in {
                    "agent_trading_account_mismatch",
                    "agent_trading_symbol_mismatch",
                }, (name, error.code)
            else:
                if name == "list_accounts":
                    listed = {item["connection_id"] for item in read["accounts"]}
                    assert {primary, secondary} <= listed, listed
        await not_bound(
            "trade_execute",
            {"account_id": primary, "symbol": symbols[1], "action": "buy", "volume": "0.1"},
        )
        await not_bound("trade_close_positions", {"account_id": secondary})
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
        assert set(catalog["symbols"]) >= set(symbols[:2])
        assert catalog["focus_pair"]["symbol"] == symbols[0]
        print(
            "PASS generic tool boundary: reads and orders open; cross-pair chart/watch/goal steps rejected"
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
        # Account-wide exposure is visible, with the focus pair named.
        assert {p["symbol"] for p in account["positions"]} == set(symbols)
        assert account["focus_pair"]["symbol"] == symbols[0]
        # The owner's standing instruction (3.3.4): this agent manages the owner's own
        # positions. A close-all still reaches only the bound pair.
        async with fixture.runtime.db.sessions() as session, session.begin():
            managing = await session.get(AgentRow, context.agent_id)
            assert managing is not None
            managing.manages_all_positions = True
        closed = await registry.execute(
            ToolCall(id="close", name="trade_close_positions", arguments={"account_id": primary}),
            context,
        )
        assert "approval_id" not in closed, closed
        assert [item["status"] for item in closed["results"]] == ["confirmed"], closed
        broker = await context.brokers.get(fixture.owner, primary)
        assert sorted(p.symbol for p in await broker.positions()) == sorted(symbols[1:])
        try:
            await context.trading.execute(
                fixture.owner,
                TradeRequest(
                    account_id=primary, symbol=symbols[1], action="buy", volume=Decimal("0.1")
                ),
                context.lease,
            )
        except LonoraError as error:
            # The door never binds an order to the pair; this Ask agent needs the card.
            assert error.code == "trade_approval_required", error.code
        else:
            raise AssertionError("Direct central execution sent without approval")
        print(
            "PASS broker manual ticket reads and close-all keeps its pair; the door binds no order"
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
        try:
            await registry.execute(
                ToolCall(
                    id=uuid4().hex,
                    name="trade_execute",
                    arguments={
                        "account_id": primary,
                        "symbol": symbols[1],
                        "action": "buy",
                        "volume": "0.1",
                    },
                ),
                child_context,
            )
        except LonoraError as error:
            # No binding refusal; the child's own trading permission decides.
            assert error.code not in BINDING, error.code
        else:
            raise AssertionError("Child sent without its own trading permission")
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
        # Reading another Agent's chart on another symbol is open; changing it is not.
        inspected = await registry.execute(
            ToolCall(
                id=uuid4().hex, name="chart_inspect", arguments={"chart_id": foreign_chart["id"]}
            ),
            context,
        )
        assert inspected["chart"]["id"] == foreign_chart["id"]
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
            # The ancestry walk binds nothing; the peer's own mode decides.
            assert error.code not in BINDING, error.code
        else:
            raise AssertionError("Peer sent without its own trading permission")
        await fixture.request("DELETE", "/charts/" + foreign_chart["id"])
        print(
            "PASS reads open across charts and accounts; direct chart+goal APIs keep the binding; peer orders are not bound"
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
