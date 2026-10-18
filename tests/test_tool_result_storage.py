"""Large observation summaries preserve evidence identity within a hard bound."""

import json

from lonora_adapter_kit.context import omitted_result
from lonora_agent.environment import bounded_result


def test_arbitrary_recovery_data_cannot_escape_summary_bound() -> None:
    result = bounded_result(
        {
            "ok": True,
            "operation_id": "operation-1",
            "recovery": {"category": "ambiguous_mutation", "extra": "x" * 500000},
        }
    )
    assert len(json.dumps(result)) < 2048
    assert result["status"] == "ambiguous"
    assert result["recovery"] == {
        "category": "ambiguous_mutation",
        "next_action": "reconcile_before_any_resend",
        "safe_to_retry": False,
    }


def test_context_omission_preserves_storage_receipt_and_failure_truth() -> None:
    for persisted in (False, True):
        result = json.loads(
            omitted_result(
                json.dumps(
                    {
                        "ok": True,
                        "status": "confirmed",
                        "operation_id": "operation-1",
                        "result_ref": "reference-1",
                        "result_persisted": persisted,
                        "result_read_tool": "artifact_read",
                        "result_format": "redacted_json",
                        "result_retention": "owner_managed",
                        "body": "x" * 500000,
                    }
                ),
                2048,
            )
        )
        assert result["ok"] and result["operation_id"] == "operation-1"
        assert result["result_ref"] == "reference-1" and result["result_persisted"] is persisted
        assert result["result_format"] == "redacted_json"
