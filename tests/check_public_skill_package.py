"""Optional real public source -> owned catalog -> actual isolated utility acceptance.

Requires an explicit reviewed local image ID, HTTPS and disposable PostgreSQL.
No source executes on the host or acquires broker authority.
"""

import asyncio
import json
import sys
from dataclasses import replace
from typing import Any

from check_streaming import Fixture
from lonora_adapter_kit.types import ToolCall
from lonora_agent.skills.access import RunSkillAccess
from lonora_agent.skills.repository import inspect_repository
from lonora_agent.workspace import AnalyticalContainer
from lonora_agent.workspace_access import RunWorkspaceAccess
from lonora_db.schema import TradeApprovalRow, TradingJournalRow
from lonora_tools.loader import load_tools
from sqlalchemy import func, select

COMMIT = "3d0f4ef6986f4984b7c6bd46f7ff4f87744c3abd"


async def main() -> None:
    f = await Fixture().open()
    try:
        r = load_tools()
        a = await f.agent("Public skill validation")
        t = await f.conversation(a)
        c = replace(
            await f.lease(await f.run(a, t)),
            workspace_access=RunWorkspaceAccess(AnalyticalContainer(sys.argv[1])),
            skill_access=RunSkillAccess(r, ()),
        )
        report = await inspect_repository(
            "https://github.com/Jakeschincariol/day-trader-skill", COMMIT
        )
        assert report["commit"] == COMMIT and len(report["skills"]) == 11
        args: dict[str, Any] = {
            "repository_url": "https://github.com/Jakeschincariol/day-trader-skill",
            "commit": COMMIT,
            "source_path": "trader-budget/SKILL.md",
            "version": "1.0.0",
            "expected_version": 0,
            "workspace_revision": 1,
            "adapted_content": "---\nname: trader-budget\ndescription: Inspect an isolated historical US-equity allocation calculation.\n---\nRun the preserved utility only in isolated analysis. It computes US-stock proposals, not broker executions. Whole shares and dollar prices cannot be substituted for broker lots or XAUUSDm risk sizing. Financial actions always use the existing verified executor.\n",
            "review": {
                "source_behavior": "Sizes whole US-equity shares or historical budget weights and writes proposals without placing orders.",
                "adapted_behavior": "Preserve the stock allocation calculation as a networkless diagnostic only; no conversion to broker lots or trade execution.",
                "assumptions": [
                    "Declared stock budget scenario only, not current broker account data."
                ],
                "limitations": [
                    "Whole-share sizing is incompatible with XAUUSDm lots without verified contract/tick monetary metadata; no gold adaptation or semantic-equivalence claim."
                ],
            },
        }
        await r.execute(
            ToolCall(
                id="scenario-input",
                name="workspace_update",
                arguments={
                    "revision": 0,
                    "files": {"scenario-prices.json": json.dumps({"AAPL": 100})},
                },
            ),
            c,
        )
        imported = await r.execute(
            ToolCall(id="public-import", name="skill_package_import", arguments=args), c
        )
        validated = await r.execute(
            ToolCall(
                id="public-test",
                name="skill_package_validate",
                arguments={
                    "skill_id": "trader-budget",
                    "expected_version": imported["resource_version"],
                    "workspace_revision": imported["workspace_revision"],
                    "utility_path": "skills/trader-budget/1.0.0/size.py",
                    "arguments": [
                        "--weights",
                        "AAPL=100",
                        "--budget",
                        "1000",
                        "--prices",
                        "scenario-prices.json",
                        "--json",
                    ],
                },
            ),
            c,
        )
        assert validated["exit_code"] == 0, validated
        values = json.loads(validated["stdout"])
        assert "result" in values and "orders" in values
        assert not validated["authority_granted"] and not validated["semantic_equivalence_verified"]
        active = await r.execute(
            ToolCall(
                id="public-activate",
                name="skill_package_control",
                arguments={
                    "skill_id": "trader-budget",
                    "expected_version": validated["resource_version"],
                    "workspace_revision": validated["workspace_revision"],
                    "action": "activate",
                },
            ),
            c,
        )
        assert active["enabled"]
        async with f.runtime.db.sessions() as s:
            assert not await s.scalar(select(func.count()).select_from(TradingJournalRow))
            assert not await s.scalar(select(func.count()).select_from(TradeApprovalRow))
        print(
            "PASS actual pinned public repository11Skills -> adapted diagnostic import -> real isolated original utility stock allocation -> current-version activation; zero financial effects, gold lot adaptation explicitly unsupported"
        )
        print(
            json.dumps(
                {
                    "commit": COMMIT,
                    "source_path": args["source_path"],
                    "archive_sha256": imported["archive_sha256"],
                    "scenario_output": values,
                    "limitations": args["review"]["limitations"],
                },
                indent=2,
            )
        )
    finally:
        await f.close()


if __name__ == "__main__":
    if len(sys.argv) != 2:
        raise SystemExit("Pass the administrator-reviewed full local analysis image ID")
    asyncio.run(main())
