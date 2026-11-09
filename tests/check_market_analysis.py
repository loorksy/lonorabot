"""Real registry/PG/simulation checks for market analysis tools and readable scope.

Snapshot, sessions with broker hours, calendar read, the candle-to-workspace bridge
(receipts, revisions, quotas, ownership) and a fixed-market agent that may read a
related symbol and account-wide exposure while every execution path stays bound.
"""

import asyncio
from dataclasses import replace
from datetime import timedelta
from decimal import Decimal
from typing import Any, cast
from unittest.mock import AsyncMock, patch
from uuid import uuid4

from check_streaming import Fixture
from lonora_adapter_kit.types import ToolCall
from lonora_adapters.market.economic_calendar import EconomicCalendarAdapter
from lonora_agent.workspace_access import RunWorkspaceAccess
from lonora_contracts.domain import utcnow
from lonora_contracts.market import CalendarEvent
from lonora_contracts.trading import TradeRequest
from lonora_core.user_error import LonoraError
from lonora_db.schema import BrokerSessionRow, RunRow, TradingAccountRow, TradingJournalRow
from lonora_tools.context import ToolContext
from lonora_tools.loader import load_tools
from lonora_tools.market_analysis import calendar_available
from sqlalchemy import func, select

GOLD, DOLLAR, EURO = "XAUUSD.r", "USDX.cash", "EURUSDm"
FRAMES = {"15m": 15, "1h": 60, "4h": 240, "1d": 1440, "1w": 10080}


def bars(symbol: str, frame: str, base: Decimal, tick: Decimal, count: int) -> list[dict[str, Any]]:
    minutes = FRAMES[frame]
    now = utcnow()
    floor = now.replace(second=0, microsecond=0)
    if minutes >= 1440:
        floor = floor.replace(hour=0, minute=0)
        if minutes == 10080:
            floor -= timedelta(days=floor.weekday())
    else:
        elapsed = floor.hour * 60 + floor.minute
        floor -= timedelta(minutes=elapsed % minutes)
    wave = [0, 3, 6, 3, 0, -3, -6, -3]
    result: list[dict[str, Any]] = []
    for index in range(count):
        price = base + tick * (Decimal(index) * 2 + Decimal(wave[index % 8] * 10))
        result.append(
            {
                "symbol": symbol,
                "timeframe": frame,
                "time": (floor - timedelta(minutes=(count - 1 - index) * minutes)).isoformat(),
                "open": str(price),
                "high": str(price + tick * 5),
                "low": str(price - tick * 5),
                "close": str(price + tick),
            }
        )
    return result


BINDING_CODES = {"agent_trading_account_mismatch", "agent_trading_symbol_mismatch"}


async def main() -> None:
    fixture = await Fixture().open()
    connections: list[str] = []
    try:
        for _ in range(2):
            created = await fixture.request(
                "POST",
                "/trading/connections",
                {"provider": "simulation", "account_id": uuid4().hex, "enabled": True},
            )
            connections.append(str(created["id"]))
        primary, secondary = connections
        now = utcnow()
        definitions = [
            (GOLD, Decimal("2700"), Decimal("0.01"), 2),
            (DOLLAR, Decimal("104"), Decimal("0.001"), 3),
            (EURO, Decimal("1.10000"), Decimal("0.00001"), 5),
        ]
        candles: dict[str, list[dict[str, Any]]] = {}
        for symbol, base, tick, _ in definitions:
            for frame in FRAMES:
                if symbol != GOLD and frame not in {"1h", "1d"}:
                    continue
                candles[symbol + ":" + frame] = bars(
                    symbol, frame, base, tick, 6 if frame == "1w" else 220
                )
        offset = 120
        snapshot: dict[str, Any] = {
            "balance": "10000",
            "currency": "USD",
            "instruments": [
                {
                    "symbol": symbol,
                    "digits": digits,
                    "tick_size": str(tick),
                    "volume_min": "0.01",
                    "volume_max": "10",
                    "volume_step": "0.01",
                }
                for symbol, _, tick, digits in definitions
            ],
            "quotes": {
                symbol: {
                    "symbol": symbol,
                    "bid": str(base),
                    "ask": str(base + tick * 3),
                    "observed_at": now.isoformat(),
                    "source": "explicit-analysis-fixture",
                }
                for symbol, base, tick, _ in definitions
            },
            "candles": candles,
            "trading_hours": {
                GOLD: {
                    "symbol": GOLD,
                    "utc_offset_minutes": offset,
                    "offset_source": "fixture",
                    "trade_sessions": {
                        day: [{"start": "00:00:00", "end": "24:00:00"}]
                        for day in ("MONDAY", "TUESDAY", "WEDNESDAY", "THURSDAY", "FRIDAY")
                    },
                    "trade_mode": "SYMBOL_TRADE_MODE_FULL",
                    "observed_at": now.isoformat(),
                    "source": "simulation",
                }
            },
        }
        for identifier in connections:
            await fixture.request(
                "POST", f"/trading/connections/{identifier}/simulation", {"snapshot": snapshot}
            )
        registry = load_tools()
        for name, read_only in (
            ("market_snapshot", True),
            ("market_sessions", True),
            ("economic_calendar_read", True),
            ("market_candles_to_workspace", False),
        ):
            tool = registry.tools[name]
            assert tool.read_only is read_only and not tool.financial, name
        assert registry.tools["market_candles_to_workspace"].replay_safe
        read_only_names = {item.name for item in registry.definitions(scope="helper")}
        assert {"market_snapshot", "market_sessions", "economic_calendar_read"} <= read_only_names
        assert "market_candles_to_workspace" not in read_only_names

        agent = await fixture.agent("Market analysis fixture")
        thread = await fixture.conversation(agent)
        context = await fixture.lease(await fixture.run(agent, thread))
        context = replace(context, workspace_access=RunWorkspaceAccess())

        async def call(
            name: str, args: dict[str, Any], *, actor: ToolContext | None = None, call_id: str = ""
        ) -> dict[str, Any]:
            return await registry.execute(
                ToolCall(id=call_id or uuid4().hex, name=name, arguments=args), actor or context
            )

        async def denied(
            name: str, args: dict[str, Any], code: str, *, actor: ToolContext | None = None
        ) -> None:
            try:
                await call(name, args, actor=actor)
            except LonoraError as error:
                assert error.code == code, (name, error.code, code)
            else:
                raise AssertionError(name + " accepted an invalid request: " + code)

        result = await call("market_snapshot", {"account_id": primary, "symbol": GOLD.lower()})
        assert result["symbol"] == GOLD and result["execution_authorized"] is False
        assert [item["timeframe"] for item in result["timeframes"]] == ["15m", "1h", "4h", "1d"]
        for item in result["timeframes"]:
            assert item["available"] and item["closed_bars"] == 199, item["timeframe"]
            assert item["forming_bar"]["unfinished"] is True
            assert item["volatility"]["regime"] in {"low", "normal", "high"}
            assert item["structure"]["label"] != "insufficient_swings"
        assert result["quote"]["freshness"] == "healthy" and result["quote"]["spread_ticks"] == 3
        assert result["levels"]["previous_day"]["available"]
        assert result["levels"]["previous_week"]["available"]
        assert result["levels"]["daily_atr"] and len(result["levels"]["distances"]) == 6
        partial = await call(
            "market_snapshot",
            {"account_id": primary, "symbol": DOLLAR, "timeframes": ["15m", "1h"]},
        )
        assert partial["timeframes"][0]["available"] is False
        assert partial["timeframes"][1]["available"] is True
        assert partial["levels"]["previous_week"]["available"] is False
        await denied(
            "market_snapshot",
            {"account_id": primary, "symbol": GOLD, "timeframes": ["H1"]},
            "unsupported_timeframe",
        )
        await denied(
            "market_snapshot", {"account_id": primary, "symbol": "NOPE.x"}, "symbol_not_found"
        )
        print("PASS market_snapshot: closed-bar multi-timeframe facts, levels and explicit gaps")

        clock = await call("market_sessions", {})
        assert len(clock["sessions"]) == 4
        assert clock["broker_trading_hours"]["reason"] == "no_instrument_requested"

        def upcoming(weekday: int) -> str:
            moment = now.replace(hour=12, minute=0, second=0, microsecond=0)
            while moment.weekday() != weekday or moment <= now:
                moment += timedelta(days=1)
            return moment.isoformat()

        hours = await call(
            "market_sessions", {"account_id": primary, "symbol": GOLD, "at": upcoming(2)}
        )
        broker_hours = hours["broker_trading_hours"]
        assert broker_hours["state"] == "open" and broker_hours["utc_offset_minutes"] == offset
        assert broker_hours["broker_local_time"] == "Wed 14:00"
        assert "london" in hours["active_sessions"]
        weekend = await call(
            "market_sessions", {"account_id": primary, "symbol": GOLD, "at": upcoming(5)}
        )
        assert weekend["broker_trading_hours"]["state"] == "closed"
        assert weekend["fx_market"]["state"] == "closed"
        unknown = await call("market_sessions", {"account_id": primary, "symbol": EURO})
        assert unknown["broker_trading_hours"] == {
            "symbol": EURO,
            "state": "unknown",
            "reason": "broker_trading_hours_unavailable",
        }
        await denied("market_sessions", {"symbol": GOLD}, "tool_arguments_invalid")
        await denied(
            "market_sessions",
            {"at": (now + timedelta(days=40)).isoformat()},
            "market_session_timestamp_out_of_range",
        )
        print("PASS market_sessions: IANA session clock and simulation broker trading hours")

        empty = await call("economic_calendar_read", {})
        assert empty["configured"] is False and empty["events"] == []
        assert empty["reason"] == "economic_calendar_not_configured"
        # Exposure reports the same state: unavailable (so not native) until configured.
        unavailable = await registry.availability(
            context, [registry.tools["economic_calendar_read"]]
        )
        assert unavailable == {"economic_calendar_read": "economic_calendar_not_configured"}
        source = await fixture.request(
            "POST",
            "/integrations",
            {
                "payload": {
                    "type": "economic_calendar",
                    "name": "Fixture calendar",
                    "url": "https://calendar.example.invalid/secret-token/events.json",
                    "enabled": True,
                }
            },
        )
        assert await calendar_available(context) is None
        events = [
            CalendarEvent(
                id="cpi",
                name="US CPI",
                currency="USD",
                observed_at=now,
                scheduled_at=now + timedelta(hours=2),
                impact="High",
                forecast="3.1%",
                source="fixture",
            ),
            CalendarEvent(
                id="ecb",
                name="ECB rate",
                currency="EUR",
                observed_at=now,
                scheduled_at=now + timedelta(hours=5),
                impact="High",
                source="fixture",
            ),
        ]
        with patch.object(EconomicCalendarAdapter, "events", AsyncMock(return_value=events)):
            usd = await call("economic_calendar_read", {"currencies": ["usd"]})
        assert usd["configured"] is True and usd["reason"] is None
        assert [item["id"] for item in usd["events"]] == ["cpi"]
        assert usd["events"][0]["integration_id"] == source["id"]
        assert usd["events"][0]["status"] == "upcoming"
        assert "secret-token" not in str(usd)
        failing = AsyncMock(side_effect=LonoraError("calendar_source_unavailable", 502))
        with patch.object(EconomicCalendarAdapter, "events", failing):
            down = await call("economic_calendar_read", {})
        assert down["configured"] is True and down["reason"] == "calendar_source_unavailable"
        assert down["sources"][0]["status"] == "unavailable" and down["events"] == []
        print("PASS economic_calendar_read: not configured, filtered events, source failure")

        inspected = await call("workspace_inspect", {})
        assert inspected["revision"] == 0
        bridge_id = uuid4().hex
        request = {"account_id": primary, "symbol": GOLD, "timeframe": "1h", "revision": 0}
        written = await call("market_candles_to_workspace", request, call_id=bridge_id)
        assert written["path"] == "market/XAUUSD.r_1h.csv" and written["revision"] == 1
        assert written["rows"] == written["closed_rows"] == 219 and written["forming_rows"] == 0
        assert "candles" not in written and len(str(written)) < 1200
        content = await call(
            "workspace_read", {"path": written["path"], "revision": 1, "limit": 16000}
        )
        lines = content["content"].splitlines()
        assert lines[0] == "time,close_time,open,high,low,close,volume,closed"
        assert lines[1].endswith(",1") and written["first_bar_at"] in lines[1]
        # The bars change, then the same call is replayed: the original receipt returns.
        async with fixture.runtime.db.sessions() as session, session.begin():
            row = await session.get(TradingAccountRow, primary, with_for_update=True)
            assert row is not None
            changed = dict(row.payload["candles"])
            changed[GOLD + ":1h"] = changed[GOLD + ":1h"][:-5]
            row.payload = {**row.payload, "candles": changed}
        replayed = await call("market_candles_to_workspace", request, call_id=bridge_id)
        assert replayed == written
        await denied("market_candles_to_workspace", request, "workspace_revision_conflict")
        await denied(
            "market_candles_to_workspace",
            {**request, "revision": 1, "path": "../escape.csv"},
            "workspace_path_unsafe",
        )
        window = await call(
            "market_candles_to_workspace",
            {
                **request,
                "revision": 1,
                "path": "data/gold_window.csv",
                "start": written["first_bar_at"],
                "end": written["first_bar_at"],
                "include_forming": True,
            },
        )
        assert window["rows"] == 1 and window["revision"] == 2
        filler = {f"fill/{index}.txt": "x" for index in range(126)}
        filled = await call("workspace_update", {"revision": 2, "files": filler})
        assert filled["revision"] == 3 and len(filled["files"]) == 128
        await denied(
            "market_candles_to_workspace",
            {**request, "revision": 3, "path": "data/one_too_many.csv"},
            "workspace_snapshot_too_large",
        )
        try:
            await registry.execute(
                ToolCall(id=uuid4().hex, name="market_candles_to_workspace", arguments=request),
                context,
                scope="helper",
            )
        except LonoraError as error:
            assert error.code == "tool_not_allowed"
        else:
            raise AssertionError("A helper run wrote into a workspace")
        # The handler refuses a helper's write too, whatever scope the caller passed.
        async with fixture.runtime.db.sessions() as session, session.begin():
            run = await session.get(RunRow, context.lease.run_id, with_for_update=True)
            assert run is not None
            run.trigger = "subagent"
        await denied(
            "market_candles_to_workspace",
            {**request, "revision": 3, "path": "data/observe.csv"},
            "tool_not_allowed",
        )
        print(
            "PASS market_candles_to_workspace: CSV in workspace, receipt replay, revision, path and quota"
        )

        bound = await fixture.request(
            "POST",
            "/agents",
            {"name": "Gold specialist", "trading_account_id": primary, "trading_symbol": GOLD},
        )
        fixture.agents.append(bound["id"])
        permission = await fixture.request("GET", f"/agents/{bound['id']}/permissions")
        await fixture.request(
            "PUT",
            f"/agents/{bound['id']}/permissions",
            {"level": "supervised", "expected_revision": permission["revision"]},
        )
        bound_thread = await fixture.conversation(bound)
        specialist = replace(
            await fixture.lease(await fixture.run(bound, bound_thread)),
            workspace_access=RunWorkspaceAccess(),
        )
        defaulted = await call("market_snapshot", {"timeframes": ["1h"]}, actor=specialist)
        assert defaulted["symbol"] == GOLD and defaulted["account_id"] == primary
        related = await call(
            "market_snapshot", {"symbol": DOLLAR, "timeframes": ["1h"]}, actor=specialist
        )
        assert related["symbol"] == DOLLAR and related["timeframes"][0]["available"]
        for name, args in (
            ("market_quote", {"symbol": DOLLAR}),
            ("market_instrument", {"symbol": DOLLAR}),
            ("market_candles", {"symbol": DOLLAR, "timeframe": "1h", "limit": 5}),
            ("market_structure", {"symbol": DOLLAR, "timeframe": "1h"}),
            ("chart_indicator", {"symbol": DOLLAR, "timeframe": "1h", "name": "atr"}),
        ):
            value = await call(name, args, actor=specialist)
            assert DOLLAR in str(value), name
        sessions = await call("market_sessions", {}, actor=specialist)
        assert sessions["broker_trading_hours"]["symbol"] == GOLD

        async def set_enabled(enabled: bool) -> None:
            async with fixture.runtime.db.sessions() as session, session.begin():
                row = await session.get(BrokerSessionRow, primary, with_for_update=True)
                assert row is not None
                row.payload = {**row.payload, "enabled": enabled}
                row.version += 1

        # The bound default call names the account and symbol; a disabled broker leaves
        # only the broker hours unknown, never the IANA session clock.
        await set_enabled(False)
        try:
            offline = await call("market_sessions", {}, actor=specialist)
        finally:
            await set_enabled(True)
        assert len(offline["sessions"]) == 4
        assert offline["fx_market"]["state"] in {"open", "closed"}
        assert offline["broker_trading_hours"] == {
            "symbol": GOLD,
            "state": "unknown",
            "reason": "broker_disabled",
        }
        await denied("market_sessions", {"symbol": "NOPE.x"}, "symbol_not_found", actor=specialist)
        exported = await call(
            "market_candles_to_workspace",
            {"symbol": DOLLAR, "timeframe": "1h", "revision": 0},
            actor=specialist,
        )
        assert exported["symbol"] == DOLLAR and exported["rows"] == 219
        catalog = await call("market_symbols", {}, actor=specialist)
        assert set(catalog["symbols"]) == {GOLD, DOLLAR, EURO}
        assert catalog["execution_scope"]["symbol"] == GOLD
        # Reading is open: another owned account is readable too.
        for name, args in (
            ("market_quote", {"account_id": secondary, "symbol": DOLLAR}),
            ("market_snapshot", {"account_id": secondary, "symbol": GOLD}),
        ):
            try:
                await call(name, args, actor=specialist)
            except LonoraError as error:
                assert error.code not in BINDING_CODES, (name, error.code)
        print("PASS fixed-market agent reads related symbols and every owned account")

        async with fixture.runtime.db.sessions() as session, session.begin():
            row = await session.get(TradingAccountRow, primary, with_for_update=True)
            assert row is not None
            row.payload = {
                **row.payload,
                "positions": [
                    {
                        "id": "manual-" + symbol,
                        "symbol": symbol,
                        "side": "buy",
                        "volume": "0.1",
                        "open_price": "100",
                    }
                    for symbol in (GOLD, DOLLAR, EURO)
                ],
            }
        account = await call("account_read", {}, actor=specialist)
        assert {item["symbol"]: item["in_execution_scope"] for item in account["positions"]} == {
            GOLD: True,
            DOLLAR: False,
            EURO: False,
        }
        assert account["execution_scope"]["symbol"] == GOLD
        history = await call(
            "account_history",
            {"start": (now - timedelta(days=1)).isoformat(), "end": now.isoformat()},
            actor=specialist,
        )
        assert history["history"] == []
        async with fixture.runtime.db.sessions() as session:
            journal_before = await session.scalar(
                select(func.count()).select_from(TradingJournalRow)
            )
        for name, args in (
            ("trade_execute", {"symbol": DOLLAR, "action": "buy", "volume": "0.1"}),
            ("trade_close_positions", {"symbol": DOLLAR}),
            (
                "watch_create",
                {
                    "symbol": DOLLAR,
                    "kind": "price",
                    "condition": "above",
                    "level": "120",
                    "prompt": "Related symbol watch fixture",
                },
            ),
            (
                "watch_create",
                {
                    "kind": "position",
                    "position_id": "manual-" + DOLLAR,
                    "condition": "closed",
                    "prompt": "Foreign ticket watch fixture",
                },
            ),
            ("chart_open", {"symbol": DOLLAR, "timeframe": "1h"}),
        ):
            try:
                await call(name, args, actor=specialist)
            except LonoraError as error:
                assert error.code == "agent_trading_symbol_mismatch", (name, error.code)
            else:
                raise AssertionError(name + " acted on a related, read-only symbol")
        # A sizing estimate is a read: open for the related symbol, and it executes nothing.
        try:
            await call(
                "market_position_size",
                {
                    "symbol": DOLLAR,
                    "side": "buy",
                    "risk_budget": "50",
                    "currency": "USD",
                    "stop_loss": "103",
                },
                actor=specialist,
            )
        except LonoraError as error:
            assert error.code not in BINDING_CODES, error.code
        closed = await call("trade_close_positions", {}, actor=specialist)
        cards = cast(
            list[dict[str, Any]],
            await fixture.request("GET", f"/trading/approvals?thread_id={bound_thread['id']}"),
        )
        card = next(item for item in cards if item["id"] == closed["approval_id"])
        assert [item["symbol"] for item in card["requests"]] == [GOLD]
        try:
            await specialist.trading.execute(
                fixture.owner,
                TradeRequest(
                    account_id=primary,
                    symbol=DOLLAR,
                    action="close_position",
                    position_id="manual-" + DOLLAR,
                ),
                specialist.lease,
            )
        except LonoraError as error:
            assert error.code == "agent_trading_symbol_mismatch", error.code
        else:
            raise AssertionError("Central execution accepted a related, read-only symbol")
        async with fixture.runtime.db.sessions() as session:
            journal_after = await session.scalar(
                select(func.count()).select_from(TradingJournalRow)
            )
        assert journal_after == journal_before
        print(
            "PASS account-wide exposure is visible; trades, closes, watches, charts and central "
            "execution stay on the bound symbol"
        )
    finally:
        for identifier in connections:
            await fixture.request("DELETE", "/trading/connections/" + identifier)
        await fixture.close()


if __name__ == "__main__":
    asyncio.run(main())
