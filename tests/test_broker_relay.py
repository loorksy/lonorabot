"""One MetaApi connection per account, kept by the Gateway (the lead's production finding).

The API process held its own MetaApi client and subscribed each account too, so MetaApi
saw two subscriptions and two synchronization owners. Now the API process opens none: it
writes each read, and an owner's direct order, to the broker relay; the Gateway claims it
once and answers with its own adapter.
"""

import asyncio
import sys
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock

import pytest
from lonora_core.user_error import LonoraError

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tests"))
sys.path.insert(0, str(ROOT))


async def connection(fixture: Any, terminal: Any, provider: str = "metaapi") -> str:
    from lonora_adapters.storage.broker_secrets import BrokerSecrets
    from lonora_db.broker_sessions import BrokerSessionRepository

    secrets = BrokerSecrets(
        fixture.runtime.db,
        fixture.runtime.settings.encryption_key.get_secret_value(),
        fixture.owner,
    )
    async with fixture.runtime.db.sessions() as session, session.begin():
        token = await secrets.write_in_session(session, "relay-" + terminal.account_id, "t")
        row = await BrokerSessionRepository().create(
            session,
            fixture.owner,
            {
                "provider": provider,
                "account_id": terminal.account_id,
                "secret_id": token if provider == "metaapi" else None,
                "enabled": True,
            },
            broker_identity={"login": terminal.login, "server": terminal.server, "platform": "mt5"},
        )
        return row.id


async def remove(fixture: Any, *ids: str) -> None:
    from lonora_db.schema import BrokerSessionRow

    async with fixture.runtime.db.sessions() as session, session.begin():
        for connection_id in ids:
            row = await session.get(BrokerSessionRow, connection_id)
            if row is not None:
                await session.delete(row)


class Serving:
    """A Gateway's relay step, running beside the API process."""

    def __init__(self, fixture: Any):
        from lonora_gateway.broker_relay import BrokerRelay
        from lonora_gateway.runtime import OwnerServices

        key = fixture.runtime.settings.encryption_key.get_secret_value()
        self.services = OwnerServices.create(fixture.runtime.db, fixture.owner, key)
        self.relay = BrokerRelay(fixture.runtime.db, lambda owner: self.services)
        self.task: asyncio.Task[None] | None = None

    async def __aenter__(self) -> "Serving":
        async def loop() -> None:
            while True:
                await self.relay.iteration()
                await asyncio.sleep(0.05)

        self.task = asyncio.create_task(loop())
        return self

    async def __aexit__(self, *_: Any) -> None:
        assert self.task is not None
        self.task.cancel()
        await asyncio.gather(self.task, *self.relay.tasks, return_exceptions=True)
        await self.services.close()


@pytest.mark.asyncio
async def test_the_api_process_reads_a_metaapi_account_through_the_gateway() -> None:
    from test_supervision import database

    database()
    from check_streaming import Fixture
    from lonora_adapters.brokers.relay import RelayedBroker

    from scripts.agent_eval.broker import FakeMetaApiBroker, FakeTerminal, installed

    fixture = await Fixture().open()
    terminal = FakeTerminal(account_id="relay-read-" + str(id(object())))
    connection_id = await connection(fixture, terminal)
    api = fixture.runtime.services(fixture.owner).brokers
    try:
        with installed(terminal):
            async with Serving(fixture) as gateway:
                adapter = await api.get(fixture.owner, connection_id)
                assert isinstance(adapter, RelayedBroker)
                assert sorted(await adapter.symbols()) == sorted(terminal.names)
                quote = await adapter.quote("XAUUSDm")
                assert quote.symbol == "XAUUSDm"
                state = await api.account(fixture.owner, connection_id)
                assert state.login == terminal.login
                # A refusal at the Gateway reaches the API process as the same error.
                with pytest.raises(LonoraError) as unknown:
                    await adapter.instrument("NOPE")
                assert unknown.value.code == "symbol_not_found"
                # Only the Gateway's manager made a MetaApi adapter.
                assert isinstance(
                    gateway.services.brokers.connections[connection_id][1], FakeMetaApiBroker
                )
        assert not any(
            isinstance(broker, FakeMetaApiBroker) for _, broker in api.connections.values()
        )
        assert "get_symbols" in terminal.calls
        # Each answer is removed once read.
        from lonora_db.schema import BrokerRelayRow
        from sqlalchemy import func, select

        async with fixture.runtime.db.sessions() as session:
            assert await session.scalar(select(func.count()).select_from(BrokerRelayRow)) == 0
    finally:
        await remove(fixture, connection_id)
        await fixture.close()


@pytest.mark.asyncio
async def test_a_request_no_gateway_took_is_withdrawn_and_never_served_late() -> None:
    from test_supervision import database

    database()
    from check_streaming import Fixture
    from lonora_db import broker_relay
    from lonora_db.schema import BrokerRelayRow
    from sqlalchemy import func, select, text

    from scripts.agent_eval.broker import FakeTerminal

    fixture = await Fixture().open()
    db = fixture.runtime.db
    terminal = FakeTerminal(account_id="relay-late-" + str(id(object())))
    connection_id = await connection(fixture, terminal)
    try:
        with pytest.raises(LonoraError) as nobody:
            await broker_relay.ask(db, fixture.owner, connection_id, "symbols", {}, 0.3)
        assert nobody.value.code == "broker_gateway_unavailable"
        assert await broker_relay.claim(db, 16) == []
        # An owner's order nobody claimed is withdrawn at its 5 s window, not after the
        # whole wait, and the owner hears that nothing was done.
        started = asyncio.get_running_loop().time()
        with pytest.raises(LonoraError) as unclaimed:
            await broker_relay.ask(db, fixture.owner, connection_id, "execute", {}, 60)
        assert unclaimed.value.code == "broker_gateway_unavailable"
        assert asyncio.get_running_loop().time() - started < 7
        assert await broker_relay.claim(db, 16) == []
        # Past its window (the database's clock) a request is never claimed: an order
        # older than 5 s, a read older than 30 s.
        async with db.sessions() as session, session.begin():
            for kind, age in (("execute", 6), ("symbols", 31)):
                session.add(
                    BrokerRelayRow(
                        owner_id=fixture.owner,
                        connection_id=connection_id,
                        kind=kind,
                        arguments={},
                        state="pending",
                        created_at=func.now() - text(f"interval '{age} seconds'"),
                    )
                )
        assert await broker_relay.claim(db, 16) == []
        # A rate limit keeps MetaApi's retry time across the relay.
        limited = LonoraError("broker_rate_limited", 429)
        limited.retry_until = 1234.5  # pyright: ignore[reportAttributeAccessIssue]

        async def gateway() -> None:
            requests: list[broker_relay.RelayRequest] = []
            for _ in range(100):
                requests = await broker_relay.claim(db, 16)
                if requests:
                    break
                await asyncio.sleep(0.05)
            await broker_relay.answer(db, requests[0].id, error=limited)

        serving = asyncio.create_task(gateway())
        with pytest.raises(LonoraError) as relayed:
            await broker_relay.ask(db, fixture.owner, connection_id, "quote", {"symbol": "X"}, 10)
        await serving
        assert relayed.value.code == "broker_rate_limited" and relayed.value.status == 429
        assert getattr(relayed.value, "retry_until", None) == 1234.5
    finally:
        async with db.sessions() as session, session.begin():
            for row in await session.scalars(select(BrokerRelayRow)):
                await session.delete(row)
        await remove(fixture, connection_id)
        await fixture.close()


@pytest.mark.asyncio
async def test_an_owner_order_on_a_metaapi_account_is_executed_by_the_gateway() -> None:
    from test_supervision import database

    database()
    from check_streaming import Fixture
    from lonora_adapters.brokers.relay import execute_order
    from lonora_contracts.trading import TradeRequest, TradeResult

    from scripts.agent_eval.broker import FakeTerminal

    fixture = await Fixture().open()
    terminal = FakeTerminal(account_id="relay-order-" + str(id(object())))
    simulated = FakeTerminal(account_id="relay-simulation-" + str(id(object())))
    connection_id = await connection(fixture, terminal)
    simulation_id = await connection(fixture, simulated, "simulation")
    api = fixture.runtime.services(fixture.owner)
    try:
        assert await api.brokers.relayed(fixture.owner, connection_id)
        assert not await api.brokers.relayed(fixture.owner, simulation_id)
        order = TradeRequest.model_validate(
            {
                "account_id": connection_id,
                "symbol": "XAUUSDm",
                "action": "buy",
                "volume": "0.01",
            }
        )
        done = TradeResult(operation_id=order.operation_id, status="confirmed")
        async with Serving(fixture) as gateway:
            gateway.services.trading.execute = AsyncMock(return_value=done)
            api.trading.execute = AsyncMock()
            assert await execute_order(fixture.runtime.db, fixture.owner, order) == done
            # A request naming another connection than its own row is refused.
            from lonora_db import broker_relay

            other = order.model_copy(update={"account_id": simulation_id})
            with pytest.raises(LonoraError) as mismatch:
                await broker_relay.ask(
                    fixture.runtime.db,
                    fixture.owner,
                    connection_id,
                    "execute",
                    other.model_dump(mode="json"),
                    10,
                )
            assert mismatch.value.code == "broker_relay_invalid"
        gateway.services.trading.execute.assert_awaited_once_with(fixture.owner, order)
        api.trading.execute.assert_not_awaited()
    finally:
        await remove(fixture, connection_id, simulation_id)
        await fixture.close()
