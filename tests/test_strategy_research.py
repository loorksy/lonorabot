"""Deterministic analytical contracts; no broker execution or network calls."""

from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest
from lonora_contracts.market import Candle, Instrument
from lonora_core.user_error import LonoraError
from lonora_market.research import (
    ResearchConfig,
    ResearchScenario,
    StrategySpec,
    backtest,
    candle_end,
    digest,
    fill,
    monte_carlo,
    research,
    signal,
)
from pydantic import ValidationError


def instrument(symbol: str = "METAL.demo", tick: str = "0.5") -> Instrument:
    return Instrument(
        symbol=symbol,
        digits=5,
        tick_size=Decimal(tick),
        volume_min=Decimal("0.1"),
        volume_max=Decimal("100"),
        volume_step=Decimal("0.1"),
    )


def candles(symbol: str = "METAL.demo", count: int = 100) -> list[Candle]:
    return [
        Candle(
            symbol=symbol,
            timeframe="1m",
            time=datetime(2024, 1, 1, tzinfo=UTC) + timedelta(minutes=i),
            open=Decimal(100 + i),
            high=Decimal(102 + i),
            low=Decimal(99 + i),
            close=Decimal("100.5") + i,
        )
        for i in range(count)
    ]


def scenario(**updates: object) -> ResearchScenario:
    values: dict[str, object] = {
        "currency": "USD",
        "initial_equity": "10000",
        "volume": "2",
        "tick_value_per_lot": "5",
        "price_basis": "bid",
        "spread_ticks": "2",
        "slippage_ticks_per_side": "1",
        "commission_per_lot_side": "3",
        "carry_cost_per_lot_day": "0",
        "latency_bars": 1,
        "provenance": "Explicit test scenario; not verified broker economics.",
    }
    return ResearchScenario.model_validate({**values, **updates})


def config(**updates: object) -> ResearchConfig:
    values: dict[str, object] = {
        "candidates": [{"fast": 1, "slow": 2}, {"fast": 2, "slow": 4}],
        "scenario": scenario(),
        "gap_policy": "reject",
        "seed": 17,
        "monte_carlo_samples": 20,
    }
    return ResearchConfig.model_validate({**values, **updates})


def run(bars: list[Candle] | None = None, settings: ResearchConfig | None = None):
    bars = candles() if bars is None else bars
    return research(
        bars,
        instrument(),
        settings or config(),
        account_id="scripted-demo",
        source="simulation_fixture",
        observed_at=datetime(2024, 2, 1, tzinfo=UTC),
    )


def test_costs_and_generic_tick_value_are_exact():
    metrics, trades = backtest(
        candles(), instrument(), StrategySpec(fast=1, slow=2), scenario(), 2, 5
    )
    assert len(trades) == 1
    trade = trades[0]
    assert trade.entry == Decimal("103.5")
    assert trade.exit == Decimal("104.0")
    assert trade.gross_pnl == 50
    assert trade.execution_cost == 40
    assert trade.commission == 12
    assert trade.net_pnl == -2
    assert metrics.net_pnl == metrics.gross_pnl - metrics.execution_cost - metrics.commission
    assert trade.signal_at <= trade.entry_at < trade.exit_at


def test_next_bar_signal_cannot_read_current_or_future_close():
    bars = candles()
    first = signal(bars, 1, StrategySpec(fast=1, slow=2))
    changed = bars[:2] + [
        bar.model_copy(
            update={
                "open": Decimal(1),
                "high": Decimal(2),
                "low": Decimal("0.5"),
                "close": Decimal(1),
            }
        )
        for bar in bars[2:]
    ]
    assert signal(changed, 1, StrategySpec(fast=1, slow=2)) == first
    _, original = backtest(bars, instrument(), StrategySpec(fast=1, slow=2), scenario())
    _, future = backtest(changed, instrument(), StrategySpec(fast=1, slow=2), scenario())
    assert original[0].signal_at == future[0].signal_at == candle_end(bars[1])
    assert original[0].entry_at == future[0].entry_at == bars[2].time
    assert original[0].entry != future[0].entry, "Fill must use the actual next open."


def test_latency_is_bounded_in_completed_bars_and_rounding_is_adverse():
    _, trades = backtest(
        candles(), instrument(), StrategySpec(fast=1, slow=2), scenario(latency_bars=3)
    )
    assert trades[0].entry_at == candles()[4].time
    assert trades[0].signal_at == candle_end(candles()[1])
    assert fill(Decimal("100.1"), True, instrument(), scenario()) == Decimal("102.0")
    assert fill(Decimal("100.1"), False, instrument(), scenario()) == Decimal("99.5")


def test_carry_uses_elapsed_time_and_volume():
    _, trades = backtest(
        candles(),
        instrument(),
        StrategySpec(fast=1, slow=2),
        scenario(carry_cost_per_lot_day="1440"),
        2,
        5,
    )
    assert trades[0].carry == 6


@pytest.mark.parametrize(
    "symbol,tick",
    [
        ("EURUSD.fx", "0.00001"),
        ("XAUUSDm", "0.01"),
        ("INDEX.cash", "0.1"),
        ("BTCUSD.coin", "0.5"),
    ],
)
def test_instrument_units_and_suffixes_are_not_inferred(symbol: str, tick: str):
    result = research(
        candles(symbol),
        instrument(symbol, tick),
        config(),
        account_id="demo",
        source="fixture",
        observed_at=datetime(2024, 2, 1, tzinfo=UTC),
    )
    assert result.symbol == symbol
    assert result.instrument.tick_size == Decimal(tick)
    assert result.config.scenario.tick_value_per_lot == 5
    assert result.execution_authorized is False
    assert result.mode == "historical_research"


def test_reproducible_data_parameters_engine_and_results():
    first, second = run(), run()
    assert first.model_dump() == second.model_dump()
    assert first.result_sha256 == digest(first.model_dump(mode="json", exclude={"result_sha256"}))
    changed = run(settings=config(seed=18))
    assert changed.dataset_sha256 == first.dataset_sha256
    assert changed.configuration_sha256 != first.configuration_sha256
    assert changed.result_sha256 != first.result_sha256
    assert first.dataset and first.instrument and first.config.scenario.provenance
    assert first.confidence == "historical_scenario_only"


def test_walk_forward_tests_are_disjoint_and_selection_has_no_future_data():
    result = run()
    assert len(result.folds) == 4
    for fold in result.folds:
        assert (
            fold.train_end
            <= fold.validation_start
            < fold.validation_end
            <= fold.test_start
            < fold.test_end
        )
        assert all(
            t.entry_at >= fold.test_start and t.exit_at <= fold.test_end for t in fold.trades
        )
    assert all(
        left.test_end <= right.test_start
        for left, right in zip(result.folds, result.folds[1:], strict=False)
    )
    bars = candles()
    start = result.folds[0].test_start
    changed = [
        bar
        if bar.time < start
        else bar.model_copy(
            update={
                "open": bar.open * 2,
                "high": bar.high * 2,
                "low": bar.low * 2,
                "close": bar.close * 2,
            }
        )
        for bar in bars
    ]
    future = run(changed)
    assert future.folds[0].selected == result.folds[0].selected
    assert future.folds[0].training == result.folds[0].training
    assert future.folds[0].validation == result.folds[0].validation


def test_gap_is_rejected_or_explicitly_reported_without_fabrication():
    bars = candles()
    bars[50:] = [
        bar.model_copy(update={"time": bar.time + timedelta(minutes=1)}) for bar in bars[50:]
    ]
    with pytest.raises(LonoraError, match="market_candle_gap"):
        run(bars)
    result = run(bars, config(gap_policy="report"))
    assert result.integrity["gap_count"] == 1
    assert len(result.dataset) == len(bars)
    assert result.integrity["session_continuity"] == "unverified"


@pytest.mark.parametrize(
    "problem,code",
    [
        ("duplicate", "duplicate_candle_timestamp"),
        ("order", "market_candle_out_of_order"),
        ("symbol", "mixed_candle_series"),
        ("ohlc", "market_candle_invalid"),
        ("naive", "market_candle_timestamp_invalid"),
    ],
)
def test_invalid_history_cannot_be_backtested(problem: str, code: str):
    bars = candles()
    if problem == "duplicate":
        bars[10] = bars[9]
    elif problem == "order":
        bars[9], bars[10] = bars[10], bars[9]
    elif problem == "symbol":
        bars[10] = bars[10].model_copy(update={"symbol": "WRONG"})
    elif problem == "ohlc":
        bars[10] = bars[10].model_copy(update={"low": Decimal(999)})
    else:
        bars[10] = bars[10].model_copy(update={"time": bars[10].time.replace(tzinfo=None)})
    with pytest.raises(LonoraError, match=code):
        run(bars)


def test_incomplete_candle_and_invalid_volume_are_blocked():
    with pytest.raises(LonoraError, match="research_incomplete_or_future_bar"):
        research(
            candles(),
            instrument(),
            config(),
            observed_at=candles()[-1].time,
            account_id="demo",
            source="fixture",
        )
    with pytest.raises(LonoraError, match="research_volume_invalid"):
        run(settings=config(scenario=scenario(volume="0.15")))


def test_monte_carlo_is_seeded_and_cannot_claim_predictive_probability():
    _, trades = backtest(candles(), instrument(), StrategySpec(fast=1, slow=2), scenario())
    assert monte_carlo(trades, scenario(), 20, 7) == monte_carlo(trades, scenario(), 20, 7)
    assert monte_carlo(trades, scenario(), 20, 7) != monte_carlo(trades, scenario(), 20, 8)
    assert monte_carlo(trades, scenario(), 20, 7)["predictive_probability"] is False
    assert monte_carlo([], scenario(), 20, 7)["status"] == "insufficient_trades"


def test_nan_and_unsupported_strategies_are_rejected():
    with pytest.raises(ValidationError):
        scenario(tick_value_per_lot="NaN")
    with pytest.raises(ValidationError):
        config(candidates=[{"kind": "arbitrary_python", "fast": 1, "slow": 2}])


def test_calendar_month_end_is_not_approximated_as_thirty_days():
    bar = candles()[0].model_copy(
        update={"timeframe": "1mn", "time": datetime(2024, 2, 1, tzinfo=UTC)}
    )
    assert candle_end(bar) == datetime(2024, 3, 1, tzinfo=UTC)
