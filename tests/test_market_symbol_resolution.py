"""Catalog validation preserves broker spelling and real discovery failures."""

from decimal import Decimal
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock

import pytest
from lonora_contracts.market import Instrument
from lonora_core.user_error import LonoraError
from lonora_tools.symbols import (
    ASK_WHICH_CONTRACT,
    CHECK_THE_SYMBOL,
    NOT_LISTED,
    SEVERAL_FOR_A_READ,
    USE_THE_SYMBOL,
    SymbolNotResolved,
    canonical_broker_symbol,
    order_symbol,
    read_symbol,
)


@pytest.mark.asyncio
@pytest.mark.parametrize("symbol", ["EURUSDm", "XAUUSD.raw", "US500.cash", "BTCUSD.a"])
async def test_strict_catalog_keeps_exact_suffix_and_resolves_only_case(symbol: str) -> None:
    broker = SimpleNamespace(symbols=AsyncMock(return_value=[symbol]))
    assert await canonical_broker_symbol(broker, symbol, require_exists=True) == symbol
    assert await canonical_broker_symbol(broker, symbol.swapcase(), require_exists=True) == symbol
    with pytest.raises(LonoraError, match="symbol_not_found"):
        await canonical_broker_symbol(broker, symbol + ".other", require_exists=True)


@pytest.mark.asyncio
async def test_strict_catalog_never_hides_discovery_failure_as_an_unknown_symbol() -> None:
    error = LonoraError("broker_connection_timeout", 409)
    broker = SimpleNamespace(symbols=AsyncMock(side_effect=error))
    with pytest.raises(LonoraError) as failure:
        await canonical_broker_symbol(broker, "EURUSDm", require_exists=True)
    assert failure.value is error
    assert await canonical_broker_symbol(broker, "EURUSDm") == "EURUSDm"


@pytest.mark.asyncio
async def test_ambiguous_case_does_not_choose_a_different_broker_instrument() -> None:
    broker = SimpleNamespace(symbols=AsyncMock(return_value=["EURUSDm", "eurusdm"]))
    assert await canonical_broker_symbol(broker, "EURUSDm", require_exists=True) == "EURUSDm"
    with pytest.raises(LonoraError, match="symbol_ambiguous"):
        await canonical_broker_symbol(broker, "EURUSDM", require_exists=True)


@pytest.mark.asyncio
async def test_invalid_catalog_shape_is_unavailable_not_an_unknown_symbol() -> None:
    broker = SimpleNamespace(symbols=AsyncMock(return_value=None))
    with pytest.raises(LonoraError, match="broker_symbols_unavailable"):
        await canonical_broker_symbol(broker, "EURUSDm", require_exists=True)


Specs = dict[str, tuple[str | None, str | None]]


class Account:
    """One account's catalogue with the broker's own specifications."""

    def __init__(self, specs: Specs):
        self.specs = specs
        self.listings = 0

    async def symbols(self) -> list[str]:
        self.listings += 1
        return sorted(self.specs)

    async def instrument(self, symbol: str) -> Instrument:
        base, quote = self.specs[symbol]
        return Instrument(
            symbol=symbol,
            description="Gold vs US Dollar" if base == "XAU" else "",
            digits=2,
            tick_size=Decimal("0.01"),
            volume_min=Decimal("0.01"),
            volume_max=Decimal(100),
            volume_step=Decimal("0.01"),
            contract_size=Decimal(100),
            base_currency=base,
            profit_currency=quote,
        )


EXNESS: Specs = {"EURUSDm": ("EUR", "USD"), "XAUUSDm": ("XAU", "USD"), "XAUEURm": ("XAU", "EUR")}
REQUESTS = ["XAUUSD", "xauusd", "gold", "الذهب", "XAU/USD", "XAU", "USD", "m", "EURUSD", "XAUUSDT"]


@pytest.mark.asyncio
@pytest.mark.parametrize("requested", ["XAUUSD", "xauusd", "gold", "الذهب"])
async def test_a_read_resolves_to_the_accounts_own_symbol_and_states_it(requested: str) -> None:
    symbol, stated = await read_symbol(Account(EXNESS), requested, require_exists=True)
    assert symbol == "XAUUSDm"
    assert stated == {
        "symbol_resolution": {
            "requested": requested,
            "symbol": "XAUUSDm",
            "description": "Gold vs US Dollar",
        }
    }
    stated["symbol_resolution"]["symbol"] = "changed by a caller"
    assert await read_symbol(Account(EXNESS), "xauusdM", require_exists=True) == ("XAUUSDm", {})


@pytest.mark.asyncio
async def test_a_read_never_takes_a_look_alike_the_broker_prices_in_another_currency() -> None:
    account = Account({"XAUUSDm": ("XAU", "EUR"), "XAUUSDT": ("XAU", "USDT")})
    with pytest.raises(SymbolNotResolved) as failure:
        await read_symbol(account, "gold")
    assert failure.value.code == "symbol_not_found" and failure.value.details == {
        "requested_symbol": "gold",
        "candidates": [],
        "next": NOT_LISTED,
        "similar_symbols": ["XAUUSDT", "XAUUSDm"],
    }


@pytest.mark.asyncio
async def test_a_read_among_several_contracts_says_so() -> None:
    account = Account({"XAUUSDm": ("XAU", "USD"), "XAUUSDc": ("XAU", "USD")})
    symbol, stated = await read_symbol(account, "gold")
    assert symbol == "XAUUSDc"
    assert [item["symbol"] for item in stated["symbol_resolution"]["other_matches"]] == ["XAUUSDm"]
    assert stated["symbol_resolution"]["note"] == SEVERAL_FOR_A_READ


@pytest.mark.asyncio
async def test_the_catalogue_is_cached_per_account_and_read_again_on_a_miss() -> None:
    account, other = Account(dict(EXNESS)), Account({"XAUUSD.r": ("XAU", "USD")})
    assert (await read_symbol(account, "gold"))[0] == "XAUUSDm"
    assert (await read_symbol(account, "EURUSD"))[0] == "EURUSDm"
    assert (await read_symbol(other, "gold"))[0] == "XAUUSD.r"
    assert (account.listings, other.listings) == (1, 1)
    with pytest.raises(SymbolNotResolved):
        await read_symbol(account, "BTCUSD")
    assert account.listings == 2
    account.specs["BTCUSDm"] = ("BTC", "USD")
    assert (await read_symbol(account, "BTCUSD"))[0] == "BTCUSDm"
    assert account.listings == 3


@pytest.mark.asyncio
@pytest.mark.parametrize("strict", [order_symbol, canonical_broker_symbol])
@pytest.mark.parametrize("requested", REQUESTS)
async def test_an_order_or_grant_symbol_is_never_resolved_to_another_symbol(
    strict: Any, requested: str
) -> None:
    """Money paths accept the catalogue's exact name (letter case aside) or fail."""
    arguments = {"require_exists": True} if strict is canonical_broker_symbol else {}
    accounts: list[Specs] = [
        EXNESS,
        {"XAUUSD": ("XAU", "USD"), "XAUUSDc": ("XAU", "USD")},
        {"GOLD": (None, None)},
    ]
    for specs in accounts:
        try:
            symbol = await strict(Account(specs), requested, **arguments)
        except SymbolNotResolved:
            continue
        assert symbol in specs and symbol.casefold() == requested.casefold()


@pytest.mark.asyncio
async def test_an_order_for_an_unlisted_code_gets_the_real_symbol_and_the_next_call() -> None:
    with pytest.raises(SymbolNotResolved) as failure:
        await order_symbol(Account(EXNESS), "XAUUSD")
    assert failure.value.code == "symbol_not_found"
    assert failure.value.details == {
        "requested_symbol": "XAUUSD",
        "candidates": [
            {
                "symbol": "XAUUSDm",
                "description": "Gold vs US Dollar",
                "volume_min": "0.01",
                "volume_step": "0.01",
                "contract_size": "100",
                "base_currency": "XAU",
                "profit_currency": "USD",
            }
        ],
        "next": USE_THE_SYMBOL.format(symbol="XAUUSDm"),
    }


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "specs",
    [
        # A standard and a cent contract; spot beside a dated future.
        {"XAUUSDm": ("XAU", "USD"), "XAUUSDc": ("XAU", "USD")},
        {"XAUUSD.r": ("XAU", "USD"), "XAUUSD-DEC26": ("XAU", "USD")},
    ],
)
async def test_an_order_never_chooses_between_two_contracts(
    specs: dict[str, tuple[str | None, str | None]],
) -> None:
    for requested in ("XAUUSD", "gold", "الذهب"):
        with pytest.raises(SymbolNotResolved) as failure:
            await order_symbol(Account(specs), requested)
        assert failure.value.code == "symbol_ambiguous"
        assert failure.value.details["next"] == ASK_WHICH_CONTRACT
        assert {item["symbol"] for item in failure.value.details["candidates"]} == set(specs)


@pytest.mark.asyncio
async def test_an_unreadable_catalogue_leaves_an_order_symbol_to_the_executor() -> None:
    broker = SimpleNamespace(symbols=AsyncMock(side_effect=LonoraError("broker_timeout", 504)))
    assert await order_symbol(broker, "XAUUSD") == "XAUUSD"


@pytest.mark.asyncio
async def test_a_single_match_the_broker_does_not_confirm_is_offered_not_asserted() -> None:
    # An index, and a CFD the broker margins and quotes in dollars: nothing confirms it.
    for specs, requested, listed in (
        ({"US30.Y": ("USD", "USD")}, "US30", "US30.Y"),
        ({"XAUUSDm": ("USD", "USD")}, "XAUUSD", "XAUUSDm"),
    ):
        account: Specs = dict(specs)
        with pytest.raises(SymbolNotResolved) as failure:
            await order_symbol(Account(account), requested)
        assert failure.value.details["next"] == CHECK_THE_SYMBOL.format(symbol=listed)
        assert (await read_symbol(Account(account), requested))[0] == listed


@pytest.mark.asyncio
async def test_an_empty_listing_leaves_a_lenient_read_to_the_broker() -> None:
    assert await read_symbol(Account({}), "XAUUSD") == ("XAUUSD", {})
    with pytest.raises(SymbolNotResolved):
        await read_symbol(Account({}), "XAUUSD", require_exists=True)
