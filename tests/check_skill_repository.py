"""Agent -> pinned public repository inspection -> durable result, no activation."""

import asyncio
import json
from io import BytesIO
from typing import Any
from unittest.mock import patch
from zipfile import ZipFile

import httpx
from check_streaming import Fixture
from lonora_adapter_kit.types import ModelMessage, ModelReply, ToolCall
from lonora_agent.executor import execute_run
from lonora_agent.skills.repository import inspect_repository
from lonora_contracts.model_routing import ModelSelection
from lonora_db.schema import RunRow, SkillRow, TradingJournalRow
from lonora_tools.loader import load_tools
from sqlalchemy import func, select


async def main() -> None:
    fixture = await Fixture().open()
    try:
        agent = await fixture.agent("Repository inspection")
        thread = await fixture.conversation(agent)
        context = await fixture.lease(await fixture.run(agent, thread))
        data = BytesIO()
        with ZipFile(data, "w") as archive:
            archive.writestr(
                "root/analysis/SKILL.md",
                "---\nname: analysis\ndescription: Review historical evidence.\n---\n# Analysis\nUse current verified inputs.",
            )
            archive.writestr("root/analysis/probe.py", "raise RuntimeError('never execute')")

        def transport(request: httpx.Request) -> httpx.Response:
            if request.url.host == "api.github.com":
                return httpx.Response(200, json=[{"sha": "b" * 40}])
            assert request.url.host == "codeload.github.com"
            return httpx.Response(200, content=data.getvalue())

        async def inspect(url: str, ref: str) -> dict[str, Any]:
            async with httpx.AsyncClient(transport=httpx.MockTransport(transport)) as client:
                return await inspect_repository(url, ref, client=client)

        rounds = 0

        async def model(
            _capability: Any, messages: list[ModelMessage], _tools: Any, **_kwargs: Any
        ):
            nonlocal rounds
            rounds += 1
            if rounds == 1:
                reply = ModelReply(
                    tool_calls=[
                        ToolCall(
                            id="inspect-package",
                            name="skill_repository_inspect",
                            arguments={"repository_url": "https://github.com/example/analysis"},
                        )
                    ]
                )
            else:
                observation = next(
                    message
                    for message in messages
                    if message.role == "tool" and message.tool_call_id == "inspect-package"
                )
                result = json.loads(observation.content)
                assert result["ok"] and result["commit"] == "b" * 40
                assert result["skills"][0]["requires_isolated_execution"]
                assert result["code_executed"] is result["installed"] is False
                reply = ModelReply(text="The package needs adaptation before it can be used.")
            return reply, ModelSelection(provider="openai", model="scripted-inspection")

        async with fixture.runtime.db.sessions() as session:
            skills_before = await session.scalar(select(func.count()).select_from(SkillRow))
            journal_before = await session.scalar(
                select(func.count()).select_from(TradingJournalRow)
            )
        with (
            patch("lonora_agent.skills.repository.inspect_repository", inspect),
            patch.object(context.router, "complete", model),
        ):
            await execute_run(context, load_tools(), 120, 5)
        async with fixture.runtime.db.sessions() as session:
            run = await session.get(RunRow, context.lease.run_id)
            assert run and run.status == "completed"
            assert await session.scalar(select(func.count()).select_from(SkillRow)) == skills_before
            assert (
                await session.scalar(select(func.count()).select_from(TradingJournalRow))
                == journal_before
            )
            assert run.model_metadata["skill_selection"]["selected_skill_ids"] == []
        print(
            "PASS Agent inspection pins a repository revision without executing source, installing instructions or creating financial operations"
        )
    finally:
        await fixture.close()


if __name__ == "__main__":
    asyncio.run(main())
