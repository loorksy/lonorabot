"""Card journeys (WP-F cards) through the tools, the owner routes and the passkey.

Expired trade approvals are never executed and «طلب جديد» only asks the agent again; an
agent's watch extension is a notice with one-use Undo, the owner's «تمديد» is not; a
tightened stop is a notice without Undo; the mandate sheet's draft grants nothing until
the owner signs it, the signature covers exactly the draft, and stopping another agent
only narrows it. Runs on the real migrated PostgreSQL schema with the simulation broker
(skipped without ``LONORA_DATABASE_URL``).
"""

from datetime import datetime, timedelta
from decimal import Decimal
from typing import Any, cast
from uuid import uuid4

import pytest
from lonora_adapter_kit.types import ToolCall
from lonora_contracts.account import Position
from lonora_contracts.account_authority import ALL_AUTHORITY_ACTIONS
from lonora_contracts.domain import utcnow
from lonora_tools.loader import load_tools
from sqlalchemy import func, select
from test_proactive_wakes import call, database, retire, simulation


async def raw(fixture: Any, method: str, path: str, body: Any = None) -> tuple[int, Any]:
    response = await fixture.client.request(method, "/api" + path, json=body)
    return response.status_code, response.json()


async def cards(fixture: Any, thread_id: str) -> list[dict[str, Any]]:
    status, body = await raw(fixture, "GET", "/owner-actions?thread_id=" + thread_id)
    assert status == 200, body
    return cast(list[dict[str, Any]], body)


@pytest.mark.asyncio
async def test_an_expired_approval_is_never_executed_and_renew_only_asks_again() -> None:
    database()
    from check_streaming import Fixture
    from lonora_db.schema import RunRow, TradeApprovalRow, TradingJournalRow
    from lonora_db.trade_approvals import APPROVAL_LIFETIME

    fixture = await Fixture().open()
    db = fixture.runtime.db
    connection = ""
    try:
        connection = await simulation(fixture, [])
        agent = await fixture.agent("Ask me", supervised=True)
        thread = await fixture.conversation(agent)
        context = await fixture.lease(await fixture.run(agent, thread))
        entry = {
            "action": "buy",
            "account_id": connection,
            "symbol": "XAUUSD",
            "volume": "0.1",
            "stop_loss": "95",
        }
        tool_call = ToolCall(id="buy-" + uuid4().hex, name="trade_execute", arguments=entry)
        registry = load_tools()
        asked = await registry.execute(tool_call, context)
        assert asked.get("_runtime_wait") and asked.get("approval_id"), asked
        approval_id = asked["approval_id"]
        async with db.sessions() as session, session.begin():
            row = await session.get(TradeApprovalRow, approval_id, with_for_update=True)
            assert row is not None and row.expires_at is not None
            assert row.expires_at - row.created_at == APPROVAL_LIFETIME
            # Its lifetime ends unapproved.
            row.expires_at = utcnow() - timedelta(seconds=1)
        status, refused = await raw(
            fixture, "POST", f"/trading/approvals/{approval_id}/decision", {"decision": "approve"}
        )
        assert (status, refused["code"]) == (409, "trade_approval_expired"), refused
        status, listed = await raw(fixture, "GET", "/trading/approvals?thread_id=" + thread["id"])
        card = next(item for item in listed if item["id"] == approval_id)
        assert card["status"] == "expired" and card["expires_at"], card
        # The same call, woken again, sends nothing: the card expired unapproved.
        again = await registry.execute(tool_call, context)
        assert again["code"] == "trade_approval_expired" and again["status"] == "expired", again
        async with db.sessions() as session:
            sent = await session.scalar(
                select(func.count())
                .select_from(TradingJournalRow)
                .where(TradingJournalRow.account_id == connection)
            )
            approvals = await session.scalar(
                select(func.count())
                .select_from(TradeApprovalRow)
                .where(TradeApprovalRow.thread_id == thread["id"])
            )
        assert sent == 0
        # «طلب جديد» asks the same agent again in the same conversation; no card is made.
        status, renewed = await raw(fixture, "POST", f"/trading/approvals/{approval_id}/renew")
        assert status == 200, renewed
        assert renewed["agent_id"] == agent["id"] and renewed["thread_id"] == thread["id"]
        status, repeated = await raw(fixture, "POST", f"/trading/approvals/{approval_id}/renew")
        assert status == 200 and repeated["id"] == renewed["id"]
        async with db.sessions() as session:
            run = await session.get(RunRow, renewed["id"])
            assert run is not None and run.trigger == "owner_card"
            assert approval_id in run.prompt and "trade_execute" in run.prompt
            assert run.model_metadata["renews_trade_approval_id"] == approval_id
            after = await session.scalar(
                select(func.count())
                .select_from(TradeApprovalRow)
                .where(TradeApprovalRow.thread_id == thread["id"])
            )
            stored = await session.get(TradeApprovalRow, approval_id)
        assert after == approvals and stored is not None and stored.status == "expired"
        # A card still waiting is answered, not renewed.
        fresh = await call(context, "trade_execute", **{**entry, "volume": "0.2"})
        status, refused = await raw(
            fixture, "POST", f"/trading/approvals/{fresh['approval_id']}/renew"
        )
        assert (status, refused["code"]) == (409, "trade_approval_not_renewable"), refused
        async with db.sessions() as session, session.begin():
            for item in await session.scalars(
                select(RunRow).where(RunRow.id == renewed["id"], RunRow.status == "queued")
            ):
                item.status = "cancelled"
    finally:
        await retire(fixture, connection)
        await fixture.close()


@pytest.mark.asyncio
async def test_an_agents_watch_extension_has_one_use_undo_the_owners_extend_has_none() -> None:
    database()
    from check_streaming import Fixture
    from lonora_db.schema import MarketWatchRow

    fixture = await Fixture().open()
    connection = ""
    try:
        connection = await simulation(fixture, [])
        agent = await fixture.agent("Watcher")
        thread = await fixture.conversation(agent)
        context = await fixture.lease(await fixture.run(agent, thread))
        start = (utcnow() + timedelta(hours=1)).replace(microsecond=0)
        watch = await call(
            context,
            "watch_create",
            account_id=connection,
            symbol="XAUUSD",
            kind="price",
            condition="below",
            level="90",
            prompt="Re-check gold below 90",
            expires_at=start.isoformat(),
        )

        async def expiry() -> datetime:
            async with fixture.runtime.db.sessions() as session:
                row = await session.get(MarketWatchRow, watch["id"])
                assert row is not None
                return datetime.fromisoformat(str(row.payload["expires_at"]))

        def notices() -> Any:
            return [item for item in shown if item["kind"] == "watch_changed"]

        await call(
            context,
            "watch_update",
            watch_id=watch["id"],
            expires_at=(start + timedelta(hours=2)).isoformat(),
        )
        shown = await cards(fixture, thread["id"])
        [first] = notices()
        assert first["status"] == "pending" and first["requires_passkey"] is False
        assert first["facts"]["watch"]["active"] is True
        assert first["facts"]["watch"]["symbol"] == "XAUUSD"
        assert datetime.fromisoformat(first["facts"]["watch"]["previous_expires_at"]) == start
        # Moved earlier: no notice, and the extension it changed can no longer be undone.
        await call(
            context,
            "watch_update",
            watch_id=watch["id"],
            expires_at=(start + timedelta(hours=1)).isoformat(),
        )
        shown = await cards(fixture, thread["id"])
        assert len(notices()) == 1 and notices()[0]["facts"]["watch"]["active"] is False
        status, stale = await raw(
            fixture, "POST", f"/owner-actions/{first['id']}/decision", {"decision": "confirm"}
        )
        assert status == 200 and stale["status_reason"] == "watch_changed_again", stale
        assert await expiry() == start + timedelta(hours=1)
        # Extended again: a fresh notice; Undo restores the expiry before it, once.
        await call(
            context,
            "watch_update",
            watch_id=watch["id"],
            expires_at=(start + timedelta(hours=5)).isoformat(),
        )
        shown = await cards(fixture, thread["id"])
        latest = next(item for item in notices() if item["status"] == "pending")
        status, undone = await raw(
            fixture, "POST", f"/owner-actions/{latest['id']}/decision", {"decision": "confirm"}
        )
        assert status == 200 and undone["status"] == "confirmed", undone
        assert undone["result"]["undone"] is True
        assert await expiry() == start + timedelta(hours=1)
        status, repeated = await raw(
            fixture, "POST", f"/owner-actions/{latest['id']}/decision", {"decision": "confirm"}
        )
        assert status == 200 and repeated["status"] == "confirmed"
        assert await expiry() == start + timedelta(hours=1)
        # The owner's «تمديد ساعتين»: two hours later, no notice (the owner did it).
        status, extended = await raw(
            fixture, "POST", f"/watches/{watch['id']}/control", {"action": "extend", "hours": 2}
        )
        assert status == 200, extended
        assert await expiry() == start + timedelta(hours=3)
        shown = await cards(fixture, thread["id"])
        assert len(notices()) == 2
        for body in (
            {"action": "extend"},
            {"action": "extend", "hours": 0},
            {"action": "extend", "hours": 25},
            {"action": "pause", "hours": 2},
        ):
            status, _ = await raw(fixture, "POST", f"/watches/{watch['id']}/control", body)
            assert status == 422, body
        # The owner's own new watch goes through the same watch service.
        status, created = await raw(
            fixture,
            "POST",
            "/watches",
            {
                "agent_id": agent["id"],
                "thread_id": thread["id"],
                "payload": {
                    "account_id": connection,
                    "symbol": "XAUUSD",
                    "kind": "price",
                    "condition": "below",
                    "level": "2330",
                    "prompt": "XAUUSD below 2330",
                    "expires_at": (utcnow() + timedelta(hours=4)).isoformat(),
                },
            },
        )
        assert status == 201 and created["agent_id"] == agent["id"], created
        assert created["thread_id"] == thread["id"]
    finally:
        await retire(fixture, connection)
        await fixture.close()


@pytest.mark.asyncio
async def test_the_mandate_draft_grants_only_what_the_owner_signs() -> None:
    database()
    from check_streaming import Fixture
    from device_fixture import Device
    from lonora_contracts.owner_actions import GrantDraft
    from lonora_db.owner_actions import grant_proposal
    from lonora_db.schema import AccountAuthorityRow, OwnerActionRow

    fixture = await Fixture().open()
    db = fixture.runtime.db
    connection = ""
    try:
        held = Position(
            id="held-ticket",
            symbol="XAUUSD",
            side="buy",
            volume=Decimal("0.1"),
            open_price=Decimal(100),
            stop_loss=Decimal(95),
        )
        connection = await simulation(fixture, [held])

        async def trading_agent(name: str, scope: str) -> dict[str, Any]:
            agent = await fixture.request(
                "POST",
                "/agents",
                {
                    "name": name + " " + uuid4().hex[:6],
                    "scope_mode": scope,
                    "trading_account_id": connection,
                    "trading_symbol": "XAUUSD",
                },
            )
            fixture.agents.append(agent["id"])
            return agent

        async def level(agent_id: str) -> str:
            return (await fixture.request("GET", f"/agents/{agent_id}/permissions"))[
                "effective_level"
            ]

        async def active(agent_id: str) -> list[AccountAuthorityRow]:
            async with db.sessions() as session:
                return list(
                    await session.scalars(
                        select(AccountAuthorityRow).where(
                            AccountAuthorityRow.agent_id == agent_id,
                            AccountAuthorityRow.status == "active",
                        )
                    )
                )

        async def sign(card_id: str, device: Device, **choices: Any) -> dict[str, Any]:
            challenge = await fixture.request("POST", f"/owner-actions/{card_id}/challenge", {})
            async with db.sessions() as session:
                stored = await session.get(OwnerActionRow, card_id)
                assert stored is not None
                pending = await session.get(AccountAuthorityRow, stored.result["authority_id"])
                assert pending is not None
                # The passkey signs exactly the envelope built from the stored draft.
                expected = grant_proposal(GrantDraft.model_validate(stored.payload), "x")
                for name in ("symbol_scope", "symbols", "actions", "allow_manual_positions"):
                    assert pending.envelope[name] == expected.model_dump(mode="json")[name], name
                assert pending.envelope["management_mode"] == "full"
            status, decided = await raw(
                fixture,
                "POST",
                f"/owner-actions/{card_id}/decision",
                {
                    "decision": "confirm",
                    "proof": device.assertion(challenge, fixture.settings.allowed_origin),
                    **choices,
                },
            )
            assert status == 200 and decided["status"] == "confirmed", decided
            return cast(dict[str, Any], decided)

        fixed = await trading_agent("Gold fixed", "fixed_market")
        fixed_thread = await fixture.conversation(fixed)
        before = await level(fixed["id"])
        # «كامل» for a fixed-pair agent: its own pair only, every action, until stopped,
        # the owner's own positions included (Q17).
        status, drafted = await raw(
            fixture,
            "POST",
            f"/agents/{fixed['id']}/account-authorities/draft",
            {"mode": "full", "thread_id": fixed_thread["id"]},
        )
        assert status == 201, drafted
        card = drafted["owner_action"]
        assert card["kind"] == "grant_authority" and card["source"] == "owner"
        assert card["thread_id"] == fixed_thread["id"] and card["requires_passkey"] is True
        assert drafted["payload_hash"] and drafted["payload"]["symbols"] == ["XAUUSD"]
        grant = card["facts"]["grant"]
        assert (grant["symbol_scope"], grant["symbols"]) == ("selected", ["XAUUSD"])
        assert grant["all_actions"] and grant["duration"] == "until_stopped"
        assert grant["allow_manual_positions"] is True and grant["full_available"] is False
        # Unsigned, it grants nothing; confirming without the passkey is refused.
        assert await active(fixed["id"]) == [] and await level(fixed["id"]) == before
        status, refused = await raw(
            fixture, "POST", f"/owner-actions/{card['id']}/decision", {"decision": "confirm"}
        )
        assert (status, refused["code"]) == (403, "owner_action_passkey_required"), refused
        assert await active(fixed["id"]) == []
        status, same = await raw(
            fixture,
            "POST",
            f"/agents/{fixed['id']}/account-authorities/draft",
            {"mode": "full", "thread_id": fixed_thread["id"]},
        )
        assert status == 201 and same["owner_action"]["id"] == card["id"]
        # A custom draft for the same agent replaces the pending one (عرض الأحدث).
        status, custom = await raw(
            fixture,
            "POST",
            f"/agents/{fixed['id']}/account-authorities/draft",
            {"thread_id": fixed_thread["id"], "actions": ["close_position"], "duration": "24h"},
        )
        assert status == 201, custom
        replaced = next(
            item for item in await cards(fixture, fixed_thread["id"]) if item["id"] == card["id"]
        )
        assert replaced["status"] == "superseded"
        assert replaced["superseded_by"] == custom["owner_action"]["id"]
        device = await Device.enroll(fixture)
        await sign(custom["owner_action"]["id"], device)
        [signed] = await active(fixed["id"])
        # The grant is exactly the draft: closing only, on its pair, for 24 hours.
        assert signed.envelope["actions"] == ["close_position"]
        assert signed.envelope["symbols"] == ["XAUUSD"] and signed.valid_until is not None
        assert await level(fixed["id"]) == "autonomous"

        # Another agent on the same pair: the conflict is shown and «إيقاف الوكيل الآخر»
        # ends only that agent's grant, it never widens anything for it.
        flexible = await trading_agent("Gold flexible", "flexible")
        flexible_thread = await fixture.conversation(flexible)
        status, other = await raw(
            fixture,
            "POST",
            f"/agents/{flexible['id']}/account-authorities/draft",
            {
                "thread_id": flexible_thread["id"],
                "symbols": ["XAUUSD"],
                "allow_manual_positions": True,
            },
        )
        assert status == 201, other
        conflicts = other["owner_action"]["facts"]["conflicts"]
        assert [item["authority_id"] for item in conflicts] == [signed.id]
        decided = await sign(other["owner_action"]["id"], device, stop_authorities=[signed.id])
        assert decided["result"]["stopped_authorities"] == [signed.id]
        assert await active(fixed["id"]) == []
        assert await level(fixed["id"]) != "autonomous"
        [kept] = await active(flexible["id"])
        assert kept.envelope["symbols"] == ["XAUUSD"]
        assert sorted(kept.envelope["actions"]) == sorted(ALL_AUTHORITY_ACTIONS)

        # Under its grant the agent tightens the stop: a notice, nothing to undo.
        context = await fixture.lease(await fixture.run(flexible, flexible_thread))
        moved = await call(
            context,
            "trade_execute",
            action="modify_position",
            account_id=connection,
            symbol="XAUUSD",
            position_id="held-ticket",
            stop_loss="97",
        )
        assert moved.get("authorization") == "account_authority", moved
        assert moved["status"] == "confirmed", moved
        [notice] = [
            item
            for item in await cards(fixture, flexible_thread["id"])
            if item["kind"] == "stop_tightened"
        ]
        assert notice["status"] == "confirmed" and notice["decided_via"] is None
        assert notice["facts"]["stop"] == {
            "symbol": "XAUUSD",
            "position_id": "held-ticket",
            "previous_stop_loss": "95",
            "stop_loss": "97",
        }
        status, refused = await raw(
            fixture, "POST", f"/owner-actions/{notice['id']}/decision", {"decision": "cancel"}
        )
        assert status == 409 and refused["code"] == "owner_action_already_decided"
        status, refused = await raw(fixture, "POST", f"/owner-actions/{notice['id']}/renew")
        assert (status, refused["code"]) == (409, "owner_action_not_renewable")
    finally:
        await retire(fixture, connection)
        await fixture.close()
