"""Real PostgreSQL/UI fixture: generated SVG attachment and a persisted cloud chart."""

import asyncio
import json
import os
import sys
from pathlib import Path
from typing import Any

from check_chart_browser import action as chart_fixture
from check_streaming import Fixture
from lonora_db.runs import complete_run
from lonora_security.runtime_storage import confined_path
from lonora_tools.artifacts import store_artifact

UI_ARTIFACT_ROOT = str(Path(__file__).resolve().parent.parent / ".runtime/ui-regression-artifacts")


async def action(data: dict[str, Any]):
    os.environ.setdefault(
        "LONORA_ARTIFACT_ROOT",
        UI_ARTIFACT_ROOT,
    )
    if data["action"] == "init":
        chart = await chart_fixture({"action": "init"})
        fixture = await Fixture().open()
        try:
            agent = await fixture.agent("Market analyst")
            await fixture.request(
                "PATCH",
                "/agents/" + agent["id"],
                {
                    "title": "Market research",
                    "description": "Explicit UI fixture for persisted trading research",
                },
            )
            thread = await fixture.conversation(agent)
            run = await fixture.run(agent, thread)
            context = await fixture.lease(run)
            content = b'<svg xmlns="http://www.w3.org/2000/svg" width="640" height="280" viewBox="0 0 640 280"><rect width="640" height="280" fill="#ececec"/><path d="M40 230 L140 185 L240 200 L350 120 L450 140 L600 45" fill="none" stroke="#333" stroke-width="4"/><text x="30" y="35" font-family="sans-serif" font-size="20">Explicit imported analysis fixture</text><script>window.svgProbe=true</script></svg>'
            artifact = await store_artifact(
                context.for_call("browser-svg"), "analysis.svg", content, "image/svg+xml"
            )
            async with fixture.runtime.db.sessions() as session, session.begin():
                await complete_run(
                    session,
                    context.lease,
                    "Saved the analysis image and the persistent market chart.",
                    {},
                )
            return {
                **chart,
                "agent": agent["id"],
                "name": agent["name"],
                "thread": thread["id"],
                "run": run["id"],
                "artifact": artifact["id"],
                "key": artifact["payload"]["key"],
                "extra_agents": [],
            }
        finally:
            await fixture.close(cleanup=False)
    if data["action"] == "cleanup":
        fixture = await Fixture().open()
        try:
            await fixture.request("DELETE", "/artifacts/" + data["artifact"])
            confined_path(fixture.settings.artifact_root, data["key"]).unlink(missing_ok=True)
            fixture.agents = [data["agent"], *data.get("extra_agents", [])]
        finally:
            await fixture.close()
        return await chart_fixture({**data, "action": "cleanup"})
    raise ValueError("Unknown UI fixture action")


if __name__ == "__main__":
    print(json.dumps(asyncio.run(action(json.load(sys.stdin)))))
