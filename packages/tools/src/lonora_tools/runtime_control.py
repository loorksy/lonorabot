from typing import Any

from lonora_contracts.domain import Contract
from lonora_trading.controls import read_controls
from pydantic import Field

from .base import Tool
from .context import ToolContext
from .memory import Empty


class WaitInput(Contract):
    question: str = Field(min_length=1, max_length=8000)


async def status(context: ToolContext, args: dict[str, Any]) -> dict[str, Any]:
    return {
        "run_id": context.lease.run_id,
        "trading": (await read_controls(context.db)).model_dump(),
    }


async def wait(context: ToolContext, args: dict[str, Any]) -> dict[str, Any]:
    return {"_runtime_wait": True, "question": args["question"]}


async def silence(context: ToolContext, args: dict[str, Any]) -> dict[str, Any]:
    return {"_runtime_silence": True}


def tools() -> list[Tool]:
    return [
        Tool(
            "runtime_status",
            "Read runtime and global financial controls; this tool cannot enable trading.",
            Empty,
            status,
            True,
        ),
        Tool(
            "wait_for_input",
            "Persist the run as waiting_input and ask the user a question before continuing.",
            WaitInput,
            wait,
        ),
        Tool(
            "group_silence",
            "Choose silence when a group reply would add no useful information.",
            Empty,
            silence,
            True,
        ),
    ]
