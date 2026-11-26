"""The fixed Mandate card (mandate 10.3, 4.2.1, 4.2.3).

It shows the agent's mode read live and one button for the other mode; the owner's tap
applies the mode the button showed. Switching to Full withdraws the agent's pending
Trade Approval cards and wakes it with fixed text; a card is never executed because of a
mode change. Runs on the real migrated PostgreSQL schema and the simulation broker
(skipped without ``LONORA_DATABASE_URL``).
"""

from decimal import Decimal
from typing import Any, cast
from uuid import uuid4

import pytest
from lonora_contracts.account import Position
from lonora_core.user_error import LonoraError
from test_proactive_wakes import call, database, retire, simulation


async def tap(fixture: Any, card_id: str, mode: str | None) -> Any:
    body: dict[str, Any] = {"decision": "confirm"}
    if mode is not None:
        body["trading_mode"] = mode
    return await fixture.client.post(f"/api/owner-actions/{card_id}/decision", json=body)


async def roster(fixture: Any) -> dict[str, dict[str, Any]]:
    rows = cast(list[dict[str, Any]], await fixture.request("GET", "/agents"))
    return {row["id"]: row for row in rows}


async def mode_of(fixture: Any, agent_id: str) -> str:
    from lonora_db.trading_mode import trading_mode

    async with fixture.runtime.db.sessions() as session:
        return await trading_mode(session, fixture.owner, agent_id)


@pytest.mark.asyncio
async def test_the_mandate_card_switches_the_mode_the_button_showed() -> None:
    database()
    from check_streaming import Fixture

    fixture = await Fixture().open()
    try:
        agent = await fixture.agent("Mandate", supervised=True)
        context = await fixture.lease(await fixture.run(agent, await fixture.conversation(agent)))
        card = (await call(context, "owner_action_propose", kind="trading_mode"))["owner_action"]
        assert card["kind"] == "trading_mode" and card["status"] == "pending", card
        # A repeated proposal returns the card already shown.
        repeat = await call(context, "owner_action_propose", kind="trading_mode")
        assert repeat["owner_action"]["id"] == card["id"] and repeat["repeated"], repeat
        shown = cast(
            list[dict[str, Any]],
            await fixture.request("GET", f"/owner-actions?thread_id={context.thread_id}"),
        )
        row = next(item for item in shown if item["id"] == card["id"])
        # Read live: the agent's current mode and its name, never the agent's words.
        assert row["facts"]["trading_mode"] == "ask"
        assert row["facts"]["agent"]["id"] == agent["id"]
        # The decision must carry the mode the button showed.
        missing = await tap(fixture, card["id"], None)
        assert missing.status_code == 422, missing.text
        assert await mode_of(fixture, agent["id"]) == "ask"
        full = await tap(fixture, card["id"], "full")
        assert full.status_code == 200, full.text
        assert full.json()["facts"]["trading_mode"] == "full"
        assert full.json()["result"]["trading_mode"] == "full"
        assert await mode_of(fixture, agent["id"]) == "full"
        # The same card stays the switch: the next tap shows Ask and applies Ask.
        ask = await tap(fixture, card["id"], "ask")
        assert ask.status_code == 200, ask.text
        assert await mode_of(fixture, agent["id"]) == "ask"
        assert ask.json()["facts"]["trading_mode"] == "ask"
        # A stale second tap applies what its button showed, never a toggle.
        again = await tap(fixture, card["id"], "ask")
        assert again.status_code == 200 and await mode_of(fixture, agent["id"]) == "ask"
        # Tapped, it no longer waits for the owner, and it is still the agent's switch.
        assert again.json()["status"] == "confirmed"
    finally:
        await fixture.close()


@pytest.mark.asyncio
async def test_only_the_signed_in_owner_decides_the_mandate_card() -> None:
    """Without a session 401, without the CSRF token 403, another owner's card 404; none of
    them changes the mode."""
    database()
    import httpx
    from check_streaming import Fixture
    from lonora_api.middleware.auth import require_owner
    from lonora_auth.identity import OwnerIdentity

    fixture = await Fixture().open()
    try:
        agent = await fixture.agent("Guarded", supervised=True)
        context = await fixture.lease(await fixture.run(agent, await fixture.conversation(agent)))
        card = (await call(context, "owner_action_propose", kind="trading_mode"))["owner_action"]
        path = f"/api/owner-actions/{card['id']}/decision"
        body = {"decision": "confirm", "trading_mode": "full"}
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(fixture.app), base_url="https://streaming.test"
        ) as anonymous:
            assert (await anonymous.post(path, json=body)).status_code == 401
        assert await mode_of(fixture, agent["id"]) == "ask"
        csrf = fixture.client.headers.pop("X-CSRF-Token")
        try:
            denied = await fixture.client.post(path, json=body)
            assert denied.status_code == 403, denied.text
        finally:
            fixture.client.headers["X-CSRF-Token"] = csrf
        assert await mode_of(fixture, agent["id"]) == "ask"
        # Another owner's signed-in session never finds this owner's card.
        fixture.app.dependency_overrides[require_owner] = lambda: OwnerIdentity(
            id=str(uuid4()), email="other-owner@example.test", token_hash="other-owner-session"
        )
        try:
            foreign = await fixture.client.post(path, json=body)
        finally:
            fixture.app.dependency_overrides.pop(require_owner)
        assert foreign.status_code == 404, foreign.text
        assert foreign.json()["code"] == "owner_action_not_found", foreign.text
        assert await mode_of(fixture, agent["id"]) == "ask"
        missing = await fixture.client.post(f"/api/owner-actions/{uuid4()}/decision", json=body)
        assert missing.status_code == 404
        # The signed-in owner's own tap still applies it.
        assert (await tap(fixture, card["id"], "full")).status_code == 200
        assert await mode_of(fixture, agent["id"]) == "full"
    finally:
        await fixture.close()


@pytest.mark.asyncio
async def test_only_lonora_raises_the_card_for_another_agent() -> None:
    database()
    from check_streaming import Fixture

    fixture = await Fixture().open()
    try:
        first = await fixture.agent("First", supervised=True)
        second = await fixture.agent("Second", supervised=True)
        context = await fixture.lease(await fixture.run(first, await fixture.conversation(first)))
        with pytest.raises(LonoraError, match="owner_action_trading_mode_agent_forbidden"):
            await call(context, "owner_action_propose", kind="trading_mode", agent_id=second["id"])
    finally:
        await fixture.close()


@pytest.mark.asyncio
async def test_switching_to_full_withdraws_pending_approvals_and_never_executes_them() -> None:
    database()
    from check_streaming import Fixture
    from lonora_db.schema import RunRow, TradeApprovalRow, TradingJournalRow
    from sqlalchemy import select

    fixture = await Fixture().open()
    connection = ""
    try:
        held = Position(
            id="mandate-ticket",
            symbol="XAUUSD",
            side="buy",
            volume=Decimal("0.1"),
            open_price=Decimal(100),
        )
        connection = await simulation(fixture, [held])
        agent = await fixture.agent("Withdraw", supervised=True)
        context = await fixture.lease(await fixture.run(agent, await fixture.conversation(agent)))
        entry = {
            "action": "buy",
            "account_id": connection,
            "symbol": "XAUUSD",
            "volume": "0.1",
            "tolerance": "2",
            "reason": "Fixture entry",
        }
        asked = await same_call(context, entry)
        assert asked.get("_runtime_wait") and asked.get("approval_id"), asked
        async with fixture.runtime.db.sessions() as session, session.begin():
            # The runtime parks a run that waits on a card.
            waiting = await session.get(RunRow, context.lease.run_id, with_for_update=True)
            assert waiting is not None
            waiting.status = "waiting_input"
        # A second card of the same agent whose run has ended: no run waits on it.
        other = await fixture.lease(await fixture.run(agent, await fixture.conversation(agent)))
        card = (await call(other, "owner_action_propose", kind="trading_mode"))["owner_action"]
        idle = await call(other, "trade_execute", **{**entry, "volume": "0.2"})
        assert idle.get("_runtime_wait") and idle.get("approval_id"), idle
        # A third whose run is still working: it reads the withdrawal itself.
        busy_run = await fixture.lease(await fixture.run(agent, await fixture.conversation(agent)))
        busy = await call(busy_run, "trade_execute", **{**entry, "volume": "0.3"})
        assert busy.get("_runtime_wait") and busy.get("approval_id"), busy
        async with fixture.runtime.db.sessions() as session, session.begin():
            ended = await session.get(RunRow, other.lease.run_id, with_for_update=True)
            assert ended is not None
            ended.status = "completed"
        full = await tap(fixture, card["id"], "full")
        assert full.status_code == 200, full.text
        # The server counts what the tap withdrew.
        assert full.json()["result"] == {"trading_mode": "full", "withdrawn": 3}, full.text
        async with fixture.runtime.db.sessions() as session:
            approval = await session.get(TradeApprovalRow, asked["approval_id"])
            assert approval is not None and approval.status == "withdrawn"
            run = await session.get(RunRow, context.lease.run_id)
            assert run is not None and run.status == "queued"
            # The card no run waited on wakes its agent with fixed server text.
            idle_card = await session.get(TradeApprovalRow, idle["approval_id"])
            assert idle_card is not None and idle_card.status == "withdrawn"
            wake = await session.scalar(
                select(RunRow).where(
                    RunRow.model_metadata["withdrawn_trade_approval_id"].as_string()
                    == idle["approval_id"]
                )
            )
            assert wake is not None and wake.agent_id == agent["id"]
            assert "Your trading mode is now Full" in (wake.prompt or ""), wake.prompt
            # A run still working is never woken a second time for the same request.
            busy_card = await session.get(TradeApprovalRow, busy["approval_id"])
            assert busy_card is not None and busy_card.status == "withdrawn"
            second = await session.scalar(
                select(RunRow).where(
                    RunRow.model_metadata["withdrawn_trade_approval_id"].as_string()
                    == busy["approval_id"]
                )
            )
            assert second is None
            sent = await session.scalar(
                select(TradingJournalRow.operation_id).where(
                    TradingJournalRow.owner_id == fixture.owner,
                    TradingJournalRow.account_id == connection,
                )
            )
            assert sent is None, "A mode change executed a pending card"
        # The waiting call reads fixed server text and decides again under Full.
        context = await fixture.lease({"id": context.lease.run_id, **agent_run(context)})
        answer = await same_call(context, entry)
        assert answer.get("status") == "withdrawn", answer
        assert answer.get("code") == "trade_approval_withdrawn"
        assert "Full" in answer.get("recovery", "")
        # The owner can never approve a withdrawn card.
        late = await fixture.client.post(
            f"/api/trading/approvals/{asked['approval_id']}/decision", json={"decision": "approve"}
        )
        assert late.status_code == 409, late.text
    finally:
        await retire(fixture, connection)
        await fixture.close()


async def same_call(context: Any, arguments: dict[str, Any]) -> dict[str, Any]:
    """The runtime resumes a waiting call with the same call id."""
    from lonora_adapter_kit.types import ToolCall
    from lonora_tools.loader import load_tools

    return await load_tools().execute(
        ToolCall(id="mandate-trade-call", name="trade_execute", arguments=arguments), context
    )


def agent_run(context: Any) -> dict[str, Any]:
    return {"agent_id": context.agent_id, "thread_id": context.thread_id}


@pytest.mark.asyncio
async def test_a_switch_to_full_while_a_card_is_prepared_decides_under_full(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The card insert re-reads the mode under the authority lock: a card raised after
    the switch would never be withdrawn, so the request is decided under Full."""
    database()
    from check_streaming import Fixture
    from lonora_db.schema import TradeApprovalRow
    from lonora_db.trading_mode import set_trading_mode
    from lonora_tools import trade
    from sqlalchemy import func, select

    fixture = await Fixture().open()
    connection = ""
    try:
        connection = await simulation(fixture, [])
        agent = await fixture.agent("Race", supervised=True)
        context = await fixture.lease(await fixture.run(agent, await fixture.conversation(agent)))
        prepare = trade.reviewed_contracts

        async def owner_taps_full_meanwhile(*args: Any) -> Any:
            async with fixture.runtime.db.sessions() as session, session.begin():
                await set_trading_mode(session, fixture.owner, agent["id"], "full", by="owner_tap")
            return await prepare(*args)

        monkeypatch.setattr(trade, "reviewed_contracts", owner_taps_full_meanwhile)
        entry = {
            "action": "buy",
            "account_id": connection,
            "symbol": "XAUUSD",
            "volume": "0.1",
            "tolerance": "2",
            "reason": "Fixture entry",
        }
        result = await call(context, "trade_execute", **entry)
        assert result.get("status") == "confirmed" and "approval_id" not in result, result
        async with fixture.runtime.db.sessions() as session:
            cards = await session.scalar(
                select(func.count())
                .select_from(TradeApprovalRow)
                .where(TradeApprovalRow.run_id == context.lease.run_id)
            )
        assert cards == 0
    finally:
        await retire(fixture, connection)
        await fixture.close()


@pytest.mark.asyncio
async def test_the_card_is_refreshed_when_the_mode_changes_elsewhere() -> None:
    database()
    from check_streaming import Fixture
    from lonora_db.schema import EventRow
    from sqlalchemy import select

    fixture = await Fixture().open()
    try:
        agent = await fixture.agent("Live", supervised=True)
        context = await fixture.lease(await fixture.run(agent, await fixture.conversation(agent)))
        card = (await call(context, "owner_action_propose", kind="trading_mode"))["owner_action"]
        assert (await tap(fixture, card["id"], "full")).status_code == 200
        async with fixture.runtime.db.sessions() as session:
            before = await session.scalar(select(EventRow.cursor).order_by(EventRow.cursor.desc()))
        # The agent switches itself to Ask: its card's conversation hears of it.
        assert (await call(context, "trading_mode_ask"))["trading_mode"] == "ask"
        async with fixture.runtime.db.sessions() as session:
            events = list(
                await session.scalars(
                    select(EventRow).where(
                        EventRow.cursor > (before or 0), EventRow.kind == "owner_action.updated"
                    )
                )
            )
        assert any(event.payload.get("id") == card["id"] for event in events), events
        shown = cast(
            list[dict[str, Any]],
            await fixture.request("GET", f"/owner-actions?thread_id={context.thread_id}"),
        )
        assert next(row for row in shown if row["id"] == card["id"])["facts"]["trading_mode"] == (
            "ask"
        )
    finally:
        await fixture.close()


@pytest.mark.asyncio
async def test_lonoras_card_for_a_deleted_agent_ends_with_it() -> None:
    database()
    from check_streaming import Fixture
    from lonora_db.schema import AgentRow, RunRow
    from sqlalchemy import select

    fixture = await Fixture().open()
    run_id = ""
    try:
        async with fixture.runtime.db.sessions() as session:
            lonora = await session.scalar(
                select(AgentRow).where(
                    AgentRow.owner_id == fixture.owner, AgentRow.role == "personal"
                )
            )
        assert lonora is not None
        team = await fixture.agent("Team", supervised=True)
        personal = {"id": lonora.id}
        context = await fixture.lease(
            await fixture.run(personal, await fixture.conversation(personal))
        )
        run_id = context.lease.run_id
        card = (
            await call(context, "owner_action_propose", kind="trading_mode", agent_id=team["id"])
        )["owner_action"]
        await fixture.request("DELETE", "/agents/" + team["id"])
        fixture.agents.remove(team["id"])
        shown = cast(
            list[dict[str, Any]],
            await fixture.request("GET", f"/owner-actions?thread_id={context.thread_id}"),
        )
        row = next(item for item in shown if item["id"] == card["id"])
        assert row["status"] != "pending", row
    finally:
        if run_id:
            # Lonora outlives the fixture: a run left working in its conversation would
            # take every later owner message there as steering (admit_runs).
            async with fixture.runtime.db.sessions() as session, session.begin():
                run = await session.get(RunRow, run_id, with_for_update=True)
                if run is not None:
                    run.status = "completed"
        await fixture.close()


@pytest.mark.asyncio
async def test_lonora_offers_its_own_mandate_card_at_onboarding() -> None:
    """4.3.1: Lonora starts in Ask and offers its Mandate card during onboarding."""
    database()
    from check_streaming import Fixture
    from lonora_db.personal_agent import ensure_personal_agent
    from lonora_db.schema import OwnerActionRow
    from lonora_db.threads import conversation_thread
    from sqlalchemy import select

    fixture = await Fixture().open()
    try:
        async with fixture.runtime.db.sessions() as session, session.begin():
            lonora = await ensure_personal_agent(session, fixture.owner)
            thread = await conversation_thread(session, fixture.owner, lonora.id)
            cards = list(
                await session.scalars(
                    select(OwnerActionRow).where(
                        OwnerActionRow.owner_id == fixture.owner,
                        OwnerActionRow.kind == "trading_mode",
                        OwnerActionRow.subject == "trading_mode:" + lonora.id,
                    )
                )
            )
            # Asked again, no second card.
            await ensure_personal_agent(session, fixture.owner)
        assert [(c.subject, c.thread_id, c.status) for c in cards] == [
            ("trading_mode:" + lonora.id, thread.id, "pending")
        ], cards
        assert await mode_of(fixture, lonora.id) == "ask"
        tapped = await tap(fixture, cards[0].id, "full")
        assert tapped.status_code == 200, tapped.text
        assert await mode_of(fixture, lonora.id) == "full"
    finally:
        await fixture.close()


@pytest.mark.asyncio
async def test_every_agent_read_carries_its_mode_and_full_is_marked_on_its_own() -> None:
    """GET /agents and GET /agents/{id} carry each agent's mode (Ask until the owner taps
    Full). The avatar marker reads it: a Full agent with no grant is marked while it is not
    paused; one the owner holds at the old ladder's "No trading" is not, since the door
    refuses its every send."""
    database()
    from check_streaming import Fixture
    from lonora_db.trading_mode import set_trading_mode

    fixture = await Fixture().open()
    try:
        agent = await fixture.agent("Roster", supervised=True)
        held = await fixture.agent("Held")
        # The old ladder's "No trading", stored in-process: no agent starts there, and no
        # route writes a level (4.1).
        from lonora_contracts.agent_permissions import PermissionChange
        from lonora_db.agent_permissions import change_permission

        state = await fixture.request("GET", f"/agents/{held['id']}/permissions")
        async with fixture.runtime.db.sessions() as session, session.begin():
            await change_permission(
                session,
                fixture.owner,
                held["id"],
                PermissionChange(level="analysis", expected_revision=state["revision"]),
            )
        assert agent["trading_mode"] == "ask"
        rows = await roster(fixture)
        assert {row["trading_mode"] for row in rows.values()} <= {"ask", "full"}, rows
        assert rows[agent["id"]]["trading_mode"] == "ask"
        assert rows[agent["id"]]["trades_on_its_own"] is False
        async with fixture.runtime.db.sessions() as session, session.begin():
            for target in (agent, held):
                await set_trading_mode(session, fixture.owner, target["id"], "full", by="owner_tap")
        rows = await roster(fixture)
        assert rows[agent["id"]]["trading_mode"] == "full"
        assert rows[agent["id"]]["trades_on_its_own"] is True
        one = await fixture.request("GET", f"/agents/{agent['id']}")
        assert one["trading_mode"] == "full" and one["trades_on_its_own"] is True
        assert rows[held["id"]]["trading_mode"] == "full"
        assert rows[held["id"]]["trades_on_its_own"] is False
        # Paused, it takes no new work: still Full, no longer marked; resumed, marked again.
        paused = await fixture.request("PATCH", f"/agents/{agent['id']}", {"paused": True})
        assert paused["trading_mode"] == "full" and paused["trades_on_its_own"] is False
        assert (await roster(fixture))[agent["id"]]["trades_on_its_own"] is False
        resumed = await fixture.request("PATCH", f"/agents/{agent['id']}", {"paused": False})
        assert resumed["trades_on_its_own"] is True
    finally:
        await fixture.close()


@pytest.mark.asyncio
async def test_the_agents_live_mandate_card_is_read_per_agent_and_never_raised_by_a_read() -> None:
    """Q7: the agent's live Mandate card, the real card, is read per agent outside the
    card's conversation. Reading answers null while there is none and never raises one; the
    tap emits ``agent.trading_mode.updated`` and the card stays the agent's switch."""
    database()
    from check_streaming import Fixture
    from lonora_api.middleware.auth import require_owner
    from lonora_auth.identity import OwnerIdentity
    from lonora_db.schema import EventRow, OwnerActionRow
    from sqlalchemy import func, select

    fixture = await Fixture().open()
    try:
        agent = await fixture.agent("Reach", supervised=True)
        path = f"/api/owner-actions/mandate?agent_id={agent['id']}"

        async def cards() -> int:
            async with fixture.runtime.db.sessions() as session:
                count = await session.scalar(
                    select(func.count())
                    .select_from(OwnerActionRow)
                    .where(
                        OwnerActionRow.owner_id == fixture.owner,
                        OwnerActionRow.subject == "trading_mode:" + agent["id"],
                    )
                )
            return int(count or 0)

        for _ in range(2):
            none = await fixture.client.get(path)
            assert none.status_code == 200 and none.json() is None, none.text
        assert await cards() == 0
        context = await fixture.lease(await fixture.run(agent, await fixture.conversation(agent)))
        card = (await call(context, "owner_action_propose", kind="trading_mode"))["owner_action"]
        live = (await fixture.client.get(path)).json()
        assert live["id"] == card["id"] and live["kind"] == "trading_mode", live
        assert live["status"] == "pending" and live["facts"]["trading_mode"] == "ask"
        assert live["facts"]["agent"]["id"] == agent["id"]
        async with fixture.runtime.db.sessions() as session:
            before = await session.scalar(select(EventRow.cursor).order_by(EventRow.cursor.desc()))
        full = await tap(fixture, card["id"], "full")
        assert full.status_code == 200, full.text
        assert full.json()["result"] == {"trading_mode": "full", "withdrawn": 0}, full.text
        async with fixture.runtime.db.sessions() as session:
            switched = list(
                await session.scalars(
                    select(EventRow).where(
                        EventRow.cursor > (before or 0),
                        EventRow.kind == "agent.trading_mode.updated",
                    )
                )
            )
        assert [
            (event.agent_id, {key: event.payload.get(key) for key in ("trading_mode", "by")})
            for event in switched
        ] == [(agent["id"], {"trading_mode": "full", "by": "owner_tap"})], switched
        # Tapped, it is still the agent's switch, read live; reading raised no second card.
        tapped = (await fixture.client.get(path)).json()
        assert tapped["id"] == card["id"] and tapped["status"] == "confirmed", tapped
        assert tapped["facts"]["trading_mode"] == "full"
        assert await cards() == 1
        # Another owner's session never finds this owner's agent.
        fixture.app.dependency_overrides[require_owner] = lambda: OwnerIdentity(
            id=str(uuid4()), email="other-owner@example.test", token_hash="other-owner-session"
        )
        try:
            foreign = await fixture.client.get(path)
        finally:
            fixture.app.dependency_overrides.pop(require_owner)
        assert foreign.status_code == 404 and foreign.json()["code"] == "agent_not_found"
    finally:
        await fixture.close()


@pytest.mark.asyncio
async def test_owner_can_request_one_mandate_card_without_switching_the_mode() -> None:
    database()
    from check_streaming import Fixture

    fixture = await Fixture().open()
    try:
        agent = await fixture.agent("Mandate from composer", supervised=True)
        path = f"/api/owner-actions/mandate?agent_id={agent['id']}"
        assert (await fixture.client.get(path)).json() is None
        requested = await fixture.client.post(path, json={})
        assert requested.status_code == 200, requested.text
        card = requested.json()
        assert card["status"] == "pending" and card["facts"]["trading_mode"] == "ask"
        assert (await fixture.client.post(path, json={})).json()["id"] == card["id"]
        agent_read = await fixture.client.get(f"/api/agents/{agent['id']}")
        assert agent_read.json()["trading_mode"] == "ask"
        confirmed = await tap(fixture, card["id"], "full")
        assert confirmed.json()["result"]["trading_mode"] == "full"
        assert (await fixture.client.post(path, json={})).json()["id"] == card["id"]
    finally:
        await fixture.close()
