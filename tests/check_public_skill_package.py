"""Optional real public source -> owned catalog -> utility run in the real workspace.

Requires the workspace supervisor's socket (on the server, inside the Gateway container:
/run/lonora-workspace/supervisor.sock), HTTPS and disposable PostgreSQL. No source
executes on the host or acquires broker authority.
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
from lonora_db.schema import TradeApprovalRow, TradingJournalRow
from lonora_security.secrets import SecretScan
from lonora_tools.loader import load_tools
from lonora_workspace.client import WorkspaceClient
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
            workspace=WorkspaceClient(sys.argv[1]),
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
        # The utility runs in .skill-validation/ in the agent's home.
        assert c.workspace is not None
        await c.workspace.write(
            SecretScan({}),
            c.agent_id,
            ".skill-validation/scenario-prices.json",
            json.dumps({"AAPL": 100}).encode(),
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
            "PASS actual pinned public repository11Skills -> adapted diagnostic import -> original utility run in the workspace (stock allocation) -> current-version activation; zero financial effects, gold lot adaptation explicitly unsupported"
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
        raise SystemExit("Pass the workspace supervisor's socket path")
    asyncio.run(main())
