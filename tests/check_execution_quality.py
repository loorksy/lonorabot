"""Disposable PostgreSQL + real simulation adapter; no live broker or live money."""

import asyncio
from decimal import Decimal
from uuid import uuid4

from check_streaming import Fixture
from lonora_contracts.domain import utcnow
from lonora_contracts.trading import TradeRequest, TradingControl
from lonora_db.schema import TradingAccountRow, TradingJournalRow
from lonora_trading.controls import read_controls, save_controls


async def main() -> None:
    fixture = await Fixture().open()
    db = fixture.runtime.db
    original = await read_controls(db)
    try:
        created = await fixture.request(
            "POST",
            "/trading/connections",
            {
                "provider": "simulation",
                "account_id": "quality-fixture-" + uuid4().hex,
                "enabled": True,
            },
        )
        account_id = created["id"]
        symbol = "EURUSDm"
        await fixture.request(
            "POST",
            f"/trading/connections/{account_id}/simulation",
            {
                "snapshot": {
                    "balance": "10000",
                    "currency": "USD",
                    "instruments": [
                        {
                            "symbol": symbol,
                            "digits": 5,
                            "tick_size": "0.00001",
                            "volume_min": "0.1",
                            "volume_max": "100",
                            "volume_step": "0.1",
                        }
                    ],
                    "quotes": {
                        symbol: {
                            "symbol": symbol,
                            "bid": "1.10000",
                            "ask": "1.10020",
                            "observed_at": utcnow().isoformat(),
                            "source": "quality-fixture",
                        }
                    },
                    "positions": [
                        {
                            "id": "manual-ticket",
                            "symbol": symbol,
                            "side": "buy",
                            "volume": "0.1",
                            "open_price": "1.1",
                        }
                    ],
                }
            },
        )
        # Simulate an external MT5 position in the authoritative broker state,
        # independently of Lonora's operation ledger. Import API intentionally
        # initializes a clean demo account and does not import live positions.
        async with db.sessions() as session, session.begin():
            row = await session.get(TradingAccountRow, account_id, with_for_update=True)
            assert row is not None
            row.payload = {
                **row.payload,
                "positions": [
                    {
                        "id": "manual-ticket",
                        "symbol": symbol,
                        "side": "buy",
                        "volume": "0.1",
                        "open_price": "1.1",
                    }
                ],
            }
        await save_controls(db, TradingControl(enabled=True))
        await fixture.request(
            "PUT",
            f"/trading/accounts/{account_id}/execution-policy",
            {
                "max_symbol_direction_volume": "0.2",
            },
        )
        service = fixture.runtime.services(fixture.owner).trading
        operations = [
            TradeRequest(account_id=account_id, symbol=symbol, action="buy", volume=Decimal("0.1"))
            for _ in range(2)
        ]
        outcomes = await asyncio.gather(
            *(service.execute(fixture.owner, operation) for operation in operations)
        )
        assert sorted(result.status for result in outcomes) == ["confirmed", "failed"], [
            (item.status, item.code) for item in outcomes
        ]
        failed = next(item for item in outcomes if item.status == "failed")
        assert failed.code == "portfolio_direction_volume_limit"
        exposure = await fixture.request("GET", f"/trading/accounts/{account_id}/exposure")
        assert len(exposure["buckets"]) == 1
        assert exposure["buckets"][0]["position_volume"] == "0.2"
        assert exposure["notional"] is None and exposure["monetary_stop_risk"] is None
        async with db.sessions() as session:
            row = await session.get(TradingJournalRow, failed.operation_id)
            assert row is not None
            assert row.result["details"]["execution_quality"]["state"] == "blocked"
        repeated = await service.execute(
            fixture.owner, next(op for op in operations if op.operation_id == failed.operation_id)
        )
        assert repeated == failed
        print(
            "PASS two concurrent operations serialized: manual + other-agent risk cannot bypass owner cap; blocked result durable/idempotent"
        )
        # A target opened outside Lonora remains closable even over the entry cap.
        close = await service.execute(
            fixture.owner,
            TradeRequest(
                account_id=account_id,
                symbol=symbol,
                action="close_position",
                position_id="manual-ticket",
            ),
        )
        assert close.status == "confirmed"
        print("PASS owner manual position closes despite entry limit")
    finally:
        await save_controls(db, original)
        await fixture.close()


if __name__ == "__main__":
    asyncio.run(main())
