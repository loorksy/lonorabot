"""Keep model judgment, optional detector observations and execution state separate.

This is a projection over captured evidence and existing server state, not a signal
generator, risk engine or execution gate. Submission still uses the executor's
current authorization, preflight, quality, journal and reconciliation checks.
"""

from lonora_contracts.market_intelligence import DetectorDefinition, Observation
from lonora_contracts.trading import TradingControl
from lonora_contracts.trading_decision import (
    DecisionEvidence,
    DecisionReadiness,
    DecisionRequest,
    EntryReadiness,
    ExecutionReadiness,
    MarketAssessment,
)
from lonora_market.detectors import detector_inputs, evaluate_detector
from lonora_market.health import assess_account, assess_candles, assess_quote, timeframe_age_seconds


def decision_readiness(
    request: DecisionRequest,
    evidence: DecisionEvidence,
    *,
    controls: TradingControl,
    broker_enabled: bool,
    broker_recovery_status: str | None,
    connection_changed: bool = False,
) -> DecisionReadiness:
    """Use source-time checks, never assume that cached health is still current."""
    now = evidence.captured_at
    quote = assess_quote(
        evidence.quote,
        account_id=request.account_id,
        symbol=request.symbol,
        now=now,
        maximum_age_seconds=30,
    )
    candles = assess_candles(
        evidence.candles,
        account_id=request.account_id,
        symbol=request.symbol,
        timeframe=request.timeframe,
        now=now,
        maximum_age_seconds=timeframe_age_seconds(request.timeframe),
    )
    account = assess_account(
        evidence.account, account_id=request.account_id, now=now, maximum_age_seconds=60
    )
    market_codes = [item.reason_code for item in (quote, candles) if not item.healthy]
    if len(evidence.candles) < 2:
        market_codes.append("decision_candles_insufficient")
    if connection_changed:
        market_codes.append("broker_connection_changed")
    # Explicitly requested related-market evidence is part of this interpretation;
    # unrelated account/position/order failures do not erase a valid market view.
    if "relationship_evidence_unreliable" in evidence.missing_codes:
        market_codes.append("relationship_evidence_unreliable")
    market_codes = list(dict.fromkeys(market_codes))
    assessment_codes = list(market_codes)
    supporting_observation = None
    supporting_codes: list[str] = []
    if not request.summary.strip():
        assessment_codes.append("market_rationale_required")
    if request.market_view is None:
        assessment_codes.append("market_interpretation_not_supplied")
    elif not assessment_codes and request.market_view.supporting_condition is not None:
        supporting_observation, supporting_codes = inspect_condition(
            request.market_view.supporting_condition, request, evidence
        )
    assessment = MarketAssessment(
        bias=request.market_view.bias
        if not assessment_codes and request.market_view
        else "INSUFFICIENT_EVIDENCE",
        reason_codes=assessment_codes,
        evidence_id=evidence.id,
        observed_at=now,
        quote_observed_at=evidence.quote.observed_at if evidence.quote else None,
        candle_observed_at=evidence.candles[-1].time if evidence.candles else None,
        supporting_observation=supporting_observation,
        supporting_reason_codes=supporting_codes,
        supporting_condition=request.market_view.supporting_condition
        if request.market_view
        else None,
    )

    observation = None
    observation_codes: list[str] = []
    if request.entry_condition is not None and not market_codes:
        observation, observation_codes = inspect_condition(
            request.entry_condition, request, evidence
        )
        if observation is not None and observation.state != "confirmed":
            observation_codes.append("entry_condition_unconfirmed")
    if assessment_codes:
        entry = EntryReadiness(state="INSUFFICIENT_EVIDENCE", reason_codes=assessment_codes)
    elif request.action == "CONDITIONAL_ENTRY":
        entry = EntryReadiness(
            state="AWAITING_REASSESSMENT", reason_codes=["conditional_reassessment_required"]
        )
    elif request.action == "WAIT":
        entry = EntryReadiness(state="NOT_CONFIRMED", reason_codes=["model_abstained"])
    else:
        # A detector can confirm its own measured condition. Its absence, false
        # result or forming state does not choose the model's action for it.
        entry = EntryReadiness(
            state="CONFIRMED"
            if observation is not None and observation.state == "confirmed"
            else "MODEL_SELECTED",
            reason_codes=observation_codes,
        )
    entry.condition, entry.observation = request.entry_condition, observation

    execution_codes = [item.reason_code for item in (quote, candles, account) if not item.healthy]
    execution_codes.extend(assessment_codes)
    execution_codes.extend(evidence.missing_codes)
    if not controls.enabled:
        execution_codes.append("trading_disabled")
    if controls.emergency_stop:
        execution_codes.append("emergency_stop")
    if not broker_enabled:
        execution_codes.append("broker_disabled")
    if broker_recovery_status is not None and broker_recovery_status != "connected":
        execution_codes.append("broker_reconciliation_required")
    if connection_changed:
        execution_codes.append("broker_connection_changed")
    if evidence.account and (
        evidence.account.trade_allowed is False or evidence.account.investor_mode is True
    ):
        execution_codes.append("broker_trading_not_allowed")
    if request.action == "CONDITIONAL_ENTRY":
        execution_codes.append("conditional_reassessment_required")
    elif entry.state not in {"CONFIRMED", "MODEL_SELECTED"}:
        execution_codes.append("entry_not_confirmed")
    return DecisionReadiness(
        market_assessment=assessment,
        entry_readiness=entry,
        execution_readiness=ExecutionReadiness(
            state="BLOCKED" if execution_codes else "REVALIDATION_REQUIRED",
            reason_codes=list(dict.fromkeys(execution_codes)),
            observed_at=now,
        ),
    )


def inspect_condition(
    condition: DetectorDefinition, request: DecisionRequest, evidence: DecisionEvidence
) -> tuple[Observation | None, list[str]]:
    """The existing detector owns condition semantics and observation provenance."""
    if "relationships" in detector_inputs(condition):
        return None, ["market_relationship_confirmation_unavailable"]
    return evaluate_detector(
        condition,
        symbol=request.symbol,
        timeframe=request.timeframe,
        quote=evidence.quote,
        candles=evidence.candles,
        observed_at=evidence.captured_at,
    ), []
