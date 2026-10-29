"""Real PostgreSQL concurrent recovery/configuration while broker identity I/O is paused."""

import asyncio
from typing import Any
from unittest.mock import AsyncMock, patch
from uuid import uuid4

from check_streaming import Fixture
from lonora_contracts.broker import BrokerConnection
from lonora_db.broker_sessions import BrokerSessionRepository
from lonora_db.schema import BrokerSessionRow, SecretRow
from sqlalchemy import select


async def main() -> None:
    fixture = await Fixture().open()
    prefix = "backfill-race-" + uuid4().hex
    created: list[str] = []

    async def post(account_id: str):
        return await fixture.client.post(
            "/api/trading/connections",
            json={
                "provider": "metaapi",
                "account_id": account_id,
                "enabled": True,
                "api_key": "fixture-token",
            },
        )

    def metadata(login: str) -> dict[str, Any]:
        return {"login": login, "server": "Fixture-Demo", "platform": "mt5"}

    try:

        async def case(change: str) -> None:
            existing_account_id = prefix + "-" + change
            with patch(
                "lonora_trading.connections.verified_identity",
                AsyncMock(return_value=metadata(existing_account_id)),
            ):
                primary = await post(existing_account_id)
            assert primary.status_code == 201, primary.text
            connection_id = primary.json()["id"]
            created.append(connection_id)
            async with fixture.runtime.db.sessions() as session, session.begin():
                row = await BrokerSessionRepository().get(
                    session, fixture.owner, connection_id, lock=True
                )
                row.state = {"broker_recovery": {"status": "disconnected", "revision": 1}}
            metadata_started = asyncio.Event()
            release_metadata = asyncio.Event()

            async def observed(config: BrokerConnection, token: str) -> dict[str, Any]:
                assert token == "fixture-token"
                if config.account_id == existing_account_id:
                    metadata_started.set()
                    await release_metadata.wait()
                return metadata(config.account_id)

            with patch(
                "lonora_trading.connections.verified_identity", AsyncMock(side_effect=observed)
            ):
                submission = asyncio.create_task(post(existing_account_id + "-new"))
                try:
                    await asyncio.wait_for(metadata_started.wait(), timeout=10)

                    async def concurrent_update() -> None:
                        async with fixture.runtime.db.sessions() as session, session.begin():
                            row = await BrokerSessionRepository().get(
                                session, fixture.owner, connection_id, lock=True
                            )
                            # Same locking/writing pattern as Gateway broker recovery.
                            row.state = {
                                **row.state,
                                "broker_recovery": {
                                    "status": "connected",
                                    "revision": 2,
                                    "unresolved_operations": [],
                                },
                                "concurrent_marker": change,
                            }
                            if change == "version":
                                row.version += 1
                            elif change == "credentials":
                                row.payload = {
                                    **row.payload,
                                    "account_id": existing_account_id + "-reconfigured",
                                }

                    # This must COMMIT before provider I/O is released: acquiring
                    # the broker row lock before network I/O would time out here.
                    await asyncio.wait_for(concurrent_update(), timeout=10)
                finally:
                    release_metadata.set()
                    result = await asyncio.wait_for(submission, timeout=10)
            if change == "recovery":
                assert result.status_code == 201, result.text
                created.append(result.json()["id"])
            else:
                assert result.status_code == 409, result.text
                assert result.json()["code"] == "broker_connection_changed", result.text
                async with fixture.runtime.db.sessions() as session:
                    assert (
                        await session.scalar(
                            select(SecretRow).where(
                                SecretRow.owner_id == fixture.owner,
                                SecretRow.name == existing_account_id + "-new",
                            )
                        )
                        is None
                    )
            async with fixture.runtime.db.sessions() as session:
                row = await session.get(BrokerSessionRow, connection_id)
                assert row
                assert row.state["broker_recovery"] == {
                    "status": "connected",
                    "revision": 2,
                    "unresolved_operations": [],
                }, row.state
                assert row.state["concurrent_marker"] == change
                if change == "recovery":
                    assert row.state["broker_identity"]["login"] == existing_account_id
                else:
                    assert "broker_identity" not in row.state
            print(
                "PASS identity backfill preserves concurrent recovery"
                if change == "recovery"
                else f"PASS identity backfill fences concurrent {change} change without orphan credentials"
            )
            # Subsequent cases must only have their own legacy identity pending.
            async with fixture.runtime.db.sessions() as session, session.begin():
                for saved_id in created:
                    row = await session.get(BrokerSessionRow, saved_id)
                    if row:
                        await session.delete(row)
            created.clear()

        for change in ("recovery", "version", "credentials"):
            await case(change)

        # With multiple legacy rows, a completed identity observation must not
        # lock that row while another account's provider metadata is still slow.
        legacy_ids: dict[str, str] = {}
        for index in range(2):
            account_id = prefix + f"-multi-{index}"
            with patch(
                "lonora_trading.connections.verified_identity",
                AsyncMock(return_value=metadata(account_id)),
            ):
                result = await post(account_id)
            assert result.status_code == 201, result.text
            legacy_ids[account_id] = result.json()["id"]
            created.append(result.json()["id"])
        async with fixture.runtime.db.sessions() as session, session.begin():
            for connection_id in legacy_ids.values():
                row = await session.get(BrokerSessionRow, connection_id)
                assert row
                row.state = {"broker_recovery": {"revision": 1}}
        observed_order: list[str] = []
        later_metadata_started = asyncio.Event()
        release_later_metadata = asyncio.Event()

        async def multi_observed(config: BrokerConnection, token: str) -> dict[str, Any]:
            if config.account_id in legacy_ids:
                observed_order.append(config.account_id)
                if len(observed_order) == 2:
                    later_metadata_started.set()
                    await release_later_metadata.wait()
            return metadata(config.account_id)

        with patch(
            "lonora_trading.connections.verified_identity", AsyncMock(side_effect=multi_observed)
        ):
            submission = asyncio.create_task(post(prefix + "-multi-new"))
            try:
                await asyncio.wait_for(later_metadata_started.wait(), timeout=10)
                first_id = legacy_ids[observed_order[0]]

                async def update_first() -> None:
                    async with fixture.runtime.db.sessions() as session, session.begin():
                        row = await BrokerSessionRepository().get(
                            session, fixture.owner, first_id, lock=True
                        )
                        row.state = {**row.state, "broker_recovery": {"revision": 2}}

                await asyncio.wait_for(update_first(), timeout=10)
            finally:
                release_later_metadata.set()
                result = await asyncio.wait_for(submission, timeout=10)
        assert result.status_code == 201, result.text
        created.append(result.json()["id"])
        async with fixture.runtime.db.sessions() as session:
            first = await session.get(BrokerSessionRow, first_id)
            assert first and first.state["broker_recovery"] == {"revision": 2}
            for connection_id in legacy_ids.values():
                row = await session.get(BrokerSessionRow, connection_id)
                assert row and row.state["broker_identity"]["connection_version"] == row.version
        print("PASS all provider metadata completes before any legacy broker row is locked")
    finally:
        async with fixture.runtime.db.sessions() as session, session.begin():
            for connection_id in created:
                row = await session.get(BrokerSessionRow, connection_id)
                if row:
                    await session.delete(row)
            for row in await session.scalars(
                select(SecretRow).where(
                    SecretRow.owner_id == fixture.owner, SecretRow.name.like(prefix + "%")
                )
            ):
                await session.delete(row)
        await fixture.close()


if __name__ == "__main__":
    asyncio.run(main())
