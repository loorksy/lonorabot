"""Exposure and discovery are presentation: they never change scope or grant authority."""

import json
from contextlib import asynccontextmanager
from itertools import product
from types import SimpleNamespace
from typing import Any, cast
from unittest.mock import AsyncMock, patch

import pytest
from lonora_adapter_kit.types import ToolCall, ToolDefinition
from lonora_contracts.domain import Contract
from lonora_core.user_error import LonoraError
from lonora_tools.base import HELPER_EFFECTS, ExposureProfile, Tool, ToolScope, eager_for
from lonora_tools.context import ToolContext
from lonora_tools.environment import EnvironmentInput
from lonora_tools.loader import load_tools
from lonora_tools.registry import (
    BRIDGE_TOOLS,
    EAGER_SCHEMA_BUDGET,
    MAX_CAPABILITY_INVENTORY_CHARS,
    MAX_PROMOTED_TOOLS,
    PROMOTED_SCHEMA_BUDGET,
    SEARCH_SCHEMA_BUDGET,
    ToolRegistry,
    schema_chars,
)
from lonora_tools.tool_discovery import MAX_SEARCH_RESULTS, search_definitions
from pydantic import Field, ValidationError


class Input(Contract):
    account_id: str = Field(min_length=1)
    symbol: str = Field(min_length=1)


async def unused(_: ToolContext, __: dict[str, Any]) -> dict[str, Any]:
    raise AssertionError("Inspection must not execute a capability")


async def missing_backend(_: ToolContext) -> str | None:
    return "fixture_unconfigured"


def registry() -> ToolRegistry:
    return ToolRegistry(
        [
            Tool(
                "market_quote",
                "Read current broker quote prices",
                Input,
                unused,
                True,
                eager=eager_for("market"),
            ),
            Tool("trade_execute", "Execute a broker trade", Input, unused, financial=True),
            Tool("skills_list", "List available procedures", Input, unused, True),
            Tool("skill_view", "Read a procedure", Input, unused, True),
            Tool("wait_for_input", "Ask for missing owner information", Input, unused),
            Tool("قراءة_السعر", "قراءة سعر السوق الحالي", Input, unused, True),
            Tool(
                "news_search",
                "Search market news headlines",
                Input,
                unused,
                True,
                availability=missing_backend,
            ),
        ]
    )


@asynccontextmanager
async def session():
    yield object()


async def inspect(
    catalog: ToolRegistry,
    arguments: dict[str, Any],
    *,
    scope: ToolScope = "full",
    native: list[str] | None = None,
) -> dict[str, Any]:
    context = cast(
        ToolContext, SimpleNamespace(db=SimpleNamespace(sessions=session), lease=object())
    )
    run = SimpleNamespace(
        trigger="subagent" if scope == "helper" else "message",
        model_metadata={"authority": "observe_only"} if scope == "observe_only" else {},
        execution_state={"tool_exposure": {"native": native or []}},
    )
    with patch("lonora_tools.registry.require_lease", AsyncMock(return_value=run)):
        return await catalog.inspect_environment(
            context, EnvironmentInput.model_validate(arguments).model_dump()
        )


PROFILE_SETS: list[list[ExposureProfile]] = [
    ["core", "market"],
    ["core", "research"],
    ["core", "market", "task"],
    ["core", "research", "task"],
    # Supervisors: the Personal Agent and any agent holding a grant. A trading
    # identity's Task Run leaves coordination out (tool_exposure.run_profiles).
    ["core", "market", "coordination"],
    ["core", "research", "coordination"],
    ["core", "research", "coordination", "task"],
]


def test_eager_working_sets_are_data_from_tool_metadata():
    catalog = load_tools()
    market = set(catalog.eager_names(["core", "market"]))
    research = set(catalog.eager_names(["core", "research"]))
    core = set(catalog.eager_names(["core"]))
    assert BRIDGE_TOOLS | {"skills_list", "skill_view", "wait_for_input"} <= core
    assert {"memory_read", "memory_write", "session_search"} <= core
    # The literal search stays reachable through tool_call; session_search replaces it.
    assert "search_internal" not in core and "search_internal" in catalog.tools
    assert {
        "list_accounts",
        "market_quote",
        "market_candles",
        "market_instrument",
        "market_snapshot",
        "market_sessions",
        "account_read",
        "chart_snapshot",
        "market_decision_record",
        "market_decision_history",
        "watch_create",
    } <= market
    # Exact swing anchors and lines are a follow-up to the snapshot's structure.
    assert "market_structure" not in market and "market_structure" in catalog.tools
    assert {"web_search", "web_fetch"} <= research and not {"web_search", "web_fetch"} & market
    # Calendar evidence is native for research Agents only when a source exists.
    assert "economic_calendar_read" in research - market
    assert catalog.tools["economic_calendar_read"].availability is not None
    # Owner restrictions are shown in the permission frame; their tools are long-tail.
    assert not {"trade_restriction_create", "trade_restriction_list"} & (market | research)
    assert not {"market_quote", "trade_execute"} & research
    assert {"task_wait", "task_step_update"} <= set(catalog.eager_names(["core", "task"]))
    assert "task_wait" not in market | research
    # Every eager name is declared on its Tool; there is no second name list.
    assert market == {
        name for name, tool in catalog.tools.items() if tool.eager & {"core", "market"}
    }
    # Registry order is deterministic and independent of the profile order given.
    assert catalog.eager_names(["market", "core"]) == catalog.eager_names(["core", "market"])
    assert catalog.eager_names(["core", "market"]) == [
        name for name in catalog.tools if name in market
    ]


@pytest.mark.parametrize(
    ("profiles", "scope"), product(PROFILE_SETS, ("full", "observe_only", "helper"))
)
def test_eager_schema_budget_holds_for_every_run_shape(
    profiles: list[ExposureProfile], scope: ToolScope
):
    catalog = load_tools()
    names = catalog.eager_names(profiles, scope)
    total = sum(schema_chars(catalog.tools[name]) for name in names)
    assert total <= EAGER_SCHEMA_BUDGET
    assert EAGER_SCHEMA_BUDGET + PROMOTED_SCHEMA_BUDGET < 30000
    if scope != "full":
        assert not any(catalog.tools[name].financial for name in names)
    if scope == "helper":
        assert all(catalog.tools[name].read_only or name in HELPER_EFFECTS for name in names)
    full = sum(map(schema_chars, catalog.tools.values()))
    assert total < full / 3


def test_native_definitions_keep_bridges_and_drop_unknown_or_out_of_scope_names():
    catalog = load_tools()
    selected = catalog.native_definitions({"market_quote", "trade_execute", "invented"})
    assert {tool.name for tool in selected} == BRIDGE_TOOLS | {"market_quote", "trade_execute"}
    read_only = catalog.native_definitions({"market_quote", "trade_execute"}, scope="helper")
    assert {tool.name for tool in read_only} == BRIDGE_TOOLS | {"market_quote"}
    assert [tool.name for tool in selected] == [
        name for name in catalog.tools if name in {tool.name for tool in selected}
    ]


def test_exposure_promotes_remembered_tools_within_count_and_schema_budget():
    catalog = load_tools()
    eager, promoted = catalog.exposure(["core", "research"])
    assert promoted == [] and set(eager) == set(catalog.eager_names(["core", "research"]))
    remembered = [
        "invented",
        "web_search",  # already eager: never counted twice
        "goal_create",  # larger than the whole promoted budget
        "list_accounts",
        "market_quote",
        "trade_execute",
        "account_activity",
        "market_symbols",
        "routine_list",
        "watch_list",
        "chart_list",
    ]
    native, promoted = catalog.exposure(["core", "research"], remembered=remembered)
    assert "goal_create" not in promoted and "invented" not in promoted
    assert promoted == [
        name
        for name in remembered
        if name in promoted  # recency order is kept for the promoted record
    ]
    assert len(promoted) <= MAX_PROMOTED_TOOLS
    assert sum(schema_chars(catalog.tools[name]) for name in promoted) <= PROMOTED_SCHEMA_BUDGET
    assert promoted[:3] == ["list_accounts", "market_quote", "trade_execute"]
    assert set(native) == set(eager) | set(promoted)
    assert native == [name for name in catalog.tools if name in set(native)]
    # Unavailable and out-of-scope tools are never promoted.
    _, limited = catalog.exposure(
        ["core", "research"],
        scope="helper",
        remembered=remembered,
        unavailable={"list_accounts": "fixture_unconfigured"},
    )
    assert "list_accounts" not in limited and "trade_execute" not in limited
    assert all(catalog.tools[name].read_only for name in limited)


def test_unavailable_eager_tools_leave_the_native_array_but_bridges_stay():
    catalog = load_tools()
    native, _ = catalog.exposure(
        ["core", "research"],
        unavailable={"web_search": "research_provider_not_configured", "tool_call": "x"},
    )
    assert "web_search" not in native and "web_fetch" in native
    assert BRIDGE_TOOLS <= set(native)


def test_scope_membership_never_generates_or_caches_native_schemas():
    catalog = registry()
    complete = {tool.name for tool in catalog.definitions()}
    read_only = {tool.name for tool in catalog.definitions("helper")}
    with patch.object(
        Tool, "definition", side_effect=AssertionError("Schema work on membership path")
    ):
        assert catalog.names() == complete
        assert catalog.names("helper") == read_only
        assert "trade_execute" not in catalog.names("helper")
        assert catalog.eager_names(["core", "market"], "helper")
        del catalog.tools["market_quote"]
        assert "market_quote" not in catalog.names()


@pytest.mark.asyncio
async def test_search_and_inspection_report_invocation_and_availability():
    catalog = registry()
    result = await inspect(catalog, {"query": "market quote"}, native=["market_quote"])
    assert [tool["name"] for tool in result["tools"]] == ["market_quote"]
    assert result["tools"][0]["invoke"] == "direct"
    assert (
        result["tools"][0]["input_schema"] == catalog.tools["market_quote"].definition().parameters
    )
    assert result["execution_authorized"] is False and "tool_call" in result["invocation"]
    exact = await inspect(catalog, {"tool_name": "trade_execute"})
    assert exact["tool"]["invoke"] == "tool_call" and exact["tool"]["available"] is True
    assert exact["tool"]["input_schema"]
    news = await inspect(catalog, {"tool_name": "news_search"})
    assert news["tool"]["available"] is False
    assert news["tool"]["unavailable_reason"] == "fixture_unconfigured"
    listed = await inspect(catalog, {"offset": 1, "limit": 2})
    assert listed["total"] == 9 and listed["next_offset"] == 3
    assert len(listed["tools"]) == 2 and all("input_schema" not in t for t in listed["tools"])
    bridges = await inspect(catalog, {"tool_name": "tool_call"})
    assert bridges["tool"]["invoke"] == "direct"


@pytest.mark.asyncio
async def test_current_read_only_scope_filters_search_inspect_and_execution():
    catalog = registry()
    result = await inspect(catalog, {"query": "trade_execute"}, scope="helper")
    assert result["tools"] == []
    with pytest.raises(LonoraError, match="tool_not_allowed"):
        await inspect(catalog, {"tool_name": "trade_execute"}, scope="helper")
    # A financial tool outside a full Run is refused as such, before any database work.
    with pytest.raises(LonoraError, match="observe_only_execution_forbidden"):
        await catalog.execute(
            ToolCall(id="denied", name="trade_execute", arguments={}),
            cast(ToolContext, None),
            "helper",
        )
    with pytest.raises(LonoraError, match="tool_not_allowed"):
        await catalog.execute(
            ToolCall(id="denied", name="wait_for_input", arguments={}),
            cast(ToolContext, None),
            "helper",
        )


@pytest.mark.asyncio
async def test_observe_only_scope_keeps_every_non_financial_capability():
    catalog = load_tools()
    names = catalog.names("observe_only")
    assert {"memory_write", "watch_create", "peer_send", "owner_call_request"} <= names
    assert not {"trade_execute", "trade_close_positions", "goal_step_execute"} & names
    assert names == {name for name, tool in catalog.tools.items() if not tool.financial}
    helper = catalog.names("helper")
    assert {"workspace_execute", "artifact_create", "web_search"} <= helper
    assert not {"memory_write", "peer_send", "child_agent_create", "subagent_spawn"} & helper
    found = await inspect(catalog, {"query": "memory_write"}, scope="observe_only")
    assert "memory_write" in [tool["name"] for tool in found["tools"]]
    with pytest.raises(LonoraError, match="observe_only_execution_forbidden"):
        await catalog.execute(
            ToolCall(id="denied", name="trade_execute", arguments={}),
            cast(ToolContext, None),
            "observe_only",
        )


@pytest.mark.asyncio
async def test_discovery_does_not_execute_aliases_or_invent_missing_capabilities():
    catalog = registry()
    result = await inspect(catalog, {"query": "MARKET_QUOTE"})
    assert [tool["name"] for tool in result["tools"]] == ["market_quote"]
    with pytest.raises(LonoraError, match="tool_not_allowed"):
        await catalog.execute(
            ToolCall(id="alias", name="MARKET_QUOTE", arguments={}), cast(ToolContext, None)
        )
    # Words the catalog never uses invent nothing, and no longer empty a search either.
    assert (await inspect(catalog, {"query": "quantum-xylophone"}))["tools"] == []
    found = await inspect(catalog, {"query": "market quantum-xylophone"})
    assert "market_quote" in [tool["name"] for tool in found["tools"]]
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
    assert MAX_SEARCH_RESULTS >= 10
    assert len(search_definitions(definitions, "broker quote", 1000)) == MAX_SEARCH_RESULTS
    assert not search_definitions(definitions, "broker quote", 0)
    assert search_definitions(definitions, "broker quote") == search_definitions(
        list(reversed(definitions)), "broker quote"
    )
    with pytest.raises(ValidationError):
        EnvironmentInput(query="x" * 301)


@pytest.mark.asyncio
async def test_real_catalog_search_bounds_total_schema_size():
    catalog = load_tools()
    result = await inspect(catalog, {"query": "goal", "limit": 40})
    assert 5 < len(result["tools"]) <= MAX_SEARCH_RESULTS
    shown = [tool for tool in result["tools"] if "input_schema" in tool]
    omitted = [tool for tool in result["tools"] if tool.get("input_schema_omitted")]
    assert sum(len(json.dumps(tool["input_schema"], ensure_ascii=False)) for tool in shown) <= (
        SEARCH_SCHEMA_BUDGET
    )
    # Two large schemas do not both fit: the later one names its required fields
    # and is loaded with an exact tool_name inspection instead.
    assert omitted and {"goal_plan", "goal_create"} & {tool["name"] for tool in shown}
    assert all(isinstance(tool["required"], list) and tool["required"] for tool in omitted)
    assert result["tools"][0].get("input_schema")


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
        ("search internet", "web_search"),
    ],
)
def test_real_catalog_discovers_supported_work_from_business_terms(query: str, expected: str):
    catalog = load_tools()
    assert expected in search_definitions(catalog.definitions(), query)
    if query == "terminal":
        assert search_definitions(catalog.definitions(), query)[0] == expected


@pytest.mark.parametrize(
    ("query", "expected"),
    [
        ("حذف المتابعات", "watch_cancel"),
        ("delete watch", "watch_cancel"),
        ("امسح المهام", "task_control"),
        ("remove the alert", "watch_cancel"),
        ("ألغِ المتابعة", "watch_cancel"),
        ("أوقف الهدف", "goal_control"),
    ],
)
def test_everyday_words_in_the_owners_language_find_the_tool(query: str, expected: str):
    catalog = load_tools()
    terms = {name: tool.search_terms for name, tool in catalog.tools.items()}
    assert search_definitions(catalog.definitions(), query, terms=terms)[0] == expected


def inventory_names(inventory: str) -> set[str]:
    return {
        name
        for line in inventory.split("<available_capabilities>\n")[1].splitlines()
        if ": " in line and not line.startswith("unavailable_now")
        for name in line.split(": ", 1)[1].split(", ")
    }


def test_current_inventory_contains_all_real_names_grouped_by_toolset():
    catalog = load_tools()
    inventory = catalog.capability_inventory()
    assert len(inventory) <= MAX_CAPABILITY_INVENTORY_CHARS
    assert inventory_names(inventory) == set(catalog.tools)
    assert f"Listed {len(catalog.tools)} of {len(catalog.tools)}" in inventory
    assert "tool_call" in inventory and "account authority or permission" in inventory
    families = {
        line.split(": ", 1)[0]
        for line in inventory.split("<available_capabilities>\n")[1].splitlines()
        if ": " in line
    }
    assert families == {tool.toolset for tool in catalog.tools.values()}
    assert "unavailable_now" not in inventory
    marked = catalog.capability_inventory(
        unavailable={"web_search": "research_provider_not_configured", "invented": "x"}
    )
    assert "unavailable_now" in marked and "web_search=research_provider_not_configured" in marked
    assert "invented" not in marked and inventory_names(marked) == set(catalog.tools)
    # A Run passes the same frozen map every turn: the text is byte-stable.
    assert marked == catalog.capability_inventory(
        unavailable={"web_search": "research_provider_not_configured", "invented": "x"}
    )


def test_inventory_obeys_current_read_only_scope_and_has_no_invented_abilities():
    catalog = registry()
    inventory = catalog.capability_inventory(scope="helper")
    assert "market_quote" in inventory and "قراءة_السعر" in inventory
    assert "trade_execute" not in inventory and "wait_for_input" not in inventory
    del catalog.tools["market_quote"]
    assert "market_quote" not in catalog.capability_inventory(scope="helper")


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
