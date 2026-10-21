"""Actual owner-authenticated catalog, detail, controls and resource lifecycle."""

import asyncio
from typing import Any
from uuid import uuid4

from check_streaming import Fixture
from lonora_api.middleware.auth import require_owner
from lonora_auth.identity import OwnerIdentity
from lonora_db.schema import EventRow, RunRow, TradingJournalRow
from sqlalchemy import func, select


async def main() -> None:
    f = await Fixture().open()
    try:
        agent = await f.agent("Owner catalog")
        other = await f.agent("Independent catalog")
        endpoint = f"/agents/{agent['id']}/skills/catalog"
        name = "owner-catalog-" + uuid4().hex[:8]
        payload: dict[str, Any] = {
            "name": name,
            "content": "Private procedural text is loaded on demand.",
            "enabled": True,
            "manifest": {
                "id": name,
                "version": "1.0.0",
                "source": "owner",
                "title": "Current owner procedure",
                "description": "Current catalog is not pinned Run state.",
                "activation": {"mode": "explicit"},
                "required_tools": ["chart_inspect"],
            },
        }
        saved = await f.request("POST", "/skills", {"agent_id": agent["id"], "payload": payload})
        entries: list[dict[str, Any]] = []
        offset = 0
        while True:
            page = await f.request("GET", endpoint + f"?offset={offset}&limit=3")
            assert page["agent_id"] == agent["id"] and len(page["items"]) <= 3
            entries.extend(page["items"])
            assert all("content" not in item for item in page["items"])
            if page["next_offset"] is None:
                assert len(entries) == page["total"]
                break
            offset = page["next_offset"]
        assert [item["id"] for item in entries] == sorted({item["id"] for item in entries})
        current = next(item for item in entries if item["id"] == name)
        assert current["available"] and current["version"] == "1.0.0"
        assert current["resource_id"] == saved["id"] and current["resource_version"] == 1
        detail = await f.request("GET", endpoint + "/" + name)
        assert detail["content"] == payload["content"]
        assert detail["manifest"]["activation"]["mode"] == "explicit"
        builtin = await f.request("GET", endpoint + "/chart-analysis")
        assert builtin["source"] == "builtin" and builtin["resource_id"] is None
        assert builtin["content"]
        independent = await f.request("GET", f"/agents/{other['id']}/skills/catalog")
        assert name not in {item["id"] for item in independent["items"]}
        assert (await f.request("GET", endpoint + "?offset=10000"))["items"] == []
        for query in ("?limit=0", "?limit=101", "?offset=-1"):
            assert (await f.client.get("/api" + endpoint + query)).status_code == 422
        assert (await f.client.get("/api" + endpoint + "/not-installed")).status_code == 404

        controls = f"/agents/{agent['id']}/skills/revocations"
        blocked = await f.request(
            "POST", controls, {"skill_id": name, "version": "1.0.0", "expected_revision": 0}
        )
        assert blocked["revision"] == 1
        detail = await f.request("GET", endpoint + "/" + name)
        assert not detail["available"] and detail["code"] == "skill_version_revoked"
        assert detail["content"] == payload["content"]
        updated = {**payload, "manifest": {**payload["manifest"], "version": "2.0.0"}}
        saved = await f.request(
            "PUT", "/skills/" + saved["id"], {"version": saved["version"], "payload": updated}
        )
        detail = await f.request("GET", endpoint + "/" + name)
        assert detail["available"] and detail["version"] == "2.0.0"
        assert detail["resource_version"] == saved["version"]
        await f.request("DELETE", "/skills/" + saved["id"])
        assert (await f.client.get("/api" + endpoint + "/" + name)).status_code == 404
        assert (await f.request("GET", controls)) == blocked

        original = f.app.dependency_overrides.get(require_owner)
        f.app.dependency_overrides[require_owner] = lambda: OwnerIdentity(
            id=str(uuid4()),
            email="other-catalog-owner@example.com",
            token_hash="scripted-other-owner",
        )
        try:
            for suffix in ("", "/chart-analysis"):
                assert (await f.client.get("/api" + endpoint + suffix)).status_code == 404
        finally:
            if original is None:
                del f.app.dependency_overrides[require_owner]
            else:
                f.app.dependency_overrides[require_owner] = original
        # Catalog reading has no Run/tool/financial side effect. Revocation is the
        # sole intentional durable transition made by this fixture.
        async with f.runtime.db.sessions() as session:
            assert await session.scalar(select(func.count()).select_from(RunRow)) == 0
            assert await session.scalar(select(func.count()).select_from(TradingJournalRow)) == 0
            assert (
                await session.scalar(
                    select(func.count())
                    .select_from(EventRow)
                    .where(
                        EventRow.agent_id == agent["id"], EventRow.kind == "skill.version_revoked"
                    )
                )
                == 1
            )
        print(
            "PASS scoped metadata/detail catalog, pagination, exact revocation/edit/delete, no Runs or trades"
        )
    finally:
        await f.close()


if __name__ == "__main__":
    asyncio.run(main())
