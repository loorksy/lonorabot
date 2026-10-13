"""Actual API/PG broker-ID discovery; explicitly imported simulation, no live trades."""

import asyncio
from uuid import uuid4

from check_streaming import Fixture
from lonora_adapter_kit.types import ToolCall
from lonora_core.user_error import LonoraError
from lonora_db.schema import TradingAccountRow
from lonora_tools.loader import load_tools


async def main() -> None:
    fixture = await Fixture().open()
    connection_id = None
    try:
        agent = await fixture.agent("Broker discovery fixture")
        thread = await fixture.conversation(agent)
        context = await fixture.lease(await fixture.run(agent, thread))
        external_id = "external-metaapi-style-" + uuid4().hex
        connection = await fixture.request(
            "POST",
            "/trading/connections",
            {
                "provider": "simulation",
                "account_id": external_id,
                "enabled": True,
            },
        )
        connection_id = connection["id"]
        await fixture.request(
            "POST",
            f"/trading/connections/{connection_id}/simulation",
            {
                "snapshot": {"balance": "1234.50", "currency": "USD"},
            },
        )
        registry = load_tools()
        directory = await registry.execute(
            ToolCall(id="list", name="list_accounts", arguments={}), context, read_only=True
        )
        row = next(item for item in directory["accounts"] if item["connection_id"] == connection_id)
        assert row["broker_account_id"] == external_id
        assert "secret_id" not in row and "api_key" not in row
        try:
            await registry.execute(
                ToolCall(id="wrong", name="account_read", arguments={"account_id": external_id}),
                context,
                read_only=True,
            )
            raise AssertionError("External ID unexpectedly accepted")
        except LonoraError as error:
            assert error.code == "broker_sessions_not_found"
        actual = await registry.execute(
            ToolCall(
                id="actual", name="account_read", arguments={"account_id": row["connection_id"]}
            ),
            context,
            read_only=True,
        )
        assert "1234.50" in str(actual) and "USD" in str(actual), actual
        print(
            "PASS saved account discovery uses the internal connection ID and reads actual imported balance without exposing secrets"
        )
    finally:
        if connection_id:
            async with fixture.runtime.db.sessions() as session, session.begin():
                row = await session.get(TradingAccountRow, connection_id)
                if row:
                    await session.delete(row)
            await fixture.request("DELETE", f"/trading/connections/{connection_id}")
        await fixture.close()


if __name__ == "__main__":
    asyncio.run(main())
