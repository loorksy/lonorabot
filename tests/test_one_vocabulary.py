"""One vocabulary: Super Bot and goal autonomy are retired; activity facts come from metadata."""

import pytest
from lonora_adapter_kit.types import ToolCall
from lonora_agent.tool_loop import started_payload
from lonora_contracts.trading_goal import GoalControl, GoalCreate
from lonora_core.attention import ATTENTION_KINDS, classify_attention
from lonora_tools.loader import load_tools
from pydantic import ValidationError


def test_no_super_bot_tool_remains_in_the_registry() -> None:
    names = {tool.name for tool in load_tools().definitions()}
    assert not {name for name in names if "super_bot" in name}
    assert {"goal_create", "goal_step_execute", "trade_execute"} <= names


def test_a_goal_has_no_autonomy_switch_or_owner_limit_knobs() -> None:
    with pytest.raises(ValidationError):
        GoalControl.model_validate({"version": 1, "action": "resume", "autonomous": True})
    with pytest.raises(ValidationError):
        GoalControl.model_validate({"version": 1, "action": "resume", "maximum_volume": "1"})
    assert GoalControl.model_validate({"version": 1, "action": "pause"}).action == "pause"
    plan = {
        "agent_id": "agent",
        "thread_id": "thread",
        "title": "Plan",
        "objective": "Review",
        "account_id": "account",
        "symbol": "XAUUSD",
        "steps": [{"id": "read", "title": "Read", "kind": "analysis"}],
    }
    assert "autonomous" not in GoalCreate.model_validate(plan).model_dump()
    with pytest.raises(ValidationError):
        GoalCreate.model_validate({**plan, "autonomous": True})


def test_retired_super_bot_events_raise_no_owner_attention() -> None:
    assert "super_bot.updated" not in ATTENTION_KINDS
    result = classify_attention("super_bot.updated", {"id": "old", "status": "pending"})
    assert result.importance == "silent" and result.code == "internal_update"


@pytest.mark.parametrize(
    ("name", "toolset", "effect"),
    [
        ("trade_execute", "trading", "financial"),
        ("trade_record_read", "trading", "read"),
        ("web_search", "research", "read"),
        ("memory_write", "memory", "change"),
        ("goal_step_execute", "goals", "financial"),
    ],
)
def test_tool_started_carries_registry_toolset_and_effect(
    name: str, toolset: str, effect: str
) -> None:
    tool = load_tools().tools[name]
    payload = started_payload(ToolCall(id="call", name=name, arguments={}), tool)
    assert payload == {"name": name, "call_id": "call", "toolset": toolset, "effect": effect}


def test_an_unknown_tool_reports_only_its_name() -> None:
    payload = started_payload(ToolCall(id="call", name="not_a_tool", arguments={}), None)
    assert payload == {"name": "not_a_tool", "call_id": "call"}
