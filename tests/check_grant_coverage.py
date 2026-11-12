"""Every term of a signed grant decides what it covers, on disposable PostgreSQL.

Review regressions for the monotonic ladder (correction 6) and owner decision D1 ("the
owner's own positions are excluded unless switched on"), with the simulation broker and a
scripted authenticator:

- A position the owner opened from Lonora's own Trading page (``POST /trading/execute``,
  no agent) is the owner's own: under a D1 grant an agent's stop removal, close, close-all
  sweep on it each become an approval card and nothing reaches the broker.
  A position the agent opened under its grant is still managed with no card.
- A request that breaks another term of a signed grant (here its per-order volume cap)
  becomes an approval card instead of a refusal, and the owner's tap sends it under that
  exact approval, never under the grant.

No live broker, MetaApi key or real order is involved.
"""

import asyncio
from datetime import timedelta
from typing import Any, cast
from uuid import uuid4

from check_streaming import Fixture
from device_fixture import Device
from lonora_adapter_kit.types import ToolCall
from lonora_adapters.brokers.simulation import SimulationBroker
from lonora_contracts.domain import utcnow
from lonora_db.personal_agent import ensure_personal_agent
from lonora_db.schema import TradeApprovalRow, TradingJournalRow
from lonora_tools.context import ToolContext
from lonora_tools.loader import load_tools
from sqlalchemy import func, select

GOLD = "XAUUSDm"


def snapshot() -> dict[str, Any]:
    return {
        "currency": "USD",
        "balance": "10000",
        "equity": "10000",
        "instruments": [
            {
                "symbol": GOLD,
                "digits": 2,
                "tick_size": "0.01",
                "volume_min": "0.1",
                "volume_max": "10",
                "volume_step": "0.1",
            }
        ],
        "quotes": {
            GOLD: {
                "symbol": GOLD,
                "bid": "100",
                "ask": "101",
                "observed_at": utcnow().isoformat(),
                "source": "explicit-grant-coverage-fixture",
                "loss_tick_value": "1",
                "profit_tick_value": "1",
                "tick_value_basis": "account_currency_per_lot",
            }
        },
    }


async def main() -> None:
    fixture = await Fixture().open()
    db = fixture.runtime.db
    registry = load_tools()
    try:
        connection = await fixture.request(
            "POST",
            "/trading/connections",
            {"provider": "simulation", "account_id": "cover-" + uuid4().hex, "enabled": True},
        )
        account = cast(str, connection["id"])
        await fixture.request(
            "POST", f"/trading/connections/{account}/simulation", {"snapshot": snapshot()}
        )
        services = fixture.runtime.services(fixture.owner)
        broker = cast(SimulationBroker, await services.brokers.get(fixture.owner, account))

        async def call(context: ToolContext, name: str, **arguments: Any) -> dict[str, Any]:
            return await registry.execute(
                ToolCall(id=uuid4().hex, name=name, arguments=arguments), context
            )

        async def context_for(agent: dict[str, Any]) -> ToolContext:
            thread = await fixture.conversation(agent)
            return await fixture.lease(await fixture.run(agent, thread))

        async def approvals(context: ToolContext) -> int:
            async with db.sessions() as session:
                return int(
                    await session.scalar(
                        select(func.count())
                        .select_from(TradeApprovalRow)
                        .where(TradeApprovalRow.run_id == context.lease.run_id)
                    )
                    or 0
                )

        async with db.sessions() as session, session.begin():
            lonora_id = (await ensure_personal_agent(session, fixture.owner)).id
        lonora = await fixture.request("GET", "/agents/" + lonora_id)
        gold = await fixture.request(
            "POST",
            "/agents",
            {
                "name": "Gold " + uuid4().hex[:6],
                "scope_mode": "flexible",
                "trading_account_id": account,
                "trading_symbol": GOLD,
            },
        )
        fixture.agents.append(gold["id"])

        # 1. The owner signs the D1 grant card: gold, until stopped, own positions excluded.
        lonora_context = await context_for(lonora)
        proposed = await call(
            lonora_context, "owner_action_propose", kind="grant_authority", agent_id=gold["id"]
        )
        card_id = proposed["owner_action"]["id"]
        device = await Device.enroll(fixture)
        challenge = await fixture.request("POST", f"/owner-actions/{card_id}/challenge", {})
        decided = await fixture.request(
            "POST",
            f"/owner-actions/{card_id}/decision",
            {
                "decision": "confirm",
                "proof": device.assertion(challenge, fixture.settings.allowed_origin),
            },
        )
        assert decided["status"] == "confirmed", decided
        assert decided["result"]["allow_manual_positions"] is False, decided
        # The settled card shows what was signed: nothing replaced (a first grant).
        cards = cast(
            list[dict[str, Any]],
            await fixture.request("GET", "/owner-actions?thread_id=" + lonora_context.thread_id),
        )
        settled = next(item for item in cards if item["id"] == card_id)
        assert settled["facts"]["replaces"] is None, settled["facts"]
        assert settled["facts"]["grant"]["allow_manual_positions"] is False
        assert "global_trading" not in settled["facts"], settled["facts"]
        print("PASS a signed grant card keeps showing what was signed: nothing replaced")

        # 2. The owner buys gold from Lonora's own Trading page: journaled with no agent.
        owner_operation = "owner-order-" + uuid4().hex[:8]
        placed = await fixture.request(
            "POST",
            "/trading/execute",
            {
                "operation_id": owner_operation,
                "account_id": account,
                "symbol": GOLD,
                "action": "buy",
                "volume": "0.2",
                "stop_loss": "90",
            },
        )
        assert placed["status"] == "confirmed", placed
        async with db.sessions() as session:
            row = await session.get(TradingJournalRow, owner_operation)
            assert row is not None
            assert row.result["details"]["execution"]["agent_id"] is None, row.result
        (owners,) = await broker.positions()

        # 3. Each agent request on the owner's own position asks; nothing reaches the broker.
        gold_context = await context_for(gold)
        before = await broker.snapshot()
        for arguments in (
            {"action": "modify_position", "clear_stop_loss": True},
            {"action": "close_position"},
        ):
            asked = await call(
                gold_context,
                "trade_execute",
                account_id=account,
                symbol=GOLD,
                position_id=owners.id,
                **arguments,
            )
            assert asked.get("_runtime_wait") and asked.get("approval_id"), asked
        swept = await call(gold_context, "trade_close_positions", account_id=account, symbol=GOLD)
        assert swept.get("_runtime_wait") and swept.get("approval_id"), swept
        assert await broker.snapshot() == before
        assert await approvals(gold_context) == 3
        (unchanged,) = await broker.positions()
        assert unchanged.stop_loss is not None and unchanged.volume == owners.volume

        # 4. The agent's own entry and its management stay covered by the grant: no card.
        own_context = await context_for(gold)
        entry = await call(
            own_context,
            "trade_execute",
            action="buy",
            account_id=account,
            symbol=GOLD,
            volume="0.1",
            stop_loss="90",
        )
        assert entry.get("status") == "confirmed", entry
        assert entry.get("authorization") == "account_authority", entry
        agents = [item for item in await broker.positions() if item.id != owners.id]
        assert len(agents) == 1, agents
        moved = await call(
            own_context,
            "trade_execute",
            action="modify_position",
            account_id=account,
            symbol=GOLD,
            position_id=agents[0].id,
            stop_loss="95",
        )
        assert moved.get("status") == "confirmed", moved
        assert moved.get("authorization") == "account_authority", moved
        assert await approvals(own_context) == 0
        print(
            "PASS a position the owner opened from Lonora's Trading page is the owner's own: an agent's stop removal, close, close-all and its own grant ask, while the agent's own position stays covered"
        )

        # 5. A request over a signed grant's own cap asks, and the tap sends it once.
        silver = await fixture.request(
            "POST",
            "/agents",
            {
                "name": "Capped " + uuid4().hex[:6],
                "scope_mode": "flexible",
                "trading_account_id": account,
                "trading_symbol": GOLD,
            },
        )
        fixture.agents.append(silver["id"])
        silver_thread = await fixture.conversation(silver)
        proposal = await fixture.request(
            "POST",
            f"/agents/{silver['id']}/account-authorities",
            {
                "thread_id": silver_thread["id"],
                "account_id": account,
                "management_mode": "bounded",
                "symbol_scope": "selected",
                "symbols": [GOLD],
                "actions": ["buy", "sell", "close_position", "modify_position"],
                "maximum_order_volume": "0.1",
                "maximum_symbol_volume": "5",
                "maximum_positions": 10,
                "maximum_pending_orders": 0,
                "maximum_actions": 50,
                "minimum_equity": "1000",
                "valid_until": (utcnow() + timedelta(days=7)).isoformat(),
                "allow_manual_positions": False,
            },
        )
        challenge = await fixture.request(
            "POST", f"/account-authorities/{proposal['id']}/challenge"
        )
        await fixture.request(
            "POST",
            "/account-authorities/verify",
            device.assertion(challenge, fixture.settings.allowed_origin),
        )
        capped = await fixture.lease(await fixture.run(silver, silver_thread))
        inside = await call(
            capped,
            "trade_execute",
            action="buy",
            account_id=account,
            symbol=GOLD,
            volume="0.1",
            stop_loss="90",
        )
        assert inside.get("status") == "confirmed", inside
        assert inside.get("authorization") == "account_authority", inside
        before = await broker.snapshot()
        over_args = {
            "action": "buy",
            "account_id": account,
            "symbol": GOLD,
            "volume": "0.3",
            "stop_loss": "90",
        }
        over = await call(capped, "trade_execute", **over_args)
        assert over.get("_runtime_wait") and over.get("approval_id"), over
        assert over.get("code") != "account_authority_volume_limit", over
        assert await broker.snapshot() == before
        await fixture.request(
            "POST", f"/trading/approvals/{over['approval_id']}/decision", {"decision": "approve"}
        )
        sent = await call(capped, "trade_execute", **over_args)
        assert sent.get("status") == "confirmed", sent
        async with db.sessions() as session:
            journal = await session.get(TradingJournalRow, sent["operation_id"])
            assert journal is not None
            execution = journal.result["details"]["execution"]
            assert "account_authority_id" not in execution, execution
        print(
            "PASS a trade over a signed grant's own cap becomes an approval card, never a refusal, and the tap sends it under that approval"
        )
    finally:
        await fixture.close()


if __name__ == "__main__":
    asyncio.run(main())
