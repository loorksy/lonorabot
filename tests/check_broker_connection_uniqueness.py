"""Actual API/PostgreSQL duplicate prevention; provider metadata is explicitly scripted."""

import asyncio
from typing import Any
from unittest.mock import AsyncMock, patch
from uuid import uuid4

from check_streaming import Fixture
from lonora_core.user_error import LonoraError
from lonora_db.broker_sessions import BrokerSessionRepository
from lonora_db.schema import BrokerSessionRow, SecretRow
from sqlalchemy import select


async def main() -> None:
    fixture = await Fixture().open()
    created: list[str] = []
    prefix = "duplicate-fixture-" + uuid4().hex

    def metadata(login: str, server: str = "Fixture-MT5") -> dict[str, Any]:
        return {"login": login, "server": server, "platform": "mt5", "broker": "Scripted fixture"}

    async def post(account: str, *, provider: str = "metaapi", key: str | None = "fixture-token"):
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

    try:
        # A repeated click is serialized by the database, not a process-local mutex.
        first_id = prefix + "-same-provider"
        responses = await asyncio.gather(
            post(first_id, provider="simulation"), post(first_id, provider="simulation")
        )
        assert sorted(response.status_code for response in responses) == [201, 409]
        success = next(response.json() for response in responses if response.status_code == 201)
        created.append(success["id"])
        assert (
            next(response.json()["code"] for response in responses if response.status_code == 409)
            == "broker_account_already_connected"
        )
        secret_id = success["payload"]["secret_id"]
        store = fixture.runtime.services(fixture.owner).secrets
        assert await store.read(secret_id) == "fixture-token"
        retry = await post(first_id + " ", provider="simulation", key="bad-replacement")
        assert retry.status_code == 409
        assert await store.read(secret_id) == "fixture-token"
        print(
            "PASS concurrent repeat links create one connection; duplicate retry never overwrites its credential"
        )

        before = await identities()
        verifier = AsyncMock(return_value=metadata("0012345"))
        with patch("lonora_trading.connections.verified_identity", verifier):
            primary = await post(prefix + "-primary")
            assert primary.status_code == 201, primary.text
            canonical = primary.json()
            created.append(canonical["id"])
            duplicate = await post(prefix + "-other-provisioning")
            assert duplicate.status_code == 409, duplicate.text
            assert duplicate.json()["code"] == "broker_account_already_connected"
            assert len((await identities()) - before) == 1
            verifier.reset_mock()
            duplicate_id = await post(prefix + "-primary", key="replacement")
            assert duplicate_id.status_code == 409
            verifier.assert_not_awaited()
            assert await store.read(canonical["payload"]["secret_id"]) == "fixture-token"
        print(
            "PASS different provisioning IDs for the same broker account are rejected without orphan credentials or provider work on retries"
        )

        # Server/platform/login come from metadata, never from caller-controlled fields.
        with patch(
            "lonora_trading.connections.verified_identity",
            AsyncMock(return_value=metadata("12345", " fixture-mt5 ")),
        ):
            normalized = await post(prefix + "-normalized")
            assert normalized.status_code == 409, normalized.text
        for suffix, observed in [
            ("other-server", metadata("12345", "Other-MT5")),
            ("other-login", metadata("98765")),
        ]:
            with patch(
                "lonora_trading.connections.verified_identity", AsyncMock(return_value=observed)
            ):
                response = await post(prefix + "-" + suffix)
                assert response.status_code == 201, response.text
                created.append(response.json()["id"])
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
            legacy_alias = await post(prefix + "-legacy-alias")
            assert legacy_alias.status_code == 409, legacy_alias.text
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
            responses = await asyncio.gather(post(prefix + "-race1"), post(prefix + "-race2"))
            assert sorted(response.status_code for response in responses) == [201, 409], [
                r.text for r in responses
            ]
            created.append(
                next(response.json()["id"] for response in responses if response.status_code == 201)
            )
        print(
            "PASS concurrent alternate provisioning IDs for the same actual account create exactly one connection"
        )

        # Failed resource creation rolls back even an encrypted credential that
        # has already been flushed inside the transaction.
        before = await identities()
        with (
            patch(
                "lonora_trading.connections.verified_identity",
                AsyncMock(return_value=metadata(prefix + "-rollback")),
            ),
            patch.object(
                BrokerSessionRepository,
                "create",
                AsyncMock(side_effect=LonoraError("fixture_rejected", 409)),
            ),
        ):
            failed = await post(prefix + "-rollback")
            assert failed.status_code == 409
        assert await identities() == before
        with patch(
            "lonora_trading.connections.verified_identity",
            AsyncMock(return_value={"login": "missing-server"}),
        ):
            incomplete = await post(prefix + "-incomplete")
            assert (
                incomplete.status_code == 503
                and incomplete.json()["code"] == "broker_identity_unavailable"
            )
        assert await identities() == before
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
