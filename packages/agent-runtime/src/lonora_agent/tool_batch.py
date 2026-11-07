"""Ordered parallel/serial segments for one assistant tool-call block.

Adapted from Hermes Agent ``agent/tool_dispatch_helpers.py``
(``_plan_tool_batch_segments``) and ``agent/tool_executor.py``
(``execute_tool_calls_segmented``). Source: NousResearch/hermes-agent, MIT
License, Copyright (c) 2025 Nous Research. Lonora admits a call to a parallel
segment from the server Tool registry only (read-only, non-financial and
``parallel_safe``); path scoping and terminal heuristics were not ported.

Call order is preserved exactly: a later call never crosses an earlier barrier,
so results, checkpoints and effect boundaries match fully serial execution.
Every mutating, financial, waiting or unknown call is a barrier executed alone
with the existing checkpoint-before-effect semantics.
"""

import asyncio
from collections.abc import Awaitable, Callable, Mapping, Sequence
from dataclasses import dataclass
from typing import Literal

from lonora_adapter_kit.types import ToolCall
from lonora_tools.base import Tool

# One run's reads share the process-wide database pool and broker sessions with
# every other worker; keep a single block from monopolising them.
MAXIMUM_PARALLEL_TOOLS = 4


@dataclass(frozen=True)
class Segment:
    kind: Literal["parallel", "serial"]
    calls: tuple[ToolCall, ...]


def parallel_admissible(call: ToolCall, tools: Mapping[str, Tool]) -> bool:
    tool = tools.get(call.name)
    return tool is not None and tool.runs_in_parallel()


def plan_segments(calls: Sequence[ToolCall], tools: Mapping[str, Tool]) -> list[Segment]:
    """Split calls into ordered segments; runs shorter than two stay serial.

    Serial segments always hold exactly one call so steering, retry deadlines
    and the inflight marker keep their per-call boundaries.
    """
    segments: list[Segment] = []
    current: list[ToolCall] = []

    def close() -> None:
        if len(current) >= 2:
            segments.append(Segment("parallel", tuple(current)))
        else:
            segments.extend(Segment("serial", (call,)) for call in current)
        current.clear()

    for call in calls:
        if parallel_admissible(call, tools):
            current.append(call)
            continue
        close()
        segments.append(Segment("serial", (call,)))
    close()
    return segments


def next_segment(calls: Sequence[ToolCall], tools: Mapping[str, Tool]) -> Segment:
    if not calls:
        raise ValueError("empty tool block")
    return plan_segments(calls, tools)[0]


async def gather_bounded[T](
    factories: Sequence[Callable[[], Awaitable[T]]], limit: int = MAXIMUM_PARALLEL_TOOLS
) -> list[T]:
    """Run independent awaitables with bounded overlap and ordered results.

    Callers convert ordinary tool failures into observations before they reach
    here. Anything that still escapes (stale lease, revoked skill authority,
    cancellation) cancels the sibling handlers before it propagates, so no
    orphaned handler can keep working after this run lost its authority.
    """
    if limit < 1:
        raise ValueError("parallel limit must be positive")
    semaphore = asyncio.Semaphore(limit)

    async def bounded(factory: Callable[[], Awaitable[T]]) -> T:
        async with semaphore:
            return await factory()

    tasks = [asyncio.ensure_future(bounded(factory)) for factory in factories]
    try:
        return list(await asyncio.gather(*tasks))
    except BaseException:
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
        raise
