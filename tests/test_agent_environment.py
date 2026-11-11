"""Operational recovery never changes effect authority or exposes submitted values."""

from typing import Any, get_args

import pytest
from lonora_adapter_kit.types import ToolCall
from lonora_agent.environment import (
    RECOVERY_HINTS,
    blocked_route,
    bounded_result,
    classify,
    environment_state,
    observe,
)
from lonora_contracts.domain import Contract
from lonora_contracts.tool_environment import FailureCategory, ToolRecovery
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
        "broker_rate_limited",
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
        ("research_provider_not_configured", "not_configured"),
        ("browser_unconfigured", "not_configured"),
        ("trading_restriction_active", "permission_denied"),
        ("agent_trading_symbol_mismatch", "permission_denied"),
        ("risk_trade_limit", "risk_limit_blocked"),
        ("unrecognized_domain_code", "terminal_domain_failure"),
    ],
)
def test_recovery_contract_preserves_stable_categories(code: str, category: str) -> None:
    metadata = classify(code, Tool("read", "Test", Contract, handler, True))
    assert ToolRecovery.model_validate(metadata).category == category
    assert not metadata["safe_to_retry"]


@pytest.mark.parametrize(
    "code,category,action",
    [
        # An owner restriction is a scope: never an invitation to try another route.
        ("trading_restriction_active", "permission_denied", "respect_scope"),
        ("restriction_all_mutations_requires_owner_message", "permission_denied", "respect_scope"),
        ("supervision_personal_agent", "permission_denied", "respect_scope"),
        ("supervision_revoke_own_oversight", "permission_denied", "respect_scope"),
        # Pausing a whole trading agent has a narrower route: restrict it, pause its work.
        ("supervision_pause_trading_agent", "terminal_domain_failure", "alternate_route"),
        # A monetary limit points at its evidence: resize within it or wait for the owner.
        ("risk_trade_limit", "risk_limit_blocked", "inspect_risk_assessment"),
        ("risk_stop_loss_required", "risk_limit_blocked", "inspect_risk_assessment"),
        ("risk_open_limit", "risk_limit_blocked", "inspect_risk_assessment"),
        ("risk_open_unbounded", "risk_limit_blocked", "inspect_risk_assessment"),
        ("risk_daily_loss_limit", "risk_limit_blocked", "inspect_risk_assessment"),
        ("risk_free_margin_floor", "risk_limit_blocked", "inspect_risk_assessment"),
        ("risk_limit_currency_mismatch", "risk_limit_blocked", "inspect_risk_assessment"),
        ("risk_economics_unavailable", "risk_limit_blocked", "inspect_risk_assessment"),
        ("risk_daily_history_incomplete", "risk_limit_blocked", "inspect_risk_assessment"),
    ],
)
def test_owner_restrictions_and_risk_limits_never_suggest_an_alternate_route(
    code: str, category: str, action: str
) -> None:
    tool = Tool("trade_execute", "Test", Contract, handler, financial=True)
    metadata = classify(code, tool)
    assert (metadata["category"], metadata["next_action"]) == (category, action)
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


def test_resolved_financial_outcome_is_settled_but_never_reported_as_confirmed() -> None:
    state: dict[str, Any] = {}
    tool = Tool("financial", "Test receipt", Contract, handler, financial=True, replay_safe=True)
    call = ToolCall(id="lost-response", name="financial", arguments={"volume": 1})
    observe(state, call, tool, {"ok": True, "status": "ambiguous"})
    resolved: dict[str, Any] = {"ok": True, "status": "resolved", "code": "owner_attested_executed"}
    record = observe(state, call, tool, resolved)
    assert resolved["recovery"]["category"] == "stale_state"
    assert resolved["recovery"]["next_action"] == "reload_authoritative_state"
    assert not resolved["recovery"]["safe_to_retry"]
    assert record["failures"] == 0 and record["code"] == "operation_resolved_unconfirmed"
    assert state["environment"]["phase"] == "working"
    # The route keeps replaying the same durable operation; a new call ID never mints one.
    blocked = blocked_route(state, call.model_copy(update={"id": "new-call"}))
    assert blocked and blocked["origin_call_id"] == "lost-response"
    batch: dict[str, Any] = {
        "ok": True,
        "results": [{"status": "confirmed"}, {"status": "resolved", "code": "target_closed"}],
    }
    observe(state, ToolCall(id="batch", name="financial", arguments={}), tool, batch)
    assert batch["recovery"]["next_action"] == "reload_authoritative_state"


def test_every_failure_tells_the_model_its_class_whether_to_repeat_and_what_to_do() -> None:
    """The unified error contract: no failure reaches the model as a bare code."""
    read = Tool("account_read", "Read", Contract, handler, True)
    limited: dict[str, Any] = {"ok": False, "code": "broker_rate_limited"}
    observe({}, ToolCall(id="a", name="account_read", arguments={}), read, limited)
    assert (limited["class"], limited["retryable"]) == ("connection", True)
    assert "tried" in limited["hint"]
    for code in ("volume_out_of_range", "volume_step_mismatch", "price_tick_mismatch"):
        refused: dict[str, Any] = {"ok": False, "code": code}
        observe({}, ToolCall(id=code, name="trade_execute", arguments={}), None, refused)
        assert (refused["class"], refused["retryable"]) == ("input", False), code
    stopped: dict[str, Any] = {"ok": False, "code": "trading_restriction_active"}
    observe({}, ToolCall(id="r", name="trade_execute", arguments={}), None, stopped)
    assert stopped["class"] == "permission" and "another way" in stopped["hint"]


def test_a_handlers_own_guidance_reaches_the_model_and_is_never_overwritten() -> None:
    sentence = "Nothing changed. Retry with the exact model of one of these."
    refused: dict[str, Any] = {"ok": False, "code": "model_not_in_catalog", "recovery": sentence}
    observe({}, ToolCall(id="m", name="model_request", arguments={}), None, refused)
    assert refused["hint"] == sentence and refused["recovery"]["category"]
    named: dict[str, Any] = {
        "ok": False,
        "code": "consult_budget_exhausted",
        "recovery": {"next_action": "decide_with_current_evidence"},
    }
    observe({}, ToolCall(id="c", name="consult_model", arguments={}), None, named)
    assert named["recovery"]["next_action"] == "decide_with_current_evidence"
    # A note that is not a failure keeps its sentence too, and recovery is never a string.
    note: dict[str, Any] = {"created": False, "code": "agent_already_exists", "recovery": sentence}
    observe({}, ToolCall(id="n", name="agent_create", arguments={}), None, note)
    assert note["hint"] == sentence and "recovery" not in note


@pytest.mark.parametrize(
    ("code", "status", "expected_class", "action"),
    [
        # Not named by classify(): the status its tool raised says what kind of refusal it is.
        ("mcp_tool_not_authorized", 403, "permission", "respect_scope"),
        ("memory_edit_no_match", 422, "input", "correct_arguments"),
        ("invalid_cron", 400, "input", "correct_arguments"),
        ("goal_trade_confirmation_required", 409, "permission", "request_owner_authorization"),
        ("goal_reconciliation_required", 409, "provider", "wait_for_authoritative_recovery"),
        ("account_authority_volume_limit", 409, "permission", "respect_scope"),
        ("work_paused_by_owner", 409, "permission", "respect_scope"),
        ("pending_price_wrong_side", 409, "input", "correct_arguments"),
        # A state conflict says nothing a model can act on: it stays as it was.
        ("task_not_running", 409, "internal", "alternate_route"),
        ("operation_status_transition_invalid", 409, "internal", "alternate_route"),
        ("quote_unavailable", 404, "internal", "alternate_route"),
        ("browser_action_failed", 403, "internal", "alternate_route"),
        ("position_sizing_economics_unavailable", 409, "internal", "alternate_route"),
        ("mcp_schema_invalid", 422, "internal", "alternate_route"),
        # A broker's own refusal stays the provider's, whatever its status.
        ("broker_disabled", 409, "provider", "alternate_route"),
        ("broker_endpoint_forbidden", 403, "provider", "alternate_route"),
        # Named codes never change with their status.
        ("trading_restriction_active", 409, "permission", "respect_scope"),
        ("emergency_stop", 409, "provider", "wait_for_authoritative_recovery"),
        ("model_not_configured", 409, "provider", "inspect_authorized_alternative"),
        ("position_volume_exceeded", 409, "input", "correct_arguments"),
        ("task_run_not_found", 409, "resolution", "inspect_existing_state"),
        # Rules that a corrected argument does not get past, and the owner's budgets.
        ("trusted_source_write_blocked", 422, "permission", "respect_scope"),
        ("owner_action_limit", 429, "permission", "respect_scope"),
        ("agent_paused", 409, "permission", "respect_scope"),
        ("trade_approval_required", 403, "permission", "request_owner_authorization"),
    ],
)
def test_a_refusal_is_classed_by_what_its_tool_said_not_by_how_its_code_is_spelt(
    code: str, status: int, expected_class: str, action: str
) -> None:
    refused: dict[str, Any] = {"ok": False, "code": code, "http_status": status}
    observe({}, ToolCall(id="c", name="some_tool", arguments={}), None, refused)
    assert (refused["class"], refused["recovery"]["next_action"]) == (expected_class, action)
    # The status is read by the runtime and goes no further.
    assert "http_status" not in refused
    if expected_class == "permission":
        assert "another" in refused["hint"]


def test_the_class_a_tool_wrote_decides_what_its_refusal_means() -> None:
    authored: dict[str, Any] = {
        "ok": False,
        "code": "routine_title_taken",
        "class": "input",
        "hint": "Another routine has that title. Choose a different one.",
    }
    observe({}, ToolCall(id="a", name="routine_create", arguments={}), None, authored)
    assert authored["recovery"]["category"] == "invalid_tool_arguments"
    assert authored["recovery"]["next_action"] == "correct_arguments"
    assert authored["hint"].startswith("Another routine")
    listed: dict[str, Any] = {
        "ok": False,
        "code": "market_watches_not_found",
        "class": "resolution",
        "candidates": [{"id": "w1", "label": "EURUSD above 1.10"}],
    }
    observe({}, ToolCall(id="w", name="watch_cancel", arguments={}), None, listed)
    # The result names what exists, so the next call is in it.
    assert listed["recovery"]["next_action"] == "follow_hint"
    bare: dict[str, Any] = {"ok": False, "code": "market_watches_not_found"}
    observe({}, ToolCall(id="b", name="watch_cancel", arguments={}), None, bare)
    assert bare["recovery"]["next_action"] == "inspect_existing_state"


def test_a_general_hint_never_says_more_than_is_known() -> None:
    order = Tool("trade_execute", "Trade", Contract, handler, financial=True)
    unknown: dict[str, Any] = {"ok": True, "status": "ambiguous"}
    observe({}, ToolCall(id="u", name="trade_execute", arguments={}), order, unknown)
    # Not known is neither failed nor sent, and the hint says so.
    assert unknown["ok"] is True and unknown["retryable"] is False
    assert "may or may not have taken effect" in unknown["hint"]
    assert "never that it failed or went through" in unknown["hint"]
    stale: dict[str, Any] = {"ok": False, "code": "quote_stale"}
    observe({}, ToolCall(id="q", name="trade_execute", arguments={}), order, stale)
    assert "too old" in stale["hint"] and "not found" not in stale["hint"]
    unsent: dict[str, Any] = {"ok": False, "code": "broker_connection_unavailable"}
    observe({}, ToolCall(id="w", name="trade_execute", arguments={}), order, unsent)
    # A connection failure on an order is never offered for another try.
    assert unsent["retryable"] is False and "Do not call it again" in unsent["hint"]
    for code in ("trade_approval_rejected", "agent_analysis_only", "shadow_execution_forbidden"):
        ruled: dict[str, Any] = {"ok": False, "code": code}
        observe({}, ToolCall(id=code, name="trade_execute", arguments={}), order, ruled)
        # The owner's no and the agent's level are rules: no other route is suggested.
        assert ruled["class"] == "permission" and "another way" in ruled["hint"], code
    read = Tool("account_read", "Read", Contract, handler, True)
    state: dict[str, Any] = {}
    call = ToolCall(id="t", name="account_read", arguments={})
    dropped: dict[str, Any] = {}
    for _ in range(3):
        dropped = {"ok": False, "code": "broker_rate_limited"}
        observe(state, call, read, dropped)
    # The third failure of the same read is no longer offered for another try.
    assert dropped["retryable"] is False and "not tried again" in dropped["hint"]
    assert set(RECOVERY_HINTS) == set(get_args(FailureCategory))


def test_reading_the_record_of_a_failed_operation_is_a_read_that_succeeded() -> None:
    read_record = Tool("trade_read_record", "Read", Contract, handler, True)
    record: dict[str, Any] = {"ok": True, "status": "failed", "code": "volume_out_of_range"}
    seen = observe(
        {}, ToolCall(id="h", name="trade_read_record", arguments={}), read_record, record
    )
    assert record["ok"] is True and "hint" not in record and "recovery" not in record
    assert seen["failures"] == 0
    # The same status from the order itself is the order's failure.
    order = Tool("trade_execute", "Trade", Contract, handler, financial=True)
    refused: dict[str, Any] = {"ok": True, "status": "rejected", "code": "trade_approval_rejected"}
    observe({}, ToolCall(id="o", name="trade_execute", arguments={}), order, refused)
    assert refused["ok"] is False and refused["class"] == "permission"


def test_a_failed_operation_is_not_an_ok_call_and_a_tools_own_words_are_kept() -> None:
    order = Tool("trade_execute", "Trade", Contract, handler, financial=True)
    failed: dict[str, Any] = {"ok": True, "status": "failed", "code": "volume_out_of_range"}
    observe({}, ToolCall(id="o", name="trade_execute", arguments={}), order, failed)
    assert failed["ok"] is False and failed["class"] == "input"
    authored: dict[str, Any] = {
        "ok": False,
        "code": "symbol_not_found",
        "class": "resolution",
        "retryable": True,
        "hint": "This account lists it as XAUUSDm.",
    }
    observe({}, ToolCall(id="s", name="market_quote", arguments={}), None, authored)
    assert authored["retryable"] is True and authored["hint"].endswith("XAUUSDm.")
