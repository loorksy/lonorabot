"""Real owner HTTP updates cannot activate or rewrite executable packages."""

import asyncio
from typing import Any

from check_streaming import Fixture
from lonora_db.schema import SkillRow, TradeApprovalRow, TradingJournalRow
from sqlalchemy import func, select


async def main() -> None:
    fixture = await Fixture().open()
    try:
        agent = await fixture.agent("Managed package update guard")
        created = await fixture.request(
            "POST",
            "/skills",
            {
                "agent_id": agent["id"],
                "payload": {
                    "name": "update-guard-fixture",
                    "content": "Use current verified evidence without financial authority.",
                    "enabled": False,
                },
            },
        )
        path = "/skills/" + created["id"]
        ordinary = await fixture.request(
            "PUT",
            path,
            {"version": created["version"], "payload": {**created["payload"], "enabled": True}},
        )
        assert ordinary["payload"]["enabled"] is True
        ordinary = await fixture.request(
            "PUT",
            path,
            {"version": ordinary["version"], "payload": {**ordinary["payload"], "enabled": False}},
        )
        async with fixture.runtime.db.sessions() as session, session.begin():
            row = await session.get(SkillRow, created["id"], with_for_update=True)
            assert row is not None
            # Even damaged managed metadata must fail closed, not become owner text.
            row.state = {"package": {"damaged_fixture_state": True}}
            ledger_before = await session.scalar(
                select(func.count()).select_from(TradingJournalRow)
            )
            approvals_before = await session.scalar(
                select(func.count()).select_from(TradeApprovalRow)
            )

        async def denied(payload: dict[str, Any], version: int, code: str) -> None:
            response = await fixture.client.put(
                "/api" + path, json={"version": version, "payload": payload}
            )
            assert response.status_code == 409 and response.json()["code"] == code

        for attempted in (
            {**ordinary["payload"], "enabled": True},
            {**ordinary["payload"], "content": "Replace unvalidated managed instructions."},
            {**ordinary["payload"], "name": "unmanaged-alias"},
        ):
            await denied(attempted, ordinary["version"], "skill_package_lifecycle_required")
        await denied(ordinary["payload"], ordinary["version"] - 1, "version_conflict")
        unchanged = await fixture.request("GET", path)
        assert unchanged["version"] == ordinary["version"]
        assert unchanged["payload"] == ordinary["payload"]
        # An owner must still be able to disable damaged/obsolete active packages.
        async with fixture.runtime.db.sessions() as session, session.begin():
            row = await session.get(SkillRow, created["id"], with_for_update=True)
            assert row is not None
            row.payload = {**row.payload, "enabled": True}
        disabled = await fixture.request(
            "PUT", path, {"version": ordinary["version"], "payload": ordinary["payload"]}
        )
        assert disabled["payload"]["enabled"] is False
        await fixture.request("DELETE", path)
        async with fixture.runtime.db.sessions() as session:
            assert (
                await session.scalar(select(func.count()).select_from(TradingJournalRow))
                == ledger_before
            )
            assert (
                await session.scalar(select(func.count()).select_from(TradeApprovalRow))
                == approvals_before
            )
        print(
            "PASS real owner HTTP editing preserves ordinary instructions; managed enable/rewrite and stale versions denied, disable/delete allowed, financial state unchanged"
        )
    finally:
        await fixture.close()


if __name__ == "__main__":
    asyncio.run(main())
