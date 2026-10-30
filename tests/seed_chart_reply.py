"""Browser/native fixture using real server state and executor; model replies are scripted."""

import asyncio
import json
import os
import sys
from pathlib import Path
from typing import Any
from unittest.mock import patch
from uuid import uuid4

from check_streaming import Fixture
from lonora_adapter_kit.types import ModelReply, ToolCall
from lonora_agent.executor import execute_run
from lonora_contracts.model_routing import ModelSelection
from lonora_db.schema import MessageRow
from lonora_security.runtime_storage import confined_path
from lonora_tools.loader import load_tools
from sqlalchemy import select

UI_ARTIFACT_ROOT = str(Path(__file__).resolve().parent.parent / ".runtime/ui-regression-artifacts")


async def fixture_data(data: dict[str, Any]) -> dict[str, Any]:
    os.environ.setdefault(
        "LONORA_ARTIFACT_ROOT",
        UI_ARTIFACT_ROOT,
    )
    fixture = await Fixture().open()
    try:
        if data.get("action") == "cleanup":
            await fixture.request("DELETE", "/agents/" + data["agent_id"])
            await fixture.request("DELETE", "/trading/connections/" + data["connection_id"])
            path = confined_path(fixture.settings.artifact_root, data["artifact_key"])
            path.unlink(missing_ok=True)
            if path.parent.is_dir():
                path.parent.rmdir()
            return {"cleaned": True}
        agent = await fixture.agent("Actual chart image fixture")
        thread = await fixture.conversation(agent)
        context = await fixture.lease(await fixture.run(agent, thread))
        connection = await fixture.request(
            "POST",
            "/trading/connections",
            {
                "provider": "simulation",
                "account_id": "chart-ui-fixture-" + uuid4().hex,
                "enabled": True,
            },
        )
        await fixture.request(
            "POST",
            "/trading/connections/" + connection["id"] + "/simulation",
            {
                "snapshot": {
                    "balance": "1000",
                    "currency": "USD",
                    "instruments": [
                        {
                            "symbol": "XAUUSD",
                            "description": "Explicit simulation gold fixture",
                            "digits": 2,
                            "tick_size": "0.01",
                            "volume_min": "0.01",
                            "volume_max": "100",
                            "volume_step": "0.01",
                        }
                    ],
                    "candles": {
                        "XAUUSD:1h": [
                            {
                                "symbol": "XAUUSD",
                                "timeframe": "1h",
                                "time": f"2026-10-01T{index:02d}:00:00Z",
                                "open": str(100 + index),
                                "high": str(104 + index),
                                "low": str(99 + index),
                                "close": str(102 + index),
                            }
                            for index in range(20)
                        ]
                    },
                }
            },
        )
        registry = load_tools()
        chart = await registry.execute(
            ToolCall(
                id="open",
                name="chart_open",
                arguments={
                    "account_id": connection["id"],
                    "symbol": "XAUUSD",
                    "timeframe": "1h",
                    "indicators": [{"name": "rsi", "period": 14}],
                    "annotations": [{"type": "price", "price": 110, "label": "Fixture support"}],
                },
            ),
            context,
        )
        scripted = [
            ModelReply(
                tool_calls=[
                    ToolCall(
                        id="snapshot",
                        name="chart_snapshot",
                        arguments={"chart_id": chart["chart"]["id"]},
                    )
                ]
            ),
            ModelReply(text="Original generated chart image."),
        ]

        async def model(*args: Any, **kwargs: Any):
            assert scripted
            return scripted.pop(0), ModelSelection(
                provider="openai", model="explicit-chart-ui-fixture"
            )

        with patch("lonora_agent.tool_loop.model_turn", model):
            await execute_run(context, registry, 90, 8)
        async with fixture.runtime.db.sessions() as session:
            first = await session.scalar(
                select(MessageRow).where(
                    MessageRow.thread_id == thread["id"], MessageRow.role == "assistant"
                )
            )
            assert first is not None
            original_file = await fixture.request("GET", "/artifacts/" + first.attachment_ids[0])
        context = await fixture.lease(await fixture.run(agent, thread))
        scripted.append(
            ModelReply(
                text="Here is the saved XAUUSD chart image.\n![chart](sandbox:/mnt/data/"
                + original_file["payload"]["key"]
                + ")"
            )
        )
        with patch("lonora_agent.tool_loop.model_turn", model):
            await execute_run(context, registry, 90, 8)
        async with fixture.runtime.db.sessions() as session:
            message = await session.scalar(
                select(MessageRow)
                .where(MessageRow.thread_id == thread["id"], MessageRow.role == "assistant")
                .order_by(MessageRow.seq.desc())
                .limit(1)
            )
            assert message is not None and len(message.attachment_ids) == 1
            artifact = await fixture.request("GET", "/artifacts/" + message.attachment_ids[0])
        return {
            "cookies": [
                {"name": cookie.name, "value": cookie.value}
                for cookie in fixture.client.cookies.jar
            ],
            "agent_id": agent["id"],
            "agent_name": agent["name"],
            "thread_id": thread["id"],
            "chart_id": chart["chart"]["id"],
            "artifact_id": artifact["id"],
            "artifact_key": artifact["payload"]["key"],
            "connection_id": connection["id"],
            "message_id": message.id,
        }
    finally:
        await fixture.close(cleanup=False)


if __name__ == "__main__":
    print(json.dumps(asyncio.run(fixture_data(json.load(sys.stdin)))))
