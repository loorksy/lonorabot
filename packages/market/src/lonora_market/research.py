"""Bounded historical research, without financial authority or broker mutation.

Only the declared SMA strategy is implemented. Broker candles are observations;
valuation and execution costs are explicitly supplied scenarios, not broker facts.
"""

import hashlib
import json
import random
from calendar import monthrange
from datetime import datetime, timedelta
from decimal import ROUND_CEILING, ROUND_FLOOR, Decimal
from typing import Any, Literal

from lonora_contracts.domain import Contract
from lonora_contracts.market import Candle, Instrument
from lonora_core.chart_controller import validate_timeframe
from lonora_core.user_error import LonoraError
from pydantic import Field, model_validator

from .health import assess_candles

ENGINE_VERSION = "sma-next-bar-v1"
ZERO = Decimal(0)


class StrategySpec(Contract):
    kind: Literal["sma_cross"] = "sma_cross"
    fast: int = Field(ge=1, le=99)
    slow: int = Field(ge=2, le=100)
    allow_short: bool = True

    @model_validator(mode="after")
    def windows(self) -> "StrategySpec":
        if self.fast >= self.slow:
            raise ValueError("research_fast_must_precede_slow")
        return self


class ResearchScenario(Contract):
    """Every monetary input is a declared scenario, never inferred from a ticker."""

    currency: str = Field(min_length=1, max_length=16, pattern=r"^[A-Za-z0-9_]+$")
    initial_equity: Decimal = Field(gt=0, le=Decimal("1e12"))
    volume: Decimal = Field(gt=0, le=Decimal("1e9"))
    tick_value_per_lot: Decimal = Field(gt=0, le=Decimal("1e9"))
    price_basis: Literal["bid", "mid"]
    spread_ticks: Decimal = Field(ge=0, le=Decimal("1e6"))
    slippage_ticks_per_side: Decimal = Field(ge=0, le=Decimal("1e6"))
    commission_per_lot_side: Decimal = Field(ge=0, le=Decimal("1e9"))
    carry_cost_per_lot_day: Decimal = Field(ge=0, le=Decimal("1e9"))
    latency_bars: int = Field(ge=1, le=5)
    provenance: str = Field(min_length=1, max_length=500)


class ResearchConfig(Contract):
    candidates: list[StrategySpec] = Field(min_length=1, max_length=12)
    scenario: ResearchScenario
    gap_policy: Literal["reject", "report"]
    monte_carlo_samples: int = Field(default=100, ge=20, le=500)
    seed: int = Field(default=0, ge=0, le=2**32 - 1)


class ResearchTrade(Contract):
    side: Literal["buy", "sell"]
    signal_at: datetime
    entry_at: datetime
    exit_at: datetime
    entry: Decimal
    exit: Decimal
    gross_pnl: Decimal
    execution_cost: Decimal
    commission: Decimal
    carry: Decimal
    net_pnl: Decimal


class ResearchMetrics(Contract):
    trades: int
    gross_pnl: Decimal
    execution_cost: Decimal
    commission: Decimal
    carry: Decimal
    net_pnl: Decimal
    return_fraction: Decimal
    max_drawdown: Decimal
    wins: int
    bankrupt: bool


class ResearchCandidateScore(Contract):
    strategy: StrategySpec
    training: ResearchMetrics
    validation: ResearchMetrics | None = None


class ResearchFold(Contract):
    train_end: datetime
    validation_start: datetime
    validation_end: datetime
    test_start: datetime
    test_end: datetime
    selected: StrategySpec
    candidate_scores: list[ResearchCandidateScore]
    training: ResearchMetrics
    validation: ResearchMetrics
    out_of_sample: ResearchMetrics
    trades: list[ResearchTrade]


class ResearchResult(Contract):
    """One reproducible contract for tool, attachment, and later audit consumers."""

    schema_version: Literal["research-v1"] = "research-v1"
    engine_version: str = ENGINE_VERSION
    mode: Literal["historical_research"] = "historical_research"
    execution_authorized: Literal[False] = False
    observed_at: datetime
    account_id: str
    symbol: str
    timeframe: str
    source: str
    dataset_sha256: str
    configuration_sha256: str
    result_sha256: str
    integrity: dict[str, Any]
    config: ResearchConfig
    instrument: Instrument
    dataset: list[Candle]
    baseline: ResearchMetrics
    folds: list[ResearchFold]
    monte_carlo: dict[str, Any]
    assumptions: list[str]
    missing_inputs: list[str]
    confidence: Literal["historical_scenario_only"] = "historical_scenario_only"


def digest(value: Any) -> str:
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()
    ).hexdigest()


def candle_end(candle: Candle) -> datetime:
    validate_timeframe(candle.timeframe)
    if candle.timeframe == "1mn":
        year = candle.time.year + (candle.time.month == 12)
        month = candle.time.month % 12 + 1
        return candle.time.replace(
            year=year, month=month, day=min(candle.time.day, monthrange(year, month)[1])
        )
    seconds = (
        int(candle.timeframe[:-1])
        * {"m": 60, "h": 3600, "d": 86400, "w": 604800}[candle.timeframe[-1]]
    )
    return candle.time + timedelta(seconds=seconds)


def validate_dataset(
    candles: list[Candle],
    instrument: Instrument,
    config: ResearchConfig,
    observed_at: datetime,
    account_id: str,
) -> dict[str, Any]:
    if not 80 <= len(candles) <= 1000:
        raise LonoraError("research_requires_80_to_1000_closed_bars", 422)
    if observed_at.tzinfo is None or observed_at.utcoffset() is None:
        raise LonoraError("research_timestamp_requires_timezone", 422)
    health = assess_candles(
        candles,
        account_id=account_id,
        symbol=instrument.symbol,
        timeframe=candles[0].timeframe,
        now=candles[-1].time,
        maximum_age_seconds=1,
    )
    if not health.healthy:
        raise LonoraError(health.reason_code, 422)
    if any(candle_end(bar) > observed_at for bar in candles):
        raise LonoraError("research_incomplete_or_future_bar", 422)
    if any(
        not value.is_finite()
        for value in (
            instrument.tick_size,
            instrument.volume_min,
            instrument.volume_max,
            instrument.volume_step,
        )
    ):
        raise LonoraError("research_instrument_invalid", 422)
    volume = config.scenario.volume
    if (
        not instrument.volume_min <= volume <= instrument.volume_max
        or (volume - instrument.volume_min) % instrument.volume_step != 0
    ):
        raise LonoraError("research_volume_invalid", 422)
    gaps = sum(
        right.time > candle_end(left) for left, right in zip(candles, candles[1:], strict=False)
    )
    overlaps = any(
        right.time < candle_end(left) for left, right in zip(candles, candles[1:], strict=False)
    )
    if overlaps:
        raise LonoraError("research_candle_interval_overlap", 422)
    if gaps and config.gap_policy == "reject":
        raise LonoraError("market_candle_gap", 422)
    if max(candidate.slow for candidate in config.candidates) >= len(candles) // 2 - 1:
        raise LonoraError("research_insufficient_training_bars", 422)
    return {
        "health": health.model_dump(mode="json"),
        "closed_bars": len(candles),
        "gap_count": gaps,
        "gap_policy": config.gap_policy,
        "session_continuity": "unverified" if gaps else "observed_contiguous",
        "live_freshness_asserted": False,
    }


def signal(candles: list[Candle], index: int, strategy: StrategySpec) -> int:
    """A decision uses completed closes through index, never a later bar."""
    if index < strategy.slow - 1:
        return 0
    fast = sum((c.close for c in candles[index - strategy.fast + 1 : index + 1]), ZERO)
    slow = sum((c.close for c in candles[index - strategy.slow + 1 : index + 1]), ZERO)
    difference = fast * strategy.slow - slow * strategy.fast
    return 1 if difference > 0 else -1 if difference < 0 and strategy.allow_short else 0


def fill(price: Decimal, buy: bool, instrument: Instrument, scenario: ResearchScenario) -> Decimal:
    spread = scenario.spread_ticks * instrument.tick_size
    adjustment = spread if scenario.price_basis == "bid" else spread / 2
    offset = adjustment if buy else ZERO if scenario.price_basis == "bid" else -adjustment
    adjusted = (
        price
        + offset
        + (1 if buy else -1) * scenario.slippage_ticks_per_side * instrument.tick_size
    )
    result = (adjusted / instrument.tick_size).to_integral_value(
        rounding=ROUND_CEILING if buy else ROUND_FLOOR
    ) * instrument.tick_size
    if result <= 0:
        raise LonoraError("research_execution_price_invalid", 422)
    return result


def backtest(
    candles: list[Candle],
    instrument: Instrument,
    strategy: StrategySpec,
    scenario: ResearchScenario,
    start: int = 0,
    end: int | None = None,
) -> tuple[ResearchMetrics, list[ResearchTrade]]:
    end = len(candles) if end is None else end
    if not 0 <= start < end <= len(candles):
        raise LonoraError("research_period_invalid", 422)
    trades: list[ResearchTrade] = []
    side, entry_index, signal_index = 0, 0, 0
    entry_fill = ZERO
    realized, peak, maximum = ZERO, scenario.initial_equity, ZERO
    bankrupt = False
    value = scenario.tick_value_per_lot * scenario.volume / instrument.tick_size

    def close(price: Decimal, at: datetime) -> ResearchTrade:
        exit_fill = fill(price, side < 0, instrument, scenario)
        gross = (price - candles[entry_index].open) * side * value
        execution = (exit_fill - entry_fill) * side * value
        commission = scenario.commission_per_lot_side * scenario.volume * 2
        days = Decimal(str((at - candles[entry_index].time).total_seconds())) / 86400
        carry = days * scenario.carry_cost_per_lot_day * scenario.volume
        return ResearchTrade(
            side="buy" if side > 0 else "sell",
            signal_at=candle_end(candles[signal_index]),
            entry_at=candles[entry_index].time,
            exit_at=at,
            entry=entry_fill,
            exit=exit_fill,
            gross_pnl=gross,
            execution_cost=gross - execution,
            commission=commission,
            carry=carry,
            net_pnl=execution - commission - carry,
        )

    for index in range(start, end):
        known = index - scenario.latency_bars
        desired = signal(candles, known, strategy) if known >= 0 else 0
        if desired != side and side:
            trade = close(candles[index].open, candles[index].time)
            trades.append(trade)
            realized += trade.net_pnl
            side = 0
        if desired and not side and scenario.initial_equity + realized > 0:
            side, entry_index, signal_index = desired, index, known
            entry_fill = fill(candles[index].open, side > 0, instrument, scenario)
        equity = scenario.initial_equity + realized
        if side:
            equity += close(candles[index].close, candle_end(candles[index])).net_pnl
        peak = max(peak, equity)
        maximum = max(maximum, peak - equity)
        bankrupt = bankrupt or equity <= 0
        if bankrupt:
            if side:
                trade = close(candles[index].close, candle_end(candles[index]))
                trades.append(trade)
                realized += trade.net_pnl
                side = 0
            break
    if side:
        trade = close(candles[end - 1].close, candle_end(candles[end - 1]))
        trades.append(trade)
    gross = sum((t.gross_pnl for t in trades), ZERO)
    costs = sum((t.execution_cost for t in trades), ZERO)
    commission = sum((t.commission for t in trades), ZERO)
    carry = sum((t.carry for t in trades), ZERO)
    net = sum((t.net_pnl for t in trades), ZERO)
    return ResearchMetrics(
        trades=len(trades),
        gross_pnl=gross,
        execution_cost=costs,
        commission=commission,
        carry=carry,
        net_pnl=net,
        return_fraction=net / scenario.initial_equity,
        max_drawdown=maximum,
        wins=sum(t.net_pnl > 0 for t in trades),
        bankrupt=bankrupt,
    ), trades


def monte_carlo(
    trades: list[ResearchTrade], scenario: ResearchScenario, samples: int, seed: int
) -> dict[str, Any]:
    generator = random.Random(seed)
    drawdowns: list[Decimal] = []
    returns: list[Decimal] = []
    ruins = 0
    for _ in range(samples):
        sequence = list(trades)
        generator.shuffle(sequence)
        equity = peak = scenario.initial_equity
        maximum = ZERO
        ruined = False
        for trade in sequence:
            # Declared stress distribution: uniform extra 0..100% of execution cost.
            stress = trade.execution_cost * Decimal(str(generator.random()))
            equity += trade.net_pnl - stress
            peak = max(peak, equity)
            maximum = max(maximum, peak - equity)
            ruined = ruined or equity <= 0
        ruins += ruined
        drawdowns.append(maximum)
        returns.append(equity - scenario.initial_equity)
    drawdowns.sort()
    returns.sort()
    return {
        "samples": samples,
        "seed": seed,
        "trade_count": len(trades),
        "method": "shuffle_closed_oos_trades_with_uniform_0_to_100_percent_extra_execution_cost",
        "status": "scenario_only" if trades else "insufficient_trades",
        "drawdown_p95": str(drawdowns[int((samples - 1) * 0.95)]),
        "net_pnl_p05": str(returns[int((samples - 1) * 0.05)]),
        "ruin_fraction": str(Decimal(ruins) / samples),
        "predictive_probability": False,
    }


def research(
    candles: list[Candle],
    instrument: Instrument,
    config: ResearchConfig,
    *,
    observed_at: datetime,
    account_id: str,
    source: str,
) -> ResearchResult:
    integrity = validate_dataset(candles, instrument, config, observed_at, account_id)
    baseline, _ = backtest(candles, instrument, config.candidates[0], config.scenario)
    folds: list[ResearchFold] = []
    oos_trades: list[ResearchTrade] = []
    train_end, width = len(candles) // 2, max(8, len(candles) // 10)
    while train_end + width * 2 <= len(candles) and len(folds) < 4:
        validation_end, test_end = train_end + width, train_end + width * 2
        ranked: list[tuple[Decimal, int, ResearchMetrics]] = []
        for index, candidate in enumerate(config.candidates):
            training, _ = backtest(candles, instrument, candidate, config.scenario, 0, train_end)
            ranked.append((training.net_pnl, index, training))
        ranked.sort(key=lambda value: (-value[0], value[1]))
        validated: list[tuple[Decimal, int, ResearchMetrics, ResearchMetrics]] = []
        for _, index, training in ranked[:3]:
            validation, _ = backtest(
                candles,
                instrument,
                config.candidates[index],
                config.scenario,
                train_end,
                validation_end,
            )
            validated.append((validation.net_pnl, index, training, validation))
        validated.sort(key=lambda value: (-value[0], value[1]))
        _, selected, training, validation = validated[0]
        validation_scores = {index: metrics for _, index, _, metrics in validated}
        candidate_scores = [
            ResearchCandidateScore(
                strategy=config.candidates[index],
                training=metrics,
                validation=validation_scores.get(index),
            )
            for _, index, metrics in ranked
        ]
        candidate = config.candidates[selected]
        out_of_sample, trades = backtest(
            candles, instrument, candidate, config.scenario, validation_end, test_end
        )
        folds.append(
            ResearchFold(
                train_end=candle_end(candles[train_end - 1]),
                validation_start=candles[train_end].time,
                validation_end=candle_end(candles[validation_end - 1]),
                test_start=candles[validation_end].time,
                test_end=candle_end(candles[test_end - 1]),
                selected=candidate,
                candidate_scores=candidate_scores,
                training=training,
                validation=validation,
                out_of_sample=out_of_sample,
                trades=trades,
            )
        )
        oos_trades.extend(trades)
        train_end += width
    data = [bar.model_dump(mode="json") for bar in candles]
    result = ResearchResult(
        observed_at=observed_at,
        account_id=account_id,
        symbol=instrument.symbol,
        timeframe=candles[0].timeframe,
        source=source,
        dataset_sha256=digest(data),
        configuration_sha256=digest(config.model_dump(mode="json")),
        result_sha256="",
        integrity=integrity,
        config=config,
        instrument=instrument,
        dataset=candles,
        baseline=baseline,
        folds=folds,
        monte_carlo=monte_carlo(
            oos_trades, config.scenario, config.monte_carlo_samples, config.seed
        ),
        assumptions=[
            "SMA direction follows completed closes; fills use later bar opens and declared latency.",
            "Each evaluation period starts flat; warmup may use earlier observations only.",
            "Baseline uses the first declared candidate and is full-sample, not out-of-sample.",
            "Expanding training ranks candidates; validation selects among the best three; tests are chronological and disjoint.",
            "Monetary tick valuation, currency, price basis and all costs are supplied scenarios, not verified broker economics.",
            "Execution is adversely tick-rounded; fixed spread/slippage, per-side commission and elapsed-time carry are modeled.",
            "Monte Carlo shuffles closed OOS trades with declared additional cost stress; it is not a future win probability.",
            "No live promotion, Shadow trade, account permission or broker order is created.",
        ],
        missing_inputs=[
            "Historical bid/ask, variable tick valuation and currency conversions.",
            "Tick-level liquidity, partial fills, market sessions, margin/liquidation and rejected orders.",
            "Actual historical commissions, swaps/rollovers and sub-bar latency.",
            "Parameter uncertainty beyond declared candidate comparison; survivorship and external strategy equivalence.",
            "Independent live or Shadow validation; historical research is distinct from persisted Shadow outcomes.",
        ],
    )
    result.result_sha256 = digest(result.model_dump(mode="json", exclude={"result_sha256"}))
    return result
