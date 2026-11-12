"""One vocabulary: Super Bot is retired; activity facts come from metadata."""

import re
from pathlib import Path

import pytest
from lonora_adapter_kit.types import ToolCall
from lonora_agent.tool_block import started_payload
from lonora_core.attention import ATTENTION_KINDS, classify_attention
from lonora_tools.loader import load_tools


def test_no_super_bot_tool_remains_in_the_registry() -> None:
    names = {tool.name for tool in load_tools().definitions()}
    assert not {name for name in names if "super_bot" in name}
    assert "trade_execute" in names


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


def test_activity_label_overrides_name_real_registry_tools() -> None:
    """The few per-tool activity labels (core turn-activity.ts) never name a stale id."""
    source = (
        Path(__file__).resolve().parents[1] / "packages/core/src/turn-activity.ts"
    ).read_text()
    table = source.split("const toolLabels", 1)[1].split("\n};", 1)[0]
    names = set(re.findall(r"^  ([a-z_]+):", table, re.MULTILINE))
    assert {"owner_action_propose", "wait_for_input"} <= names
    assert names <= set(load_tools().tools), names - set(load_tools().tools)
