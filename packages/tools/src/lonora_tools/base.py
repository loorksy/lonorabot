from collections.abc import Awaitable, Callable, Mapping
from dataclasses import dataclass, field
from typing import Any, Literal

from lonora_adapter_kit.types import ToolDefinition
from pydantic import BaseModel

from .context import ToolContext
from .environment import recovery_metadata
from .schema import compact_input_schema

# Dispatch deadlines bound a stuck dependency without changing effect identity.
# Financial operations own broker deadlines and reconciliation; cancelling one
# after send would manufacture ambiguity, so they are never wrapped.
DEFAULT_READ_TIMEOUT_SECONDS = 45.0
DEFAULT_MUTATION_TIMEOUT_SECONDS = 90.0

# Exposure profiles name the working sets a Run receives as native schemas from
# its first model turn. "core" applies to every Run; an agent bound to a broker
# account and the owner's Personal Agent add "market", every other agent
# "research"; a supervisor (the Personal Agent, and any agent while it holds a
# supervision grant) adds "coordination"; durable Task Runs add "task". Exposure is
# presentation only: execution validates every boundary whatever was exposed, and
# any registered tool stays reachable via tool_call.
ExposureProfile = Literal["core", "market", "research", "coordination", "task"]
EXPOSURE_PROFILES: tuple[ExposureProfile, ...] = (
    "core",
    "market",
    "research",
    "coordination",
    "task",
)


def eager_for(*profiles: ExposureProfile) -> frozenset[ExposureProfile]:
    return frozenset(profiles)


# Which registered tools a Run may use. "full" is an ordinary Run. An
# "observe_only" wake (server-authored, about events it did not cause) has no
# financial effects: it keeps memory, watches, routines, peers, owner
# notifications and artifacts. The executor refuses broker mutations from it,
# from its helpers and peer runs (lineage) and from the Tasks and tickets it
# starts (they inherit the narrowing). Watches and routines it sets up
# are the Agent's own later work and fire with the Agent's normal authority,
# still under its signed grant and limits. A "helper" is a temporary subagent:
# reads plus sandbox computation and reports, never memory writes, new agents,
# peer messages or financial tools.
ToolScope = Literal["full", "observe_only", "helper"]
HELPER_EFFECTS = frozenset({"workspace_execute", "artifact_create"})


def run_scope(trigger: str, metadata: Mapping[str, Any]) -> ToolScope:
    if trigger == "subagent":
        return "helper"
    if metadata.get("authority") == "observe_only":
        return "observe_only"
    return "full"


# Returns None when the backend a tool needs is configured, otherwise the code
# its handler would fail with. Presentation only; the handler stays authoritative.
AvailabilityCheck = Callable[[ToolContext], Awaitable[str | None]]


@dataclass(frozen=True)
class Tool:
    name: str
    description: str
    input_type: type[BaseModel]
    handler: Callable[[ToolContext, dict[str, Any]], Awaitable[dict[str, Any]]]
    read_only: bool = False
    financial: bool = False
    replay_safe: bool = False
    legacy_replay_safe: bool = False
    # Read-only handlers that share no per-run mutable state may run beside
    # other independent reads from the same assistant message. Anything that
    # suspends, changes instruction authority or ends the turn stays serial.
    parallel_safe: bool = True
    # Status checks legitimately repeated while monitoring are exempt from the
    # no-progress loop guardrail; they still count genuine failures.
    poller: bool = False
    # None selects the read/mutation default; financial tools are never wrapped.
    timeout_seconds: float | None = None
    # Capability family; also the operating-policy chapter that governs the tool.
    # The loader fills it from the tool's module when a definition leaves it empty.
    toolset: str = ""
    # Profiles whose Runs receive this schema natively from the first turn.
    eager: frozenset[ExposureProfile] = field(default_factory=frozenset[ExposureProfile])
    availability: AvailabilityCheck | None = None
    # Everyday English and Arabic words for this capability that its description does
    # not use. Discovery only: they are matched by tool search, never sent as schema.
    search_terms: str = ""

    def permitted(self, scope: ToolScope) -> bool:
        if scope == "full":
            return True
        if self.financial:
            return False
        return scope == "observe_only" or self.read_only or self.name in HELPER_EFFECTS

    def dispatch_timeout(self) -> float | None:
        if self.financial:
            return None
        if self.timeout_seconds is not None:
            return self.timeout_seconds
        return DEFAULT_READ_TIMEOUT_SECONDS if self.read_only else DEFAULT_MUTATION_TIMEOUT_SECONDS

    def runs_in_parallel(self) -> bool:
        """Only replay-safe observation without effects can overlap another call."""
        return self.read_only and not self.financial and self.parallel_safe

    def environment(self, *, schema: bool = True) -> dict[str, Any]:
        result = {
            "name": self.name,
            "purpose": self.description,
            **recovery_metadata(self.read_only, self.financial),
        }
        if schema:
            result["input_schema"] = self.definition().parameters
        result["crash_replay"] = (
            "read_only"
            if self.read_only
            else "handler_receipt"
            if self.replay_safe
            else "reconcile_required"
        )
        result["legacy_checkpoint_replay"] = self.read_only or self.legacy_replay_safe
        result["batch_execution"] = "parallel_read" if self.runs_in_parallel() else "serial"
        if self.toolset:
            result["toolset"] = self.toolset
        return result

    def definition(self) -> ToolDefinition:
        schema = compact_input_schema(self.input_type.model_json_schema())
        if self.name == "trade_execute":
            schema.get("properties", {}).pop("operation_id", None)
        return ToolDefinition(name=self.name, description=self.description, parameters=schema)
