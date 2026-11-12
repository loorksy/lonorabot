"""Deterministic final execution gate. Policies are loaded from owner settings only."""

from decimal import Decimal
from typing import Any

from lonora_contracts.domain import utcnow
from lonora_contracts.execution_quality import ExecutionPolicy, ExecutionQuality, ExecutionSnapshot
from lonora_contracts.market import Quote
from lonora_contracts.trading import TradeRequest, TradeResult
from lonora_db.client import Database
from lonora_db.transactions import SettingsRepository, execution_policy_key
from lonora_market.health import assess_account, assess_quote

from .exposure import account_exposure


def policy_key(owner_id: str, account_id: str) -> str:
    return execution_policy_key(owner_id, account_id)


async def execution_policy(db: Database, owner_id: str, account_id: str) -> ExecutionPolicy:
    async with db.sessions() as session:
        payload = await SettingsRepository().get(session, policy_key(owner_id, account_id))
    return ExecutionPolicy.model_validate(payload)


def evaluate_execution(
    request: TradeRequest,
    snapshot: ExecutionSnapshot,
    policy: ExecutionPolicy,
    *,
    planned_quote: Quote | None = None,
) -> ExecutionQuality:
    reasons: list[str] = []
    account_health = assess_account(
        snapshot.account,
        account_id=request.account_id,
        now=snapshot.observed_at,
        maximum_age_seconds=policy.account_max_age_seconds,
    )
    health = [account_health]
    if account_health.state != "healthy":
        reasons.append(account_health.reason_code)
    quote = snapshot.quote
    spread = quote.ask - quote.bid if quote else None
    if quote:
        quote_health = assess_quote(
            quote,
            account_id=request.account_id,
            symbol=request.symbol,
            now=snapshot.observed_at,
            maximum_age_seconds=policy.quote_max_age_seconds,
        )
        health.append(quote_health)
        if quote_health.state != "healthy":
            reasons.append(quote_health.reason_code)
    planned_price = None
    drift = None
    if quote and planned_quote and request.action in {"buy", "sell"}:
        if planned_quote.symbol != request.symbol:
            reasons.append("planned_symbol_mismatch")
        planned_price = planned_quote.ask if request.action == "buy" else planned_quote.bid
        submission_price = quote.ask if request.action == "buy" else quote.bid
        drift = (submission_price - planned_price) * (1 if request.action == "buy" else -1)
    return ExecutionQuality(
        state="blocked" if reasons else "executable",
        health=health,
        reasons=reasons,
        planned_price=planned_price,
        adverse_price_drift=drift,
        observed_at=snapshot.observed_at,
        spread=spread,
        exposure=account_exposure(snapshot),
        quote_observed_at=quote.observed_at if quote else None,
        submission_price=(
            quote.ask
            if request.action == "buy"
            else quote.bid
            if request.action == "sell"
            else None
        )
        if quote
        else None,
    )


def actual_execution(
    request: TradeRequest, result: TradeResult, quality: ExecutionQuality | None
) -> dict[str, Any]:
    evidence: dict[str, Any] = {"response_received_at": utcnow().isoformat()}
    if quality:
        evidence.update(quality.model_dump(mode="json"))
    # Only broker-supplied fill fields; a pending order price is not an actual fill.
    if result.status == "confirmed" and request.action in {"buy", "sell"}:
        raw = result.details.get("price")
        try:
            fill = Decimal(str(raw)) if raw is not None else None
        except ArithmeticError:
            fill = None
        if fill is not None and fill.is_finite() and fill > 0:
            evidence["actual_fill_price"] = str(fill)
            if quality and quality.submission_price is not None:
                slippage = fill - quality.submission_price
                evidence["adverse_slippage"] = str(
                    slippage if request.action == "buy" else -slippage
                )
                evidence["slippage_unit"] = "price"
        if result.details.get("volume") is not None:
            evidence["broker_reported_volume"] = result.details["volume"]
    return evidence
