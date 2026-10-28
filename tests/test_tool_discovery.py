"""Progressive presentation never changes execution scope or grants authority."""

import json
from contextlib import asynccontextmanager
from types import SimpleNamespace
from typing import Any, cast
from unittest.mock import AsyncMock, patch

import pytest
from lonora_adapter_kit.types import ToolCall, ToolDefinition
from lonora_contracts.domain import Contract
from lonora_core.user_error import LonoraError
from lonora_tools.base import Tool
from lonora_tools.context import ToolContext
from lonora_tools.environment import EnvironmentInput
from lonora_tools.loader import load_tools
from lonora_tools.registry import MAX_CAPABILITY_INVENTORY_CHARS, ToolRegistry
from lonora_tools.tool_discovery import MAX_SEARCH_RESULTS, search_definitions
from pydantic import Field, ValidationError


class Input(Contract):
    account_id: str = Field(min_length=1)
    symbol: str = Field(min_length=1)


async def unused(_: ToolContext, __: dict[str, Any]) -> dict[str, Any]:
    raise AssertionError("Inspection must not execute a capability")


def registry() -> ToolRegistry:
    return ToolRegistry(
        [
            Tool("market_quote", "Read current broker quote prices", Input, unused, True),
            Tool("trade_execute", "Execute a broker trade", Input, unused, financial=True),
            Tool("skills_list", "List available procedures", Input, unused, True),
            Tool("skill_view", "Read a procedure", Input, unused, True),
            Tool("wait_for_input", "Ask for missing owner information", Input, unused),
            Tool("قراءة_السعر", "قراءة سعر السوق الحالي", Input, unused, True),
        ]
    )


@asynccontextmanager
async def session():
    yield object()


async def inspect(
    catalog: ToolRegistry, arguments: dict[str, Any], *, read_only: bool = False
) -> dict[str, Any]:
    context = cast(
        ToolContext, SimpleNamespace(db=SimpleNamespace(sessions=session), lease=object())
    )
    run = SimpleNamespace(
        trigger="message", model_metadata={"authority": "observe_only"} if read_only else {}
    )
    with patch("lonora_tools.registry.require_lease", AsyncMock(return_value=run)):
        return await catalog.inspect_environment(
            context, EnvironmentInput.model_validate(arguments).model_dump()
        )


def test_initial_surface_is_compact_and_full_definitions_remain_available():
    catalog = load_tools()
    initial = catalog.discovery_definitions()
    assert {tool.name for tool in initial} == {
        "tool_environment",
        "skills_list",
        "skill_view",
        "wait_for_input",
    }
    full = catalog.definitions()
    assert len(full) > 100
    # Compare the actual serialized native schemas, not a synthetic tool count.
    compact_bytes = len(json.dumps([tool.model_dump() for tool in initial]))
    full_bytes = len(json.dumps([tool.model_dump() for tool in full]))
    assert compact_bytes < full_bytes / 10
    selected = catalog.discovery_definitions(False, {"market_quote", "trade_execute", "invented"})
    assert {tool.name for tool in selected} == {tool.name for tool in initial} | {
        "market_quote",
        "trade_execute",
    }


def test_scope_membership_never_generates_or_caches_native_schemas():
    catalog = registry()
    complete = {tool.name for tool in catalog.definitions()}
    read_only = {tool.name for tool in catalog.definitions(True)}
    with patch.object(
        Tool, "definition", side_effect=AssertionError("Schema work on membership path")
    ):
        assert catalog.names() == complete
        assert catalog.names(True) == read_only
        assert "trade_execute" not in catalog.names(True)
        del catalog.tools["market_quote"]
        assert "market_quote" not in catalog.names()


@pytest.mark.asyncio
async def test_search_then_inspection_activate_exact_native_schemas_only():
    catalog = registry()
    result = await inspect(catalog, {"query": "market quote"})
    assert [tool["name"] for tool in result["tools"]] == ["market_quote"]
    assert result["execution_authorized"] is False
    assert catalog.discovered_names(result) == {"market_quote"}
    exact = await inspect(catalog, {"tool_name": "trade_execute"})
    assert catalog.discovered_names(exact) == {"trade_execute"}
    listed = await inspect(catalog, {"offset": 1, "limit": 2})
    assert listed["total"] == 7 and listed["next_offset"] == 3
    assert len(listed["tools"]) == 2
    assert not catalog.discovered_names(listed)
    assert not catalog.discovered_names({**exact, "ok": False})
    assert not catalog.discovered_names({"tool": {"name": "trade_execute", "input_schema": {}}})
    assert not catalog.discovered_names(
        {"tools": [None, "trade_execute", {"name": "invented", "input_schema": {}}]}
    )


@pytest.mark.asyncio
async def test_current_read_only_scope_filters_search_inspect_and_selected_definitions():
    catalog = registry()
    result = await inspect(catalog, {"query": "trade_execute"}, read_only=True)
    assert result["tools"] == [] and not catalog.discovered_names(result)
    with pytest.raises(LonoraError, match="tool_not_allowed"):
        await inspect(catalog, {"tool_name": "trade_execute"}, read_only=True)
    assert "trade_execute" not in {
        tool.name for tool in catalog.discovery_definitions(True, {"trade_execute", "market_quote"})
    }
    with pytest.raises(LonoraError, match="tool_not_allowed"):
        await catalog.execute(
            ToolCall(id="denied", name="trade_execute", arguments={}),
            cast(ToolContext, None),
            True,
        )


@pytest.mark.asyncio
async def test_discovery_does_not_execute_aliases_or_invent_missing_capabilities():
    catalog = registry()
    result = await inspect(catalog, {"query": "MARKET_QUOTE"})
    assert catalog.discovered_names(result) == {"market_quote"}
    with pytest.raises(LonoraError, match="tool_not_allowed"):
        await catalog.execute(
            ToolCall(id="alias", name="MARKET_QUOTE", arguments={}), cast(ToolContext, None)
        )
    assert (await inspect(catalog, {"query": "market quantum-never-configured"}))["tools"] == []
    assert (await inspect(catalog, {"query": "   "}))["tools"] == []


@pytest.mark.asyncio
async def test_unicode_search_and_bounded_schema_results():
    catalog = registry()
    result = await inspect(catalog, {"query": "قراءة سعر"})
    assert [tool["name"] for tool in result["tools"]] == ["قراءة_السعر"]
    definitions = [
        ToolDefinition(name=f"quote_{index}", description="broker quote", parameters={})
        for index in range(30)
    ]
    assert len(search_definitions(definitions, "broker quote", 1000)) == MAX_SEARCH_RESULTS
    assert not search_definitions(definitions, "broker quote", 0)
    assert search_definitions(definitions, "broker quote") == search_definitions(
        list(reversed(definitions)), "broker quote"
    )
    with pytest.raises(ValidationError):
        EnvironmentInput(query="x" * 301)


def test_activation_rejects_replaced_or_removed_schema():
    catalog = registry()
    result = {"tool": catalog.tools["market_quote"].environment()}
    assert catalog.discovered_names(result) == {"market_quote"}
    catalog.tools["market_quote"] = Tool(
        "market_quote", "Changed input", EnvironmentInput, unused, True
    )
    assert not catalog.discovered_names(result)
    del catalog.tools["market_quote"]
    assert not catalog.discovered_names(result)


@pytest.mark.parametrize(
    ("query", "expected"),
    [
        ("terminal", "workspace_execute"),
        ("run terminal command", "workspace_execute"),
        ("open trade", "trade_execute"),
        ("place order", "trade_execute"),
        ("buy sell positions", "trade_execute"),
        ("read market quotes", "market_quote"),
        ("read github repository", "web_fetch"),
    ],
)
def test_real_catalog_discovers_supported_work_from_business_terms(query: str, expected: str):
    catalog = load_tools()
    assert expected in search_definitions(catalog.definitions(), query)
    if query == "terminal":
        assert search_definitions(catalog.definitions(), query)[0] == expected


def test_current_inventory_contains_all_real_names_without_changing_native_schemas():
    catalog = load_tools()
    initial = catalog.discovery_definitions()
    inventory = catalog.capability_inventory()
    assert len(inventory) <= MAX_CAPABILITY_INVENTORY_CHARS
    names = {
        name
        for line in inventory.split("<available_capabilities>\n")[1].splitlines()
        if ": " in line
        for name in line.split(": ", 1)[1].split(", ")
    }
    assert names == set(catalog.tools)
    assert f"Listed {len(catalog.tools)} of {len(catalog.tools)}" in inventory
    assert "not establish backend readiness" in inventory
    assert "account authority or permission" in inventory
    assert catalog.discovery_definitions() == initial and len(initial) == 4


def test_inventory_obeys_current_read_only_scope_and_has_no_invented_abilities():
    catalog = registry()
    inventory = catalog.capability_inventory(read_only=True)
    assert "market_quote" in inventory and "قراءة_السعر" in inventory
    assert "trade_execute" not in inventory and "wait_for_input" not in inventory
    del catalog.tools["market_quote"]
    assert "market_quote" not in catalog.capability_inventory(read_only=True)


def test_large_inventory_is_explicitly_bounded_and_directs_to_paginated_metadata():
    catalog = ToolRegistry(
        [
            Tool(f"capability_{index:05d}", "Read bounded evidence", Input, unused, True)
            for index in range(2000)
        ]
    )
    inventory = catalog.capability_inventory()
    assert len(inventory) <= MAX_CAPABILITY_INVENTORY_CHARS
    assert f"of {len(catalog.tools)} permitted capabilities" in inventory
    assert f"Listed {len(catalog.tools)} of" not in inventory
    assert "paginate complete metadata" in inventory
