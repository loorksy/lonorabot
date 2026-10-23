"""Read-only sizing from current, exact-account broker economics.

The estimate models execution at the requested stop, not a maximum possible loss.
It neither authorizes execution nor estimates margin or unobserved trading costs.
"""

import asyncio
from datetime import datetime
from decimal import ROUND_CEILING, ROUND_FLOOR, Decimal, localcontext

from lonora_adapter_kit.broker import BrokerStateReader
from lonora_contracts.account import AccountState
from lonora_contracts.domain import utcnow
from lonora_contracts.market import Instrument, Quote
from lonora_contracts.position_sizing import PositionSizingRequest, PositionSizingResult
from lonora_contracts.trading import TradeRequest
from lonora_core.trading_run_market import require_exact_symbol
from lonora_core.user_error import LonoraError
from lonora_market.health import assess_account, assess_quote, require_healthy
from lonora_security.financial import validate_trade


def calculate_position_size(
    request: PositionSizingRequest,
    account: AccountState,
    instrument: Instrument,
    quote: Quote,
    *,
    observed_at: datetime | None = None,
) -> PositionSizingResult:
    now = observed_at or utcnow()
    if account.id != request.account_id:
        raise LonoraError("position_sizing_account_mismatch", 409)
    if not account.currency.strip() or request.currency != account.currency:
        raise LonoraError("position_sizing_currency_mismatch", 409)
    require_exact_symbol(request.symbol, instrument.symbol)
    require_exact_symbol(request.symbol, quote.symbol)
    require_healthy(
        assess_account(account, account_id=request.account_id, now=now, maximum_age_seconds=60)
    )
    require_healthy(
        assess_quote(
            quote,
            account_id=request.account_id,
            symbol=request.symbol,
            now=now,
            maximum_age_seconds=60,
        )
    )
    loss_value = quote.loss_tick_value
    if (
        quote.tick_value_basis != "account_currency_per_lot"
        or loss_value is None
        or not loss_value.is_finite()
        or loss_value <= 0
    ):
        raise LonoraError("position_sizing_economics_unavailable", 409)
    values = (
        request.risk_budget,
        request.stop_loss,
        instrument.tick_size,
        instrument.volume_min,
        instrument.volume_max,
        instrument.volume_step,
        quote.bid,
        quote.ask,
        loss_value,
    )
    if instrument.point_size is not None:
        values = (*values, instrument.point_size)
    if any(not value.is_finite() or value <= 0 for value in values):
        raise LonoraError("position_sizing_values_invalid", 409)
    if instrument.volume_max < instrument.volume_min:
        raise LonoraError("position_sizing_instrument_invalid", 409)
    # Include the full decimal exponent range so subtracting a small spread from
    # a large nominal price cannot silently lose significant broker digits.
    precision = max(
        64,
        sum(len(value.as_tuple().digits) for value in values)
        + max(value.adjusted() for value in values)
        - min(value.adjusted() for value in values)
        + 32,
    )
    if precision > 512 or any(abs(value.adjusted()) > 128 for value in values):
        raise LonoraError("position_sizing_numeric_precision", 409)
    with localcontext() as context:
        context.prec = precision
        entry = quote.ask if request.side == "buy" else quote.bid
        stop_reference = quote.bid if request.side == "buy" else quote.ask
        if (
            request.stop_loss >= stop_reference
            if request.side == "buy"
            else request.stop_loss <= stop_reference
        ):
            raise LonoraError("stop_loss_wrong_side", 409)
        point = instrument.point_size or Decimal(10) ** -instrument.digits
        if abs(stop_reference - request.stop_loss) < instrument.stops_level * point:
            raise LonoraError("stop_loss_stops_level", 409)
        # The spread is already included in entry-to-stop distance. Tick values
        # are broker-account money per lot, not contract size or profit currency.
        ticks = (abs(entry - request.stop_loss) / instrument.tick_size).to_integral_value(
            rounding=ROUND_CEILING
        )
        per_lot = ticks * loss_value
        if per_lot * instrument.volume_min > request.risk_budget:
            raise LonoraError("position_sizing_below_minimum", 409)
        capacity = min(request.risk_budget / per_lot, instrument.volume_max)
        steps = ((capacity - instrument.volume_min) / instrument.volume_step).to_integral_value(
            rounding=ROUND_FLOOR
        )
        volume = instrument.volume_min + steps * instrument.volume_step
        modeled_loss = per_lot * volume
        # Defend the budget boundary even if a non-terminating division rounded
        # capacity upwards at a lattice boundary.
        if modeled_loss > request.risk_budget:
            volume -= instrument.volume_step
            modeled_loss = per_lot * volume
        if volume < instrument.volume_min or modeled_loss > request.risk_budget:
            raise LonoraError("position_sizing_below_minimum", 409)
        validate_trade(
            TradeRequest(
                account_id=request.account_id,
                symbol=request.symbol,
                action=request.side,
                volume=volume,
                stop_loss=request.stop_loss,
            ),
            instrument,
        )
        return PositionSizingResult(
            account_id=account.id,
            currency=account.currency,
            symbol=request.symbol,
            side=request.side,
            risk_budget=request.risk_budget,
            entry=entry,
            stop_loss=request.stop_loss,
            volume=volume,
            modeled_stop_loss=modeled_loss,
            per_lot_stop_loss=per_lot,
            tick_size=instrument.tick_size,
            loss_tick_value=loss_value,
            quote_at=quote.observed_at,
            account_at=account.observed_at,
            observed_at=now,
            source=quote.source,
            instrument=instrument,
        )


async def position_size(
    broker: BrokerStateReader, request: PositionSizingRequest
) -> PositionSizingResult:
    """Read through one owner-scoped adapter; never rewrite a broker account ID."""
    # Resolve the contract first: an unknown symbol must not race a missing-quote
    # failure and leave callers with different errors on otherwise identical reads.
    instrument = await broker.instrument(request.symbol)
    require_exact_symbol(request.symbol, instrument.symbol)
    account, quote = await asyncio.gather(broker.account(), broker.quote(request.symbol))
    return calculate_position_size(request, account, instrument, quote)
