"""Creating and steering agents from chat (W15-4) on disposable PostgreSQL.

Runs the agent_create tool, the creation and Undo cards (owner-session decision route),
the watch steering tools and the owner's watch control route against the simulation
broker. No live broker, model provider or real order is involved.
"""

import asyncio
from dataclasses import replace
from datetime import timedelta
from typing import Any, cast
from unittest.mock import patch
from uuid import uuid4

from check_streaming import Fixture
from lonora_adapter_kit.types import ModelMessage, ModelReply, ToolCall
from lonora_agent.executor import execute_run
from lonora_contracts.domain import utcnow
from lonora_contracts.model_routing import ModelSelection
from lonora_contracts.routines import RoutineCreate
from lonora_contracts.runs import Lease, RunRequest
from lonora_core.user_error import LonoraError
from lonora_db.agent_creation import MAXIMUM_ACTIVE_AGENTS, agent_origin, report_targets
from lonora_db.agent_permissions import permission_record
from lonora_db.agent_state import agent_live_state
from lonora_db.personal_agent import ensure_personal_agent
from lonora_db.routines import create_routine
from lonora_db.runs import claim_next, create_run
from lonora_db.schema import (
    AccountAuthorityRow,
    AgentRow,
    EventRow,
    MemoryRow,
    OwnerActionRow,
    RoutineRow,
    RunRow,
)
from lonora_db.threads import conversation_thread
from lonora_tools.context import ToolContext
from lonora_tools.loader import load_tools
from sqlalchemy import func, select

GOLD = "XAUUSD.r"


def snapshot(symbols: list[str]) -> dict[str, Any]:
    return {
        "currency": "USD",
        "balance": "10000",
        "instruments": [
            {
                "symbol": symbol,
                "digits": 2,
                "tick_size": "0.01",
                "volume_min": "0.1",
                "volume_max": "10",
                "volume_step": "0.1",
            }
            for symbol in symbols
        ],
        "quotes": {},
    }


async def main() -> None:
    fixture = await Fixture().open()
    db = fixture.runtime.db
    registry = load_tools()
    owner = fixture.owner
    created_ids: list[str] = []
    set_aside: list[str] = []
    try:

        async def connect(symbols: list[str]) -> str:
            connection = await fixture.request(
                "POST",
                "/trading/connections",
                {"provider": "simulation", "account_id": "create-" + uuid4().hex, "enabled": True},
            )
            account = cast(str, connection["id"])
            await fixture.request(
                "POST",
                f"/trading/connections/{account}/simulation",
                {"snapshot": snapshot(symbols)},
            )
            await fixture.runtime.services(owner).brokers.get(owner, account)
            return account

        # A shared CI database may hold other checks' agents: set them aside so the
        # per-owner cap is measured from this check's own agents, and restore them after.
        async with db.sessions() as session, session.begin():
            for row in await session.scalars(
                select(AgentRow).where(
                    AgentRow.owner_id == owner,
                    AgentRow.role.not_in(["personal", "delegated"]),
                    AgentRow.paused.is_(False),
                )
            ):
                row.paused = True
                set_aside.append(row.id)
        account = await connect([GOLD, "EURUSD"])
        async with db.sessions() as session, session.begin():
            lonora = await ensure_personal_agent(session, owner)
            lonora_id = lonora.id
            thread_id = (await conversation_thread(session, owner, lonora_id)).id

        async def end_runs(agent_id: str) -> None:
            async with db.sessions() as session, session.begin():
                for run in await session.scalars(
                    select(RunRow).where(
                        RunRow.agent_id == agent_id,
                        RunRow.status.in_(["queued", "leased", "running"]),
                    )
                ):
                    run.status = "completed"

        async def owner_turn(text: str) -> ToolContext:
            # The previous turn ended: a new message starts a new run, not a steer.
            await end_runs(lonora_id)
            sent = await fixture.request(
                "POST",
                f"/threads/{thread_id}/messages",
                {"content": text, "client_nonce": "create-" + uuid4().hex},
            )
            run = {"id": sent["run_ids"][0], "agent_id": lonora_id, "thread_id": thread_id}
            return await fixture.lease(run)

        async def wake(agent_id: str, agent_thread: str) -> ToolContext:
            async with db.sessions() as session, session.begin():
                run = await create_run(
                    session,
                    owner,
                    RunRequest(
                        thread_id=agent_thread,
                        agent_id=agent_id,
                        trigger="routine",
                        prompt="Scheduled check",
                    ),
                )
                run_id = run.id
            return await fixture.lease(
                {"id": run_id, "agent_id": agent_id, "thread_id": agent_thread}
            )

        async def call(
            context: ToolContext, name: str, arguments: dict[str, Any], call_id: str | None = None
        ) -> dict[str, Any]:
            return await registry.execute(
                ToolCall(id=call_id or "call-" + uuid4().hex, name=name, arguments=arguments),
                context,
            )

        async def refused(context: ToolContext, name: str, arguments: dict[str, Any]) -> str:
            try:
                await call(context, name, arguments)
            except LonoraError as error:
                return error.code
            raise AssertionError("Expected a refusal from " + name)

        async def decide(card_id: str, decision: str) -> dict[str, Any]:
            response = await fixture.client.post(
                f"/api/owner-actions/{card_id}/decision", json={"decision": decision}
            )
            assert response.is_success, response.text
            return cast(dict[str, Any], response.json())

        async def cards(thread: str) -> list[dict[str, Any]]:
            response = await fixture.client.get("/api/owner-actions", params={"thread_id": thread})
            assert response.is_success, response.text
            return cast(list[dict[str, Any]], response.json())

        async def grants(agent_id: str) -> int:
            async with db.sessions() as session:
                return int(
                    await session.scalar(
                        select(func.count())
                        .select_from(AccountAuthorityRow)
                        .where(AccountAuthorityRow.agent_id == agent_id)
                    )
                    or 0
                )

        # 1. The owner asks; the trading template resolves the focus pair from the only
        #    account's catalog (the broker's suffixed spelling) and starts at Ask me.
        context = await owner_turn("أنشئ وكيل ذهب يدير صفقاتي على حسابي")
        gold = await call(
            context,
            "agent_create",
            {
                "template": "trading",
                "name": "Gold agent",
                "market": "XAUUSD",
                "responsibility": "Manage gold trades on the owner's account.",
            },
            "gold-call",
        )
        assert gold["created"] is True and gold["deduplicated"] is False, gold
        gold_id = gold["agent"]["id"]
        created_ids.append(gold_id)
        assert gold["agent"]["focus"] == {"account_id": account, "symbol": GOLD}, gold
        assert gold["agent"]["trading_level"] == "ask_me"
        async with db.sessions() as session:
            row = await session.get(AgentRow, gold_id)
            assert row is not None
            assert (row.parent_id, row.scope_mode, row.role) == (None, "flexible", "specialist")
            assert row.trading_account_id == account and row.trading_symbol == GOLD
            assert (await permission_record(session, owner, gold_id)).fallback_level == "supervised"
            origin = await agent_origin(session, owner, gold_id)
            assert origin["created_via"] == "owner_message" and origin["source_message_id"]
            assert origin["created_by_agent_id"] == lonora_id and origin["template"] == "trading"
            event = await session.scalar(
                select(EventRow).where(
                    EventRow.kind == "agent.created", EventRow.agent_id == gold_id
                )
            )
            assert event is not None and event.payload["source_message_id"]
        assert await grants(gold_id) == 0
        print("PASS an owner message creates a flexible root trading agent at Ask me, no grant")

        # 2. A crash replay of the same call and a retry under a new call id return it.
        again = await call(
            context,
            "agent_create",
            {"template": "trading", "name": "Gold agent", "market": "XAUUSD"},
            "gold-call",
        )
        retry = await call(
            context,
            "agent_create",
            {"template": "trading", "name": "Gold agent", "market": "XAUUSD"},
        )
        assert again["agent"]["id"] == gold_id and retry["agent"]["id"] == gold_id
        assert retry["deduplicated"] is True
        async with db.sessions() as session:
            named = await session.scalar(
                select(func.count())
                .select_from(AgentRow)
                .where(AgentRow.owner_id == owner, AgentRow.name.like("Gold agent%"))
            )
            assert named == 1, named
        print("PASS replays and retries of one owner request never add a second agent")

        # 3. The result card: server facts and Undo; nothing the model wrote but the name.
        shown = [card for card in await cards(thread_id) if card["kind"] == "agent_created"]
        assert len(shown) == 1, shown
        undo_card = shown[0]
        assert undo_card["status"] == "pending" and undo_card["requires_passkey"] is False
        facts = undo_card["facts"]["agent"]
        assert facts["name"] == "Gold agent" and facts["symbol"] == GOLD
        assert facts["level"] == "supervised" and facts["template"] == "trading"
        assert undo_card["facts"]["undo"] == "delete"
        assert "responsibility" not in str(undo_card["facts"]), undo_card
        print("PASS the result card shows the agent, its pair and Ask me, with Undo")

        # 4. A research agent that reports to the gold agent, and a supervisor: one peer
        #    link, notes in both agents, No trading for both.
        news = await call(
            context,
            "agent_create",
            {
                "template": "research",
                "name": "News agent",
                "responsibility": "Follow economic news and report important items.",
                "report_to": [gold_id],
            },
        )
        supervisor = await call(
            context, "agent_create", {"template": "supervisor", "name": "Supervisor"}
        )
        news_id, supervisor_id = news["agent"]["id"], supervisor["agent"]["id"]
        created_ids.extend([news_id, supervisor_id])
        assert news["agent"]["trading_level"] == "no_trading" and news["agent"]["focus"] is None
        assert news["agent"]["reports_to"] == [gold_id]
        async with db.sessions() as session:
            for agent_id in (news_id, supervisor_id):
                row = await session.get(AgentRow, agent_id)
                assert row is not None and row.role == "general" and row.scope_mode == "flexible"
                level = (await permission_record(session, owner, agent_id)).fallback_level
                assert level == "analysis"
            news_memory = await session.get(MemoryRow, news_id)
            gold_memory = await session.get(MemoryRow, gold_id)
            assert news_memory is not None and gold_memory is not None
            assert "# OPERATING.md" in news_memory.content and gold_id in news_memory.content
            assert news_id in gold_memory.content, gold_memory.content
        directory = await call(context, "list_agents", {})
        entries = {item["id"]: item for item in directory["agents"]}
        assert entries[news_id]["reports_to"] == [gold_id]
        assert entries[news_id]["template"] == "research"
        assert entries[gold_id]["reports_to"] == []
        print("PASS a research agent reports to the gold agent: one link, notes in both")

        # 5. At most three creations per run.
        assert (
            await refused(context, "agent_create", {"template": "general", "name": "Fourth"})
            == "agent_create_run_limit"
        )
        repeat = await call(
            context,
            "agent_create",
            {"template": "research", "name": "News agent", "report_to": [gold_id]},
        )
        assert repeat["deduplicated"] is True and repeat["agent"]["id"] == news_id
        print("PASS at most three creations per run; a repeat still returns its agent")

        # 6. Without an owner message the creation is a card; the tap creates it once.
        async with db.sessions() as session, session.begin():
            gold_thread = (await conversation_thread(session, owner, gold_id)).id
        quiet = await wake(gold_id, gold_thread)
        proposal = await call(
            quiet, "agent_create", {"template": "research", "name": "Silver scout"}, "scout"
        )
        assert proposal["created"] is False and proposal["owner_must_tap"] is True, proposal
        card_id = proposal["owner_action"]["id"]
        repeated = await call(
            quiet, "agent_create", {"template": "research", "name": "Silver scout"}
        )
        assert repeated["owner_action"]["id"] == card_id and repeated["already_shown"] is True
        async with db.sessions() as session:
            assert (
                await session.scalar(
                    select(func.count())
                    .select_from(AgentRow)
                    .where(AgentRow.owner_id == owner, AgentRow.name == "Silver scout")
                )
                == 0
            )
        listed = {card["id"]: card for card in await cards(gold_thread)}
        assert listed[card_id]["kind"] == "create_agent"
        assert listed[card_id]["facts"]["agent"]["level"] == "analysis"
        confirmed = await decide(card_id, "confirm")
        assert confirmed["status"] == "confirmed", confirmed
        scout_id = confirmed["result"]["agent_id"]
        created_ids.append(scout_id)
        assert (await decide(card_id, "confirm"))["result"]["agent_id"] == scout_id
        async with db.sessions() as session:
            origin = await agent_origin(session, owner, scout_id)
            assert origin["created_via"] == "owner_card" and origin["card_id"] == card_id
        after = [card for card in await cards(gold_thread) if card["kind"] == "agent_created"]
        assert len(after) == 1 and after[0]["facts"]["agent"]["name"] == "Silver scout"
        print("PASS without an owner message a creation card waits; the tap creates it once")

        # 7. Undo removes an agent that has done nothing; it pauses one that has started.
        removed = await decide(after[0]["id"], "confirm")
        assert removed["status"] == "confirmed" and removed["result"]["undo"] == "deleted"
        async with db.sessions() as session:
            assert await session.get(AgentRow, scout_id) is None
        created_ids.remove(scout_id)
        paused = await decide(undo_card["id"], "confirm")
        assert paused["result"]["undo"] == "paused", paused  # The gold agent has a run.
        async with db.sessions() as session:
            row = await session.get(AgentRow, gold_id)
            assert row is not None and row.paused is True
        await fixture.request("PATCH", f"/agents/{gold_id}", {"paused": False})
        print("PASS Undo removes an untouched agent and pauses one that started work")

        # 8. Two accounts with the same symbol: one focused question, then the choice.
        second = await connect([GOLD])
        ask = await owner_turn("Create a gold agent")
        question = await call(
            ask, "agent_create", {"template": "trading", "name": "Gold two", "market": "XAUUSD"}
        )
        assert question["created"] is False and question["code"] == "agent_market_ambiguous"
        assert {item["account_id"] for item in question["candidates"]} == {account, second}
        chosen = await call(
            ask,
            "agent_create",
            {"template": "trading", "name": "Gold two", "market": GOLD, "account_id": second},
        )
        assert chosen["agent"]["focus"] == {"account_id": second, "symbol": GOLD}
        created_ids.append(chosen["agent"]["id"])
        assert (
            await refused(
                ask, "agent_create", {"template": "trading", "name": "Copper", "market": "HG"}
            )
            == "symbol_not_found"
        )
        print("PASS two matching accounts ask one question; an unknown symbol is refused")

        # 9. The per-owner cap of active agents.
        async with db.sessions() as session, session.begin():
            count = await session.scalar(
                select(func.count())
                .select_from(AgentRow)
                .where(
                    AgentRow.owner_id == owner,
                    AgentRow.role != "delegated",
                    AgentRow.paused.is_(False),
                )
            )
            filler: list[str] = []
            for index in range(MAXIMUM_ACTIVE_AGENTS - int(count or 0)):
                row = AgentRow(owner_id=owner, name=f"Filler {index}", role="legacy")
                session.add(row)
                await session.flush()
                filler.append(row.id)
        created_ids.extend(filler)
        capped = await owner_turn("Create a research agent")
        assert (
            await refused(capped, "agent_create", {"template": "research", "name": "One more"})
            == "agent_limit_reached"
        )
        print("PASS the per-owner cap of active agents is enforced")

        # 10. Steering watches: only your own; cancel, resume, move the expiry.
        async with db.sessions() as session, session.begin():
            news_thread = (await conversation_thread(session, owner, news_id)).id
        gold_turn = await wake(gold_id, gold_thread)
        until = utcnow() + timedelta(hours=3)
        watch = await call(
            gold_turn,
            "watch_create",
            {
                "kind": "price",
                "account_id": account,
                "symbol": GOLD,
                "condition": "above",
                "level": "2100",
                "prompt": "Gold above 2100",
                "expires_at": until.isoformat(),
            },
        )
        watch_id = watch["id"]
        news_turn = await wake(news_id, news_thread)
        assert (
            await refused(news_turn, "watch_cancel", {"watch_id": watch_id})
            == "market_watches_not_found"
        )
        await end_runs(gold_id)
        state = await live(db, owner, gold_id)
        assert state["state"] == "waiting" and state["phase"] == "monitoring", state
        assert state["reason_code"] == "market_watch" and state["watch_count"] == 1
        assert state["watches"][0]["symbol"] == GOLD and state["watches"][0]["expires_at"]
        assert state["watches"][0]["condition"] == "above" and "prompt" not in state["watches"][0]
        gold_turn = await wake(gold_id, gold_thread)
        cancelled = await call(gold_turn, "watch_cancel", {"watch_id": watch_id})
        assert cancelled["payload"]["enabled"] is False
        assert (
            cancelled["state"]["code"] == "watch_cancelled" and cancelled["undo"] == "watch_resume"
        )
        assert (await live(db, owner, gold_id))["watch_count"] == 0
        resumed = await call(gold_turn, "watch_resume", {"watch_id": watch_id})
        assert resumed["payload"]["enabled"] is True and "code" not in resumed["state"]
        later = utcnow() + timedelta(hours=6)
        moved = await call(
            gold_turn,
            "watch_update",
            {"watch_id": watch_id, "expires_at": later.isoformat(), "level": "2150"},
        )
        assert moved["payload"]["level"] == "2150"
        assert moved["payload"]["expires_at"].startswith(later.isoformat()[:16])
        response = await fixture.client.post(
            f"/api/watches/{watch_id}/control", json={"action": "cancel"}
        )
        assert response.is_success and response.json()["state"]["code"] == "watch_cancelled"
        print("PASS an agent steers only its own watches; the owner cancels any from the list")

        # 11. routine_toggle reaches only the agent's own routines.
        async with db.sessions() as session, session.begin():
            routine = await create_routine(
                session, owner, gold_id, RoutineCreate(prompt="Check gold", interval_seconds=3600)
            )
            routine_id = routine.id
        assert (
            await refused(news_turn, "routine_toggle", {"routine_id": routine_id, "enabled": False})
            == "routine_not_found"
        )
        toggled = await call(
            gold_turn, "routine_toggle", {"routine_id": routine_id, "enabled": False}
        )
        assert toggled["enabled"] is False
        async with db.sessions() as session:
            row = await session.get(RoutineRow, routine_id)
            assert row is not None and row.enabled is False
        print("PASS routine_toggle steers only the agent's own routines")

        # 12. Scripted model, normal runtime: "a news agent that reports to the gold agent,
        #     and a supervisor" yields one of each and one link, also when a restarted
        #     worker replays the turn under new call ids.
        await end_runs(gold_id)
        async with db.sessions() as session, session.begin():
            for row in await session.scalars(select(AgentRow).where(AgentRow.id.in_(filler))):
                row.paused = True
        scenario = await owner_turn(
            "أنشئ وكيل أخبار يتابع الأخبار الاقتصادية ويبلغ وكيل الذهب بالمهم، ووكيل يشرف عليهم"
        )
        attempt = {"value": 0}

        async def model(_: Any, messages: list[ModelMessage], tools: Any, **kwargs: Any) -> Any:
            turn = sum(1 for message in messages if message.role == "tool")
            prefix = f"try{attempt['value']}-"
            plan = [
                ToolCall(
                    id=prefix + "news",
                    name="agent_create",
                    arguments={
                        "template": "research",
                        "name": "Macro news",
                        "responsibility": "Follow economic news and X analysts.",
                        "report_to": [gold_id],
                    },
                ),
                ToolCall(
                    id=prefix + "supervisor",
                    name="agent_create",
                    arguments={"template": "supervisor", "name": "Desk supervisor"},
                ),
            ]
            selection = ModelSelection(provider="openai", model="scripted-agent-create")
            if turn < len(plan):
                return ModelReply(tool_calls=[plan[turn]], text=""), selection
            return ModelReply(tool_calls=[], text="أنشأت وكيل الأخبار ووكيل الإشراف."), selection

        with patch.object(scenario.router, "complete", model):
            await execute_run(scenario, registry, 120, 6)
            attempt["value"] = 1
            async with db.sessions() as session, session.begin():
                row = await session.get(RunRow, scenario.lease.run_id, with_for_update=True)
                assert row is not None and row.status == "completed", row and row.status
                # A restarted worker that lost the transcript runs the turn again.
                row.status, row.execution_state = "queued", {}
                claimed = await claim_next(session, "restarted-worker", 120)
                assert claimed is not None and claimed.id == row.id
                lease = Lease(run_id=row.id, owner="restarted-worker", fence=claimed.lease_fence)
            await execute_run(replace(scenario, lease=lease), registry, 120, 6)
        async with db.sessions() as session:
            macro = list(
                await session.scalars(
                    select(AgentRow).where(
                        AgentRow.owner_id == owner, AgentRow.name.like("Macro news%")
                    )
                )
            )
            desk = list(
                await session.scalars(
                    select(AgentRow).where(
                        AgentRow.owner_id == owner, AgentRow.name.like("Desk supervisor%")
                    )
                )
            )
            assert len(macro) == 1 and len(desk) == 1, ([r.name for r in macro], len(desk))
            links = [
                agent_id
                for agent in (macro[0], desk[0])
                for agent_id in report_targets(await agent_origin(session, owner, agent.id))
            ]
            assert links == [gold_id], links
            created_ids.extend([macro[0].id, desk[0].id])
        print("PASS a scripted turn creates one news agent, one supervisor and one link, once")

        # No creation path ever produced a grant.
        for agent_id in created_ids:
            assert await grants(agent_id) == 0
        async with db.sessions() as session:
            names = sorted(name for name in registry.tools if name.startswith("agent_"))
            assert names == ["agent_create"], names
            orphan = await session.scalar(
                select(func.count())
                .select_from(OwnerActionRow)
                .where(OwnerActionRow.owner_id == owner, OwnerActionRow.kind == "create_agent")
            )
            assert orphan == 1
        print("PASS no agent created from chat holds a grant")
    finally:
        async with db.sessions() as session, session.begin():
            for row in await session.scalars(select(AgentRow).where(AgentRow.id.in_(set_aside))):
                row.paused = False
        for agent_id in created_ids:
            try:
                await fixture.request("DELETE", "/agents/" + agent_id)
            except AssertionError:
                pass
        await fixture.close(cleanup=False)


async def live(db: Any, owner: str, agent_id: str) -> dict[str, Any]:
    async with db.sessions() as session:
        return (await agent_live_state(session, owner, agent_id)).model_dump(mode="json")


if __name__ == "__main__":
    asyncio.run(main())
