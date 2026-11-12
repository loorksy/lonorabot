"""Super Bot is retired: one signed grant is the only authority, and devices bind it.

Runs on a fresh migrated PostgreSQL database (LONORA_DATABASE_URL):

1. No Super Bot tool or route remains.
2. A grant signed from the trading-level controls returns the same grant on a
   lost-response replay, and the agent shows "trades on its own" only while that grant
   is in force: pausing the agent or revoking the passkey device ends it, and replaying
   the old proof never restores it.
3. Migration 0040_retire_super_bot_requests marks pending and activated requests
   retired and withdraws their open inbox items; the downgrade restores exactly those
   rows and the upgrade is repeatable. A retired request grants nothing.
"""

import asyncio
import subprocess
import sys
from datetime import timedelta
from pathlib import Path
from typing import Any, cast

from check_streaming import Fixture
from device_fixture import Device
from lonora_contracts.domain import utcnow
from lonora_db.schema import AgentRow, AttentionRow, SuperBotRequestRow
from lonora_tools.loader import load_tools
from sqlalchemy import select

ROOT = Path(__file__).resolve().parents[1]
BEFORE = "0040_explicit_agent_permission_rows"


async def alembic(action: str, revision: str) -> None:
    await asyncio.to_thread(
        subprocess.run,
        [sys.executable, "-m", "alembic", "-c", "packages/db/alembic.ini", action, revision],
        check=True,
        cwd=ROOT,
        stdout=subprocess.DEVNULL,
    )


async def simulated_account(f: Fixture, name: str) -> str:
    account = (
        await f.request(
            "POST",
            "/trading/connections",
            {"provider": "simulation", "account_id": name, "enabled": True},
        )
    )["id"]
    await f.request(
        "POST",
        f"/trading/connections/{account}/simulation",
        {
            "snapshot": {
                "balance": "2500",
                "equity": "2500",
                "currency": "USD",
                "instruments": [
                    {
                        "symbol": "EURUSDm",
                        "digits": 5,
                        "tick_size": "0.00001",
                        "volume_min": "0.01",
                        "volume_max": "10",
                        "volume_step": "0.01",
                    }
                ],
                "quotes": {},
                "positions": [],
                "orders": [],
            }
        },
    )
    return account


def bounded_grant(thread_id: str, account: str) -> dict[str, Any]:
    return {
        "thread_id": thread_id,
        "account_id": account,
        "symbols": ["EURUSDm"],
        "actions": ["buy", "sell", "close_position", "modify_position"],
        "maximum_order_volume": "0.1",
        "maximum_symbol_volume": "0.2",
        "maximum_positions": 2,
        "maximum_pending_orders": 0,
        "maximum_actions": 10,
        "minimum_equity": "1000",
        "valid_until": (utcnow() + timedelta(days=1)).isoformat(),
    }


async def on_its_own(f: Fixture, agent_id: str) -> bool:
    return bool((await f.request("GET", f"/agents/{agent_id}"))["trades_on_its_own"])


async def retired_surface(f: Fixture, agent: dict[str, Any], thread: dict[str, Any]) -> None:
    names = {tool.name for tool in load_tools().definitions()}
    assert not {name for name in names if name.startswith("super_bot")}, names
    for method, path in (
        ("GET", f"/api/agents/{agent['id']}/super-bot"),
        ("POST", f"/api/agents/{agent['id']}/super-bot/proposals"),
        ("POST", "/api/super-bot/verify"),
        ("POST", "/api/super-bot/control"),
    ):
        response = await f.client.request(method, path, json={})
        assert response.status_code in {404, 405}, (path, response.status_code)
    print("PASS no Super Bot tool or route remains")


async def signed_grant_and_devices(f: Fixture, device: Device) -> None:
    agent = await f.agent("Device authority", supervised=True)
    thread = await f.conversation(agent)
    account = await simulated_account(f, "device-authority")
    assert not await on_its_own(f, agent["id"])
    proposal = await f.request(
        "POST", f"/agents/{agent['id']}/account-authorities", bounded_grant(thread["id"], account)
    )
    challenge = await f.request("POST", f"/account-authorities/{proposal['id']}/challenge", {})
    proof = device.assertion(challenge, f.settings.allowed_origin)
    grant = await f.request("POST", "/account-authorities/verify", proof)
    assert grant["status"] == "active"
    assert (await f.request("POST", "/account-authorities/verify", proof))["id"] == grant["id"]
    assert await on_its_own(f, agent["id"])
    roster = cast(list[dict[str, Any]], await f.request("GET", "/agents"))
    assert next(item for item in roster if item["id"] == agent["id"])["trades_on_its_own"]
    live = await f.request("GET", f"/agents/{agent['id']}/state")
    assert "super_bot" not in live and live["account_authorities"][0]["status"] == "active"
    async with f.runtime.db.sessions() as session, session.begin():
        row = await session.get(AgentRow, agent["id"])
        assert row
        row.paused = True
    assert not await on_its_own(f, agent["id"])
    async with f.runtime.db.sessions() as session, session.begin():
        row = await session.get(AgentRow, agent["id"])
        assert row
        row.paused = False
    assert await on_its_own(f, agent["id"])
    print(
        "PASS a grant signed from the trading-level controls returns the same grant on a "
        "lost-response replay, and the agent trades on its own only while it is not paused"
    )

    devices = cast(list[dict[str, Any]], await f.request("GET", "/auth/devices"))
    await f.request("DELETE", "/auth/devices/" + devices[0]["id"])
    stopped = cast(
        list[dict[str, Any]], await f.request("GET", f"/agents/{agent['id']}/account-authorities")
    )
    assert next(item for item in stopped if item["id"] == grant["id"])["status"] == "revoked"
    assert not await on_its_own(f, agent["id"])
    replay = await f.client.post("/api/account-authorities/verify", json=proof)
    assert replay.status_code == 403, replay.status_code
    assert not await on_its_own(f, agent["id"])
    print(
        "PASS revoking the passkey device revokes its grants, and replaying the old proof never "
        "restores authority"
    )


async def migration_round_trip(f: Fixture) -> None:
    owner = f.owner
    agent = await f.agent("Retired request", supervised=True)
    thread = await f.conversation(agent)
    account = await simulated_account(f, "retire-migration")
    await alembic("downgrade", BEFORE)
    now = utcnow()
    statuses = {"sb-pending": "pending", "sb-activated": "activated", "sb-paused": "paused"}
    async with f.runtime.db.sessions() as session, session.begin():
        for identifier, status in statuses.items():
            session.add(
                SuperBotRequestRow(
                    id=identifier + "-" + owner[:8],
                    owner_id=owner,
                    agent_id=agent["id"],
                    thread_id=thread["id"],
                    goal_id="retired-goal",
                    mode="autonomous",
                    status=status,
                    envelope={"symbol": "EURUSDm", "account_id": account},
                    envelope_hash="hash",
                    expires_at=now + timedelta(minutes=10),
                    created_at=now,
                    updated_at=now,
                )
            )
        session.add(
            AttentionRow(
                id="sb-attention-" + owner[:8],
                owner_id=owner,
                agent_id=agent["id"],
                thread_id=thread["id"],
                logical_key="sb-attention-" + owner[:8],
                coalesce_key="sb-attention",
                importance="action_required",
                code="super_bot_authorization",
                status="ready",
                parameters={},
                due_at=now,
            )
        )

    async def observed() -> tuple[dict[str, str], str]:
        async with f.runtime.db.sessions() as session:
            rows = {
                row.id.rsplit("-", 1)[0]: row.status
                for row in await session.scalars(
                    select(SuperBotRequestRow)
                    .where(SuperBotRequestRow.owner_id == owner)
                    .execution_options(populate_existing=True)
                )
            }
            item = await session.get(
                AttentionRow, "sb-attention-" + owner[:8], populate_existing=True
            )
            assert item
            return rows, item.status

    retired = {"sb-pending": "retired", "sb-activated": "retired", "sb-paused": "paused"}
    for attempt in range(2):
        await alembic("upgrade", "head")
        rows, item = await observed()
        assert rows == retired and item == "suppressed", (rows, item)
        if attempt == 0:
            await alembic("downgrade", BEFORE)
            rows, item = await observed()
            assert rows == statuses and item == "ready", (rows, item)
    assert not await on_its_own(f, agent["id"])
    live = await f.request("GET", f"/agents/{agent['id']}/state")
    assert live["pending_authorization_count"] == 0 and "super_bot" not in live
    print(
        "PASS migration 0040 retires pending and activated Super Bot requests and withdraws "
        "their inbox items without deleting a row, restores exactly those rows on downgrade "
        "and repeats cleanly; a retired request grants nothing"
    )


async def main() -> None:
    f = await Fixture().open()
    try:
        agent = await f.agent("Retired surface")
        thread = await f.conversation(agent)
        await retired_surface(f, agent, thread)
        await signed_grant_and_devices(f, await Device.enroll(f))
        await migration_round_trip(f)
    finally:
        await f.close()


if __name__ == "__main__":
    asyncio.run(main())
