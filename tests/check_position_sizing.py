"""Disposable PostgreSQL, real simulation import and registered read-only sizing."""

import asyncio
from decimal import Decimal
from unittest.mock import AsyncMock, patch
from uuid import uuid4

from check_streaming import Fixture
from lonora_adapter_kit.types import ToolCall
from lonora_contracts.domain import utcnow
from lonora_core.user_error import LonoraError
from lonora_db.schema import TradeApprovalRow, TradingAccountRow, TradingJournalRow
from lonora_tools.loader import load_tools
from sqlalchemy import func, select


async def main() -> None:
    fixture = await Fixture().open()
    try:
        symbols = ["EURUSDm", "XAUUSD.a", "US500.cash", "BTCUSD#"]
        created = await fixture.request(
            "POST",
            "/trading/connections",
            {
                "provider": "simulation",
                "account_id": "sizing-fixture-" + uuid4().hex,
                "enabled": True,
            },
        )
        account_id = created["id"]
        await fixture.request(
            "POST",
            f"/trading/connections/{account_id}/simulation",
            {
                "snapshot": {
                    "currency": "USDc",
                    "balance": "1000000",
                    "instruments": [
                        {
                            "symbol": symbol,
                            "digits": 2,
                            "tick_size": "0.01",
                            "volume_min": "0.03",
                            "volume_max": "100",
                            "volume_step": "0.02",
                            "contract_size": "100",
                            "profit_currency": "USD",
                            "point_size": "0.01",
                            "stops_level": 10,
                        }
                        for symbol in symbols
                    ],
                    "quotes": {
                        symbol: {
                            "symbol": symbol,
                            "bid": "100.00",
                            "ask": "100.02",
                            "observed_at": utcnow().isoformat(),
                            "source": "explicit_simulation",
                            "profit_tick_value": "0.9",
                            "loss_tick_value": "1",
                            "tick_value_basis": "account_currency_per_lot",
                            "account_currency_exchange_rate": "0.01",
                        }
                        for symbol in symbols
                    },
                },
            },
        )
        agent = await fixture.agent("Personal sizing fixture")
        thread = await fixture.conversation(agent)
        context = await fixture.lease(await fixture.run(agent, thread))
        registry = load_tools()
        assert registry.tools["market_position_size"].read_only
        assert not registry.tools["market_position_size"].financial
        broker = await context.brokers.get(fixture.owner, account_id)
        async with fixture.runtime.db.sessions() as session:
            before_journal = await session.scalar(
                select(func.count()).select_from(TradingJournalRow)
            )
            before_approvals = await session.scalar(
                select(func.count()).select_from(TradeApprovalRow)
            )

        async def run(symbol: str, **overrides: object):
            return await registry.execute(
                ToolCall(
                    id=uuid4().hex,
                    name="market_position_size",
                    arguments={
                        "account_id": account_id,
                        "symbol": symbol,
                        "side": "buy",
                        "risk_budget": "50",
                        "currency": "USDc",
                        "stop_loss": "99.00",
                        **overrides,
                    },
                ),
                context,
                read_only=True,
            )

        with patch.object(broker, "execute", AsyncMock()) as mutate:
            results = await asyncio.gather(*(run(symbol) for symbol in symbols))
            assert {result["symbol"] for result in results} == set(symbols)
            for result in results:
                assert result["currency"] == "USDc" and result["execution_authorized"] is False
                assert Decimal(result["volume"]) == Decimal("0.49")
                assert Decimal(result["modeled_stop_loss"]) == Decimal("49.98")
                assert result["instrument"]["profit_currency"] == "USD"
            mutate.assert_not_awaited()
        print(
            "PASS real simulation import retains broker economics; concurrent exact-market USDc estimates never convert or execute"
        )

        for symbol, overrides, code in (
            (symbols[0], {"currency": "USD"}, "position_sizing_currency_mismatch"),
            ("not-a-broker-symbol", {}, "broker_instrument_unavailable"),
        ):
            try:
                await run(symbol, **overrides)
            except LonoraError as error:
                assert error.code == code, error.code
            else:
                raise AssertionError("unsafe estimate accepted")

        actual = await broker.account()
        with patch.object(
            broker, "account", AsyncMock(return_value=actual.model_copy(update={"id": "other"}))
        ):
            try:
                await run(symbols[0])
            except LonoraError as error:
                assert error.code == "position_sizing_account_mismatch"
            else:
                raise AssertionError("broker account identity was rewritten")

        specialist = await fixture.request(
            "POST",
            "/agents",
            {
                "name": "Sizing specialist",
                "trading_account_id": account_id,
                "trading_symbol": symbols[0],
            },
        )
        fixture.agents.append(specialist["id"])
        specialist_thread = await fixture.conversation(specialist)
        specialist_context = await fixture.lease(await fixture.run(specialist, specialist_thread))
        try:
            await registry.execute(
                ToolCall(
                    id=uuid4().hex,
                    name="market_position_size",
                    arguments={
                        "account_id": account_id,
                        "symbol": symbols[1],
                        "side": "buy",
                        "risk_budget": "50",
                        "currency": "USDc",
                        "stop_loss": "99",
                    },
                ),
                specialist_context,
            )
        except LonoraError as error:
            assert error.code == "agent_trading_symbol_mismatch"
        else:
            raise AssertionError("specialist crossed its exact-symbol boundary")
        print("PASS native currency/account identity and specialist symbol scope fail closed")

        async with fixture.runtime.db.sessions() as session, session.begin():
            row = await session.get(TradingAccountRow, account_id, with_for_update=True)
            assert row is not None
            quotes = dict(row.payload["quotes"])
            quote = dict(quotes[symbols[0]])
            quote.pop("loss_tick_value")
            quotes[symbols[0]] = quote
            row.payload = {**row.payload, "quotes": quotes}
        assert (await broker.quote(symbols[0])).bid == 100
        try:
            await run(symbols[0])
        except LonoraError as error:
            assert error.code == "position_sizing_economics_unavailable"
        else:
            raise AssertionError("missing money economics accepted")
        async with fixture.runtime.db.sessions() as session:
            assert (
                await session.scalar(select(func.count()).select_from(TradingJournalRow))
                == before_journal
            )
            assert (
                await session.scalar(select(func.count()).select_from(TradeApprovalRow))
                == before_approvals
            )
        assert not await broker.positions() and not await broker.orders()
        print(
            "PASS missing economics keeps prices available; estimates create no approvals, journals, positions or orders"
        )
    finally:
        await fixture.close()


if __name__ == "__main__":
    asyncio.run(main())
