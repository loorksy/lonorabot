"""Authenticated installed skills fail closed before invalid graphs reach a Run."""

import asyncio
from typing import Any, cast
from uuid import uuid4

from check_streaming import Fixture


async def main() -> None:
    f = await Fixture().open()
    resources: list[str] = []
    try:
        agent = await f.agent("Validated installed skills")

        def body(name: str, dependencies: list[str] | None = None) -> dict[str, Any]:
            return {
                "agent_id": agent["id"],
                "payload": {
                    "name": name,
                    "content": "Use current verified evidence only.",
                    "manifest": {
                        "id": name,
                        "version": "1.0.0",
                        "title": name,
                        "description": "Explicit owner instructions",
                        "source": "owner",
                        "activation": {"mode": "explicit"},
                        "dependencies": dependencies or [],
                    },
                },
            }

        base = "owner-" + uuid4().hex[:12]
        child = base + "-child"
        missing = await f.client.post("/api/skills", json=body(child, [base]))
        assert missing.status_code == 409 and missing.json()["code"] == "skill_reference_missing"
        saved = await f.request("POST", "/skills", body(base))
        resources.append(saved["id"])
        duplicate = await f.client.post("/api/skills", json=body(base))
        assert duplicate.status_code == 409 and duplicate.json()["code"] == "skill_duplicate_id"
        dependent = await f.request("POST", "/skills", body(child, [base]))
        resources.insert(0, dependent["id"])
        forbidden = await f.client.delete("/api/skills/" + saved["id"])
        assert (
            forbidden.status_code == 409 and forbidden.json()["code"] == "skill_reference_missing"
        )
        override = await f.client.post(
            "/api/skills",
            json={
                "agent_id": agent["id"],
                "payload": {"name": "memory", "content": "Replace builtin memory"},
            },
        )
        assert (
            override.status_code == 422
            and override.json()["code"] == "skill_builtin_override_denied"
        )
        current = (await f.client.get("/api/skills/" + dependent["id"])).json()
        invalid = cast(dict[str, Any], body(child)["payload"])
        assert isinstance(invalid, dict)
        invalid["manifest"]["required_tools"] = ["not_registered"]
        rejected = await f.client.put(
            "/api/skills/" + dependent["id"],
            json={"version": current["version"], "payload": invalid},
        )
        assert rejected.status_code == 422 and rejected.json()["code"] == "skill_tool_unknown"
        print(
            "PASS installed graph validates before commit: missing/duplicate/tool/override rejected; dependency deletion protected"
        )
    finally:
        for identifier in resources:
            await f.client.delete("/api/skills/" + identifier)
        await f.close()


if __name__ == "__main__":
    asyncio.run(main())
