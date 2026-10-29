"""Real disposable PostgreSQL identity, scope, discovery and inbox/anchor checks."""

import asyncio
from uuid import uuid4

from check_streaming import Fixture
from lonora_adapter_kit.types import ToolCall
from lonora_contracts.domain import AgentCreate, utcnow
from lonora_db.agent_binding import assert_market_binding, binding_context
from lonora_db.agents import create_agent
from lonora_db.personal_agent import (
    account_event_agent,
    discover_specialists,
    ensure_personal_agent,
)
from lonora_db.schema import AgentRow, MessageRow, TradeApprovalRow
from lonora_tools.loader import load_tools
from sqlalchemy import func, select


async def checks() -> None:
    f = await Fixture().open()
    connections: list[str] = []
    original_name = "Lonora"
    personal_id = ""
    try:

        async def bootstrap() -> str:
            async with f.runtime.db.sessions() as session, session.begin():
                return (await ensure_personal_agent(session, f.owner)).id

        identities = await asyncio.gather(*(bootstrap() for _ in range(12)))
        assert len(set(identities)) == 1
        personal_id = identities[0]
        async with f.runtime.db.sessions() as session:
            assert (
                await session.scalar(
                    select(func.count())
                    .select_from(AgentRow)
                    .where(AgentRow.owner_id == f.owner, AgentRow.role == "personal")
                )
                == 1
            )
            agent = await session.get(AgentRow, personal_id)
            assert agent is not None
            original_name = agent.name
            assert agent.trading_symbol is None and "NOT" in binding_context(agent)
        renamed = await f.request(
            "PATCH", f"/agents/{personal_id}", {"name": "Owner " + uuid4().hex[:8]}
        )
        assert renamed["role"] == "personal" and await bootstrap() == personal_id
        denied = await f.client.delete(f"/api/agents/{personal_id}")
        assert denied.status_code == 409 and denied.json()["code"] == "personal_agent_cannot_delete"
        forged = await f.client.post("/api/agents", json={"name": "Impostor", "role": "personal"})
        assert forged.status_code == 422
        print(
            "PASS exactly one Personal Agent across concurrent bootstrap, rename and reconnect; client cannot forge/delete it"
        )

        symbols = ["EURUSDm", "XAUUSD.pro", "US500.cash", "BTCUSD.a"]
        connection = await f.request(
            "POST",
            "/trading/connections",
            {"provider": "simulation", "account_id": uuid4().hex, "enabled": True},
        )
        account = connection["id"]
        connections.append(account)
        await f.request(
            "POST",
            f"/trading/connections/{account}/simulation",
            {
                "snapshot": {
                    "currency": "USD",
                    "balance": "10000",
                    "instruments": [
                        {
                            "symbol": symbol,
                            "digits": 2,
                            "tick_size": "0.01",
                            "volume_min": "0.1",
                            "volume_max": "100",
                            "volume_step": "0.1",
                        }
                        for symbol in symbols
                    ],
                    "quotes": {
                        symbol: {
                            "symbol": symbol,
                            "bid": "100",
                            "ask": "101",
                            "observed_at": utcnow().isoformat(),
                            "source": "explicit-personal-fixture",
                        }
                        for symbol in symbols
                    },
                }
            },
        )
        personal = await f.request("GET", f"/agents/{personal_id}")
        thread = await f.conversation(personal)
        context = await f.lease(await f.run(personal, thread))
        registry = load_tools()
        actual = await registry.execute(
            ToolCall(id=uuid4().hex, name="market_symbols", arguments={"account_id": account}),
            context,
        )
        assert set(symbols) <= set(actual["symbols"])
        permission = await f.request("GET", f"/agents/{personal_id}/permissions")
        assert permission["effective_level"] == "analysis"
        await f.request(
            "PUT",
            f"/agents/{personal_id}/permissions",
            {"level": "supervised", "expected_revision": permission["revision"]},
        )
        trade = await registry.execute(
            ToolCall(
                id=uuid4().hex,
                name="trade_execute",
                arguments={
                    "account_id": account,
                    "symbol": symbols[0],
                    "action": "buy",
                    "volume": "0.1",
                },
            ),
            context,
        )
        assert trade["_runtime_wait"] is True
        broker = await context.brokers.get(f.owner, account)
        assert await broker.positions() == []
        async with f.runtime.db.sessions() as session:
            approval = await session.get(TradeApprovalRow, trade["approval_id"])
            assert (
                approval
                and approval.status == "pending"
                and approval.timeline_seq == thread.get("next_seq", 1)
            )
        print(
            "PASS Personal Agent reads multiple exact broker markets; visibility still requires durable approval before execution"
        )

        async with f.runtime.db.sessions() as session, session.begin():
            a = await create_agent(
                session,
                f.owner,
                AgentCreate(
                    name="Unrelated display name",
                    trading_account_id=account,
                    trading_symbol=symbols[0],
                ),
            )
            f.agents.append(a.id)
            b = await create_agent(
                session,
                f.owner,
                AgentCreate(
                    name="EURUSD misleading", trading_account_id=account, trading_symbol=symbols[1]
                ),
            )
            f.agents.append(b.id)
            assert [
                row.id for row in await discover_specialists(session, f.owner, account, symbols[0])
            ] == [a.id]
            assert await discover_specialists(session, f.owner, account, symbols[2]) == []
            assert_market_binding(a, account, symbols[0])
            assert (await account_event_agent(session, f.owner)).id == personal_id
            message = MessageRow(
                thread_id=thread["id"],
                role="assistant",
                agent_id=personal_id,
                seq=1,
                content="Canonical newest preview",
            )
            session.add(message)
        inbox = (await f.client.get("/api/threads/inbox")).json()
        entry = next(row for row in inbox if row["agent_id"] == personal_id)
        assert entry["last_message"]["content"] == "Canonical newest preview"
        assert entry["last_message"]["seq"] == 1
        print(
            "PASS specialist discovery is structured, no-specialist fallback stays Personal; account owner unique; inbox returns durable newest message"
        )
    finally:
        if personal_id:
            await f.request("PATCH", f"/agents/{personal_id}", {"name": original_name})
            async with f.runtime.db.sessions() as session, session.begin():
                from lonora_db.schema import ThreadRow

                thread_ids = list(
                    await session.scalars(
                        select(ThreadRow.id).where(ThreadRow.agent_id == personal_id)
                    )
                )
                from lonora_db.schema import RunRow
                from sqlalchemy import delete

                await session.execute(delete(RunRow).where(RunRow.thread_id.in_(thread_ids)))
                await session.execute(
                    delete(MessageRow).where(MessageRow.thread_id.in_(thread_ids))
                )
                for row in (
                    await session.scalars(select(ThreadRow).where(ThreadRow.id.in_(thread_ids)))
                ).all():
                    row.next_seq = 1
        for connection in connections:
            await f.client.delete(f"/api/trading/connections/{connection}")
        await f.close()


if __name__ == "__main__":
    asyncio.run(checks())
