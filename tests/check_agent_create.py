"""Creating and steering agents from chat on disposable PostgreSQL (mandate 3.1.2, 3.3).

Runs agent_create as Lonora (from the owner's message and on its own judgment) and as a
team agent, the watch steering tools and the owner's watch control route against the
simulation broker. No live broker, model provider or real order is involved.
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
from lonora_contracts.model_routing import AgentModelChange, ModelSelection
from lonora_contracts.routines import RoutineCreate
from lonora_contracts.runs import Lease, RunRequest
from lonora_core.user_error import LonoraError, ToolRefusal
from lonora_db.agent_creation import agent_origin
from lonora_db.agent_models import change_agent_model, stored_agent_model
from lonora_db.agent_state import agent_live_state
from lonora_db.management_task import live_management_task
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
from lonora_db.trading_mode import set_trading_mode
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

        async def method(agent_id: str) -> str:
            async with db.sessions() as session:
                row = await session.get(MemoryRow, agent_id)
                return row.content if row else ""

        async def mandate_cards(agent_id: str) -> list[dict[str, Any]]:
            return [
                card
                for card in await cards(thread_id)
                if card["kind"] == "trading_mode" and card["facts"]["agent"]["id"] == agent_id
            ]

        # Lonora's current model: a new agent uses it until the owner assigns another.
        lead_model = ModelSelection(provider="openai", model="lead-model-" + uuid4().hex[:6])
        async with db.sessions() as session, session.begin():
            await change_agent_model(
                session, owner, lonora_id, AgentModelChange(mode="fixed", primary=lead_model)
            )

        # 1. «أنشئ وكيل ذهب بصلاحية كاملة»: Lonora creates it at once, flat, in Ask, and
        #    shows its Mandate card (4.3.2); the instrument is its method, never a binding.
        context = await owner_turn("أنشئ وكيل ذهب بصلاحية كاملة يدير صفقاتي على حسابي")
        gold = await call(
            context,
            "agent_create",
            {
                "name": "Gold agent",
                "market": "XAUUSD",
                "mode": "full",
                "responsibility": "Manage gold trades on the owner's account.",
            },
            "gold-call",
        )
        assert gold["created"] is True and gold["deduplicated"] is False, gold
        gold_id = gold["agent"]["id"]
        created_ids.append(gold_id)
        assert gold["agent"]["trading_mode"] == "ask" and gold["mandate_card_shown"] is True
        assert "owner_action" not in gold and "peer_send" in gold["next"]
        async with db.sessions() as session:
            row = await session.get(AgentRow, gold_id)
            assert row is not None
            assert (row.parent_id, row.scope_mode, row.role, row.template) == (
                None,
                "flexible",
                "general",
                None,
            )
            assert row.trading_account_id is None and row.trading_symbol is None
            assert row.trading_mode == "ask"
            origin = await agent_origin(session, owner, gold_id)
            assert origin["created_via"] == "owner_message" and origin["source_message_id"]
            assert origin["created_by_agent_id"] == lonora_id and origin["template"] is None
            assert origin["report_to"] == []
            copied = await stored_agent_model(session, owner, gold_id)
            assert copied.preference.primary == lead_model, copied
            event = await session.scalar(
                select(EventRow).where(
                    EventRow.kind == "agent.created", EventRow.agent_id == gold_id
                )
            )
            assert event is not None and event.payload["source_message_id"]
            assert await live_management_task(session, owner, gold_id) is None
        assert f'Lonora assigned you "{GOLD}" on the account' in await method(gold_id)
        (mandate,) = await mandate_cards(gold_id)
        assert mandate["status"] == "pending" and mandate["facts"]["trading_mode"] == "ask"
        assert await grants(gold_id) == 0
        print("PASS the owner's request creates a flat agent in Ask with its Mandate card")

        # 2. A crash replay of the same call and a retry under a new call id return it.
        again = await call(
            context, "agent_create", {"name": "Gold agent", "market": "XAUUSD"}, "gold-call"
        )
        retry = await call(context, "agent_create", {"name": "Gold agent", "market": "XAUUSD"})
        assert again["agent"]["id"] == gold_id and retry["agent"]["id"] == gold_id
        assert retry["deduplicated"] is True
        async with db.sessions() as session:
            named = await session.scalar(
                select(func.count())
                .select_from(AgentRow)
                .where(AgentRow.owner_id == owner, AgentRow.name.like("Gold agent%"))
            )
            assert named == 1, named
        assert len(await mandate_cards(gold_id)) == 1
        print("PASS replays and retries of one owner request never add a second agent")

        # 3. On its own judgment (a routine wake, no owner message) Lonora creates without
        #    asking: the new agent copies Lonora's mode, unless Lonora creates it in Ask.
        own = await wake(lonora_id, thread_id)
        scout = await call(
            own, "agent_create", {"name": "Scout", "responsibility": "Scan the majors."}
        )
        scout_id = scout["agent"]["id"]
        created_ids.append(scout_id)
        assert scout["created"] is True and scout["agent"]["trading_mode"] == "ask", scout
        assert scout["mandate_card_shown"] is False
        async with db.sessions() as session, session.begin():
            assert (await agent_origin(session, owner, scout_id))["created_via"] == "lead"
            # The owner's tap on Lonora's own Mandate card.
            await set_trading_mode(session, owner, lonora_id, "full", by="owner_tap")
        runner = await call(own, "agent_create", {"name": "Runner"})
        runner_id = runner["agent"]["id"]
        created_ids.append(runner_id)
        careful = await call(own, "agent_create", {"name": "Careful", "mode": "ask"})
        careful_id = careful["agent"]["id"]
        created_ids.append(careful_id)
        assert runner["agent"]["trading_mode"] == "full", runner
        assert careful["agent"]["trading_mode"] == "ask", careful
        async with db.sessions() as session, session.begin():
            # Full starts its continuous account-management task at once (4.5.1).
            assert await live_management_task(session, owner, runner_id) is not None
            assert await live_management_task(session, owner, careful_id) is None
            # Later changes to Lonora's mode never change another agent's mode (4.3.4).
            await set_trading_mode(session, owner, lonora_id, "ask", by="owner_tap")
            assert (
                await session.get(AgentRow, runner_id, populate_existing=True)
            ).trading_mode == (  # type: ignore[union-attr]
                "full"
            )
        print("PASS on its own judgment Lonora's agents copy its mode, or start in Ask")

        # 4. The guard against a runaway loop: three creations per minute within one run.
        assert await refused(own, "agent_create", {"name": "Fourth"}) == "agent_create_run_limit"
        # A minute later the same run creates again: a rate, never a count of agents.
        async with db.sessions() as session, session.begin():
            for row in await session.scalars(
                select(EventRow).where(
                    EventRow.run_id == own.lease.run_id, EventRow.kind == "agent.created"
                )
            ):
                row.created_at = utcnow() - timedelta(minutes=2)
        fourth = await call(own, "agent_create", {"name": "Fourth", "mode": "ask"})
        assert fourth["created"] is True, fourth
        created_ids.append(fourth["agent"]["id"])
        print("PASS at most three creations per minute in a run; the total is never counted")

        # 5. No leading (3.2.2): a team agent's call is refused with the way to ask Lonora.
        async with db.sessions() as session, session.begin():
            gold_thread = (await conversation_thread(session, owner, gold_id)).id
            scout_thread = (await conversation_thread(session, owner, scout_id)).id
        team = await wake(gold_id, gold_thread)
        try:
            await call(team, "agent_create", {"name": "Helper"})
        except ToolRefusal as error:
            assert error.code == "agent_create_lead_only" and error.status == 403
            assert "peer_send" in error.details["hint"] and "Lonora" in error.details["hint"]
        else:
            raise AssertionError("a team agent created an agent")
        try:
            await call(team, "child_agent_create", {"name": "Child", "task": "x"})
        except ToolRefusal as error:
            assert error.code == "agent_create_lead_only", error.code
        else:
            raise AssertionError("a team agent created a child agent")
        await end_runs(gold_id)
        print("PASS a team agent cannot create agents and is told to ask Lonora")

        # 6. Two accounts with the same symbol: one focused question, then the choice.
        second = await connect([GOLD])
        ask = await owner_turn("Create a gold agent")
        question = await call(ask, "agent_create", {"name": "Gold two", "market": "XAUUSD"})
        assert question["created"] is False and question["code"] == "agent_market_ambiguous"
        assert {item["account_id"] for item in question["candidates"]} == {account, second}
        chosen = await call(
            ask, "agent_create", {"name": "Gold two", "market": GOLD, "account_id": second}
        )
        created_ids.append(chosen["agent"]["id"])
        async with db.sessions() as session:
            row = await session.get(AgentRow, chosen["agent"]["id"])
            assert row is not None and row.trading_account_id is None
        assert f'"{GOLD}" on the account' in await method(chosen["agent"]["id"])
        assert (
            await refused(ask, "agent_create", {"name": "Copper", "market": "HG"})
            == "symbol_not_found"
        )
        print("PASS two matching accounts ask one question; an unknown symbol is refused")

        # 7. No limit on the number of agents (mandate 3.3.2): 25 active agents and
        # more are created; only the per-run guard above ever refuses.
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
            for index in range(max(25 - int(count or 0), 0)):
                row = AgentRow(owner_id=owner, name=f"Filler {index}", role="legacy")
                session.add(row)
                await session.flush()
                filler.append(row.id)
        created_ids.extend(filler)
        uncapped = await owner_turn("Create a research agent")
        more = await call(uncapped, "agent_create", {"name": "One more"})
        assert more["created"] is True, more
        created_ids.append(more["agent"]["id"])
        print("PASS 25 active agents exist and another is created: no cap on agents")

        # 8. Steering watches: only your own; cancel, resume, move the expiry.
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
        news_turn = await wake(scout_id, scout_thread)
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

        # 9. routine_toggle reaches only the agent's own routines.
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

        # 10. Scripted model, normal runtime: «أنشئ وكيل أخبار» yields one agent, also when
        #     a restarted worker replays the turn under new call ids.
        await end_runs(gold_id)
        await end_runs(scout_id)
        scenario = await owner_turn(
            "أنشئ وكيل أخبار يتابع الأخبار الاقتصادية ويبلغ وكيل الذهب بالمهم"
        )
        attempt = {"value": 0}

        async def model(_: Any, messages: list[ModelMessage], tools: Any, **kwargs: Any) -> Any:
            turn = sum(1 for message in messages if message.role == "tool")
            call_id = f"try{attempt['value']}-news"
            selection = ModelSelection(provider="openai", model="scripted-agent-create")
            if turn == 0:
                create_call = ToolCall(
                    id=call_id,
                    name="agent_create",
                    arguments={
                        "name": "Macro news",
                        "responsibility": "Follow economic news and tell the gold agent "
                        "what matters.",
                    },
                )
                return ModelReply(tool_calls=[create_call], text=""), selection
            return ModelReply(tool_calls=[], text="أنشأت وكيل الأخبار ليتابع الاقتصاد."), selection

        with patch.object(scenario.router, "complete", model):
            await execute_run(scenario, registry, 120, 6)
            attempt["value"] = 1
            async with db.sessions() as session, session.begin():
                row = await session.get(RunRow, scenario.lease.run_id, with_for_update=True)
                assert row is not None and row.status == "completed", row and (
                    row.status,
                    row.error_code,
                    row.result,
                )
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
            assert len(macro) == 1, [r.name for r in macro]
            created_ids.append(macro[0].id)
        print("PASS a scripted turn creates one news agent, once across a worker restart")

        # No creation path ever produced a grant or a card other than the Mandate card.
        for agent_id in created_ids:
            assert await grants(agent_id) == 0
        async with db.sessions() as session:
            names = sorted(name for name in registry.tools if name.startswith("agent_"))
            assert names == ["agent_control", "agent_create", "agent_inspect"], names
            assert not any(registry.tools[name].financial for name in names)
            kinds = set(
                await session.scalars(
                    select(OwnerActionRow.kind).where(
                        OwnerActionRow.owner_id == owner, OwnerActionRow.thread_id == thread_id
                    )
                )
            )
            assert kinds <= {"trading_mode"}, kinds
        print("PASS no agent created from chat holds a grant, and no creation card exists")
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
