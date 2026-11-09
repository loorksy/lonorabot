"""Ordered parallel/serial segments for one assistant tool-call block.

Adapted from Hermes Agent ``agent/tool_dispatch_helpers.py``
(``_plan_tool_batch_segments``) and ``agent/tool_executor.py``
(``execute_tool_calls_segmented``), source
https://github.com/NousResearch/hermes-agent at revision
a9ff9799e273f525b82718cdc69fdec71b1dca5a. Lonora admits a call to a parallel
segment from the server Tool registry only (read-only, non-financial and
``parallel_safe``); path scoping and terminal heuristics were not ported.

Call order is preserved exactly: a later call never crosses an earlier barrier,
so results, checkpoints and effect boundaries match fully serial execution.
Every mutating, financial, waiting or unknown call is a barrier executed alone
with the existing checkpoint-before-effect semantics.

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
