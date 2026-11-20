"""Delegated research identities never inherit owner-wide financial authority."""

import asyncio
from typing import Any, cast
from uuid import uuid4

from check_streaming import Fixture
from legacy_agents import legacy_child
from lonora_adapter_kit.types import ToolCall
from lonora_contracts.domain import AgentCreate, utcnow
from lonora_contracts.runs import RunRequest
from lonora_core.user_error import LonoraError
from lonora_db.agent_binding import require_financial_agent
from lonora_db.agents import agent_data, create_agent
from lonora_db.runs import create_run, run_data
from lonora_db.schema import AgentRow
from lonora_tools.loader import load_tools

# The door no longer refuses a role or an ancestry (6.9). A delegated identity is in
# Ask by default since the data step (default_level; migration 0128 made every stored
# delegated agent an ordinary team agent). A new order with a tolerance and a reason
# raises one pending Trade Approval and is not sent.


async def denied(
    awaitable: Any, codes: tuple[str, ...] = ("delegated_financial_authority_forbidden",)
) -> None:
    try:
        await awaitable
    except LonoraError as error:
        assert error.code in codes, error.code
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
        quotes = {
            symbol: {
                "symbol": symbol,
                "bid": "100",
                "ask": "101",
                "observed_at": utcnow().isoformat(),
                "source": "delegated-scope-fixture",
            }
            for symbol in ("BTCUSD.pro", "EURUSDm")
        }
        await f.request(
            "POST",
            f"/trading/connections/{connection}/simulation",
            {"snapshot": {"balance": "10000", "currency": "USD", "quotes": quotes}},
        )
        async with f.runtime.db.sessions() as session, session.begin():
            personal_row = await session.get(AgentRow, personal["id"])
            assert personal_row
            child = await legacy_child(session, f.owner, personal_row, "Personal researcher")
            grandchild = await legacy_child(session, f.owner, child, "Research descendant")
            specialist = await create_agent(
                session,
                f.owner,
                AgentCreate(
                    name="Bound specialist", trading_account_id=connection, trading_symbol="EURUSDm"
                ),
            )
            bound_child = await legacy_child(session, f.owner, specialist, "Specialist child")
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

        async def pending_approval(ctx: Any, call_id: str, symbol: str) -> None:
            """Ask sends nothing: a tolerance and a reason raise one pending Trade Approval."""
            result = await registry.execute(
                ToolCall(
                    id=call_id,
                    name="trade_execute",
                    arguments={
                        "account_id": connection,
                        "symbol": symbol,
                        "action": "buy",
                        "volume": "0.1",
                        "reason": "The owner decides this order",
                        "tolerance": "1.5",
                    },
                ),
                ctx,
            )
            assert result.get("_runtime_wait") is True and result.get("approval_id"), result
            assert result.get("status") != "confirmed", result
            shown = cast(
                list[dict[str, Any]],
                await f.request("GET", f"/trading/approvals?thread_id={ctx.thread_id}"),
            )
            card = next(row for row in shown if row["id"] == result["approval_id"])
            assert card["status"] == "pending", card["status"]

        await pending_approval(context, "ask-trade", "BTCUSD.pro")
        print(
            "PASS Personal children and descendants are explicit research identities: account reads work, and a new order raises a pending Trade Approval"
        )
        descendant_thread = await f.conversation(grandchild_data)
        descendant_context = await f.lease(await f.run(grandchild_data, descendant_thread))
        await pending_approval(descendant_context, "descendant-trade", "EURUSDm")
        # A specialist peer's order under a delegated run's ancestry is decided by the
        # specialist's own trading permission, never by the ancestry's role.
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
        await pending_approval(peer_context, "peer-trade", "EURUSDm")
        print(
            "PASS a descendant's order and a specialist peer's order each raise a pending Trade Approval and neither is sent"
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
        await f.close()


if __name__ == "__main__":
    asyncio.run(main())
