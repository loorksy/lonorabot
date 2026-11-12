"""The whole team's book on every wake, by symbol and by currency (mandate 5.4).

Two agents on EURUSD and XAUUSD appear under EUR, USD and XAU; the owner's own
ticket is the owner's; the picture carries tickets only, never another agent's
memory; currencies come from the broker's instrument metadata, learned once.
"""

import asyncio
import json
from decimal import Decimal
from typing import Any
from unittest.mock import patch

from check_account_picture import Book, picture_of, position
from check_streaming import Fixture
from lonora_agent.context.picture import MAX_TEAM_SYMBOLS, account_picture
from lonora_contracts.account import Order
from lonora_core.user_error import LonoraError
from lonora_db.broker_sessions import BrokerSessionRepository
from lonora_db.memory import commit_memory
from lonora_trading.picture import CURRENCIES_KEY, instrument_legs, learn_currencies


def instrument(symbol: str, base: str, profit: str) -> dict[str, Any]:
    return {
        "symbol": symbol,
        "digits": 5,
        "tick_size": "0.00001",
        "volume_min": "0.01",
        "volume_max": "100",
        "volume_step": "0.01",
        "base_currency": base,
        "profit_currency": profit,
    }


async def main() -> None:
    assert instrument_legs("EUR", "USD") == ["EUR", "USD"]
    assert instrument_legs("XAU", "USD") == ["XAU", "USD"]
    assert instrument_legs("USD", "USD") == ["USD"]  # a CFD quoted in dollars
    assert instrument_legs("US500", "USD") == ["USD"]  # not a currency code: quote only
    assert instrument_legs(None, "JPY") == ["JPY"] and instrument_legs(None, None) == []
    assert instrument_legs("BTC", "USDT") == ["BTC", "USDT"]  # a crypto pair
    f = await Fixture().open()
    try:
        account = (
            await f.request(
                "POST",
                "/trading/connections",
                {"provider": "simulation", "account_id": "picture-source", "enabled": True},
            )
        )["id"]
        await f.request(
            "POST",
            f"/trading/connections/{account}/simulation",
            {
                "snapshot": {
                    "currency": "USD",
                    "balance": "10000",
                    "instruments": [
                        instrument("EURUSD", "EUR", "USD"),
                        instrument("XAUUSD", "XAU", "USD"),
                        instrument("US500", "USD", "USD"),
                    ],
                    "quotes": {},
                }
            },
        )
        euro = await f.agent("Euro book")
        gold = await f.agent("Gold book")
        async with f.runtime.db.sessions() as session, session.begin():
            # Another agent's memory must never reach the picture.
            await commit_memory(
                session, f.owner, gold["id"], "# MEMORY.md\nGold-secret-thesis", None
            )
        book = Book(f, account)
        await book.opened(euro["id"], position("eur-1", "EURUSD", "buy", "1.0", "10"))
        await book.opened(gold["id"], position("xau-1", "XAUUSD", "sell", "0.5", "-3"))
        await book.opened(
            gold["id"],
            Order(
                id="xau-2",
                symbol="XAUUSD",
                side="buy_limit",
                volume=Decimal("0.2"),
                price=Decimal(2300),
            ),
        )
        await book.opened(None, position("own-1", "US500", "buy", "2.0", "5"))
        # A symbol the broker refuses to describe must not hold back the others.
        await book.opened(euro["id"], position("odd-1", "AAA.odd", "buy", "0.01", "0"))
        await book.reconcile()
        async with f.runtime.db.sessions() as session:
            before = picture_of(await account_picture(session, f.owner, euro["id"]))
        assert sorted(before["team"][0]["currencies_unknown"]) == [
            "AAA.odd",
            "EURUSD",
            "US500",
            "XAUUSD",
        ]
        brokers = f.runtime.services(f.owner).brokers
        # A transient failure (a rate limit) stores nothing; the next pass learns it.
        broker = await brokers.get(f.owner, account)
        real = broker.instrument

        async def limited(symbol: str) -> Any:
            if symbol == "EURUSD":
                raise LonoraError("broker_rate_limited", 429)
            return await real(symbol)

        with (
            patch.object(broker, "instrument", limited),
            patch("lonora_trading.picture.RETRY_SECONDS", 0),
        ):
            assert await learn_currencies(f.runtime.db, brokers, f.owner) == 2
        async with f.runtime.db.sessions() as session:
            row = await BrokerSessionRepository().get(session, f.owner, account)
            assert "EURUSD" not in row.state[CURRENCIES_KEY]["symbols"]
        assert await learn_currencies(f.runtime.db, brokers, f.owner) == 1
        assert await learn_currencies(f.runtime.db, brokers, f.owner) == 0  # once
        async with f.runtime.db.sessions() as session:
            row = await BrokerSessionRepository().get(session, f.owner, account)
            learned = row.state[CURRENCIES_KEY]["symbols"]
            assert learned["XAUUSD"] == ["XAU", "USD"] and learned["AAA.odd"] == [], learned
            text = await account_picture(session, f.owner, euro["id"])
        assert "Gold-secret-thesis" not in text
        (team,) = picture_of(text)["team"]
        # The broker lists no currencies for the refused symbol: it stays unknown.
        assert team["currencies_unknown"] == ["AAA.odd"] and team["stale"] is False
        symbols = {item["symbol"]: item for item in team["by_symbol"]}
        assert [p["agent"] for p in symbols["EURUSD"]["positions"]] == [euro["name"]]
        assert [p["agent"] for p in symbols["XAUUSD"]["positions"]] == [gold["name"]]
        assert [o["ticket"] for o in symbols["XAUUSD"]["orders"]] == ["xau-2"]
        assert symbols["XAUUSD"]["net_volume"] == "-0.5"
        assert symbols["US500"]["positions"][0]["agent"] is None  # the owner's own
        currencies = {item["currency"]: item["symbols"] for item in team["by_currency"]}
        assert set(currencies) == {"EUR", "USD", "XAU"}, currencies
        assert [(s["symbol"], s["leg"]) for s in currencies["EUR"]] == [("EURUSD", "base")]
        assert [(s["symbol"], s["leg"]) for s in currencies["XAU"]] == [("XAUUSD", "base")]
        assert sorted((s["symbol"], s["leg"]) for s in currencies["USD"]) == [
            ("EURUSD", "quote"),
            ("US500", "quote"),
            ("XAUUSD", "quote"),
        ]
        held = {key: value for key, value in json.loads(json.dumps(team)).items()}
        assert "memory" not in json.dumps(held).casefold()
        # Bounded: the largest symbols, and a count for the rest.
        for index in range(MAX_TEAM_SYMBOLS):
            await book.opened(
                euro["id"], position(f"small-{index}", f"S{index:02d}", "buy", "0.01", "0")
            )
        await book.reconcile()
        async with f.runtime.db.sessions() as session:
            (team,) = picture_of(await account_picture(session, f.owner, euro["id"]))["team"]
        assert len(team["by_symbol"]) == MAX_TEAM_SYMBOLS and team["symbols_not_shown"] == 4
        assert team["by_symbol"][0]["symbol"] == "US500", team["by_symbol"][0]
        # Every ticket is shown or counted, including those of symbols not listed.
        shown = sum(len(item["positions"]) for item in team["by_symbol"])
        assert shown + team["positions_not_shown"] == 24, (shown, team["positions_not_shown"])
        # Currencies count every symbol, listed or not.
        usd = next(item for item in team["by_currency"] if item["currency"] == "USD")
        assert {s["symbol"] for s in usd["symbols"]} >= {"EURUSD", "XAUUSD", "US500"}
        print("PASS team book: EURUSD and XAUUSD appear under EUR, USD and XAU")
        print("PASS team book: holders by name, the owner's own ticket, tickets only, bounded")
        print("PASS instrument currencies are learned once; a refused symbol holds none back")
    finally:
        await f.close()


if __name__ == "__main__":
    asyncio.run(main())
