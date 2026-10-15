"""Disposable PG + explicitly imported simulation. No MetaApi keys, packets or live trades."""

import asyncio
from datetime import timedelta
from decimal import Decimal
from typing import Any
from uuid import uuid4

from check_streaming import Fixture
from lonora_adapter_kit.types import ToolCall
from lonora_contracts.domain import utcnow
from lonora_contracts.trading import TradeRequest, TradeResult, TradingControl
from lonora_core.user_error import LonoraError
from lonora_db.broker_sessions import BrokerSessionRepository
from lonora_db.schema import EventRow, TradingAccountRow, TradingJournalRow
from lonora_session.idempotency import request_hash
from lonora_tools.loader import load_tools
from lonora_trading.controls import read_controls, save_controls
from lonora_trading.idempotency import trade_fingerprint
from sqlalchemy import delete, func, select


async def main() -> None:
    fixture = await Fixture().open()
    original_controls = await read_controls(fixture.runtime.db)
    connection_id: str | None = None
    operations: list[str] = []
    try:
        agent = await fixture.agent("Pending order fixture")
        thread = await fixture.conversation(agent)
        context = await fixture.lease(await fixture.run(agent, thread))
        connection = await fixture.request(
            "POST",
            "/trading/connections",
            {
                "provider": "simulation",
                "account_id": "opaque-adapter-fixture-" + uuid4().hex,
                "enabled": True,
            },
        )
        connection_id = connection["id"]
        assert isinstance(connection_id, str)
        await fixture.request(
            "POST",
            "/trading/connections/" + connection_id + "/simulation",
            {
                "snapshot": {
                    "broker": "Fixture native broker",
                    "login": "24680",
                    "server": "Fixture-Demo",
                    "platform": "mt5",
                    "balance": "1000",
                    "currency": "USD",
                    "instruments": [
                        {
                            "symbol": "XAUUSD.a",
                            "digits": 2,
                            "tick_size": "0.01",
                            "volume_min": "0.1",
                            "volume_max": "100",
                            "volume_step": "0.1",
                        }
                    ],
                    "quotes": {
                        "XAUUSD.a": {
                            "symbol": "XAUUSD.a",
                            "bid": "100",
                            "ask": "101",
                            "observed_at": utcnow().isoformat(),
                            "source": "explicit-pending-fixture",
                        }
                    },
                }
            },
        )
        registry = load_tools()
        await registry.execute(
            ToolCall(
                id="read-account", name="account_read", arguments={"account_id": connection_id}
            ),
            context,
            read_only=True,
        )
        await registry.execute(
            ToolCall(
                id="read-account-again",
                name="account_read",
                arguments={"account_id": connection_id},
            ),
            context,
            read_only=True,
        )
        directory = await registry.execute(
            ToolCall(id="directory", name="list_accounts", arguments={}), context, read_only=True
        )
        entry = next(
            item for item in directory["accounts"] if item["connection_id"] == connection_id
        )
        assert entry["broker_identity"]["login"] == "24680" and "broker_account_id" not in entry
        async with fixture.runtime.db.sessions() as session:
            cached = await BrokerSessionRepository().get(session, fixture.owner, connection_id)
            assert (
                cached.version == 1 and cached.state["broker_identity"]["connection_version"] == 1
            )
            events = await session.scalar(
                select(func.count())
                .select_from(EventRow)
                .where(
                    EventRow.kind == "broker_identity.updated",
                    EventRow.payload["connection_id"].as_string() == connection_id,
                )
            )
            assert events == 1
        print(
            "PASS broker-native directory identity is cached under unchanged config version and observation-only refresh emits no WS loop"
        )

        await save_controls(fixture.runtime.db, TradingControl(enabled=True))
        service = fixture.runtime.services(fixture.owner).trading

        async def trade(action: str, **fields: Any) -> tuple[TradeRequest, TradeResult]:
            operation = "pending-fixture-" + uuid4().hex
            operations.append(operation)
            request = TradeRequest.model_validate(
                {
                    "account_id": connection_id,
                    "operation_id": operation,
                    "action": action,
                    "symbol": "XAUUSD.a",
                    **fields,
                }
            )
            return request, await service.execute(fixture.owner, request, context.lease)

        requests: list[tuple[TradeRequest, TradeResult]] = []
        for action, price in (
            ("buy_limit", "99"),
            ("sell_limit", "103"),
            ("buy_stop", "103"),
            ("sell_stop", "99"),
        ):
            request, result = await trade(
                action,
                volume="0.1",
                price=price,
                **({"stop_loss": "98", "take_profit": "110"} if action == "buy_limit" else {}),
            )
            assert result.status == "confirmed" and result.details["simulation"] is True
            requests.append((request, result))
        broker = await context.brokers.get(fixture.owner, connection_id)
        assert {order.side for order in await broker.orders()} == {
            "buy_limit",
            "sell_limit",
            "buy_stop",
            "sell_stop",
        }
        replay = await service.execute(fixture.owner, requests[0][0], context.lease)
        assert replay.broker_id == requests[0][1].broker_id and len(await broker.orders()) == 4
        print(
            "PASS all four native pending types persist through the fenced execution journal and replay creates no duplicate order"
        )

        ticket = requests[0][1].broker_id
        assert ticket
        _, edited = await trade("modify_order", order_id=ticket, price="98.50")
        assert edited.status == "confirmed"
        target = next(order for order in await broker.orders() if order.id == ticket)
        assert (target.price, target.stop_loss, target.take_profit) == (
            Decimal("98.50"),
            Decimal(98),
            Decimal(110),
        )
        await trade("modify_order", order_id=ticket, take_profit="111")
        await trade("modify_order", order_id=ticket, clear_stop_loss=True)
        target = next(order for order in await broker.orders() if order.id == ticket)
        assert (
            target.price == Decimal("98.50")
            and target.stop_loss is None
            and target.take_profit == Decimal(111)
        )
        _, cancelled = await trade("cancel_order", order_id=ticket)
        assert cancelled.status == "confirmed" and len(await broker.orders()) == 3
        print(
            "PASS pending price/protection edits preserve unspecified fields; explicit clear and cancel affect only the requested ticket"
        )

        bad_operation = "pending-fixture-" + uuid4().hex
        operations.append(bad_operation)
        bad = TradeRequest(
            account_id=connection_id,
            operation_id=bad_operation,
            action="buy_limit",
            symbol="XAUUSD.a",
            volume=Decimal("0.1"),
            price=Decimal(103),
        )
        try:
            await service.execute(fixture.owner, bad, context.lease)
        except LonoraError as error:
            assert error.code == "pending_price_wrong_side"
        else:
            raise AssertionError("Wrong-side pending price unexpectedly submitted")
        async with fixture.runtime.db.sessions() as session:
            assert await session.get(TradingJournalRow, bad_operation) is None
        assert len(await broker.orders()) == 3
        legacy_payload = requests[0][0].model_dump(mode="json")
        legacy_payload.pop("clear_stop_loss")
        legacy_payload.pop("clear_take_profit")
        legacy_payload.pop("thesis_id")
        assert trade_fingerprint(requests[0][0]) == request_hash(legacy_payload)
        print(
            "PASS invalid pending geometry is rejected before submission and default-false clear fields preserve legacy journal fingerprints"
        )
        await trade("buy", volume="0.1", stop_loss="99", take_profit="105")
        await trade("sell", volume="0.1", stop_loss="105", take_profit="99")
        assert len(await broker.positions()) == 2

        async def rejects_market(expected: str, **fields: Any) -> None:
            try:
                await trade("buy", volume="0.1", **fields)
            except LonoraError as error:
                assert error.code == expected, (error.code, expected)
            else:
                raise AssertionError("Expected " + expected)

        await rejects_market("stop_loss_wrong_side", stop_loss="102")
        async with fixture.runtime.db.sessions() as session, session.begin():
            account_row = await session.get(TradingAccountRow, connection_id)
            assert account_row is not None
            data = dict(account_row.payload)
            original_instruments = data["instruments"]
            quote = {
                **data["quotes"]["XAUUSD.a"],
                "observed_at": (utcnow() - timedelta(seconds=120)).isoformat(),
            }
            account_row.payload = {**data, "quotes": {"XAUUSD.a": quote}}
        await rejects_market("market_quote_stale")
        async with fixture.runtime.db.sessions() as session, session.begin():
            account_row = await session.get(TradingAccountRow, connection_id)
            assert account_row is not None
            account_row.payload = {**account_row.payload, "instruments": []}
        _, stale_cancel = await trade("cancel_order", order_id=requests[1][1].broker_id)
        assert stale_cancel.status == "confirmed"
        async with fixture.runtime.db.sessions() as session, session.begin():
            account_row = await session.get(TradingAccountRow, connection_id)
            assert account_row is not None
            data = dict(account_row.payload)
            quote = {
                **data["quotes"]["XAUUSD.a"],
                "observed_at": utcnow().isoformat(),
                "symbol": "WRONG-SYMBOL",
            }
            account_row.payload = {
                **data,
                "quotes": {"XAUUSD.a": quote},
                "instruments": original_instruments,
            }
        await rejects_market("broker_symbol_mismatch")
        async with fixture.runtime.db.sessions() as session, session.begin():
            account_row = await session.get(TradingAccountRow, connection_id)
            assert account_row is not None
            data = dict(account_row.payload)
            quote = {
                **data["quotes"]["XAUUSD.a"],
                "observed_at": utcnow().isoformat(),
                "symbol": "XAUUSD.a",
            }
            account_row.payload = {**data, "quotes": {"XAUUSD.a": quote}, "trade_allowed": False}
        await rejects_market("broker_trading_not_allowed")
        assert len(await broker.positions()) == 2
        print(
            "PASS ordinary buy/sell require fresh exact broker quotes and valid protection; native trade denial blocks while stale quotes/delisted specifications do not block exact-ticket cancellation"
        )

        async with fixture.runtime.db.sessions() as session, session.begin():
            row = await BrokerSessionRepository().get(session, fixture.owner, connection_id)
            await BrokerSessionRepository().update(
                session,
                fixture.owner,
                connection_id,
                {**row.payload, "enabled": False},
                row.version,
            )
        directory = await registry.execute(
            ToolCall(id="changed-directory", name="list_accounts", arguments={}),
            context,
            read_only=True,
        )
        entry = next(
            item for item in directory["accounts"] if item["connection_id"] == connection_id
        )
        assert entry["broker_identity"] is None and entry["enabled"] is False
        print(
            "PASS connection edits invalidate old native identity rather than presenting stale labels as current"
        )
    finally:
        await save_controls(fixture.runtime.db, original_controls)
        async with fixture.runtime.db.sessions() as session, session.begin():
            await session.execute(
                delete(TradingJournalRow).where(TradingJournalRow.operation_id.in_(operations))
            )
        if connection_id:
            await fixture.request("DELETE", "/trading/connections/" + connection_id)
        await fixture.close()


if __name__ == "__main__":
    asyncio.run(main())
