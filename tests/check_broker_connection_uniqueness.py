"""Actual API/PostgreSQL duplicate prevention; provider metadata is explicitly scripted.

A MetaApi account is connected from chat (broker_connect, mandate 9.2): its gateway step
reads the legacy connections' identity (``observe_legacy_identities``), records it under
the row locks (``record_identities``) and creates the row with MetaApi's observed identity
(``BrokerSessionRepository.create``). ``link`` below is that sequence; the route that
linked a MetaApi account by id refuses it.
"""

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
    created: list[str] = []
    prefix = "duplicate-fixture-" + uuid4().hex
    store = BrokerSecrets(
        fixture.runtime.db,
        fixture.runtime.settings.encryption_key.get_secret_value(),
        fixture.owner,
    )

    def metadata(login: str, server: str = "Fixture-MT5") -> dict[str, Any]:
        return {"login": login, "server": server, "platform": "mt5", "broker": "Scripted fixture"}

    async def post(
        account: str, *, provider: str = "simulation", key: str | None = "fixture-token"
    ):
        return await fixture.client.post(
            "/api/trading/connections",
            json={"provider": provider, "account_id": account, "enabled": True, "api_key": key},
        )

    async def identities() -> set[str]:
        async with fixture.runtime.db.sessions() as session:
            return set(
                await session.scalars(
                    select(SecretRow.id).where(SecretRow.owner_id == fixture.owner)
                )
            )

    async with fixture.runtime.db.sessions() as session, session.begin():
        token_id = await store.write_in_session(session, prefix + "-token", "fixture-token")

    async def link(account: str) -> dict[str, Any]:
        """broker_connect's creation of a MetaApi connection for an account at MetaApi."""
        config = BrokerConnection(
            provider="metaapi", account_id=account, secret_id=token_id, enabled=True
        )
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
            created.append(row.id)
            return {"id": row.id, "state": dict(row.state)}

    async def refused(account: str) -> str:
        try:
            await link(account)
        except LonoraError as failure:
            return failure.code
        raise AssertionError("linked")

    try:
        # A repeated click is serialized by the database, not a process-local mutex.
        first_id = prefix + "-same-provider"
        responses = await asyncio.gather(post(first_id), post(first_id))
        assert sorted(response.status_code for response in responses) == [201, 409]
        success = next(response.json() for response in responses if response.status_code == 201)
        created.append(success["id"])
        assert (
            next(response.json()["code"] for response in responses if response.status_code == 409)
            == "broker_account_already_connected"
        )
        secret_id = success["payload"]["secret_id"]
        # Broker values are read only through the broker layer's reader (7.2.3).
        assert await store.read(secret_id) == "fixture-token"
        retry = await post(first_id + " ", key="bad-replacement")
        assert retry.status_code == 409
        assert await store.read(secret_id) == "fixture-token"
        print(
            "PASS concurrent repeat links create one connection; duplicate retry never overwrites its credential"
        )

        # A MetaApi account is never linked by its id any more (9.2); nothing is saved.
        before = await identities()
        by_id = await post(prefix + "-by-id", provider="metaapi")
        assert by_id.status_code == 409 and by_id.json()["code"] == "broker_connect_from_chat"
        assert await identities() == before
        print("PASS a MetaApi account id typed into the route is refused; connect is from chat")

        verifier = AsyncMock(return_value=metadata("0012345"))
        with patch("lonora_trading.connections.verified_identity", verifier):
            canonical = await link(prefix + "-primary")
            assert await refused(prefix + "-other-provisioning") == (
                "broker_account_already_connected"
            )
        print("PASS different provisioning IDs for the same broker account are rejected")

        # Server/platform/login come from metadata, never from caller-controlled fields.
        with patch(
            "lonora_trading.connections.verified_identity",
            AsyncMock(return_value=metadata("12345", " fixture-mt5 ")),
        ):
            assert await refused(prefix + "-normalized") == "broker_account_already_connected"
        for suffix, observed in [
            ("other-server", metadata("12345", "Other-MT5")),
            ("other-login", metadata("98765")),
        ]:
            with patch(
                "lonora_trading.connections.verified_identity", AsyncMock(return_value=observed)
            ):
                await link(prefix + "-" + suffix)
        print(
            "PASS broker login/server normalization catches aliases while genuinely different accounts remain connectable"
        )

        # A legacy row without current identity must be checked with its existing
        # credential before an alternate provisioning ID can be accepted.
        async with fixture.runtime.db.sessions() as session, session.begin():
            row = await session.get(BrokerSessionRow, canonical["id"])
            assert row
            row.state = {
                **row.state,
                "broker_identity": {"login": "untrusted", "connection_version": row.version - 1},
            }

        async def legacy_observation(config: Any, token: str) -> dict[str, Any]:
            assert token == "fixture-token"
            if config.account_id.endswith(("primary", "legacy-alias")):
                return metadata("12345")
            if config.account_id.endswith("other-server"):
                return metadata("12345", "Other-MT5")
            return metadata("98765")

        with patch(
            "lonora_trading.connections.verified_identity",
            AsyncMock(side_effect=legacy_observation),
        ) as lookup:
            assert await refused(prefix + "-legacy-alias") == "broker_account_already_connected"
            assert lookup.await_count >= 2
        print(
            "PASS legacy missing/stale identity is verified before another provider alias is accepted"
        )

        async with fixture.runtime.db.sessions() as session, session.begin():
            row = await session.get(BrokerSessionRow, canonical["id"])
            assert row
            row.state = canonical["state"]

        with patch(
            "lonora_trading.connections.verified_identity",
            AsyncMock(return_value=metadata(prefix + "-race")),
        ):
            results = await asyncio.gather(
                link(prefix + "-race1"), link(prefix + "-race2"), return_exceptions=True
            )
        failures = [result for result in results if isinstance(result, LonoraError)]
        assert len(failures) == 1, results
        assert failures[0].code == "broker_account_already_connected"
        print(
            "PASS concurrent alternate provisioning IDs for the same actual account create exactly one connection"
        )

        # Failed resource creation rolls back even an encrypted credential that
        # has already been flushed inside the transaction.
        before = await identities()
        with patch.object(
            BrokerSessionRepository,
            "create",
            AsyncMock(side_effect=LonoraError("fixture_rejected", 409)),
        ):
            failed = await post(prefix + "-rollback")
            assert failed.status_code == 409
        assert await identities() == before
        with patch(
            "lonora_trading.connections.verified_identity",
            AsyncMock(return_value={"login": "missing-server"}),
        ):
            assert await refused(prefix + "-incomplete") == "broker_identity_unavailable"
        print("PASS rejected or unverifiable connection rolls back credentials atomically")
    finally:
        async with fixture.runtime.db.sessions() as session, session.begin():
            for connection_id in created:
                row = await session.get(BrokerSessionRow, connection_id)
                if row:
                    await session.delete(row)
            for secret in await session.scalars(
                select(SecretRow).where(
                    SecretRow.owner_id == fixture.owner, SecretRow.name.like(prefix + "%")
                )
            ):
                await session.delete(secret)
        await fixture.close()


if __name__ == "__main__":
    asyncio.run(main())
