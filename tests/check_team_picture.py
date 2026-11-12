"""The whole team's book on every wake, by symbol and by currency (mandate 5.4).

Two agents on EURUSD and XAUUSD appear under EUR, USD and XAU; the owner's own
ticket is the owner's; the picture carries tickets only, never another agent's
memory; currencies come from the broker's instrument metadata, learned once.
"""

import asyncio
import json
from decimal import Decimal
from typing import Any

from check_account_picture import Book, picture_of, position
from check_streaming import Fixture
from lonora_agent.context.picture import account_picture
from lonora_contracts.account import Order
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
        await book.reconcile()
        async with f.runtime.db.sessions() as session:
            before = picture_of(await account_picture(session, f.owner, euro["id"]))
        assert sorted(before["team"][0]["currencies_unknown"]) == ["EURUSD", "US500", "XAUUSD"]
        assert (
            await learn_currencies(f.runtime.db, f.runtime.services(f.owner).brokers, f.owner) == 3
        )
        assert (
            await learn_currencies(f.runtime.db, f.runtime.services(f.owner).brokers, f.owner) == 0
        )  # once
        async with f.runtime.db.sessions() as session:
            row = await BrokerSessionRepository().get(session, f.owner, account)
            assert row.state[CURRENCIES_KEY]["XAUUSD"] == ["XAU", "USD"], row.state[CURRENCIES_KEY]
            text = await account_picture(session, f.owner, euro["id"])
        assert "Gold-secret-thesis" not in text
        (team,) = picture_of(text)["team"]
        assert team["currencies_unknown"] == []
        symbols = {item["symbol"]: item for item in team["by_symbol"]}
        assert [p["holder"] for p in symbols["EURUSD"]["positions"]] == [euro["name"]]
        assert [p["holder"] for p in symbols["XAUUSD"]["positions"]] == [gold["name"]]
        assert [o["ticket"] for o in symbols["XAUUSD"]["orders"]] == ["xau-2"]
        assert symbols["XAUUSD"]["net_volume"] == "-0.5"
        assert symbols["US500"]["positions"][0]["holder"] == "owner"
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
        print("PASS team book: EURUSD and XAUUSD appear under EUR, USD and XAU")
        print("PASS team book: holders by name, the owner's own ticket, tickets only")
        print("PASS instrument currencies are learned once from the broker")
    finally:
        await f.close()


if __name__ == "__main__":
    asyncio.run(main())
