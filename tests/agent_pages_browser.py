"""Real PostgreSQL fixture for the phase 4a agent pages (tests/web/agent-pages.spec.mjs).

A simulation account with imported candles, a trading agent on XAUUSD, a research agent,
a group with a purpose and a lead, and one open position the owner opened through the
executor. Cleanup removes them through the API (the UI itself never deletes an agent or a
group).
"""

import asyncio
import json
import sys
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import uuid4

from check_streaming import Fixture
from lonora_db.events import emit
from lonora_db.schema import BrokerSessionRow, CloudChartRow, TradingJournalRow
from lonora_gateway.attention import attention_tick
from sqlalchemy import delete

SYMBOL = "XAUUSD"


def snapshot() -> dict[str, Any]:
    """A simulation account with 15m candles and a fresh quote (the executor refuses a stale one)."""
    start = datetime.now(UTC).replace(second=0, microsecond=0) - timedelta(minutes=15 * 60)
    return {
        "balance": "10000",
        "currency": "USD",
        "candles": {
            f"{SYMBOL}:15m": [
                {
                    "symbol": SYMBOL,
                    "timeframe": "15m",
                    "time": (start + timedelta(minutes=15 * index)).isoformat(),
                    "open": str(150 + index),
                    "high": str(154 + index),
                    "low": str(149 + index),
                    "close": str(152 + index),
                }
                for index in range(60)
            ]
        },
        "instruments": [
            {
                "symbol": SYMBOL,
                "description": "Explicit imported fixture",
                "digits": 2,
                "tick_size": "0.01",
                "volume_min": "0.01",
                "volume_max": "100",
                "volume_step": "0.01",
            }
        ],
        "quotes": {
            SYMBOL: {
                "symbol": SYMBOL,
                "bid": "210",
                "ask": "211",
                "observed_at": datetime.now(UTC).isoformat(),
                "source": "simulation/imported-fixture",
            }
        },
    }


def agent_operations(owner: str, account: str, agent: str) -> list[TradingJournalRow]:
    """Settled operations of the trading agent, one per order-log state the page names."""
    now = datetime.now(UTC)

    def row(
        minutes: int, status: str, request: dict[str, Any], details: dict[str, Any]
    ) -> TradingJournalRow:
        return TradingJournalRow(
            operation_id=f"agent-pages-{uuid4()}",
            owner_id=owner,
            account_id=account,
            request_hash="0" * 64,
            request={"account_id": account, "symbol": SYMBOL, **request},
            status=status,
            result={"details": {"execution": {"agent_id": agent}, **details}},
            submitted_at=now - timedelta(minutes=minutes),
            updated_at=now - timedelta(minutes=minutes),
        )

    verified = {"verification": {"status": "verified"}}
    return [
        row(
            40,
            "confirmed",
            {"action": "buy", "volume": "0.3"},
            {**verified, "price": "211.00", "volume": "0.3"},
        ),
        # A MetaApi DONE_PARTIAL receipt as the executor writes it: never verified.
        row(
            30,
            "confirmed",
            {"action": "sell", "volume": "0.5"},
            {
                "partial_execution": True,
                "numeric_code": 10010,
                "price": 209.5,
                "volume": 0.2,
                "verification": {"status": "pending"},
            },
        ),
        # A placed limit order: accepted by the broker, not filled, no fill price.
        row(25, "confirmed", {"action": "buy_limit", "volume": "0.4", "price": "205"}, verified),
        row(20, "failed", {"action": "buy_stop", "volume": "0.1", "price": "220"}, {}),
        row(10, "resolved", {"action": "close_position", "position_id": "p-1"}, {}),
    ]


def cookies(fixture: Fixture) -> list[dict[str, str | None]]:
    return [{"name": cookie.name, "value": cookie.value} for cookie in fixture.client.cookies.jar]


async def action(data: dict[str, Any]) -> dict[str, Any]:
    if data["action"] == "init":
        fixture = await Fixture().open()
        try:
            tag = uuid4().hex[:6]
            connection = await fixture.request(
                "POST",
                "/trading/connections",
                {"provider": "simulation", "account_id": "agent-pages-" + tag, "enabled": True},
            )
            await fixture.request(
                "POST",
                f"/trading/connections/{connection['id']}/simulation",
                {"snapshot": snapshot()},
            )
            chart = {"account": connection["id"], "symbol": SYMBOL}
            trader = await fixture.request(
                "POST",
                "/agents/create",
                {
                    "template": "trading",
                    "name": f"Gold desk {tag}",
                    "responsibility": "Follows gold",
                    "market": chart["symbol"],
                    "account_id": chart["account"],
                },
            )
            research = await fixture.request(
                "POST",
                "/agents/create",
                {"template": "research", "name": f"Reader {tag}", "responsibility": "Reads"},
            )
            group = await fixture.request(
                "POST",
                "/groups/create",
                {
                    "name": f"Desk {tag}",
                    "member_ids": [trader["id"], research["id"]],
                    "participation": "mentions_or_lead",
                    "purpose": "Gold research",
                    "lead_agent_id": research["id"],
                },
            )
            opened = await fixture.request(
                "POST",
                "/trading/execute",
                {
                    "account_id": chart["account"],
                    "operation_id": str(uuid4()),
                    "action": "buy",
                    "symbol": chart["symbol"],
                    "volume": "0.1",
                    "stop_loss": "200",
                },
            )
            assert opened["status"] == "confirmed", opened
            async with fixture.runtime.db.sessions() as session, session.begin():
                operations = agent_operations(fixture.owner, chart["account"], trader["id"])
                operations[-1].result = {
                    "details": {
                        **operations[-1].result["details"],
                        "resolution": {"source": "owner", "outcome": "not_executed"},
                    }
                }
                session.add_all(operations)
            watch = await fixture.request(
                "POST",
                "/watches",
                {
                    "agent_id": trader["id"],
                    "payload": {
                        "kind": "price",
                        "account_id": chart["account"],
                        "symbol": SYMBOL,
                        "condition": "below",
                        "level": "200",
                        "prompt": "Tell me when gold dips.",
                        "expires_at": (datetime.now(UTC) + timedelta(hours=3)).isoformat(),
                    },
                },
            )
            return {
                "watch": watch["id"],
                "cookies": cookies(fixture),
                "account": chart["account"],
                "symbol": chart["symbol"],
                "trader": trader,
                "research": research,
                "group": group,
            }
        finally:
            await fixture.close(cleanup=False)
    if data["action"] == "seed_modifies":
        # Two owner modifies on the open position: the older one still pending (its row time
        # bumped by verification rechecks), the newer one confirmed.
        fixture = await Fixture().open()
        try:
            account = await fixture.request("GET", f"/trading/accounts/{data['account']}")
            position = account["positions"][0]["id"]
            now = datetime.now(UTC)
            request = {
                "account_id": data["account"],
                "symbol": SYMBOL,
                "action": "modify_position",
                "position_id": position,
                "clear_stop_loss": False,
                "clear_take_profit": False,
            }
            async with fixture.runtime.db.sessions() as session, session.begin():
                session.add_all(
                    [
                        TradingJournalRow(
                            operation_id=f"agent-pages-{uuid4()}",
                            owner_id=fixture.owner,
                            account_id=data["account"],
                            request_hash="0" * 64,
                            request={**request, "stop_loss": "204"},
                            status="submitted",
                            result={"details": {}},
                            submitted_at=now - timedelta(minutes=10),
                            updated_at=now,
                        ),
                        TradingJournalRow(
                            operation_id=f"agent-pages-{uuid4()}",
                            owner_id=fixture.owner,
                            account_id=data["account"],
                            request_hash="0" * 64,
                            request={**request, "stop_loss": "206"},
                            status="confirmed",
                            result={"details": {"verification": {"status": "verified"}}},
                            submitted_at=now - timedelta(minutes=2),
                            updated_at=now - timedelta(minutes=2),
                        ),
                    ]
                )
            return {"position": position}
        finally:
            await fixture.close(cleanup=False)
    if data["action"] == "chart_events":
        # Scene updates as the chart runtime streams them, for any agent's chart.
        fixture = await Fixture().open()
        try:
            async with fixture.runtime.db.sessions() as session, session.begin():
                for event in data["events"]:
                    emit(
                        session,
                        fixture.owner,
                        "cloud_charts.scene_updated",
                        agent_id=event["agent_id"],
                        payload={"id": event["id"], "version": 1, "status": "ready", "code": None},
                    )
        finally:
            await fixture.close(cleanup=False)
        return {"emitted": len(data["events"])}
    if data["action"] == "move_chart":
        # chart_set_symbol: the chart moves to another pair (the repository's update event).
        fixture = await Fixture().open()
        try:
            async with fixture.runtime.db.sessions() as session, session.begin():
                row = await session.get(CloudChartRow, data["chart"], with_for_update=True)
                assert row is not None
                row.payload = {**row.payload, "symbol": data["to"]}
                row.version += 1
                row.updated_at = datetime.now(UTC)
                emit(
                    session,
                    fixture.owner,
                    "cloud_charts.updated",
                    agent_id=row.agent_id,
                    thread_id=row.thread_id,
                    payload={"id": row.id, "version": row.version},
                )
        finally:
            await fixture.close(cleanup=False)
        return {"moved": True}
    if data["action"] == "degrade":
        # The broker session as broker_recovery writes it when the account stops answering.
        fixture = await Fixture().open()
        try:
            async with fixture.runtime.db.sessions() as session, session.begin():
                row = await session.get(BrokerSessionRow, data["account"], with_for_update=True)
                assert row is not None
                now = datetime.now(UTC).isoformat()
                row.state = {
                    **row.state,
                    "broker_recovery": {
                        "status": "disconnected",
                        "reason_code": "broker_unreachable",
                        "since": now,
                        "observed_at": now,
                        "last_success_at": None,
                        "unresolved_operations": [],
                        # The owner's open position: an outage with exposure is critical.
                        "positions": [
                            {
                                "id": "fixture-position",
                                "symbol": SYMBOL,
                                "side": "buy",
                                "volume": "0.1",
                                "open_price": "211",
                                "profit": "0",
                            }
                        ],
                    },
                }
                # The transition broker_recovery emits; the attention gateway raises it.
                emit(
                    session,
                    fixture.owner,
                    "broker.degraded",
                    payload={
                        "account_id": data["account"],
                        "status": "disconnected",
                        "reason_code": "broker_unreachable",
                        "previous_status": "connected",
                        "transition_id": "disconnected:" + now,
                    },
                )
            await attention_tick(
                fixture.runtime.db, fixture.runtime.services(fixture.owner).brokers, fixture.owner
            )
        finally:
            await fixture.close(cleanup=False)
        return {"degraded": True}
    if data["action"] == "cleanup":
        fixture = await Fixture().open()
        try:
            for group in data.get("groups", []) + [data["group"]["id"]]:
                await fixture.client.delete(f"/api/groups/{group}")
            await fixture.client.delete(f"/api/watches/{data['watch']}")
            for agent in (data["trader"]["id"], data["research"]["id"], *data.get("agents", [])):
                await fixture.client.delete(f"/api/agents/{agent}")
            async with fixture.runtime.db.sessions() as session, session.begin():
                await session.execute(
                    delete(TradingJournalRow).where(
                        TradingJournalRow.operation_id.like("agent-pages-%")
                    )
                )
            await fixture.client.delete(f"/api/trading/connections/{data['account']}")
        finally:
            await fixture.close(cleanup=False)
        return {"cleaned": True}
    raise ValueError("Unknown agent pages fixture action")


if __name__ == "__main__":
    print(json.dumps(asyncio.run(action(json.load(sys.stdin)))))
