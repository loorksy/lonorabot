"""Market interpretation remains useful without pretending an entry is executable."""

import hashlib
from datetime import timedelta
from decimal import Decimal

import pytest
from lonora_contracts.account import AccountState
from lonora_contracts.domain import utcnow
from lonora_contracts.market import Candle, Quote
from lonora_contracts.market_intelligence import DetectorDefinition
from lonora_contracts.trading import TradingControl
from lonora_contracts.trading_decision import (
    DecisionEvidence,
    DecisionRequest,
    MarketViewRequest,
    TradingDecision,
)
from lonora_tools.trading_decision import fingerprint
from lonora_trading.decision_readiness import decision_readiness


def sample(symbol: str = "EURUSDm", timeframe: str = "15m"):
    now = utcnow()
    condition = DetectorDefinition(id="support-break", kind="level", level=Decimal("99"))
    request = DecisionRequest(
        account_id="account",
        symbol=symbol,
        timeframe=timeframe,
        action="BUY",
        summary="The observed bid is above the explicit structural level; this is an interpretation.",
        market_view=MarketViewRequest(bias="BULLISH", supporting_condition=condition),
        entry_condition=condition,
    )
    evidence = DecisionEvidence(
        id="evidence",
        captured_at=now,
        quote=Quote(
            symbol=symbol,
            bid=Decimal("100"),
            ask=Decimal("101"),
            observed_at=now,
            source="scripted-broker",
        ),
        candles=[
            Candle(
                symbol=symbol,
                timeframe=timeframe,
                time=now - timedelta(minutes=2 - i),
                open=Decimal("99"),
                high=Decimal("102"),
                low=Decimal("98"),
                close=Decimal("100"),
            )
            for i in range(2)
        ],
        account=AccountState(
            id="account",
            balance=Decimal("10000"),
            equity=Decimal("10000"),
            margin=Decimal("0"),
            free_margin=Decimal("10000"),
            currency="USD",
            observed_at=now,
        ),
    )
    return request, evidence


def project(
    request: DecisionRequest, evidence: DecisionEvidence, *, connection_changed: bool = False
):
    return decision_readiness(
        request,
        evidence,
        controls=TradingControl(enabled=True),
        broker_enabled=True,
        broker_recovery_status="connected",
        connection_changed=connection_changed,
    )


@pytest.mark.parametrize(
    "symbol,timeframe",
    [("EURUSDm", "1m"), ("XAUUSDm", "15m"), ("US30.cash", "4h"), ("BTCUSD.pro", "1d")],
)
def test_supported_interpretation_uses_real_condition_and_never_authorizes(
    symbol: str, timeframe: str
):
    request, evidence = sample(symbol, timeframe)
    value = project(request, evidence)
    assert value.market_assessment.bias == "BULLISH"
    observation = value.market_assessment.supporting_observation
    assert observation and observation.symbol == symbol and observation.values["bid"] == "100"
    assert observation.detector_version == "1"
    assert value.market_assessment.confidence == "not_calibrated"
    assert value.entry_readiness.state == "CONFIRMED"
    assert value.execution_readiness.state == "REVALIDATION_REQUIRED"
    assert value.execution_readiness.execution_authorized is False
    assert "final_preflight_and_execution_quality" in value.execution_readiness.remaining_checks


@pytest.mark.parametrize(
    "missing",
    ["broker_orders_unavailable", "broker_positions_unavailable", "broker_account_unavailable"],
)
def test_irrelevant_account_reads_do_not_erase_a_grounded_market_bias(missing: str):
    request, evidence = sample()
    evidence.missing_codes = [missing]
    evidence.account = None
    value = project(request, evidence)
    assert value.market_assessment.bias == "BULLISH"
    assert value.entry_readiness.state == "CONFIRMED"
    assert value.execution_readiness.state == "BLOCKED"
    assert missing in value.execution_readiness.reason_codes


def test_reconciliation_cannot_erase_market_analysis_or_allow_execution():
    request, evidence = sample()
    value = decision_readiness(
        request,
        evidence,
        controls=TradingControl(enabled=True),
        broker_enabled=True,
        broker_recovery_status="reconciling",
    )
    assert value.market_assessment.bias == "BULLISH"
    assert value.entry_readiness.state == "CONFIRMED"
    assert value.execution_readiness.reason_codes == ["broker_reconciliation_required"]


@pytest.mark.parametrize(
    "problem",
    [
        "stale_quote",
        "missing_candles",
        "wrong_symbol",
        "wrong_timeframe",
        "future_candles",
        "duplicate_candles",
        "quote_only",
    ],
)
def test_bad_market_data_never_supports_direction_or_entry(problem: str):
    request, evidence = sample()
    assert evidence.quote
    if problem == "stale_quote":
        evidence.quote.observed_at -= timedelta(minutes=5)
    elif problem in {"missing_candles", "quote_only"}:
        evidence.candles = []
    elif problem == "wrong_symbol":
        evidence.quote.symbol = "OTHERm"
    elif problem == "wrong_timeframe":
        evidence.candles[0].timeframe = "1h"
    elif problem == "future_candles":
        evidence.candles[-1].time += timedelta(days=1)
    else:
        evidence.candles[-1].time = evidence.candles[0].time
    value = project(request, evidence)
    assert value.market_assessment.bias == "INSUFFICIENT_EVIDENCE"
    assert value.entry_readiness.state == "INSUFFICIENT_EVIDENCE"
    assert value.execution_readiness.state == "BLOCKED"


def test_requested_buy_and_available_prices_do_not_manufacture_market_assessment():
    request, evidence = sample()
    request.market_view = None
    request.entry_condition = None
    value = project(request, evidence)
    assert value.market_assessment.bias == "INSUFFICIENT_EVIDENCE"
    assert value.entry_readiness.reason_codes == ["entry_condition_required"]
    assert value.execution_readiness.state == "BLOCKED"


def test_unconfirmed_support_does_not_become_an_opinion():
    request, evidence = sample()
    assert request.market_view
    request.market_view.supporting_condition = DetectorDefinition(
        id="not-broken", kind="level", level=Decimal("105")
    )
    value = project(request, evidence)
    assert value.market_assessment.bias == "INSUFFICIENT_EVIDENCE"
    assert "market_supporting_condition_unconfirmed" in value.market_assessment.reason_codes


def test_directional_opinion_does_not_manufacture_entry_and_open_bar_is_not_closed_confirmation():
    request, evidence = sample()
    request.entry_condition = None
    value = project(request, evidence)
    assert (
        value.market_assessment.bias == "BULLISH" and value.entry_readiness.state == "NOT_CONFIRMED"
    )
    request.entry_condition = DetectorDefinition(id="doji", kind="candle", pattern="doji")
    evidence.candles[-1].open = evidence.candles[-1].close
    value = project(request, evidence)
    assert (
        value.entry_readiness.observation and value.entry_readiness.observation.state == "forming"
    )
    assert value.entry_readiness.state == "NOT_CONFIRMED"


def test_controls_and_changed_connection_stay_authoritative():
    request, evidence = sample()
    value = decision_readiness(
        request,
        evidence,
        controls=TradingControl(enabled=False, emergency_stop=True),
        broker_enabled=False,
        broker_recovery_status="connected",
    )
    assert value.market_assessment.bias == "BULLISH"
    assert {"emergency_stop", "trading_disabled", "broker_disabled"} <= set(
        value.execution_readiness.reason_codes
    )
    changed = project(request, evidence, connection_changed=True)
    assert changed.market_assessment.bias == "INSUFFICIENT_EVIDENCE"
    assert "broker_connection_changed" in changed.execution_readiness.reason_codes


def test_legacy_identity_and_record_remain_readable():
    request, evidence = sample()
    request.market_view = None
    request.entry_condition = None
    old_json = request.model_dump_json(
        exclude={"market_view", "entry_condition", "relationship_ids"}
    )
    assert fingerprint(request) == hashlib.sha256(old_json.encode()).hexdigest()
    old = TradingDecision(
        id="old",
        owner_id="owner",
        agent_id="agent",
        run_id="run",
        account_id=request.account_id,
        symbol=request.symbol,
        timeframe=request.timeframe,
        recorded_at=evidence.captured_at,
        requested_action="BUY",
        action="BUY",
        summary=request.summary,
        gate_codes=[],
        evidence=evidence,
    )
    serialized = old.model_dump(mode="json", exclude={"readiness"})
    assert TradingDecision.model_validate(serialized).readiness is None
