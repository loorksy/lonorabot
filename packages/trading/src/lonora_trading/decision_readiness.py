"""Separate a grounded market opinion from entry confirmation and financial authority.

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
    if not request.summary.strip():
        assessment_codes.append("market_rationale_required")
    if request.market_view is None:
        assessment_codes.append("market_interpretation_not_supplied")
    elif not assessment_codes:
        supporting_observation, reasons = inspect_condition(
            request.market_view.supporting_condition, request, evidence
        )
        assessment_codes.extend(reasons)
        if supporting_observation is not None and supporting_observation.state != "confirmed":
            assessment_codes.append("market_supporting_condition_unconfirmed")
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
        supporting_condition=request.market_view.supporting_condition
        if request.market_view
        else None,
    )

    entry = EntryReadiness(state="NOT_CONFIRMED", reason_codes=["entry_condition_required"])
    if request.entry_condition is not None:
        required = detector_inputs(request.entry_condition)
        unavailable = [
            value.reason_code
            for name, value in (("quote", quote), ("candles", candles))
            if name in required and not value.healthy
        ]
        # Relationship detectors require their own deterministic current snapshots;
        # this projection does not invent them or map an unrelated relationship ID.
        if "relationships" in required:
            unavailable.append("entry_relationship_confirmation_unavailable")
        if market_codes:
            unavailable.extend(market_codes)
        if unavailable:
            entry = EntryReadiness(
                state="INSUFFICIENT_EVIDENCE",
                reason_codes=list(dict.fromkeys(unavailable)),
                condition=request.entry_condition,
            )
        else:
            observation = evaluate_detector(
                request.entry_condition,
                symbol=request.symbol,
                timeframe=request.timeframe,
                quote=evidence.quote,
                candles=evidence.candles,
                observed_at=now,
            )
            confirmed = observation.state == "confirmed" and request.action != "WAIT"
            entry = EntryReadiness(
                state="CONFIRMED" if confirmed else "NOT_CONFIRMED",
                reason_codes=[]
                if confirmed
                else [
                    "entry_direction_required"
                    if request.action == "WAIT"
                    else "entry_condition_unconfirmed"
                ],
                observation=observation,
                condition=request.entry_condition,
            )

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
    if entry.state != "CONFIRMED":
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
