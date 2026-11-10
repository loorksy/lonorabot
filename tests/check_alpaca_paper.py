"""Alpaca paper journey through the authenticated API and the single executor.

Runs on disposable PostgreSQL against the local fake Alpaca server (tests/alpaca_fake.py):
the provider catalog, a verified paper connection, owner-path executions with the signed
send boundary, a lost response that recovery settles from the client order id without a
resend, a protection edit, a close refused because exit legs hold the quantity, Trading
OFF blocking an entry while an exit still runs, a lost close settled from broker target
state, and a scan proving the keys never reach the database's readable records or the
logs. No network and no Alpaca account are involved.
"""

import asyncio
import logging
from decimal import Decimal
from typing import Any, cast
from uuid import uuid4

from alpaca_fake import KEY_ID, SECRET_KEY, FakeAlpaca, Transport
from check_streaming import Fixture
from lonora_adapters.brokers import alpaca
from lonora_contracts.trading import TradeRequest, TradingControl
from lonora_core.user_error import LonoraError
from lonora_db.schema import BrokerSessionRow, EventRow, TradingJournalRow
from lonora_trading.controls import read_controls, save_controls
from lonora_trading.reconciliation import reconcile_ambiguous
from sqlalchemy import delete, select

AAPL_ID = "b0b6dd9d-8b9b-48a9-ba46-b9d54906e415"
BTC_ID = "276e2673-764b-4ab6-a611-caf665ca6340"


class Capture(logging.Handler):
    def __init__(self) -> None:
        super().__init__(logging.DEBUG)
        self.lines: list[str] = []

    def emit(self, record: logging.LogRecord) -> None:
        self.lines.append(self.format(record))


async def main() -> None:
    fake = FakeAlpaca()
    transport = Transport(fake)
    alpaca.transport_factory = lambda: transport
    capture = Capture()
    logging.getLogger().addHandler(capture)
    logging.getLogger().setLevel(logging.DEBUG)
    fixture = await Fixture().open()
    db = fixture.runtime.db
    original = await read_controls(db)
    operations: list[str] = []
    connection_id: str | None = None
    try:
        catalog = await fixture.client.get("/api/trading/providers")
        entry = next(item for item in catalog.json() if item["provider"] == "alpaca")
        assert entry["environment"] == "paper" and entry["live_trading"] is False
        assert [field["name"] for field in entry["fields"]] == ["key_id", "secret_key"]
        print("PASS the provider catalog offers Alpaca as paper only with its two key fields")

        wrong = await fixture.client.post(
            "/api/trading/connections",
            json={"provider": "alpaca", "key_id": KEY_ID, "secret_key": "wrong", "enabled": True},
        )
        assert wrong.status_code == 409 and wrong.json()["code"] == "broker_credentials_rejected"
        mixed = await fixture.client.post(
            "/api/trading/connections",
            json={"provider": "alpaca", "api_key": SECRET_KEY, "enabled": True},
        )
        assert mixed.status_code == 422
        body = {"provider": "alpaca", "key_id": KEY_ID, "secret_key": SECRET_KEY, "enabled": True}
        created = await fixture.client.post("/api/trading/connections", json=body)
        assert created.status_code == 201, created.text
        connection = created.json()
        connection_id = cast(str, connection["id"])
        assert connection["payload"]["account_id"] == "PA3TEST00001"
        assert connection["payload"]["provider"] == "alpaca" and connection["payload"]["secret_id"]
        assert KEY_ID not in created.text and SECRET_KEY not in created.text
        again = await fixture.client.post("/api/trading/connections", json=body)
        assert (
            again.status_code == 409 and again.json()["code"] == "broker_account_already_connected"
        )
        listed = await fixture.client.get("/api/trading/connections")
        assert KEY_ID not in listed.text and SECRET_KEY not in listed.text
        async with db.sessions() as session:
            row = await session.get(BrokerSessionRow, connection_id)
            assert row is not None
            identity = row.state["broker_identity"]
            assert (identity["login"], identity["platform"]) == ("PA3TEST00001", "alpaca")
        print(
            "PASS a paper connection is verified read-only; wrong keys and duplicates are refused"
        )

        snapshot = await fixture.request("GET", f"/trading/accounts/{connection_id}")
        assert snapshot["account"]["currency"] == "USD", snapshot
        print("PASS the account snapshot reads the paper account in its currency")

        await save_controls(db, TradingControl(enabled=True))
        service = fixture.runtime.services(fixture.owner).trading
        brokers = fixture.runtime.services(fixture.owner).brokers
        account = connection_id

        def trade(action: str, symbol: str = "AAPL", **fields: Any) -> TradeRequest:
            operation = "alpaca-" + uuid4().hex
            operations.append(operation)
            return TradeRequest.model_validate(
                {
                    "account_id": account,
                    "operation_id": operation,
                    "action": action,
                    "symbol": symbol,
                    **fields,
                }
            )

        async def journal(operation_id: str) -> TradingJournalRow:
            async with db.sessions() as session:
                row = await session.get(TradingJournalRow, operation_id, populate_existing=True)
                assert row is not None
                return row

        bracket = trade("buy", volume="2", stop_loss="220", take_profit="240")
        result = await service.execute(fixture.owner, bracket)
        assert result.status == "confirmed", result
        row = await journal(bracket.operation_id)
        assert row.result["details"]["execution"]["send_authorized"] is True
        assert row.result["details"]["verification"]["status"] == "verified", row.result
        placed = [o for o in fake.orders.values() if o.get("group_role") == "entry"]
        assert placed[0]["client_order_id"] == alpaca.client_order_id(bracket.operation_id)
        print("PASS an owner bracket entry crosses before_send once and verifies from broker state")

        lost = trade("buy", "BTC/USD", volume="0.5")
        transport.lose_after.add("POST /v2/orders")
        sent_before = len(fake.mutations)
        result = await service.execute(fixture.owner, lost)
        assert result.status == "ambiguous", result
        assert await reconcile_ambiguous(db, brokers) >= 1
        row = await journal(lost.operation_id)
        assert row.status == "confirmed" and row.result["details"].get("reconciled") is True, (
            row.result
        )
        assert len(fake.mutations) == sent_before + 1  # observed, never resent
        tagged = [
            o
            for o in fake.orders.values()
            if o["client_order_id"] == alpaca.client_order_id(lost.operation_id)
        ]
        assert len(tagged) == 1
        print(
            "PASS a lost entry response is ambiguous, then confirmed by client order id, no resend"
        )

        tighten = trade("modify_position", position_id=AAPL_ID, stop_loss="225")
        result = await service.execute(fixture.owner, tighten)
        assert result.status == "confirmed", result
        position = next(
            p
            for p in await (await brokers.get(fixture.owner, account)).positions()
            if p.id == AAPL_ID
        )
        assert position.stop_loss == Decimal(225) and position.take_profit == Decimal(240)
        print("PASS tightening a stop replaces exactly the stop leg")

        held = trade("close_position", position_id=AAPL_ID)
        result = await service.execute(fixture.owner, held)
        assert (result.status, result.code) == ("failed", "broker_request_rejected"), result
        print("PASS closing a protected stock position is refused by Alpaca (legs hold the qty)")

        await save_controls(db, TradingControl(enabled=False))
        sent_before = len(fake.mutations)
        try:
            await service.execute(fixture.owner, trade("buy", "BTC/USD", volume="0.1"))
        except LonoraError as error:
            assert error.code == "trading_disabled", error.code
        else:
            raise AssertionError("Trading OFF admitted a new entry")
        assert len(fake.mutations) == sent_before
        partial = trade("close_position", "BTC/USD", position_id=BTC_ID, volume="0.2")
        result = await service.execute(fixture.owner, partial)
        assert result.status == "confirmed", result
        print("PASS Trading OFF blocks an entry before any send and still runs an exit")

        exit_all = trade("close_position", "BTC/USD", position_id=BTC_ID)
        transport.lose_after.add(f"DELETE /v2/positions/{BTC_ID}")
        result = await service.execute(fixture.owner, exit_all)
        assert result.status == "ambiguous", result
        await reconcile_ambiguous(db, brokers)
        row = await journal(exit_all.operation_id)
        assert row.status == "resolved", (row.status, row.result)
        assert row.result["code"] == "target_closed", row.result
        assert row.result["details"]["resolution"]["source"] == "broker_state"
        print("PASS a lost close is settled from broker target state (target_closed), not resent")

        async with db.sessions() as session:
            texts = [
                str(item.result)
                for item in await session.scalars(
                    select(TradingJournalRow).where(TradingJournalRow.operation_id.in_(operations))
                )
            ] + [str(item.payload) for item in await session.scalars(select(EventRow))]
            texts += [
                str(r.payload) + str(r.state)
                for r in await session.scalars(select(BrokerSessionRow))
            ]
        haystack = "\n".join(texts + capture.lines)
        assert KEY_ID not in haystack and SECRET_KEY not in haystack
        print("PASS the keys appear in no journal entry, event, connection record or log line")

        assert fake.seen_hosts <= {"paper-api.alpaca.markets", "data.alpaca.markets"}
        print("PASS only the paper trading host and the market data host were addressed")
    finally:
        await save_controls(db, original)
        async with db.sessions() as session, session.begin():
            await session.execute(
                delete(TradingJournalRow).where(TradingJournalRow.operation_id.in_(operations))
            )
        if connection_id:
            await fixture.client.delete("/api/trading/connections/" + connection_id)
        await fixture.close()
        alpaca.transport_factory = None


if __name__ == "__main__":
    asyncio.run(main())
