"""Read-side market evidence for the model's own analysis; never signals or orders."""

import asyncio
import logging
import re
from datetime import datetime, timedelta
from typing import Any

from lonora_adapter_kit.broker import TradingHoursReader
from lonora_contracts.domain import Contract, utcnow
from lonora_contracts.market import Candle, Quote
from lonora_core.chart_controller import validate_timeframe
from lonora_core.user_error import LonoraError
from lonora_market.broker import broker_market
from lonora_market.candles import CSV_COLUMNS, candles_csv
from lonora_market.economic_calendar import configured_sources, read_calendar, select_events
from lonora_market.health import assess_candles, timeframe_age_seconds
from lonora_market.sessions import broker_trading_state, session_clock
from lonora_market.snapshot import TimeframeInput, market_snapshot
from lonora_market.watch_lifecycle import candle_close_time
from pydantic import Field, model_validator

from .base import Tool, eager_for
from .context import ToolContext
from .market import CandlesInput, QuoteInput
from .symbols import canonical_broker_symbol
from .workspace import access, workspace_available

READ_TIMEOUT_SECONDS = 20
DEFAULT_TIMEFRAMES = ["15m", "1h", "4h", "1d"]
# Errors the model corrects by changing its arguments.
SYMBOL_ARGUMENT_ERRORS = frozenset({"symbol_not_found", "symbol_ambiguous"})

logger = logging.getLogger(__name__)


def _aware(value: datetime | None) -> bool:
    return value is None or (value.tzinfo is not None and value.utcoffset() is not None)


class SnapshotInput(QuoteInput):
    timeframes: list[str] = Field(
        default=DEFAULT_TIMEFRAMES,
        min_length=1,
        max_length=6,
        description="Exact broker timeframes such as 15m, 1h, 4h, 1d; not M15/H1.",
    )
    bars: int = Field(default=200, ge=50, le=1000, description="Bars read per timeframe.")
    swing_bars: int = Field(default=2, ge=1, le=10)
    trend_bars: int = Field(default=20, ge=5, le=200)
    atr_period: int = Field(default=14, ge=2, le=100)
    rsi_period: int = Field(default=14, ge=2, le=100)


class SessionsInput(Contract):
    account_id: str | None = Field(
        default=None, description="Optional connection_id; with symbol, adds broker hours."
    )
    symbol: str | None = None
    at: datetime | None = Field(
        default=None, description="Optional timezone-aware instant within 31 days; default now."
    )

    @model_validator(mode="after")
    def check(self) -> "SessionsInput":
        if not _aware(self.at):
            raise ValueError("market_session_timestamp_invalid")
        if bool(self.symbol) and not self.account_id:
            raise ValueError("market_session_symbol_requires_account")
        return self


class CalendarReadInput(Contract):
    currencies: list[str] = Field(
        default_factory=list[str],
        max_length=20,
        description="Currency codes such as USD, EUR; empty means all.",
    )
    impacts: list[str] = Field(
        default_factory=list[str],
        max_length=6,
        description="Source impact labels such as high or medium; empty means all.",
    )
    hours_back: int = Field(default=12, ge=0, le=168)
    hours_ahead: int = Field(default=48, ge=0, le=336)
    limit: int = Field(default=40, ge=1, le=200)


class CandlesWorkspaceInput(CandlesInput):
    revision: int = Field(ge=0, description="Current workspace revision from workspace_inspect.")
    path: str | None = Field(
        default=None,
        max_length=256,
        pattern=r"^[A-Za-z0-9_.\-/]+\.csv$",
        description="Workspace CSV path; default market/<symbol>_<timeframe>.csv.",
    )
    start: datetime | None = Field(default=None, description="Optional aware lower bar time.")
    end: datetime | None = Field(default=None, description="Optional aware upper bar time.")
    include_forming: bool = Field(
        default=False, description="Also write the unfinished bar, marked closed=0."
    )

    @model_validator(mode="after")
    def check_range(self) -> "CandlesWorkspaceInput":
        if not _aware(self.start) or not _aware(self.end):
            raise ValueError("invalid_candle_range")
        if self.start and self.end and self.end < self.start:
            raise ValueError("invalid_candle_range")
        return self


async def _bars(
    context: ToolContext, account_id: str, symbol: str, timeframe: str, limit: int
) -> TimeframeInput:
    provider = await broker_market(context.brokers, context.owner_id, account_id)
    try:
        async with asyncio.timeout(READ_TIMEOUT_SECONDS):
            return await provider.candles(symbol, timeframe, limit)
    except LonoraError as error:
        return error.code
    except TimeoutError:
        return "market_history_timeout"


async def _quote(context: ToolContext, account_id: str, symbol: str) -> Quote | str:
    provider = await broker_market(context.brokers, context.owner_id, account_id)
    try:
        async with asyncio.timeout(READ_TIMEOUT_SECONDS):
            return await provider.quote(symbol)
    except LonoraError as error:
        return error.code
    except TimeoutError:
        return "market_quote_timeout"


async def snapshot(context: ToolContext, args: dict[str, Any]) -> dict[str, Any]:
    params = SnapshotInput.model_validate(args)
    timeframes = list(dict.fromkeys(validate_timeframe(item) for item in params.timeframes))
    broker = await context.brokers.get(context.owner_id, params.account_id)
    symbol = await canonical_broker_symbol(broker, params.symbol, require_exists=True)
    instrument = await broker.instrument(symbol)
    daily_limit = max(params.atr_period + 5, 10)
    # Only a bar closed before the read began counts as closed.
    requested_at = utcnow()
    extra = [] if "1d" in timeframes else ["1d"]
    quote, bars = await asyncio.gather(
        _quote(context, params.account_id, symbol),
        asyncio.gather(
            *(
                _bars(
                    context,
                    params.account_id,
                    symbol,
                    timeframe,
                    params.bars if timeframe in timeframes else daily_limit,
                )
                for timeframe in [*timeframes, *extra]
            ),
            _bars(context, params.account_id, symbol, "1w", 3),
        ),
    )
    series = dict(zip([*timeframes, *extra], bars[:-1], strict=True))
    daily, weekly = series["1d"], bars[-1]
    if extra:
        series.pop("1d")
    return market_snapshot(
        account_id=params.account_id,
        symbol=symbol,
        now=utcnow(),
        bars_read_at=requested_at,
        digits=instrument.digits,
        tick_size=instrument.tick_size,
        quote=quote,
        timeframes=series,
        daily=daily,
        weekly=weekly,
        swing_bars=params.swing_bars,
        trend_bars=params.trend_bars,
        atr_period=params.atr_period,
        rsi_period=params.rsi_period,
    )


async def sessions(context: ToolContext, args: dict[str, Any]) -> dict[str, Any]:
    params = SessionsInput.model_validate(args)
    now = utcnow()
    at = params.at or now
    if abs(at - now) > timedelta(days=31):
        raise LonoraError("market_session_timestamp_out_of_range", 422)
    result = session_clock(at)
    if not params.account_id or not params.symbol:
        result["broker_trading_hours"] = {
            "state": "unknown",
            "reason": "no_instrument_requested",
        }
        return result
    result["broker_trading_hours"] = await _broker_hours(
        context, params.account_id, params.symbol, at
    )
    return result


async def _broker_hours(
    context: ToolContext, account_id: str, requested: str, at: datetime
) -> dict[str, Any]:
    """Broker hours, or unknown with a reason: the session clock never needs the broker.

    Only a symbol the model can correct is an error; an unreachable, disabled or
    failing broker (exactly when the clock matters most) leaves the hours unknown.
    """
    symbol = requested
    try:
        async with asyncio.timeout(READ_TIMEOUT_SECONDS):
            broker = await context.brokers.get(context.owner_id, account_id)
            symbol = await canonical_broker_symbol(broker, requested, require_exists=True)
            if not isinstance(broker, TradingHoursReader):
                return {"symbol": symbol, "state": "unknown", "reason": "broker_hours_not_exposed"}
            return broker_trading_state(await broker.trading_hours(symbol), at)
    except LonoraError as error:
        if error.code in SYMBOL_ARGUMENT_ERRORS:
            raise
        reason = error.code
    except TimeoutError:
        reason = "broker_hours_timeout"
    except ConnectionError:
        reason = "broker_connection_failure"
    except Exception as error:
        # Broker SDK exception text can carry credentials; only the type is logged.
        logger.warning("market_sessions_broker_hours_failed type=%s", type(error).__name__)
        reason = "broker_hours_failed"
    return {"symbol": symbol, "state": "unknown", "reason": reason}


async def calendar_available(context: ToolContext) -> str | None:
    """Presentation only: the handler still answers configured=false on its own."""
    if await configured_sources(context.db, context.owner_id):
        return None
    return "economic_calendar_not_configured"


async def calendar(context: ToolContext, args: dict[str, Any]) -> dict[str, Any]:
    params = CalendarReadInput.model_validate(args)
    sources, events = await read_calendar(context.db, context.owner_id)
    now = utcnow()
    window = {
        "from": (now - timedelta(hours=params.hours_back)).isoformat(),
        "to": (now + timedelta(hours=params.hours_ahead)).isoformat(),
    }
    if not sources:
        return {
            "configured": False,
            "reason": "economic_calendar_not_configured",
            "observed_at": now.isoformat(),
            "window": window,
            "sources": [],
            "events": [],
            "guidance": "No enabled economic calendar integration exists. Calendar evidence is "
            "unavailable; do not infer scheduled events. The owner can add one in Integrations.",
        }
    page, total = select_events(
        events,
        now=now,
        hours_back=params.hours_back,
        hours_ahead=params.hours_ahead,
        currencies={item.strip().upper() for item in params.currencies if item.strip()},
        impacts={item.strip().casefold() for item in params.impacts if item.strip()},
        limit=params.limit,
    )
    readable = any(item["status"] == "ok" for item in sources)
    return {
        "configured": True,
        "reason": None if readable else "calendar_source_unavailable",
        "observed_at": now.isoformat(),
        "window": window,
        "sources": sources,
        "events": page,
        "total_matches": total,
        "truncated": total > len(page),
    }


def _default_path(symbol: str, timeframe: str) -> str:
    return "market/" + re.sub(r"[^A-Za-z0-9_.-]", "_", symbol).strip(".") + "_" + timeframe + ".csv"


async def candles_to_workspace(context: ToolContext, args: dict[str, Any]) -> dict[str, Any]:
    params = CandlesWorkspaceInput.model_validate(args)
    timeframe = validate_timeframe(params.timeframe)
    workspace = access(context)
    # The receipt identity is the request as made, so an interrupted call replays its
    # recorded write without needing the broker again.
    path = params.path or _default_path(params.symbol, timeframe)
    intent = {
        "account_id": params.account_id,
        "symbol": params.symbol,
        "timeframe": timeframe,
        "limit": params.limit,
        "start": params.start.isoformat() if params.start else None,
        "end": params.end.isoformat() if params.end else None,
        "include_forming": params.include_forming,
    }

    async def produce() -> tuple[bytes, dict[str, Any]]:
        broker = await context.brokers.get(context.owner_id, params.account_id)
        symbol = await canonical_broker_symbol(broker, params.symbol, require_exists=True)
        requested_at = utcnow()
        provider = await broker_market(context.brokers, context.owner_id, params.account_id)
        try:
            async with asyncio.timeout(READ_TIMEOUT_SECONDS):
                series = await provider.candles(symbol, timeframe, params.limit)
        except TimeoutError:
            raise LonoraError("market_history_timeout", 504) from None
        health = assess_candles(
            series,
            account_id=params.account_id,
            symbol=symbol,
            timeframe=timeframe,
            now=utcnow(),
            maximum_age_seconds=timeframe_age_seconds(timeframe),
        )
        if health.state in {"degraded", "unavailable"}:
            raise LonoraError(health.reason_code, 409)
        rows: list[Candle] = []
        flags: list[bool] = []
        close_times: list[str] = []
        for bar in series:
            closes_at = candle_close_time(bar.time, timeframe)
            closed = closes_at <= requested_at
            if (
                (not closed and not params.include_forming)
                or (params.start and bar.time < params.start)
                or (params.end and bar.time > params.end)
            ):
                continue
            rows.append(bar)
            flags.append(closed)
            close_times.append(closes_at.isoformat())
        if not rows:
            raise LonoraError("market_candles_window_empty", 409)
        return candles_csv(rows, flags, close_times), {
            "symbol": symbol,
            "timeframe": timeframe,
            "rows": len(rows),
            "closed_rows": sum(flags),
            "forming_rows": len(flags) - sum(flags),
            "first_bar_at": rows[0].time.isoformat(),
            "last_bar_at": rows[-1].time.isoformat(),
            "freshness": health.state,
            "columns": list(CSV_COLUMNS),
            "read_hint": "pandas.read_csv(path, parse_dates=['time', 'close_time'])",
        }

    return await workspace.write_generated(context, params.revision, path, intent, produce)


def tools() -> list[Tool]:
    return [
        Tool(
            "market_snapshot",
            "One compact multi-timeframe summary for an exact broker symbol: bid/ask/spread and "
            "freshness; per timeframe closed-bar trend slope, swing structure, range, ATR with "
            "percentile volatility regime and RSI; previous day/week high-low with distances in "
            "price and daily ATR. Forming bars are excluded and reported separately. Numbers "
            "and labels are evidence, not signals; no execution authority.",
            SnapshotInput,
            snapshot,
            True,
            # One call replaces a quote read plus a candle read per timeframe for
            # the first look at a market, so it travels natively with trading Runs.
            eager=eager_for("market"),
        ),
        Tool(
            "market_sessions",
            "DST-correct Sydney/Tokyo/London/New York session clock from IANA zones: active "
            "sessions and overlaps, time to next open/close, FX weekend closure; with account_id "
            "and symbol, the broker's own trading hours when the adapter reports them, otherwise "
            "unknown. Conventional hours ignore holidays.",
            SessionsInput,
            sessions,
            True,
            # Session-scoped work ("during today's London session") needs the
            # DST-correct clock rather than hours recomputed by the model.
            eager=eager_for("market"),
        ),
        Tool(
            "economic_calendar_read",
            "Read recent and upcoming economic calendar events from the owner's configured "
            "calendar sources, filtered by currencies, impact and hours window. Returns "
            "configured=false when no source exists; events are only what sources report.",
            CalendarReadInput,
            calendar,
            True,
            # Research Agents (news and event monitoring) receive it natively, but
            # only when the owner configured a calendar source.
            eager=eager_for("research"),
            availability=calendar_available,
        ),
        Tool(
            "market_candles_to_workspace",
            "Write broker candles for one exact symbol/timeframe into this Agent's analytical "
            "workspace as CSV at the given revision, without passing bars through the "
            "conversation. Returns only path, rows, time range and the new revision for "
            "workspace_execute. Closed bars only unless include_forming. Quotas apply.",
            CandlesWorkspaceInput,
            candles_to_workspace,
            replay_safe=True,
            availability=workspace_available,
        ),
    ]
