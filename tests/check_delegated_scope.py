"""Delegated research identities never inherit owner-wide financial authority."""

import asyncio
from decimal import Decimal
from typing import Any
from uuid import uuid4

from check_streaming import Fixture
from lonora_adapter_kit.types import ToolCall
from lonora_contracts.domain import AgentCreate
from lonora_contracts.runs import RunRequest
from lonora_contracts.trading import TradeRequest
from lonora_contracts.trading_goal import GoalCreate, GoalStep
from lonora_core.user_error import LonoraError
from lonora_db.agent_binding import require_financial_agent
from lonora_db.agents import agent_data, create_agent
from lonora_db.runs import create_run, run_data
from lonora_db.schema import AgentRow
from lonora_db.trading_goals import create_goal
from lonora_tools.loader import load_tools


async def denied(awaitable: Any) -> None:
    try:
        await awaitable
    except LonoraError as error:
        assert error.code == "delegated_financial_authority_forbidden", error.code
    else:
        raise AssertionError("Delegation gained financial authority")


async def main() -> None:
    f = await Fixture().open()
    connection = ""
    try:
        personal = next(
            a for a in (await f.client.get("/api/agents")).json() if a["role"] == "personal"
        )
        connection = (
            await f.request(
                "POST",
                "/trading/connections",
                {"provider": "simulation", "account_id": uuid4().hex, "enabled": True},
            )
        )["id"]
        await f.request(
            "POST",
            f"/trading/connections/{connection}/simulation",
            {"snapshot": {"balance": "10000", "currency": "USD"}},
        )
        async with f.runtime.db.sessions() as session, session.begin():
            child = await create_agent(
                session, f.owner, AgentCreate(name="Personal researcher"), parent_id=personal["id"]
            )
            grandchild = await create_agent(
                session, f.owner, AgentCreate(name="Research descendant"), parent_id=child.id
            )
            specialist = await create_agent(
                session,
                f.owner,
                AgentCreate(
                    name="Bound specialist", trading_account_id=connection, trading_symbol="EURUSDm"
                ),
            )
            bound_child = await create_agent(
                session, f.owner, AgentCreate(name="Specialist child"), parent_id=specialist.id
            )
            f.agents.extend([child.id, grandchild.id, bound_child.id, specialist.id])
            child_data = agent_data(child)
            grandchild_data = agent_data(grandchild)
            specialist_data = agent_data(specialist)
            assert child.role == grandchild.role == "delegated"
            assert child_data["scope"]["execution_authority"] == "none"
            assert child.trading_account_id is None and child.trading_symbol is None
            assert bound_child.role == "specialist" and bound_child.trading_symbol == "EURUSDm"
            assert bound_child.trading_account_id == connection
        thread = await f.conversation(child_data)
        context = await f.lease(await f.run(child_data, thread))
        registry = load_tools()
        account = await registry.execute(
            ToolCall(id="allowed-read", name="account_read", arguments={"account_id": connection}),
            context,
        )
        assert account["account"]["balance"] == "10000"
        await denied(
            registry.execute(
                ToolCall(
                    id="forbidden-trade",
                    name="trade_execute",
                    arguments={
                        "account_id": connection,
                        "symbol": "BTCUSD.pro",
                        "action": "buy",
                        "volume": "0.1",
                    },
                ),
                context,
            )
        )
        async with f.runtime.db.sessions() as session, session.begin():
            await denied(
                create_goal(
                    session,
                    f.owner,
                    GoalCreate(
                        agent_id=child.id,
                        thread_id=thread["id"],
                        title="Bypass attempt",
                        objective="Not financial authority",
                        account_id=connection,
                        symbol="BTCUSD.pro",
                        steps=[GoalStep(id="a", title="Analyze")],
                    ),
                )
            )
        async with f.runtime.db.sessions() as session, session.begin():
            await denied(
                create_agent(
                    session,
                    f.owner,
                    AgentCreate(
                        name="Laundered", trading_account_id=connection, trading_symbol="XAUUSDm"
                    ),
                    parent_id=child.id,
                )
            )
        print(
            "PASS Personal children and descendants are explicit research identities: account reads work, arbitrary trade/goal/scope laundering fail before proposal"
        )
        descendant_thread = await f.conversation(grandchild_data)
        descendant_context = await f.lease(await f.run(grandchild_data, descendant_thread))
        await f.request("PUT", "/trading/controls", {"enabled": True, "emergency_stop": False})
        await denied(
            descendant_context.trading.execute(
                f.owner,
                TradeRequest(
                    operation_id=uuid4().hex,
                    account_id=connection,
                    symbol="EURUSDm",
                    action="buy",
                    volume=Decimal("0.1"),
                ),
                descendant_context.lease,
            )
        )
        # Even an otherwise valid specialist peer cannot turn delegated run ancestry into authority.
        specialist_thread = await f.conversation(specialist_data)
        async with f.runtime.db.sessions() as session, session.begin():
            peer = await create_run(
                session,
                f.owner,
                RunRequest(
                    thread_id=specialist_thread["id"],
                    agent_id=specialist.id,
                    trigger="peer",
                    parent_run_id=context.lease.run_id,
                ),
            )
            peer_data = run_data(peer)
        peer_context = await f.lease(peer_data)
        await denied(
            peer_context.trading.execute(
                f.owner,
                TradeRequest(
                    operation_id=uuid4().hex,
                    account_id=connection,
                    symbol="EURUSDm",
                    action="buy",
                    volume=Decimal("0.1"),
                ),
                peer_context.lease,
            )
        )
        print(
            "PASS direct descendant execution and scoped peer collaboration cannot bypass persisted delegated authority"
        )
        # Delete the intermediate parent: SET NULL must not turn the survivor into legacy.
        await f.request("DELETE", "/agents/" + child.id)
        f.agents.remove(child.id)
        async with f.runtime.db.sessions() as session:
            orphan = await session.get(AgentRow, grandchild.id)
            assert orphan and orphan.parent_id is None and orphan.role == "delegated"
            await denied(require_financial_agent(session, f.owner, orphan.id))
        print(
            "PASS parent deletion retains permanent nonfinancial scope; specialist child exact binding remains intact"
        )
    finally:
        await f.request("PUT", "/trading/controls", {"enabled": False, "emergency_stop": False})
        await f.close()


if __name__ == "__main__":
    asyncio.run(main())
