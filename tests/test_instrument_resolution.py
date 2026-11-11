"""An instrument request resolves from the account's own catalogue, never by guesswork."""

from decimal import Decimal

import pytest
from lonora_contracts.market import Instrument
from lonora_market.instruments import catalogue_matches, contradicts, instrument_codes


def spec(symbol: str, base: str | None = None, quote: str | None = None) -> Instrument:
    return Instrument(
        symbol=symbol,
        digits=2,
        tick_size=Decimal("0.01"),
        volume_min=Decimal("0.01"),
        volume_max=Decimal(100),
        volume_step=Decimal("0.01"),
        base_currency=base,
        profit_currency=quote,
    )


@pytest.mark.parametrize(
    "requested", ["الذهب", "ذهب", "gold", "Gold", "XAUUSD", "xauusd", "XAU/USD"]
)
def test_a_common_name_and_a_canonical_code_name_the_same_instrument(requested: str) -> None:
    assert instrument_codes(requested)[0] == "XAUUSD"
    assert catalogue_matches(["EURUSDm", "XAUUSDm", "XAGUSDm"], requested) == ["XAUUSDm"]


@pytest.mark.parametrize(
    "name",
    ["XAUUSDm", "XAUUSDc", "XAUUSD.r", "XAUUSD.pro", "XAUUSD#", "XAUUSD_i", "#XAUUSD", "m.XAUUSD"],
)
def test_the_usual_broker_affixes_resolve_from_the_catalogue(name: str) -> None:
    assert catalogue_matches(["EURUSD", name, "XAGUSD"], "XAUUSD") == [name]
    assert catalogue_matches(["EURUSD", name, "XAGUSD"], "الذهب") == [name]


def test_the_exact_name_wins_and_letter_case_alone_is_the_same_symbol() -> None:
    catalogue = ["XAUUSD", "XAUUSDc", "XAUUSD.r"]
    assert catalogue_matches(catalogue, "XAUUSD") == ["XAUUSD"]
    assert catalogue_matches(catalogue, "xauusdC") == ["XAUUSDc"]
    assert catalogue_matches(["GOLD", "XAUEUR"], "gold") == ["GOLD"]


def test_a_broker_that_names_gold_by_its_word_still_resolves() -> None:
    assert catalogue_matches(["GOLDm", "SILVERm", "EURUSDm"], "XAUUSD") == ["GOLDm"]
    assert catalogue_matches(["GOLD", "EURUSD"], "الذهب") == ["GOLD"]
    # The word is only a fallback: where the code is listed, the word adds nothing.
    assert catalogue_matches(["EURO-STOXX", "EURUSDm"], "اليورو") == ["EURUSDm"]


def test_every_matching_contract_is_returned_so_an_order_never_picks_one() -> None:
    # A standard and a cent symbol, and spot beside a dated future: all are candidates,
    # the bare code first, then the shortest name.
    assert catalogue_matches(["XAUUSDc", "XAUUSDm", "EURUSDm"], "gold") == ["XAUUSDc", "XAUUSDm"]
    assert catalogue_matches(["XAUUSD-DEC26", "XAUUSD", "XAUUSD.r"], "gold") == [
        "XAUUSD",
        "XAUUSD.r",
        "XAUUSD-DEC26",
    ]


@pytest.mark.parametrize(
    ("catalogue", "requested"),
    [
        # Another instrument that only shares letters is never a naming variant.
        (["XAUUSDT", "XAUUSDJPY", "XAUEUR", "XAGUSD"], "XAUUSD"),
        (["US300", "US3000m", "AUS30"], "US30"),
        (["EURUSDm"], "EURUSDm.other"),
        (["EURUSDm", "GBPUSDm"], "EUR"),
        (["BTCUSD", 3, None], "ETHUSD"),
        (["XAUUSDm"], ""),
        # A fragment of a name (an affix alone) is never a request for the instrument.
        (["XAUUSD.r", "m.XAUUSD", "XAUUSD_i"], "r"),
        (["XAUUSD.r", "m.XAUUSD", "XAUUSD.pro"], "m"),
        (["XAUUSD.pro", "pro.XAUUSD"], "pro"),
        (["EURO-STOXX", "EURUSDm"], "STOXX"),
    ],
)
def test_a_different_instrument_is_never_a_match(catalogue: list[object], requested: str) -> None:
    assert catalogue_matches(catalogue, requested) == []


def test_the_brokers_own_currencies_reject_a_look_alike() -> None:
    assert not contradicts("XAUUSD", spec("XAUUSDm", "XAU", "USD"))
    assert contradicts("XAUUSD", spec("XAUUSDm", "XAU", "EUR"))
    assert contradicts("BTCUSD", spec("BTCUSDt", "BTC", "USDT"))
    # Unreported currencies, and codes that are not a currency pair, prove nothing.
    assert not contradicts("XAUUSD", spec("XAUUSDm"))
    assert not contradicts("US30", spec("US30.cash", "USD", "USD"))
