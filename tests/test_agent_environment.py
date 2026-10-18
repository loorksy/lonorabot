"""Operational recovery never changes effect authority or exposes submitted values."""

from typing import Any

import pytest
from lonora_adapter_kit.types import ToolCall
from lonora_agent.environment import (
    blocked_route,
    bounded_result,
    classify,
    environment_state,
    observe,
)
from lonora_contracts.domain import Contract
from lonora_contracts.tool_environment import ToolRecovery
from lonora_tools.base import Tool
from lonora_tools.context import ToolContext


async def handler(_: ToolContext, arguments: dict[str, Any]) -> dict[str, Any]:
    return arguments


@pytest.mark.parametrize(
    "code",
    [
        "broker_connection_timeout",
        "tool_read_timeout",
        "broker_candles_unavailable",
        "tool_connection_failure",
    ],
)
def test_only_server_declared_read_is_automatically_retried(code: str) -> None:
    for read_only in (False, True):
        tool = Tool("test", "Test", Contract, handler, read_only)
        assert classify(code, tool)["safe_to_retry"] == read_only
    assert not classify(code, None)["safe_to_retry"]


@pytest.mark.parametrize(
    "code,category",
    [
        ("tool_arguments_invalid", "invalid_tool_arguments"),
        ("version_conflict", "version_conflict"),
        ("chart_indicator_not_found", "not_found"),
        ("broker_result_ambiguous", "ambiguous_mutation"),
        ("trading_disabled", "health_blocked"),
        ("device_authorization_required", "authorization_required"),
        ("search_not_configured", "not_configured"),
        ("unrecognized_domain_code", "terminal_domain_failure"),
    ],
)
def test_recovery_contract_preserves_stable_categories(code: str, category: str) -> None:
    metadata = classify(code, Tool("read", "Test", Contract, handler, True))
    assert ToolRecovery.model_validate(metadata).category == category
    assert not metadata["safe_to_retry"]


def test_partial_legacy_environment_and_bounded_observation_state() -> None:
    state: dict[str, Any] = {"environment": {}}
    environment_state(state)
    for index in range(100):
        observe(
            state,
            ToolCall(id=str(index), name="read", arguments={"secret": str(index)}),
            None,
            {"ok": False, "code": "test_domain_error"},
        )
    assert len(state["environment"]["routes"]) == 32
    assert len(state["environment"]["recent"]) == 12
    assert "secret" not in str(state)


def test_batch_ambiguity_cannot_be_replayed_as_success() -> None:
    state: dict[str, Any] = {}
    call = ToolCall(id="first", name="financial", arguments={"volume": 1})
    tool = Tool("financial", "Test", Contract, handler, financial=True)
    result: dict[str, Any] = {
        "ok": True,
        "results": [
            {"operation_id": "one", "status": "confirmed"},
            {"operation_id": "two", "status": "ambiguous"},
        ],
    }
    observe(state, call, tool, result)
    assert not result["recovery"]["safe_to_retry"]
    assert blocked_route(state, call.model_copy(update={"id": "different"}))
    bounded = bounded_result(result)
    assert bounded["ok"] and bounded["results"][1]["status"] == "ambiguous"
    assert bounded["result_count"] == 2 and not bounded["results_truncated"]


def test_financial_tool_cannot_be_registered_as_safe_read() -> None:
    from lonora_core.user_error import LonoraError
    from lonora_tools.registry import ToolRegistry

    with pytest.raises(LonoraError, match="tool_effect_contract_invalid"):
        ToolRegistry(
            [
                Tool(
                    "bad-effect",
                    "Invalid server declaration",
                    Contract,
                    handler,
                    read_only=True,
                    financial=True,
                )
            ]
        )


def test_later_ambiguous_operation_does_not_reconcile_an_older_success() -> None:
    state: dict[str, Any] = {}
    tool = Tool("financial", "Test receipt", Contract, handler, financial=True, replay_safe=True)
    call = ToolCall(id="old-success", name="financial", arguments={"volume": 1})
    observe(state, call, tool, {"ok": True, "status": "confirmed"})
    later = call.model_copy(update={"id": "new-uncertain-operation"})
    observe(state, later, tool, {"ok": True, "status": "ambiguous"})
    blocked = blocked_route(state, later)
    assert blocked and blocked["origin_call_id"] == "new-uncertain-operation"
