"""Create a real waiting-input Run for browser acceptance; scripted model, no broker calls."""

import asyncio
import json
import sys
from typing import Any
from unittest.mock import patch
from uuid import uuid4

from check_streaming import Fixture
from lonora_adapter_kit.types import ModelReply, ToolCall
from lonora_agent.executor import execute_run
from lonora_contracts.model_routing import ModelSelection
from lonora_tools.loader import load_tools


async def create(data: dict[str, Any]) -> dict[str, Any]:
    fixture = await Fixture().open()
    try:
        agent = await fixture.agent("Question browser")
        thread = await fixture.conversation(agent)
        run = await fixture.run(agent, thread)
        context = await fixture.lease(run)
        arabic = data.get("locale") == "ar"
        question = "هل تريد تحليل السوق؟" if arabic else "Would you like a market analysis?"
        choices = (
            [{"id": "analysis", "label": "نعم، حلل السوق"}, {"id": "wait", "label": "لا، انتظر"}]
            if arabic
            else [
                {"id": "analysis", "label": "Yes, analyze the market"},
                {"id": "wait", "label": "No, wait"},
            ]
        )
        identity = "browser-question-" + uuid4().hex

        async def complete(*args: Any, **kwargs: Any):
            return ModelReply(
                tool_calls=[
                    ToolCall(
                        id=identity,
                        name="wait_for_input",
                        arguments={"question": question, "choices": choices},
                    )
                ]
            ), ModelSelection(provider="openai", model="explicit-question-browser")

        with patch.object(context.router, "complete", complete):
            await execute_run(context, load_tools(), 120, 4)
        current = await fixture.request("GET", "/runs/" + run["id"])
        assert current["status"] == "waiting_input"
        assert current["input_request"]["id"] == identity
        return {
            "agent": agent,
            "thread": thread,
            "run": current,
            "question": current["input_request"],
            "cookies": [
                {"name": cookie.name, "value": cookie.value}
                for cookie in fixture.client.cookies.jar
            ],
        }
    finally:
        # Browser uses these persisted rows; cleanup is authenticated through its API.
        await fixture.close(cleanup=False)


if __name__ == "__main__":
    print(json.dumps(asyncio.run(create(json.load(sys.stdin)))))
