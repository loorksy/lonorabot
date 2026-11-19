from typing import Any

from lonora_contracts.domain import Contract
from lonora_contracts.model_routing import ModelSelection
from pydantic import Field

from .base import Tool
from .context import ToolContext


class SubagentInput(Contract):
    task: str = Field(min_length=1, max_length=8000)
    model: ModelSelection | None = Field(
        default=None,
        description="Another available model for this helper, by exact id; omit to use yours.",
    )


class ChildInput(Contract):
    task: str = Field(min_length=1, max_length=8000)
    name: str = Field(min_length=1, max_length=80)


class InspectInput(Contract):
    run_id: str


async def spawn(context: ToolContext, args: dict[str, Any]) -> dict[str, Any]:
    from lonora_agent.collaboration.subagents import spawn_subagent

    params = SubagentInput.model_validate(args)
    return await spawn_subagent(context, params.task, params.model)


async def inspect(context: ToolContext, args: dict[str, Any]) -> dict[str, Any]:
    from lonora_agent.collaboration.subagents import inspect_subagent

    return await inspect_subagent(context, args["run_id"])


async def child(context: ToolContext, args: dict[str, Any]) -> dict[str, Any]:
    from lonora_agent.collaboration.child_agents import create_child

    return await create_child(context, args["name"], args["task"])


def tools() -> list[Tool]:
    return [
        Tool(
            "subagent_spawn",
            "Start a bounded temporary research run without creating a permanent agent "
            "identity, optionally on another available model.",
            SubagentInput,
            spawn,
        ),
        Tool(
            "subagent_inspect",
            "Inspect the state and outcome of a run this Agent delegated (its subagents, peer "
            "or collaboration requests it sent) or of an agent it supervises. Other Agents' "
            "runs are run_not_found.",
            InspectInput,
            inspect,
            True,
            poller=True,
        ),
        Tool(
            "child_agent_create",
            "Compatibility only: a child identity under your own scope with its own thread "
            "and memory. For a persistent agent the owner asks for, use agent_create.",
            ChildInput,
            child,
        ),
    ]
