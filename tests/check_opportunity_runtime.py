"""Real broker-neutral tools/DB/approval/journal with evolving durable theses."""

import asyncio
from datetime import timedelta
from typing import Any
from unittest.mock import patch
from uuid import uuid4

from check_streaming import Fixture
from lonora_adapter_kit.types import ToolCall
from lonora_agent.context.decisions import decision_context
from lonora_contracts.domain import utcnow
from lonora_db.schema import RunRow, TradingAccountRow, TradingJournalRow
from lonora_db.trading_opportunities import owned_opportunity
from lonora_tools.loader import load_tools
from lonora_trading.opportunities import (
    maintenance_opportunities,
    refresh_opportunity,
    sync_opportunity_execution,
)
from sqlalchemy import select


async def main() -> None:
    f = await Fixture().open()
    account = ""
    try:
        account = (
            await f.request(
                "POST",
                "/trading/connections",
                {"provider": "simulation", "account_id": uuid4().hex, "enabled": True},
            )
        )["id"]
        symbols = ("EURUSDm", "XAUUSDm", "US30.cash", "BTCUSD.pro")
        now = utcnow()
        await f.request(
            "POST",
            f"/trading/connections/{account}/simulation",
            {
                "snapshot": {
                    "balance": "10000",
                    "currency": "USD",
                    "instruments": [
                        {
                            "symbol": s,
                            "digits": 2,
                            "tick_size": "0.01",
                            "volume_min": "0.01",
                            "volume_max": "10",
                            "volume_step": "0.01",
                        }
                        for s in symbols
                    ],
                    "quotes": {
                        s: {
                            "symbol": s,
                            "bid": "100",
                            "ask": "101",
                            "observed_at": now.isoformat(),
                            "source": "explicit-thesis-fixture",
                        }
                        for s in symbols
                    },
                    "candles": {
                        s + ":1m": [
                            {
                                "symbol": s,
                                "timeframe": "1m",
                                "time": (now - timedelta(seconds=60)).isoformat(),
                                "open": "100",
                                "high": "103",
                                "low": "99",
                                "close": "101",
                            }
                        ]
                        for s in symbols
                    },
                }
            },
        )
        agent = await f.agent("Evolving thesis", supervised=True)
        thread = await f.conversation(agent)
        context = await f.lease(await f.run(agent, thread))
        tools = load_tools()

        async def call(name: str, args: dict[str, Any], key: str | None = None):
            return await tools.execute(
                ToolCall(id=key or uuid4().hex, name=name, arguments=args), context
            )

        async def decision(symbol: str, action: str):
            return await call(
                "market_decision_record",
                {
                    "account_id": account,
                    "symbol": symbol,
                    "timeframe": "1m",
                    "action": action,
                    "summary": "Explicit public fixture analysis",
                },
            )

        created: list[dict[str, Any]] = []
        for symbol in symbols:
            record = await decision(symbol, "BUY")
            assert record["action"] == "BUY"
            params = {
                "account_id": account,
                "symbol": symbol,
                "timeframe": "1m",
                "setup_key": "fixture-level-breakout",
                "definition": {
                    "direction": "BUY",
                    "rationale": "Observed evidence",
                    "entry_condition": "Recorded fresh confirmation",
                    "invalidation_condition": "Contradicting recorded evidence",
                    "strategy_version": "fixture-v1",
                    "expires_at": (now + timedelta(hours=1)).isoformat(),
                },
                "supporting_decision_ids": [record["id"]],
            }
            row = await call("market_opportunity_create", params)
            repeat = await call("market_opportunity_create", params)
            assert row["id"] == repeat["id"] and row["version"] == repeat["version"]
            confirmed = await call(
                "market_opportunity_update",
                {
                    "opportunity_id": row["id"],
                    "expected_version": row["version"],
                    "status": "confirmed",
                    "reason_code": "fresh_fixture_confirmation",
                    "supporting_decision_ids": [record["id"]],
                },
            )
            assert confirmed["status"] == "confirmed"
            created.append(confirmed)
        print(
            "PASS exact forex/metal/index/crypto setup identity persists across wake-style tool calls and confirms only from real recorded evidence"
        )

        contradiction = await decision(symbols[1], "SELL")
        invalid = await call(
            "market_opportunity_update",
            {
                "opportunity_id": created[1]["id"],
                "expected_version": created[1]["version"],
                "status": "invalidated",
                "reason_code": "recorded_opposing_evidence",
                "supporting_decision_ids": created[1]["payload"]["supporting_decision_ids"],
                "contradicting_decision_ids": [contradiction["id"]],
            },
        )
        history = (await call("market_opportunity_read", {"opportunity_id": invalid["id"]}))[
            "history"
        ]
        assert [h["status"] for h in reversed(history)] == ["forming", "confirmed", "invalidated"]
        async with f.runtime.db.sessions() as session, session.begin():
            row = await owned_opportunity(session, f.owner, created[2]["id"], lock=True)
            await refresh_opportunity(session, row, now=now + timedelta(hours=2))
            assert row.status == "expired"
            stale = await owned_opportunity(session, f.owner, created[3]["id"], lock=True)
            await refresh_opportunity(session, stale, now=now + timedelta(seconds=40))
            assert stale.status == "degraded"
        read = await f.request("GET", "/trading/opportunities/" + created[2]["id"])
        assert (
            read["status"] == "expired" and read["state"]["reason_code"] == "thesis_horizon_elapsed"
        )
        async with f.runtime.db.sessions() as session, session.begin():
            expired = await owned_opportunity(session, f.owner, created[2]["id"], lock=True)
            await refresh_opportunity(session, expired, now=now + timedelta(hours=2))
            wakes = list(
                await session.scalars(
                    select(RunRow).where(
                        RunRow.model_metadata["opportunity_id"].as_string() == expired.id
                    )
                )
            )
            # The opportunity is the Agent's own work: one wake, with its normal authority,
            # in its work lane, reporting back to its conversation.
            assert len(wakes) == 1 and "authority" not in wakes[0].model_metadata
            assert wakes[0].agent_id == agent["id"] and wakes[0].trigger == "watch"
            assert wakes[0].model_metadata["origin_thread_id"] == thread["id"]
            assert wakes[0].thread_id != thread["id"]
            seed = await decision_context(session, f.owner, agent["id"])
            assert created[0]["id"] in seed and len(seed) < 6500
        print(
            "PASS versioned forming/confirmed/invalidated history, explicit expiry without SL, source freshness degradation and restart/API persistence"
        )

        thesis = created[0]
        args = {
            "account_id": account,
            "symbol": symbols[0],
            "action": "buy",
            "volume": "0.1",
            "tolerance": "5",
            "reason": "Fixture entry",
            "thesis_id": thesis["id"],
        }
        proposal = await call("trade_execute", args, "entry-once")
        assert proposal["_runtime_wait"]
        await f.request(
            "POST",
            "/trading/approvals/" + proposal["approval_id"] + "/decision",
            {"decision": "approve"},
        )
        result = await call("trade_execute", args, "entry-once")
        assert result["results"][0]["status"] == "confirmed", result
        replay = await call("trade_execute", args, "entry-once")
        assert (
            replay["results"] == result["results"]
            and replay["approval_id"] == result["approval_id"]
        )
        broker = await context.brokers.get(f.owner, account)
        positions = await broker.positions()
        assert len(positions) == 1
        state = await f.request("GET", "/trading/opportunities/" + thesis["id"])
        assert (
            state["status"] == "acted_on" and state["state"]["entry_position_id"] == positions[0].id
        )
        # Opportunities are the agent's memory, never a gate (mandate 14.2.5): a second
        # entry on the same thesis is the agent's own decision and becomes its entry.
        second_args = {**args, "volume": "0.2"}
        second = await call("trade_execute", second_args, "second-entry")
        await f.request(
            "POST",
            "/trading/approvals/" + second["approval_id"] + "/decision",
            {"decision": "approve"},
        )
        added = await call("trade_execute", second_args, "second-entry")
        assert added["results"][0]["status"] == "confirmed", added
        first_position = positions[0].id
        positions = await broker.positions()
        assert len(positions) == 2
        state = await f.request("GET", "/trading/opportunities/" + thesis["id"])
        target = state["state"]["entry_position_id"]
        assert state["status"] == "acted_on" and target not in {None, first_position}, state
        assert state["state"]["entry_operation_id"] == added["results"][0]["operation_id"]
        partial_args = {
            "account_id": account,
            "symbol": symbols[0],
            "action": "close_position",
            "position_id": target,
            "volume": "0.04",
            "thesis_id": thesis["id"],
        }
        # In Ask a partial close of the agent's own position executes without a card.
        partial = await call("trade_execute", partial_args, "partial-close")
        assert "approval_id" not in partial, partial
        assert partial["results"][0]["status"] == "confirmed"
        partial_state = await f.request("GET", "/trading/opportunities/" + thesis["id"])
        assert (
            partial_state["status"] == "acted_on"
            and {p.id: str(p.volume) for p in await broker.positions()}[target] == "0.16"
        )
        close_args = {
            "account_id": account,
            "symbol": symbols[0],
            "action": "close_position",
            "position_id": target,
            "thesis_id": thesis["id"],
        }
        close_result = await call("trade_execute", close_args, "close-real-ticket")
        assert "approval_id" not in close_result, close_result
        assert close_result["results"][0]["status"] == "confirmed", close_result
        assert [p.id for p in await broker.positions()] == [first_position]
        finished = await f.request("GET", "/trading/opportunities/" + thesis["id"])
        assert finished["status"] == "completed"
        print(
            "PASS same approval/journal/adapter path verifies entry and full exit, repeats return one receipt, and a second entry on a thesis is the agent's own decision"
        )

        async def refresh_market() -> None:
            # Fresh fixture evidence for the follow-up theses; no live market involved.
            current = utcnow()
            async with f.runtime.db.sessions() as session, session.begin():
                row = await session.get(TradingAccountRow, account, with_for_update=True)
                assert row is not None
                payload = dict(row.payload)
                payload["quotes"] = {
                    s: {**quote, "observed_at": current.isoformat()}
                    for s, quote in payload["quotes"].items()
                }
                payload["candles"] = {
                    key: [
                        {**candle, "time": (current - timedelta(seconds=60)).isoformat()}
                        for candle in candles
                    ]
                    for key, candles in payload["candles"].items()
                }
                row.payload = payload

        async def fresh_thesis(setup: str) -> dict[str, Any]:
            await refresh_market()
            record = await decision(symbols[0], "BUY")
            row = await call(
                "market_opportunity_create",
                {
                    "account_id": account,
                    "symbol": symbols[0],
                    "timeframe": "1m",
                    "setup_key": setup,
                    "definition": {
                        "direction": "BUY",
                        "rationale": "Observed evidence",
                        "entry_condition": "Recorded fresh confirmation",
                        "invalidation_condition": "Contradicting recorded evidence",
                        "strategy_version": "fixture-v1",
                        "expires_at": (utcnow() + timedelta(hours=1)).isoformat(),
                    },
                    "supporting_decision_ids": [record["id"]],
                },
            )
            return await call(
                "market_opportunity_update",
                {
                    "opportunity_id": row["id"],
                    "expected_version": row["version"],
                    "status": "confirmed",
                    "reason_code": "fresh_fixture_confirmation",
                    "supporting_decision_ids": [record["id"]],
                },
            )

        real_execute = broker.execute

        async def lose_before_effect(request: Any, before_send: Any = None) -> Any:
            assert before_send
            await before_send()
            raise TimeoutError("scripted response loss before the simulated effect")

        async def lose_after_effect(*args: Any, **kwargs: Any) -> Any:
            await real_execute(*args, **kwargs)
            raise TimeoutError("scripted response loss after the simulated effect")

        async def entry(
            thesis: dict[str, Any], key: str, lose: Any = None, volume: str = "0.1"
        ) -> dict[str, Any]:
            await refresh_market()
            entry_args = {
                "account_id": account,
                "symbol": symbols[0],
                "action": "buy",
                "volume": volume,
                "tolerance": "5",
                "reason": "Fixture entry",
                "thesis_id": thesis["id"],
            }
            card = await call("trade_execute", entry_args, key)
            await f.request(
                "POST",
                "/trading/approvals/" + card["approval_id"] + "/decision",
                {"decision": "approve"},
            )
            if lose is None:
                return (await call("trade_execute", entry_args, key))["results"][0]
            with patch.object(broker, "execute", side_effect=lose):
                return (await call("trade_execute", entry_args, key))["results"][0]

        async def thesis_state(thesis: dict[str, Any]) -> dict[str, Any]:
            return await f.request("GET", "/trading/opportunities/" + thesis["id"])

        statement = {"statement": "Checked the broker terminal history for this request."}
        unsent = await fresh_thesis("fixture-lost-entry-not-executed")
        lost = await entry(unsent, "lost-entry-not-executed", lose_before_effect)
        assert lost["status"] == "ambiguous", lost
        assert (await thesis_state(unsent))["state"]["pending_operation_ids"] == [
            lost["operation_id"]
        ]
        await f.request(
            "POST",
            f"/trading/journal/{lost['operation_id']}/resolve",
            {"outcome": "not_executed", **statement},
        )
        released = await thesis_state(unsent)
        assert released["status"] == "confirmed", released
        assert released["state"]["pending_operation_ids"] == []
        assert not released["state"].get("entry_operation_id")
        # Identical parameters in this Run replay the same resolved operation; a fresh
        # entry is a different request.
        retried = await entry(unsent, "lost-entry-retry", volume="0.2")
        assert retried["status"] == "confirmed", retried
        assert (await thesis_state(unsent))["status"] == "acted_on"

        executed = await fresh_thesis("fixture-lost-entry-executed")
        lost = await entry(executed, "lost-entry-executed", lose_after_effect)
        assert lost["status"] == "ambiguous", lost
        await f.request(
            "POST",
            f"/trading/journal/{lost['operation_id']}/resolve",
            {"outcome": "executed", **statement},
        )
        attested = await thesis_state(executed)
        assert attested["status"] == "acted_on", attested
        assert attested["state"]["entry_operation_id"] == lost["operation_id"]
        assert attested["state"]["pending_operation_ids"] == []
        assert attested["state"]["reason_code"] == "thesis_entry_attested"
        again = await entry(executed, "lost-entry-second", volume="0.3")
        # An acted-on thesis is memory, never a gate: the next entry is sent and linked.
        assert again["status"] == "confirmed", again
        assert (await thesis_state(executed))["state"]["entry_operation_id"] == again[
            "operation_id"
        ]
        assert await maintenance_opportunities(f.runtime.db, f.owner) >= 0
        # A broker-state resolution never says who closed the position, but the thesis
        # position is observed closed: the thesis completes.
        position_id = (await thesis_state(unsent))["state"]["entry_position_id"]
        assert position_id
        operation_id = "thesis-observed-close-" + uuid4().hex
        observed_closed = TradingJournalRow(
            operation_id=operation_id,
            owner_id=f.owner,
            account_id=account,
            request_hash="explicit-fixture",
            request={
                "account_id": account,
                "operation_id": operation_id,
                "action": "close_position",
                "symbol": symbols[0],
                "position_id": position_id,
                "thesis_id": unsent["id"],
            },
            status="resolved",
            result={
                "operation_id": operation_id,
                "status": "resolved",
                "code": "target_closed",
                "details": {"resolution": {"source": "broker_state", "basis": "target_closed"}},
            },
        )
        async with f.runtime.db.sessions() as session, session.begin():
            await sync_opportunity_execution(session, observed_closed)
        completed = await thesis_state(unsent)
        assert completed["status"] == "completed", completed
        assert completed["state"]["reason_code"] == "thesis_position_no_longer_open"
        print(
            "PASS an owner attestation settles a thesis entry link: not_executed releases it for a fresh entry, executed acts on it and a later entry is linked; an observed-closed position completes its thesis"
        )

        def journal_row(
            thesis_id: str, status: str, *, action: str = "buy", symbol: str = symbols[0]
        ) -> TradingJournalRow:
            identifier = "thesis-memory-" + uuid4().hex
            return TradingJournalRow(
                operation_id=identifier,
                owner_id=f.owner,
                account_id=account,
                request_hash="explicit-fixture",
                request={
                    "account_id": account,
                    "operation_id": identifier,
                    "action": action,
                    "symbol": symbol,
                    "volume": "0.1",
                    "thesis_id": thesis_id,
                },
                status=status,
                result={"operation_id": identifier, "status": status, "details": {}},
            )

        async def sync(row: TradingJournalRow) -> dict[str, Any]:
            async with f.runtime.db.sessions() as session, session.begin():
                await sync_opportunity_execution(session, row)
            return await thesis_state({"id": row.request["thesis_id"]})

        memory = await fresh_thesis("fixture-memory-links")
        # Several open operations on one thesis are all kept, and each settles on its own.
        first, second = (journal_row(memory["id"], "ambiguous") for _ in range(2))
        await sync(first)
        held = await sync(second)
        assert held["state"]["pending_operation_ids"] == [
            first.operation_id,
            second.operation_id,
        ], held
        second.status = "failed"
        assert (await sync(second))["state"]["pending_operation_ids"] == [first.operation_id]
        # Another market's operation is never this thesis's memory.
        foreign = journal_row(memory["id"], "confirmed", symbol=symbols[1])
        unchanged = await sync(foreign)
        assert unchanged["status"] == "confirmed", unchanged
        assert unchanged["state"].get("last_operation_id") != foreign.operation_id
        # An ended thesis records an operation that names it and is never revived.
        ended = await f.request("GET", "/trading/opportunities/" + created[1]["id"])
        assert ended["status"] == "invalidated", ended
        late = journal_row(ended["id"], "confirmed", symbol=ended["symbol"])
        after = await sync(late)
        assert after["status"] == "invalidated", after
        assert after["state"]["last_operation_id"] == late.operation_id
        print(
            "PASS a thesis keeps every open operation, ignores another market's and is never revived once ended"
        )

        async def expired_with_position(setup: str, position_id: str) -> dict[str, Any]:
            """A thesis acted on, whose expiry then passes before its position closes."""
            thesis = await fresh_thesis(setup)
            async with f.runtime.db.sessions() as session, session.begin():
                row = await owned_opportunity(session, f.owner, thesis["id"], lock=True)
                row.status = "acted_on"
                row.state = {**row.state, "entry_position_id": position_id}
                await refresh_opportunity(session, row, now=utcnow() + timedelta(hours=2))
                assert row.status == "expired", row.status
            return thesis

        def close_row(thesis_id: str, position_id: str, status: str) -> TradingJournalRow:
            row = journal_row(thesis_id, status, action="close_position")
            row.request = {**row.request, "position_id": position_id, "volume": None}
            if status == "resolved":
                row.result = {
                    **row.result,
                    "code": "target_closed",
                    "details": {"resolution": {"source": "broker_state", "basis": "target_closed"}},
                }
            return row

        # An expired thesis still completes when its position fully closes.
        closed = await expired_with_position("fixture-expired-close", "pos-expired-close")
        done = await sync(close_row(closed["id"], "pos-expired-close", "confirmed"))
        assert done["status"] == "completed", done
        assert done["state"]["reason_code"] == "thesis_position_closed", done
        observed = await expired_with_position("fixture-expired-observed", "pos-expired-seen")
        seen = await sync(close_row(observed["id"], "pos-expired-seen", "resolved"))
        assert seen["status"] == "completed", seen
        assert seen["state"]["reason_code"] == "thesis_position_no_longer_open", seen
        # An expired thesis is still never revived by an entry.
        revived = await sync(journal_row(observed["id"], "confirmed"))
        assert revived["status"] == "completed", revived
        print(
            "PASS an expired thesis completes when its position closes or is observed closed, and is never revived by an entry"
        )

        # The thesis's own entry settles after the thesis expired: it is still recorded as
        # the thesis entry (never reviving it), so closing its position completes it.
        late = await fresh_thesis("fixture-late-entry")
        pending_entry = journal_row(late["id"], "ambiguous")
        linked = await sync(pending_entry)
        assert linked["state"]["pending_operation_ids"] == [pending_entry.operation_id], linked
        async with f.runtime.db.sessions() as session, session.begin():
            row = await owned_opportunity(session, f.owner, late["id"], lock=True)
            await refresh_opportunity(session, row, now=utcnow() + timedelta(hours=2))
            assert row.status == "expired", row.status
        pending_entry.status = "confirmed"
        pending_entry.result = {
            **pending_entry.result,
            "status": "confirmed",
            "details": {"position_id": "pos-late-entry"},
        }
        settled = await sync(pending_entry)
        assert settled["status"] == "expired", settled
        assert settled["state"]["entry_operation_id"] == pending_entry.operation_id, settled
        assert settled["state"]["entry_position_id"] == "pos-late-entry", settled
        assert settled["state"]["pending_operation_ids"] == [], settled
        late_done = await sync(close_row(late["id"], "pos-late-entry", "confirmed"))
        assert late_done["status"] == "completed", late_done
        assert late_done["state"]["reason_code"] == "thesis_position_closed", late_done
        print(
            "PASS an entry that settles after its thesis expired is still its entry, and closing its position completes the thesis"
        )
    finally:
        await f.close()


if __name__ == "__main__":
    asyncio.run(main())
