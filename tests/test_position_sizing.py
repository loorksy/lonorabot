"""Broker-unit estimates using explicit fixtures; never contacts a real broker."""

import asyncio
from datetime import timedelta
from decimal import Decimal
from unittest.mock import AsyncMock, Mock

import pytest
from lonora_adapter_kit.broker import BrokerStateReader
from lonora_adapters.brokers import normalize
from lonora_contracts.account import AccountState
from lonora_contracts.domain import utcnow
from lonora_contracts.market import Instrument, Quote
from lonora_contracts.position_sizing import PositionSizingRequest
from lonora_core.user_error import LonoraError
from lonora_trading.position_sizing import calculate_position_size, position_size


def state(symbol: str = "EURUSDm", currency: str = "USD"):
    now = utcnow()
    account = AccountState(
        id="connection",
        currency=currency,
        balance=Decimal("10000"),
        equity=Decimal("10000"),
        margin=Decimal("0"),
        free_margin=Decimal("10000"),
        observed_at=now,
    )
    instrument = Instrument(
        symbol=symbol,
        digits=2,
        tick_size=Decimal("0.01"),
        volume_min=Decimal("0.01"),
        volume_max=Decimal("100"),
        volume_step=Decimal("0.01"),
        stops_level=10,
        point_size=Decimal("0.01"),
    )
    quote = Quote(
        symbol=symbol,
        bid=Decimal("100.00"),
        ask=Decimal("100.02"),
        observed_at=now,
        source="explicit_broker_fixture",
        loss_tick_value=Decimal("1"),
        profit_tick_value=Decimal("0.9"),
        tick_value_basis="account_currency_per_lot",
        account_currency_exchange_rate=Decimal("7.52"),
    )
    request = PositionSizingRequest(
        account_id="connection",
        symbol=symbol,
        side="buy",
        risk_budget=Decimal("50"),
        currency=currency,
        stop_loss=Decimal("99.00"),
    )
    return request, account, instrument, quote


@pytest.mark.parametrize("symbol", ["EURUSDm", "XAUUSD.a", "US500.cash", "BTCUSD#"])
@pytest.mark.parametrize("currency", ["USD", "EUR", "USC", "USDc"])
def test_exact_arbitrary_symbol_and_account_units(symbol: str, currency: str):
    request, account, instrument, quote = state(symbol, currency)
    result = calculate_position_size(request, account, instrument, quote)
    assert result.volume == Decimal("0.49")
    assert result.modeled_stop_loss == Decimal("49.98")
    assert result.per_lot_stop_loss == 102  # Includes spread exactly once.
    assert result.loss_tick_value == 1  # Never multiply by the unrelated 7.52 FX field.
    assert result.symbol == symbol and result.currency == currency
    assert result.quote_at == quote.observed_at
    assert result.account_at == account.observed_at
    assert result.instrument == instrument and not result.execution_authorized
    assert set(result.exclusions) == {"gaps", "slippage", "commission", "swap", "margin_validation"}


def test_sell_and_nonzero_anchored_volume_lattice():
    request, account, instrument, quote = state()
    request.side, request.stop_loss, request.risk_budget = "sell", Decimal("101"), Decimal("52")
    instrument.volume_min, instrument.volume_step = Decimal("0.03"), Decimal("0.02")
    result = calculate_position_size(request, account, instrument, quote)
    assert result.entry == quote.bid and result.per_lot_stop_loss == 100
    assert result.volume == Decimal("0.51") and result.modeled_stop_loss == 51


def test_maximum_volume_and_fractional_max_not_on_lattice():
    request, account, instrument, quote = state()
    instrument.volume_min = Decimal("0.03")
    instrument.volume_step = Decimal("0.02")
    instrument.volume_max = Decimal("0.10")
    result = calculate_position_size(request, account, instrument, quote)
    assert result.volume == Decimal("0.09")


def test_tick_size_different_from_point_and_adverse_tick_ceiling():
    request, account, instrument, quote = state()
    instrument.tick_size = Decimal("0.05")
    instrument.point_size = Decimal("0.01")
    result = calculate_position_size(request, account, instrument, quote)
    assert result.per_lot_stop_loss == 21  # 1.02 / .05 rounds adversely to 21 ticks.
    assert result.volume == Decimal("2.38")
    assert result.modeled_stop_loss == Decimal("49.98")


@pytest.mark.parametrize("budget", ["0.0001", "1.019999999999999999999999999999999999999"])
def test_never_round_up_to_minimum_risk(budget: str):
    request, account, instrument, quote = state()
    request.risk_budget = Decimal(budget)
    with pytest.raises(LonoraError, match="position_sizing_below_minimum"):
        calculate_position_size(request, account, instrument, quote)


def test_exact_minimum_risk_and_high_precision_boundary():
    request, account, instrument, quote = state()
    request.risk_budget = Decimal("1.02")
    assert calculate_position_size(request, account, instrument, quote).volume == Decimal("0.01")
    request.risk_budget = Decimal("50.999999999999999999999999999999999999999")
    result = calculate_position_size(request, account, instrument, quote)
    assert result.volume == Decimal("0.49") and result.modeled_stop_loss <= request.risk_budget


@pytest.mark.parametrize(
    "field,value,code",
    [
        ("id", "another-account", "position_sizing_account_mismatch"),
        ("currency", "EUR", "position_sizing_currency_mismatch"),
        ("currency", "", "position_sizing_currency_mismatch"),
    ],
)
def test_account_identity_is_not_rewritten(field: str, value: str, code: str):
    request, account, instrument, quote = state()
    setattr(account, field, value)
    with pytest.raises(LonoraError, match=code):
        calculate_position_size(request, account, instrument, quote)
    assert getattr(account, field) == value


@pytest.mark.parametrize("resource", ["account", "quote"])
@pytest.mark.parametrize(
    "offset,code",
    [
        (-61, "stale"),
        (6, "timestamp_future"),
        (None, "timestamp_invalid"),
    ],
)
def test_source_freshness_cannot_be_reset_by_read(resource: str, offset: int | None, code: str):
    request, account, instrument, quote = state()
    observed = account if resource == "account" else quote
    observed.observed_at = (
        observed.observed_at + timedelta(seconds=offset)
        if offset is not None
        else observed.observed_at.replace(tzinfo=None)
    )
    with pytest.raises(LonoraError, match=code):
        calculate_position_size(request, account, instrument, quote)


@pytest.mark.parametrize("resource", ["instrument", "quote"])
def test_exact_symbol_mismatch(resource: str):
    request, account, instrument, quote = state()
    (instrument if resource == "instrument" else quote).symbol = "EURUSD"
    with pytest.raises(LonoraError, match="broker_symbol_mismatch"):
        calculate_position_size(request, account, instrument, quote)


@pytest.mark.parametrize(
    "value", [None, Decimal(0), Decimal(-1), Decimal("NaN"), Decimal("Infinity")]
)
def test_invalid_loss_economics_fail_closed(value: Decimal | None):
    request, account, instrument, quote = state()
    quote.loss_tick_value = value
    with pytest.raises(LonoraError, match="position_sizing_economics_unavailable"):
        calculate_position_size(request, account, instrument, quote)


def test_missing_unit_basis_and_contract_size_are_not_money():
    request, account, instrument, quote = state()
    quote.tick_value_basis = None
    instrument.contract_size = Decimal("100000")
    with pytest.raises(LonoraError, match="position_sizing_economics_unavailable"):
        calculate_position_size(request, account, instrument, quote)


@pytest.mark.parametrize(
    "side,stop,code",
    [
        ("buy", "100.01", "stop_loss_wrong_side"),
        ("sell", "100.01", "stop_loss_wrong_side"),
        ("buy", "99.95", "stop_loss_stops_level"),
        ("sell", "100.07", "stop_loss_stops_level"),
        ("buy", "99.001", "price_tick_mismatch"),
    ],
)
def test_protection_validation(side: str, stop: str, code: str):
    request, account, instrument, quote = state()
    request = request.model_copy(update={"side": side, "stop_loss": Decimal(stop)})
    with pytest.raises(LonoraError, match=code):
        calculate_position_size(request, account, instrument, quote)


@pytest.mark.parametrize("bad", [None, "NaN", "Infinity", "-1", "0", {}, True])
def test_bad_optional_sdk_economics_preserve_valid_prices(bad: object):
    raw = {
        "symbol": "arbitrary.suffix",
        "bid": "10",
        "ask": "11",
        "time": utcnow(),
        "lossTickValue": bad,
        "profitTickValue": bad,
        "accountCurrencyExchangeRate": bad,
    }
    quote = normalize.quote(raw)
    assert quote.bid == 10 and quote.ask == 11
    assert quote.loss_tick_value is None and quote.profit_tick_value is None
    assert quote.tick_value_basis is None and quote.account_currency_exchange_rate is None


def test_sdk_optional_metadata_preserved_without_inference():
    instrument = normalize.instrument(
        {
            "symbol": "arbitrary.suffix",
            "digits": 2,
            "tickSize": "0.01",
            "minVolume": "1",
            "maxVolume": "100",
            "volumeStep": "1",
            "contractSize": "123.4",
            "baseCurrency": "XYZ",
            "profitCurrency": "USC",
        }
    )
    assert instrument.contract_size == Decimal("123.4")
    assert instrument.base_currency == "XYZ" and instrument.profit_currency == "USC"
    assert (
        normalize.quote(
            {
                "symbol": instrument.symbol,
                "bid": 1,
                "ask": 2,
                "time": utcnow(),
            }
        ).loss_tick_value
        is None
    )


def test_same_reader_and_no_mutations():
    request, account, instrument, quote = state()
    broker = Mock(spec=BrokerStateReader)
    broker.account = AsyncMock(return_value=account)
    broker.instrument = AsyncMock(return_value=instrument)
    broker.quote = AsyncMock(return_value=quote)
    broker.execute = AsyncMock()
    broker.positions = AsyncMock()
    broker.orders = AsyncMock()
    result = asyncio.run(position_size(broker, request))
    assert not result.execution_authorized
    broker.account.assert_awaited_once_with()
    broker.instrument.assert_awaited_once_with(request.symbol)
    broker.quote.assert_awaited_once_with(request.symbol)
    broker.execute.assert_not_awaited()
    broker.positions.assert_not_awaited()
    broker.orders.assert_not_awaited()


def test_unknown_contract_fails_before_quote_races():
    request, _, _, _ = state()
    broker = Mock(spec=BrokerStateReader)
    broker.instrument = AsyncMock(side_effect=LonoraError("broker_instrument_unavailable", 404))
    broker.account = AsyncMock()
    broker.quote = AsyncMock(side_effect=LonoraError("quote_unavailable", 404))
    with pytest.raises(LonoraError, match="broker_instrument_unavailable"):
        asyncio.run(position_size(broker, request))
    broker.account.assert_not_awaited()
    broker.quote.assert_not_awaited()


@pytest.mark.parametrize("value", ["1e1000000000", "1e-1000000000", "1." + "2" * 600])
def test_untrusted_numeric_magnitudes_are_bounded(value: str):
    request, account, instrument, quote = state()
    request.risk_budget = Decimal(value)
    with pytest.raises(LonoraError, match="position_sizing_numeric_precision"):
        calculate_position_size(request, account, instrument, quote)


@pytest.mark.parametrize("value", [Decimal("NaN"), Decimal("Infinity"), Decimal(0), Decimal(-1)])
def test_unvalidated_point_size_is_rejected(value: Decimal):
    request, account, instrument, quote = state()
    instrument.point_size = value
    with pytest.raises(LonoraError, match="position_sizing_values_invalid"):
        calculate_position_size(request, account, instrument, quote)
