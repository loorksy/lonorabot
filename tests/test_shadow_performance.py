import json
from typing import Any

from lonora_trading.performance import quality_summary


def record(identifier: str, price_return: str, analysis: str) -> dict[str, Any]:
    return {
        "id": identifier,
        "price_return_fraction": price_return,
        "quality": {
            "analysis": {"state": analysis, "full_evidence": "large" * 10000},
            "entry": {"state": "late_confirmation"},
            "management": {"state": "planned_invalidation"},
            "execution": {"state": "virtual_fill", "live_slippage": None},
        },
        "gate_codes": ["late_confirmation", "late_confirmation"],
    }


def test_return_never_substitutes_for_quality_or_grants_authority():
    summary = quality_summary(
        [record("winner", "0.05", "contradicted"), record("loser", "-0.02", "validly_invalidated")],
        mode="shadow",
    )
    assert summary["positive_price_return_count"] == 1
    assert summary["quality_dimensions"]["analysis"]["state_counts"] == {
        "contradicted": 1,
        "validly_invalidated": 1,
    }
    assert summary["sample_state"] == "insufficient_data"
    assert summary["monetary_pnl"] is None
    assert not summary["safety_policy_changed"] and not summary["live_authority_granted"]


def test_repeated_patterns_require_sample_and_never_duplicate_one_record():
    rows = [record(str(i), "0.01", "source_evidence_available") for i in range(20)]
    assert (
        quality_summary(rows[:19], mode="shadow", minimum_sample=5)["repeated_gate_failures"] == []
    )
    summary = quality_summary(rows, mode="shadow")
    assert summary["repeated_gate_failures"] == [{"code": "late_confirmation", "count": 20}]
    assert (
        quality_summary(rows, mode="shadow", minimum_sample=30)["sample_state"]
        == "insufficient_data"
    )


def test_projection_is_bounded_without_embedding_immutable_evidence():
    rows = [record(str(i), "-0.01", f"state_{i}") for i in range(1000)]
    summary = quality_summary(rows, mode="shadow")
    analysis = summary["quality_dimensions"]["analysis"]
    assert len(analysis["examples"]) == 3 and len(analysis["state_counts"]) == 16
    assert analysis["other_state_count"] == 984
    assert len(json.dumps(summary)) < 6000
