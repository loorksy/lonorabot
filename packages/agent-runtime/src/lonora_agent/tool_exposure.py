"""Per-Run native tool exposure, chosen once and frozen in the checkpoint.

The eager working set comes from Tool metadata (``Tool.eager`` profiles); the
agent's remembered long-tail tools are promoted within a bounded budget; tools
whose backend is not configured are left out and named in the inventory. The
native tools array is therefore identical on every model turn of a Run, which
keeps the provider's reusable prompt prefix intact, while every registered
capability stays callable through the ``tool_call`` bridge. Nothing here
grants or removes authority: execution validates every call.
"""

import logging
from typing import Any, cast

from lonora_adapter_kit.types import ModelMessage, ToolCall, ToolDefinition
from lonora_core.user_error import LonoraError
from lonora_db.agent_binding import agent_binding
from lonora_db.schema import AgentRow, RunRow, ThreadRow
from lonora_db.supervision import supervised_ids
from lonora_db.threads import thread_options
from lonora_db.tool_usage import record_tool_use, remembered_tools
from lonora_tools.base import EXPOSURE_PROFILES, ExposureProfile, ToolScope
from lonora_tools.context import ToolContext
from lonora_tools.registry import BRIDGE_TOOLS, ToolRegistry

from .context.command import owner_command

log = logging.getLogger("lonora.tool_loop")

EXPOSURE_VERSION = 1


def run_profiles(
    agent: AgentRow, task_run: bool, *, supervises: bool = False
) -> list[ExposureProfile]:
    """``market`` for trading identities: an agent bound to a broker account, and
    the owner's Personal Agent, which reads every owned account and analyzes
    directly when no specialist exists. Other agents get ``research``.

    ``coordination`` (inspect and message the agents it supervises) for the Personal
    Agent, which supervises every agent by default, and for any agent while it holds
    a supervision grant. A trading identity's Task Run leaves it out: its market and
    task schemas fill the eager budget, and coordination stays one tool_call away.
    """
    trading = bool(agent.trading_account_id) or agent.role == "personal"
    profiles: list[ExposureProfile] = ["core", "market" if trading else "research"]
    if (agent.role == "personal" or supervises) and not (trading and task_run):
        profiles.append("coordination")
    if task_run:
        profiles.append("task")
    return profiles


def saved_exposure(state: dict[str, Any]) -> dict[str, Any] | None:
    raw = state.get("tool_exposure")
    if not isinstance(raw, dict):
        return None
    exposure = cast(dict[str, Any], raw)
    if (
        exposure.get("version") != EXPOSURE_VERSION
        or not isinstance(exposure.get("native"), list)
        or not isinstance(exposure.get("profiles"), list)
        or not isinstance(exposure.get("unavailable"), dict)
    ):
        return None
    return exposure


def legacy_names(
    state: dict[str, Any], messages: list[ModelMessage], pending: list[ToolCall]
) -> set[str]:
    """Schemas an older release already presented to this checkpoint's model."""
    discovered: Any = state.get("discovered_tool_names")
    names: set[str] = set()
    if isinstance(discovered, list):
        names = {name for name in cast(list[Any], discovered) if isinstance(name, str)}
    names |= {call.name for message in messages for call in message.tool_calls}
    return names | {call.name for call in pending}


async def ensure_exposure(
    context: ToolContext,
    registry: ToolRegistry,
    state: dict[str, Any],
    messages: list[ModelMessage],
    pending: list[ToolCall],
    *,
    scope: ToolScope,
    task_run: bool,
) -> dict[str, Any]:
    """Return this Run's frozen exposure, choosing it on the Run's first entry."""
    exposure = saved_exposure(state)
    if exposure is not None:
        return exposure
    async with context.db.sessions() as session:
        agent = await agent_binding(session, context.owner_id, context.agent_id)
        remembered = await remembered_tools(session, context.owner_id, context.agent_id)
        supervising = bool(await supervised_ids(session, context.owner_id, context.agent_id))
        thread = await session.get(ThreadRow, context.thread_id)
        run = await session.get(RunRow, context.lease.run_id)
        command = run and await owner_command(session, run.thread_id, run.input_seq)
        # The owner switched on web search for this chat (Q33), or this message is the
        # /search command: its schema is native.
        web_search = (thread is not None and thread_options(thread).web_search) or (
            command is not None and command["name"] == "search"
        )
    profiles = run_profiles(agent, task_run, supervises=supervising)
    unavailable = await registry.availability(context)
    native, promoted = registry.exposure(
        profiles, scope=scope, remembered=remembered, unavailable=unavailable
    )
    # A checkpoint from an earlier release keeps every schema it already showed.
    kept = {
        name
        for name in legacy_names(state, messages, pending)
        if name in registry.tools and registry.tools[name].permitted(scope)
    }
    chosen = set(native) | kept
    if (
        web_search
        and "web_search" in registry.tools
        and registry.tools["web_search"].permitted(scope)
        and "web_search" not in unavailable
    ):
        chosen.add("web_search")
    exposure = {
        "version": EXPOSURE_VERSION,
        "profiles": profiles,
        "native": [name for name in registry.tools if name in chosen],
        "promoted": promoted,
        "unavailable": unavailable,
    }
    state["tool_exposure"] = exposure
    state.pop("discovered_tool_names", None)
    return exposure


def native_definitions(
    registry: ToolRegistry, exposure: dict[str, Any], scope: ToolScope
) -> list[ToolDefinition]:
    return registry.native_definitions(set(cast(list[str], exposure["native"])), scope)


def inventory(registry: ToolRegistry, exposure: dict[str, Any], scope: ToolScope) -> str:
    return registry.capability_inventory(
        scope, cast(dict[str, str], exposure.get("unavailable", {}))
    )


def exposure_profiles(exposure: dict[str, Any]) -> list[ExposureProfile]:
    return [
        profile
        for profile in EXPOSURE_PROFILES
        if profile in cast(list[Any], exposure.get("profiles", []))
    ]


async def remember_use(
    context: ToolContext,
    registry: ToolRegistry,
    exposure: dict[str, Any],
    call: ToolCall,
    result: dict[str, Any],
    *,
    scope: ToolScope,
) -> None:
    """Remember a successful long-tail tool for promotion into later Runs.

    Best effort and presentation only: a failure is logged, never retried and
    never changes the call's observation. Narrowed Runs (helpers share their
    parent's agent id; observe-only wakes are automated) record nothing, so they
    never displace the agent's own tools or change its next tools array.
    """
    if (
        scope != "full"
        or call.name not in registry.tools
        or call.name in BRIDGE_TOOLS
        or result.get("ok") is False
        or call.name in registry.eager_names(exposure_profiles(exposure))
    ):
        return
    try:
        async with context.db.sessions() as session, session.begin():
            await record_tool_use(session, context.owner_id, context.agent_id, call.name)
    except LonoraError as error:
        log.warning("tool_usage_not_recorded name=%s code=%s", call.name, error.code)
    except Exception as error:
        log.warning("tool_usage_not_recorded name=%s type=%s", call.name, type(error).__name__)
