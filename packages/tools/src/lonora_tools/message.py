from typing import Any

from lonora_contracts.domain import Contract
from pydantic import Field

from .base import Tool
from .context import ToolContext


class PeerInput(Contract):
    agent_id: str
    task: str = Field(min_length=1, max_length=8000)


async def send(context: ToolContext, args: dict[str, Any]) -> dict[str, Any]:
    from lonora_agent.collaboration.peer_messages import delegate_peer

    return await delegate_peer(context, args["agent_id"], args["task"])


def tools() -> list[Tool]:
    return [
        Tool(
            "peer_send",
            "Ask an existing owned agent for help. Its outcome returns durably to this run/thread.",
            PeerInput,
            send,
        )
    ]
