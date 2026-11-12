"""Real PostgreSQL concurrent recovery/configuration while broker identity I/O is paused.

broker_connect's gateway step creates a MetaApi connection: ``observe_legacy_identities``
(provider I/O, no lock), then ``record_identities`` and ``BrokerSessionRepository.create``
under the owner lock. ``link`` below is that sequence."""

import asyncio
from typing import Any
from unittest.mock import AsyncMock, patch
from uuid import uuid4

from check_streaming import Fixture
from lonora_adapters.storage.broker_secrets import BrokerSecrets
from lonora_contracts.broker import BrokerConnection
from lonora_core.user_error import LonoraError
from lonora_db.broker_sessions import BrokerSessionRepository
from lonora_db.schema import BrokerSessionRow, SecretRow
from lonora_trading import connections
from sqlalchemy import select


async def main() -> None:
    fixture = await Fixture().open()
    prefix = "backfill-race-" + uuid4().hex
    created: list[str] = []

    store = BrokerSecrets(
        fixture.runtime.db,
        fixture.runtime.settings.encryption_key.get_secret_value(),
        fixture.owner,
    )
    async with fixture.runtime.db.sessions() as session, session.begin():
        token_id = await store.write_in_session(session, prefix + "-token", "fixture-token")

    async def link(account_id: str) -> tuple[str, str]:
        """("created", connection id) or ("refused", code), as broker_connect's step."""
        config = BrokerConnection(
            provider="metaapi", account_id=account_id, secret_id=token_id, enabled=True
        )
        try:
            identity = await connections.verified_identity(config, "fixture-token")
            legacy = await connections.observe_legacy_identities(
                fixture.runtime.db, store, fixture.owner
            )
            repository = BrokerSessionRepository()
            async with fixture.runtime.db.sessions() as session, session.begin():
                await repository.lock_owner(session, fixture.owner)
                await connections.record_identities(session, fixture.owner, legacy)
                row = await repository.create(
                    session, fixture.owner, config.model_dump(mode="json"), broker_identity=identity
                )
                return "created", row.id
        except LonoraError as failure:
            return "refused", failure.code

    def metadata(login: str) -> dict[str, Any]:
        return {"login": login, "server": "Fixture-Demo", "platform": "mt5"}

    try:

        async def case(change: str) -> None:
            existing_account_id = prefix + "-" + change
            with patch(
                "lonora_trading.connections.verified_identity",
                AsyncMock(return_value=metadata(existing_account_id)),
            ):
                outcome, connection_id = await link(existing_account_id)
            assert outcome == "created", connection_id
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
                submission = asyncio.create_task(link(existing_account_id + "-new"))
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
                assert result[0] == "created", result
                created.append(result[1])
            else:
                assert result == ("refused", "broker_connection_changed"), result
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
                else f"PASS identity backfill fences concurrent {change} change"
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
                outcome, connection_id = await link(account_id)
            assert outcome == "created", connection_id
            legacy_ids[account_id] = connection_id
            created.append(connection_id)
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
            submission = asyncio.create_task(link(prefix + "-multi-new"))
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
        assert result[0] == "created", result
        created.append(result[1])
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
