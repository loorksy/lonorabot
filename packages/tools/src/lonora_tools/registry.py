"""The one runtime tool registry: membership, exposure, discovery and dispatch.

Exposure follows the stable-bridge design of Hermes Agent's Tool Search
(``tools/tool_search.py`` and ``tools/tool_search_validation.py``, source
https://github.com/NousResearch/hermes-agent at revision
a9ff9799e273f525b82718cdc69fdec71b1dca5a): a Run receives a bounded eager
working set as native schemas, frozen for the whole Run, and reaches every
other capability through the stable ``tool_call`` bridge. Lonora resolves a
bridge call into the real tool call before anything else observes it (see
``resolve_call``), so receipts, guardrails, approvals and financial checks see
exactly the call a direct invocation would produce. The argument
normalization in ``resolve_call`` is adapted from Hermes'
``normalize_tool_call_entries``; batches, connector routing and the separate
describe bridge were not ported (``tool_environment`` returns schemas). A
batch-shaped ``calls`` payload never dispatches; ``proposed_names`` only reads
its target names for the reply truth gates.

MIT License

Copyright (c) 2025 Nous Research

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
"""

import asyncio
import json
import logging
from collections.abc import Collection, Iterable, Mapping, Sequence
from typing import Any, cast

from lonora_adapter_kit.types import ToolCall, ToolDefinition
from lonora_core.user_error import LonoraError
from lonora_db.runs import require_lease

from .base import AvailabilityCheck, ExposureProfile, Tool, ToolScope, eager_for, run_scope
from .context import ToolContext
from .environment import BridgeInput, EnvironmentInput
from .market_binding import guard_market_tool, prepare_market_arguments, scope_market_result
from .schema import validate_arguments
from .tool_discovery import MAX_SEARCH_RESULTS, search_definitions

log = logging.getLogger("lonora.tools")

MAX_CAPABILITY_INVENTORY_CHARS = 8000
INSPECTOR = "tool_environment"
BRIDGE = "tool_call"
BRIDGE_TOOLS = frozenset({INSPECTOR, BRIDGE})
# Native schema budgets in serialized ToolDefinition JSON characters. The eager
# budget is enforced for every profile combination by the registry tests; the
# promoted budget is enforced when a Run's exposure is chosen. The core set
# carries ranked history recall and granular memory edits: one avoided
# whole-document memory rewrite saves more than the schema characters they add.
# The market set carries the multi-timeframe snapshot and the session clock; the
# promoted budget gave up the same 900 characters (it still holds six typical
# long-tail schemas), so the worst-case native set stays at 29,800 characters.
EAGER_SCHEMA_BUDGET = 25700
PROMOTED_SCHEMA_BUDGET = 4100
MAX_PROMOTED_TOOLS = 6
# Search results carry input schemas up to this many characters in total;
# later results name their required fields and are inspected exactly.
SEARCH_SCHEMA_BUDGET = 16000
INVOCATION = (
    "Call a tool marked invoke=direct by its own name. Call any other tool with tool_call "
    '{"name": <exact name>, "arguments": {...matching its input_schema}}. Both paths run the '
    "same validation, permission, approval, receipt and financial checks."
)
CORE = eager_for("core")


def schema_chars(tool: Tool) -> int:
    return len(tool.definition().model_dump_json())


def proposed_names(call: ToolCall) -> set[str]:
    """Every tool name a call proposes, read through the bridge resolved or not.

    ``resolve_call`` leaves malformed bridge calls (flattened or unexpected keys,
    non-object arguments, a nested bridge, a Hermes-style ``calls`` batch) as
    ``tool_call``. They never dispatch, but prose beside them may still claim
    their outcome, so the reply truth gates read the intended targets. Names are
    case-folded. This grants nothing and runs nothing.
    """
    names = {call.name.strip().casefold()}

    def visit(payload: Any, depth: int) -> None:
        if isinstance(payload, str):
            try:
                payload = json.loads(payload)
            except ValueError:
                return
        if depth > 4:
            return
        if isinstance(payload, list):
            for item in cast(list[Any], payload)[:32]:
                visit(item, depth + 1)
        elif isinstance(payload, dict):
            entry = cast(dict[str, Any], payload)
            target = entry.get("name")
            if isinstance(target, str):
                names.add(target.strip().casefold())
                if target.strip().casefold() == BRIDGE:
                    visit(entry.get("arguments"), depth + 1)
            if "calls" in entry:
                visit(entry["calls"], depth + 1)

    if call.name == BRIDGE:
        visit(call.arguments, 0)
    return names


class ToolRegistry:
    def __init__(self, tools: list[Tool]):
        self.tools = {tool.name: tool for tool in tools}
        if len(self.tools) != len(tools):
            raise LonoraError("duplicate_tool_registration", 500)
        if any(
            (tool.financial and tool.read_only)
            # A financial deadline would cancel after send and create ambiguity.
            or (tool.financial and tool.timeout_seconds is not None)
            or (tool.timeout_seconds is not None and not 0 < tool.timeout_seconds <= 600)
            # Pollers are repeated observations; a repeated effect is never one.
            or (tool.poller and not tool.read_only)
            for tool in tools
        ):
            raise LonoraError("tool_effect_contract_invalid", 500)
        if BRIDGE_TOOLS & self.tools.keys():
            raise LonoraError("duplicate_tool_registration", 500)
        self.tools[INSPECTOR] = Tool(
            INSPECTOR,
            "Discover capabilities by query using concise English catalog terms, list bounded "
            "metadata, or inspect an exact tool_name for its input schema and current "
            "availability. Call a discovered tool that is not in your native tool list through "
            "tool_call. Discovery grants no authority.",
            EnvironmentInput,
            self.inspect_environment,
            True,
            toolset="core",
            eager=CORE,
        )
        self.tools[BRIDGE] = Tool(
            BRIDGE,
            "Invoke any listed capability that is not in your native tool list by its exact "
            "name, with arguments matching its input_schema from tool_environment. Native tools "
            "are called directly. The call runs through the same validation, permission, "
            "approval, receipt and financial checks as a direct call and grants no authority.",
            BridgeInput,
            self.unresolved_bridge,
            True,
            toolset="core",
            eager=CORE,
        )

    def resolve_call(self, call: ToolCall) -> ToolCall:
        """Unwrap a well-formed bridge call into the real call, keeping its id.

        Every later boundary (planner, guardrails, inflight markers, receipts,
        approvals, financial truth and reconciliation, policy chapters, the
        persisted transcript) then sees the same call a direct invocation would
        have produced. Anything that does not name a registered tool stays a
        ``tool_call`` and fails in ``unresolved_bridge`` without any effect.
        """
        if call.name != BRIDGE or set(call.arguments) - {"name", "arguments"}:
            return call
        target, arguments = call.arguments.get("name"), call.arguments.get("arguments")
        if isinstance(target, str):
            target = target.strip()
        if arguments is None or (isinstance(arguments, str) and not arguments.strip()):
            arguments = {}
        if isinstance(arguments, str):
            try:
                arguments = json.loads(arguments)
            except ValueError:
                return call
        if (
            not isinstance(target, str)
            or target not in self.tools
            or target in BRIDGE_TOOLS
            or not isinstance(arguments, dict)
        ):
            return call
        return ToolCall(id=call.id, name=target, arguments=cast(dict[str, Any], arguments))

    def resolve_calls(self, calls: Sequence[ToolCall]) -> list[ToolCall]:
        return [self.resolve_call(call) for call in calls]

    async def unresolved_bridge(self, _: ToolContext, arguments: dict[str, Any]) -> dict[str, Any]:
        """Only calls resolve_call could not unwrap reach this; it never dispatches."""
        name = arguments["name"]
        if name in BRIDGE_TOOLS:
            raise LonoraError("tool_call_target_invalid", 400)
        if name in self.tools:
            # A known target that bypassed reply-intake resolution must not run
            # here: that would skip the loop's per-call effect boundaries.
            raise LonoraError("tool_call_unresolved", 409)
        raise LonoraError("tool_call_target_unknown", 404)

    async def availability(
        self, context: ToolContext, tools: Iterable[Tool] | None = None
    ) -> dict[str, str]:
        """Codes for tools whose backend is not configured; presentation only.

        A failing check never hides a capability: the handler stays authoritative.
        A check depends only on the context, so one shared by several tools runs
        once per call.
        """
        unavailable: dict[str, str] = {}
        checked: dict[AvailabilityCheck, str | None] = {}
        for tool in self.tools.values() if tools is None else tools:
            check = tool.availability
            if check is None:
                continue
            if check not in checked:
                checked[check] = None
                try:
                    checked[check] = await check(context)
                except LonoraError as error:
                    if error.code == "stale_lease":
                        raise
                    log.warning(
                        "tool_availability_check_failed name=%s code=%s", tool.name, error.code
                    )
                except Exception as error:
                    log.warning(
                        "tool_availability_check_failed name=%s type=%s",
                        tool.name,
                        type(error).__name__,
                    )
            reason = checked[check]
            if reason:
                unavailable[tool.name] = reason
        return unavailable

    def eager_names(
        self, profiles: Collection[ExposureProfile], scope: ToolScope = "full"
    ) -> list[str]:
        """The profiles' eager working set in deterministic registry order."""
        return [
            name
            for name, tool in self.tools.items()
            if tool.eager & set(profiles) and tool.permitted(scope)
        ]

    def exposure(
        self,
        profiles: Collection[ExposureProfile],
        *,
        scope: ToolScope = "full",
        remembered: Sequence[str] = (),
        unavailable: Mapping[str, str] | None = None,
    ) -> tuple[list[str], list[str]]:
        """Choose a Run's native tool names once: (native, promoted).

        The eager set minus unavailable tools, plus remembered long-tail tools
        in recency order within MAX_PROMOTED_TOOLS and PROMOTED_SCHEMA_BUDGET.
        The bridge tools are always native.
        """
        missing = unavailable or {}
        chosen = {
            name
            for name in self.eager_names(profiles, scope)
            if name in BRIDGE_TOOLS or name not in missing
        } | BRIDGE_TOOLS
        promoted: list[str] = []
        used = 0
        for name in remembered:
            tool = self.tools.get(name)
            if tool is None or name in chosen or name in missing or not tool.permitted(scope):
                continue
            if len(promoted) >= MAX_PROMOTED_TOOLS:
                break
            size = schema_chars(tool)
            if used + size > PROMOTED_SCHEMA_BUDGET:
                continue
            promoted.append(name)
            chosen.add(name)
            used += size
        return [name for name in self.tools if name in chosen], promoted

    def native_definitions(
        self, names: Collection[str], scope: ToolScope = "full"
    ) -> list[ToolDefinition]:
        """Native schemas for a frozen exposure, in registry order.

        Names no longer registered or outside the current scope are dropped;
        the bridge tools are always present.
        """
        return [
            tool.definition()
            for name, tool in self.tools.items()
            if (name in names or name in BRIDGE_TOOLS) and tool.permitted(scope)
        ]

    def describe(
        self,
        tool: Tool,
        native: Collection[str],
        unavailable: Mapping[str, str],
        *,
        schema: bool = True,
    ) -> dict[str, Any]:
        entry = tool.environment(schema=schema)
        entry["invoke"] = "direct" if tool.name in native or tool.name in BRIDGE_TOOLS else BRIDGE
        reason = unavailable.get(tool.name)
        entry["available"] = reason is None
        if reason is not None:
            entry["unavailable_reason"] = reason
        return entry

    async def inspect_environment(
        self, context: ToolContext, arguments: dict[str, Any]
    ) -> dict[str, Any]:
        async with context.db.sessions() as session:
            run = await require_lease(session, context.lease)
            scope = run_scope(run.trigger, run.model_metadata)
            exposure: Any = run.execution_state.get("tool_exposure")
        native: set[str] = set()
        if isinstance(exposure, dict):
            listed = cast(dict[str, Any], exposure).get("native")
            if isinstance(listed, list):
                native = {name for name in cast(list[Any], listed) if isinstance(name, str)}
        allowed = [tool for tool in self.tools.values() if tool.permitted(scope)]
        name = arguments.get("tool_name")
        if name:
            tool = next((tool for tool in allowed if tool.name == name), None)
            if tool is None:
                raise LonoraError("tool_not_allowed", 403)
            unavailable = await self.availability(context, [tool])
            return {
                "tool": self.describe(tool, native, unavailable),
                "invocation": INVOCATION,
                "execution_authorized": False,
            }
        offset, limit = arguments.get("offset", 0), arguments.get("limit", 20)
        if arguments.get("query"):
            names = search_definitions(
                [tool.definition() for tool in allowed],
                arguments["query"],
                min(limit, MAX_SEARCH_RESULTS),
            )
            found = [self.tools[name] for name in names]
            unavailable = await self.availability(context, found)
            entries: list[dict[str, Any]] = []
            budget = SEARCH_SCHEMA_BUDGET
            for tool in found:
                entry = self.describe(tool, native, unavailable, schema=False)
                parameters = tool.definition().parameters
                size = len(json.dumps(parameters, ensure_ascii=False))
                if size <= budget:
                    entry["input_schema"] = parameters
                    budget -= size
                else:
                    entry["input_schema_omitted"] = True
                    entry["required"] = parameters.get("required", [])
                entries.append(entry)
            return {
                "tools": entries,
                "total": len(names),
                "next_offset": None,
                "invocation": INVOCATION,
                "execution_authorized": False,
            }
        page = allowed[offset : offset + limit]
        unavailable = await self.availability(context, page)
        return {
            "tools": [self.describe(tool, native, unavailable, schema=False) for tool in page],
            "total": len(allowed),
            "next_offset": offset + limit if offset + limit < len(allowed) else None,
            "invocation": INVOCATION,
            "execution_authorized": False,
        }

    def definitions(self, scope: ToolScope = "full") -> list[ToolDefinition]:
        return [tool.definition() for tool in self.tools.values() if tool.permitted(scope)]

    def names(self, scope: ToolScope = "full") -> set[str]:
        """Current permitted membership without generating native JSON schemas."""
        return {name for name, tool in self.tools.items() if tool.permitted(scope)}

    def capability_inventory(
        self, scope: ToolScope = "full", unavailable: Mapping[str, str] | None = None
    ) -> str:
        """Bounded names from the current permitted registry, never a second catalog.

        Grouped by toolset. A Run computes ``unavailable`` once, so the text is
        stable for the whole Run and keeps the reusable prompt prefix intact.
        """
        families: dict[str, list[str]] = {}
        for name, tool in sorted(self.tools.items()):
            if not tool.permitted(scope):
                continue
            family = (
                tool.toolset
                or getattr(tool.handler, "__module__", "capabilities").rsplit(".", 1)[-1]
            )
            families.setdefault(family, []).append(name)
        total = sum(len(names) for names in families.values())
        prefix = (
            "Current capability inventory from the permitted live registry. Your native tool "
            "list is this Run's working set, not the full set of abilities. Call a native tool "
            "by its own name. Call any other capability below with tool_call, using its exact "
            "name and arguments; inspect it with tool_environment first when you do not know "
            "its input schema, and before claiming an ability is absent. Registered does not "
            "establish account authority or permission; execution still validates all current "
            "boundaries. Historical self-descriptions do not override this current inventory.\n"
            "<available_capabilities>\n"
        )
        missing = sorted(
            (name, code)
            for name, code in (unavailable or {}).items()
            if name in self.tools and self.tools[name].permitted(scope)
        )
        notice = ""
        if missing:
            notice = (
                "unavailable_now (backend or permission missing when this Run started; calls "
                "fail with the code unless that changed): "
                + ", ".join(f"{name}={code}" for name, code in missing)
            )[:1200] + "\n"
        lines: list[str] = []
        shown = 0
        # Reserve enough space for a bounded count/footer even for a large registry.
        budget = MAX_CAPABILITY_INVENTORY_CHARS - len(prefix) - len(notice) - 250
        for family, names in sorted(families.items()):
            line = family + ": "
            included = 0
            for name in names:
                piece = (", " if included else "") + name
                if len(line) + len(piece) > budget:
                    break
                line += piece
                included += 1
            if included:
                lines.append(line)
                shown += included
                budget -= len(line) + 1
            if included < len(names):
                break
        return (
            prefix
            + "\n".join(lines)
            + "\n"
            + notice
            + f"Listed {shown} of {total} permitted capabilities. "
            "Use tool_environment without a query to paginate complete metadata if needed.\n"
            "</available_capabilities>"
        )

    async def execute(
        self, call: ToolCall, context: ToolContext, scope: ToolScope = "full"
    ) -> dict[str, Any]:
        tool = self.tools.get(call.name)
        if tool is None:
            raise LonoraError("tool_not_allowed", 403)
        if tool.financial and scope != "full":
            raise LonoraError("observe_only_execution_forbidden", 403)
        if not tool.permitted(scope):
            raise LonoraError("tool_not_allowed", 403)
        async with context.db.sessions() as session:
            run = await require_lease(session, context.lease)
            if tool.financial:
                # The Run row, not the caller's scope, is authoritative.
                if run_scope(run.trigger, run.model_metadata) != "full":
                    raise LonoraError("observe_only_execution_forbidden", 403)
                # The financial implementation checks current permission before
                # preparing a new action. Keep completed receipt retrieval
                # possible after downgrade; the executor rechecks before send.
        timeout = tool.dispatch_timeout()
        if timeout is None:
            return await self.dispatch(tool, call, context)
        # TimeoutError keeps the loop's existing classification: an observation
        # for a read, tool_execution_uncertain for an interrupted mutation.
        async with asyncio.timeout(timeout):
            return await self.dispatch(tool, call, context)

    async def dispatch(self, tool: Tool, call: ToolCall, context: ToolContext) -> dict[str, Any]:
        arguments = await prepare_market_arguments(
            context, call.name, dict(call.arguments), tool.input_type
        )
        arguments = validate_arguments(tool.input_type, arguments)
        arguments = await guard_market_tool(context, call.name, arguments, read=tool.read_only)
        result = await tool.handler(context.for_call(call.id), arguments)
        return await scope_market_result(context, call.name, result, arguments)
