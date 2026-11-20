"""A permission draft never names a connection that was deleted (prepare_delete).

Choosing Full proposes the agent's saved draft; a draft naming a deleted account would
propose an account that is gone. Runs on the real migrated PostgreSQL schema (skipped
without ``LONORA_DATABASE_URL``).
"""

import os
from typing import Any
from uuid import uuid4

import pytest


@pytest.mark.asyncio
async def test_a_deleted_connection_leaves_the_rest_of_each_draft() -> None:
    if not os.environ.get("LONORA_DATABASE_URL"):
        pytest.skip("Disconnecting runs on the real migrated schema.")
    from check_streaming import Fixture

    fixture = await Fixture().open()
    kept: dict[str, Any] | None = None
    try:

        async def connection(name: str) -> dict[str, Any]:
            return await fixture.request(
                "POST",
                "/trading/connections",
                {"provider": "simulation", "account_id": name + uuid4().hex, "enabled": True},
            )

        async def saved(agent: dict[str, Any], account_id: str) -> dict[str, Any]:
            path = f"/agents/{agent['id']}/permissions"
            current = await fixture.request("GET", path)
            return await fixture.request(
                "PUT",
                path + "/customization",
                {
                    "expected_revision": current["revision"],
                    "customization": {
                        "account_id": account_id,
                        "symbol_scope": "selected",
                        "symbols": ["XAUUSD"],
                        "actions": ["buy"],
                        "limits": {"maximum_order_volume": "0.5"},
                        "duration": "7d",
                    },
                },
            )

        gone, kept = await connection("gone-"), await connection("kept-")
        named = await saved(await fixture.agent("Draft on the deleted account"), gone["id"])
        other = await saved(await fixture.agent("Draft on another account"), kept["id"])
        await fixture.request("DELETE", f"/trading/connections/{gone['id']}")

        after = await fixture.request("GET", f"/agents/{named['agent_id']}/permissions")
        assert after["revision"] > named["revision"]
        assert after["customization"] == {
            **named["customization"],
            "account_id": "",
            "symbols": [],
        }
        assert (await fixture.request("GET", f"/agents/{other['agent_id']}/permissions")) == other
    finally:
        if kept is not None:
            await fixture.request("DELETE", f"/trading/connections/{kept['id']}")
        await fixture.close()
