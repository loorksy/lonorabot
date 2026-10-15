"""Source-time confirmation semantics are identical for live and delayed replay."""

import json
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Any

import pytest
from lonora_contracts.market import Candle, Quote
from lonora_contracts.market_intelligence import DetectorDefinition
from lonora_contracts.market_watch import Watch
from lonora_market.detectors import evaluate_detector
from lonora_market.watch_lifecycle import advance_watch
from lonora_market.watchers import source_observation_time

NOW = datetime(2026, 10, 15, 12, tzinfo=UTC)


def config(**kwargs: object) -> Watch:
    return Watch.model_validate(
        dict(
            kind="dynamic",
            account_id="demo",
            symbol="EURUSDm",
            prompt="Inspect",
            detector={"id": "level", "kind": "level", "level": "100"},
            confirmation_ttl_seconds=10,
            **kwargs,
        )
    )


def advance(
    at: datetime, processing_at: datetime, state: dict[str, Any] | None = None, **kwargs: object
):
    return advance_watch(
        config(**kwargs),
        state or {},
        matched=True,
        observation_id=at.isoformat(),
        observed_at=at,
        now=processing_at,
    )


def test_delayed_quote_uses_source_time_not_worker_time() -> None:
    quote = Quote(
        symbol="EURUSDm", bid=Decimal(101), ask=Decimal(102), observed_at=NOW, source="broker"
    )
    detector = config().detector
    assert detector
    observation = evaluate_detector(
        detector,
        symbol=quote.symbol,
        timeframe="1m",
        quote=quote,
        candles=[],
        observed_at=NOW + timedelta(seconds=8),
    )
    at = source_observation_time(config(), {"observation": observation.model_dump(mode="json")})
    state, actionable = advance(at, NOW + timedelta(seconds=8))
    assert actionable
    assert state["confirmation_valid_until"] == (NOW + timedelta(seconds=10)).isoformat()
    expired, actionable = advance(at, NOW + timedelta(seconds=11))
    assert not actionable and expired["lifecycle"] == "expired"


def test_delayed_closed_candle_uses_actual_close_boundary() -> None:
    detector = DetectorDefinition(id="doji", kind="candle", pattern="doji")
    bar = Candle(
        symbol="EURUSDm",
        timeframe="1m",
        time=NOW - timedelta(minutes=1),
        open=Decimal(100),
        high=Decimal(102),
        low=Decimal(98),
        close=Decimal(100),
    )
    evidence = evaluate_detector(
        detector,
        symbol=bar.symbol,
        timeframe=bar.timeframe,
        quote=None,
        candles=[bar],
        observed_at=NOW + timedelta(seconds=8),
    )
    assert evidence.state == "confirmed" and evidence.observed_at == NOW
    assert evidence.values["close_time"] == NOW.isoformat()
    expired, actionable = advance(evidence.observed_at, NOW + timedelta(seconds=11))
    assert expired["lifecycle"] == "expired" and not actionable


@pytest.mark.parametrize("delay", [0, 3, 9])
def test_restart_and_delayed_replay_preserve_expiry(delay: int) -> None:
    live, _ = advance(NOW, NOW)
    replay, _ = advance(NOW, NOW + timedelta(seconds=delay))
    assert live["confirmation_valid_until"] == replay["confirmation_valid_until"]
    restored = json.loads(json.dumps(replay))
    state, actionable = advance(NOW + timedelta(seconds=11), NOW + timedelta(seconds=11), restored)
    assert state["lifecycle"] == "expired" and not actionable
    assert state["confirmation_valid_until"] == live["confirmation_valid_until"]


def test_repolling_same_evidence_does_not_satisfy_debounce() -> None:
    state, actionable = advance(NOW, NOW, debounce_seconds=5)
    assert state["lifecycle"] == "forming" and not actionable
    state, actionable = advance(NOW, NOW + timedelta(seconds=8), state, debounce_seconds=5)
    assert state["lifecycle"] == "forming" and not actionable
    state, actionable = advance(
        NOW + timedelta(seconds=5), NOW + timedelta(seconds=8), state, debounce_seconds=5
    )
    assert actionable and state["candidate_since"] == NOW.isoformat()
    assert state["confirmation_valid_until"] == (NOW + timedelta(seconds=15)).isoformat()


def test_older_or_future_evidence_cannot_replace_current_confirmation() -> None:
    state, _ = advance(NOW, NOW)
    for source in [NOW - timedelta(seconds=1), NOW + timedelta(seconds=5)]:
        result, actionable = advance(source, NOW + timedelta(seconds=1), state)
        assert result == state and not actionable


def test_composite_old_required_evidence_is_not_renewed_by_fresh_quote() -> None:
    detector = DetectorDefinition.model_validate(
        {
            "id": "both",
            "kind": "all",
            "children": [
                {"id": "price", "kind": "level", "level": "99"},
                {"id": "candle", "kind": "candle", "pattern": "doji"},
            ],
        }
    )
    quote = Quote(
        symbol="EURUSDm",
        bid=Decimal(101),
        ask=Decimal(102),
        observed_at=NOW + timedelta(seconds=20),
        source="broker",
    )
    bar = Candle(
        symbol=quote.symbol,
        timeframe="1m",
        time=NOW - timedelta(minutes=1),
        open=Decimal(100),
        high=Decimal(102),
        low=Decimal(98),
        close=Decimal(100),
    )
    evidence = evaluate_detector(
        detector,
        symbol=quote.symbol,
        timeframe="1m",
        quote=quote,
        candles=[bar],
        observed_at=quote.observed_at,
    )
    assert evidence.state == "confirmed" and evidence.observed_at == NOW
    expired, actionable = advance(evidence.observed_at, quote.observed_at)
    assert expired["lifecycle"] == "expired" and not actionable


def test_corrected_same_bar_can_confirm_without_refreshing_its_source_time() -> None:
    configuration = config()
    state, _ = advance_watch(
        configuration, {}, matched=False, observation_id="bar-before", observed_at=NOW, now=NOW
    )
    state, actionable = advance_watch(
        configuration,
        state,
        matched=True,
        observation_id="bar-corrected",
        observed_at=NOW,
        now=NOW + timedelta(seconds=8),
    )
    assert actionable
    assert state["confirmation_valid_until"] == (NOW + timedelta(seconds=10)).isoformat()
    state, actionable = advance_watch(
        configuration,
        state,
        matched=True,
        observation_id="bar-corrected",
        observed_at=NOW,
        now=NOW + timedelta(seconds=11),
    )
    assert not actionable and state["lifecycle"] == "expired"
