"""Full delegation on the grant card, on disposable PostgreSQL.

The grant card offers one choice in its own list of options: Custom (owner decision D1
defaults, selected by default) or Full delegation (every pair on the account, every
action, the owner's own positions, until stopped, no daily loss limit from the card).
Exercised end to end with the simulation broker and a scripted authenticator: the choice
is stored in the card's draft through the owner's decision route, the envelope is built
only from that stored draft, signing still needs the passkey, switching withdraws a
proposal prepared for the other choice, and the account's own execution policy (money
limits and execution caps) still refuses what breaks it under Full. An agent preselects
Full only from the owner's own message, and never for a fixed-market agent. No live
broker, MetaApi key or real order is involved.
"""

import asyncio
from decimal import Decimal
from typing import Any, cast
from uuid import uuid4

from check_streaming import Fixture
from device_fixture import Device
from lonora_adapter_kit.types import ToolCall
from lonora_adapters.brokers.simulation import SimulationBroker
from lonora_agent.context.permissions import permission_context
from lonora_contracts.domain import utcnow
from lonora_contracts.runs import RunRequest
from lonora_contracts.trading import TradingControl
from lonora_db.personal_agent import ensure_personal_agent
from lonora_db.runs import create_run, run_data
from lonora_db.schema import (
    AccountAuthorityRow,
    MessageRow,
    OwnerActionRow,
    RunRow,
    TradeApprovalRow,
    TradingAccountRow,
)
from lonora_tools.context import ToolContext
from lonora_tools.loader import load_tools
from lonora_trading.controls import read_controls, save_controls
from sqlalchemy import func, select

GOLD, EURO = "XAUUSDm", "EURUSDm"
ALL_ACTIONS = [
    "buy",
    "sell",
    "buy_limit",
    "sell_limit",
    "buy_stop",
    "sell_stop",
    "close_position",
    "modify_position",
    "cancel_order",
    "modify_order",
]


def snapshot() -> dict[str, Any]:
    return {
        "currency": "USD",
        "balance": "10000",
        "equity": "10000",
        "instruments": [
            {
                "symbol": symbol,
                "digits": 2,
                "tick_size": "0.01",
                "volume_min": "0.1",
                "volume_max": "10",
                "volume_step": "0.1",
            }
            for symbol in (GOLD, EURO)
        ],
        "quotes": {
            symbol: {
                "symbol": symbol,
                "bid": "100",
                "ask": "101",
                "observed_at": utcnow().isoformat(),
                "source": "explicit-full-delegation-fixture",
                "loss_tick_value": "1",
                "profit_tick_value": "1",
                "tick_value_basis": "account_currency_per_lot",
            }
            for symbol in (GOLD, EURO)
        },
        "positions": [
            {
                "id": "manual-ticket",
                "symbol": GOLD,
                "side": "buy",
                "volume": "0.2",
                "open_price": "95",
                "stop_loss": "80",
            }
        ],
    }


async def main() -> None:
    fixture = await Fixture().open()
    db = fixture.runtime.db
    original = await read_controls(db)
    registry = load_tools()
    try:
        await save_controls(db, TradingControl(enabled=True))
        connection = await fixture.request(
            "POST",
            "/trading/connections",
            {"provider": "simulation", "account_id": "full-" + uuid4().hex, "enabled": True},
        )
        account = cast(str, connection["id"])
        await fixture.request(
            "POST", f"/trading/connections/{account}/simulation", {"snapshot": snapshot()}
        )
        services = fixture.runtime.services(fixture.owner)
        broker = cast(SimulationBroker, await services.brokers.get(fixture.owner, account))
        # The owner's own MT5 position, modelled on this disposable fixture row only.
        async with db.sessions() as session, session.begin():
            book = await session.get(TradingAccountRow, account, with_for_update=True)
            assert book is not None
            book.payload = {**book.payload, "positions": snapshot()["positions"]}
        # Money limits and an execution cap the owner set elsewhere, before any grant.
        policy_path = f"/trading/accounts/{account}/execution-policy"
        await fixture.request(
            "PUT",
            policy_path,
            {"risk": {"currency": "USD", "max_trade_risk": "50"}, "max_positions": 2},
        )

        async def raw(
            method: str, path: str, body: dict[str, Any] | None = None
        ) -> tuple[int, dict[str, Any]]:
            response = await fixture.client.request(method, "/api" + path, json=body)
            return response.status_code, response.json()

        async def call(context: ToolContext, name: str, **arguments: Any) -> dict[str, Any]:
            return await registry.execute(
                ToolCall(id=uuid4().hex, name=name, arguments=arguments), context
            )

        async def scripted_context(agent: dict[str, Any]) -> tuple[ToolContext, dict[str, Any]]:
            """A Run that answers no owner message (a scheduled wake)."""
            thread = await fixture.conversation(agent)
            async with db.sessions() as session, session.begin():
                run = await create_run(
                    session,
                    fixture.owner,
                    RunRequest(agent_id=agent["id"], thread_id=thread["id"], trigger="schedule"),
                )
                data = run_data(run)
            return await fixture.lease(data), thread

        async def owner_context(
            agent: dict[str, Any], words: str
        ) -> tuple[ToolContext, dict[str, Any]]:
            """A Run that answers the owner's own message in the agent's conversation; the
            scripted Runs before it are finished first, so the message starts its own."""
            thread = await fixture.conversation(agent)
            async with db.sessions() as session, session.begin():
                for active in await session.scalars(
                    select(RunRow)
                    .where(
                        RunRow.thread_id == thread["id"],
                        RunRow.status.in_(["queued", "leased", "running", "waiting_input"]),
                    )
                    .with_for_update()
                ):
                    active.status = "completed"
            sent = await fixture.request(
                "POST",
                f"/threads/{thread['id']}/messages",
                {"content": words, "client_nonce": "full-" + uuid4().hex},
            )
            run = {"id": sent["run_ids"][0], "agent_id": agent["id"], "thread_id": thread["id"]}
            return await fixture.lease(run), thread

        async def card(thread_id: str, card_id: str) -> dict[str, Any]:
            response = await fixture.client.get("/api/owner-actions?thread_id=" + thread_id)
            assert response.is_success, response.text
            rows = cast(list[dict[str, Any]], response.json())
            return next(row for row in rows if row["id"] == card_id)

        async def stored(card_id: str) -> OwnerActionRow:
            async with db.sessions() as session:
                row = await session.get(OwnerActionRow, card_id)
                assert row is not None
                return row

        async def choose(card_id: str, delegation: str) -> dict[str, Any]:
            status, body = await raw(
                "POST",
                f"/owner-actions/{card_id}/decision",
                {"decision": "choose", "delegation": delegation},
            )
            assert status == 200, (status, body)
            return body

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
        fixed = await fixture.request(
            "POST",
            "/agents",
            {
                "name": "Fixed " + uuid4().hex[:6],
                "scope_mode": "fixed_market",
                "trading_account_id": account,
                "trading_symbol": GOLD,
            },
        )
        fixture.agents.append(fixed["id"])

        # 1. The card opens on Custom with the D1 defaults; Full is the other choice in
        #    the same list. A Run that answers no owner message never preselects Full.
        lonora_context, lonora_thread = await scripted_context(lonora)
        proposed = await call(
            lonora_context,
            "owner_action_propose",
            kind="grant_authority",
            agent_id=gold["id"],
            delegation="full",
        )
        assert proposed["delegation"] == "custom", proposed
        assert proposed["full_delegation_not_preselected"] == "owner_message_required", proposed
        assert proposed["passkey_required"] is True and proposed["execution_authorized"] is False
        card_id = proposed["owner_action"]["id"]
        shown = await card(lonora_thread["id"], card_id)
        grant = shown["facts"]["grant"]
        assert grant["delegation"] == "custom" and grant["full_available"] is True, grant
        assert grant["symbol_scope"] == "selected" and grant["symbols"] == [GOLD], grant
        assert grant["duration"] == "until_stopped" and grant["allow_manual_positions"] is False
        daily = shown["facts"]["money"]["daily_loss"]
        assert daily["proposed"] == "300.00" and daily["basis"] == "suggested", daily
        custom_payload = (await stored(card_id)).payload
        custom_hash = (await stored(card_id)).payload_hash
        print(
            "PASS the grant card opens on Custom with the D1 defaults (focus pair, until stopped, own positions excluded, 3% daily loss); a wake never preselects Full"
        )

        # 2. Switching is the owner's decision on the card: the stored draft changes, the
        #    card settles nothing, and switching back restores Custom exactly.
        switched = await choose(card_id, "full")
        assert switched["status"] == "pending" and switched["requires_passkey"] is True
        full = switched["facts"]["grant"]
        assert full["delegation"] == "full" and full["symbol_scope"] == "account", full
        assert full["symbols"] == [] and full["all_actions"] is True, full
        assert full["duration"] == "until_stopped" and full["allow_manual_positions"] is True
        assert switched["facts"]["money"]["daily_loss"]["proposed"] is None
        row = await stored(card_id)
        assert row.payload["delegation"] == "full" and row.payload["daily_loss"] is None
        assert row.payload["custom"]["symbols"] == [GOLD], row.payload
        assert row.payload_hash != custom_hash
        back = await choose(card_id, "custom")
        assert back["facts"]["grant"]["delegation"] == "custom"
        assert back["facts"]["money"]["daily_loss"]["proposed"] == "300.00"
        row = await stored(card_id)
        assert row.payload == custom_payload and row.payload_hash == custom_hash
        again = await choose(card_id, "custom")
        assert again["updated_at"] == back["updated_at"], "a repeated choice changed the card"
        await choose(card_id, "full")
        # Only the owner's session reaches the choice; a tool never does.
        status, refused = await raw(
            "POST", f"/owner-actions/{card_id}/decision", {"decision": "choose"}
        )
        assert status == 422 and refused["code"] == "owner_action_delegation_required", refused
        print(
            "PASS the owner switches Custom and Full on the card through the decision route: the stored draft follows, back and forth, and nothing is signed"
        )

        # 3. Full still needs the passkey ceremony, and the envelope comes only from the
        #    stored draft: every pair, every action, own positions, no expiry, no caps.
        status, refused = await raw(
            "POST", f"/owner-actions/{card_id}/decision", {"decision": "confirm"}
        )
        assert status == 403 and refused["code"] == "owner_action_passkey_required", refused
        # A screen that still shows Custom (another screen chose Full, or the answer to
        # that choice was lost) never signs Full: its challenge names Custom, or sends the
        # own-positions switch only Custom shows, and is refused before anything is
        # prepared; the card is read again instead.
        for stale in (
            {"delegation": "custom", "allow_manual_positions": True},
            {"delegation": "custom", "allow_manual_positions": False},
            {"delegation": "custom"},
            {"allow_manual_positions": True},
            {"allow_manual_positions": False},
        ):
            status, refused = await raw("POST", f"/owner-actions/{card_id}/challenge", stale)
            assert status == 409, (stale, status, refused)
            assert refused["code"] == "owner_action_card_changed", (stale, refused)
        assert (await stored(card_id)).result == {}, "a stale challenge prepared a grant"
        # A screen showing Full shows no own-positions switch, so it sends none.
        status, refused = await raw(
            "POST",
            f"/owner-actions/{card_id}/challenge",
            {"delegation": "full", "allow_manual_positions": False},
        )
        assert status == 422, (status, refused)
        assert refused["code"] == "owner_action_full_delegation_terms_fixed", refused
        status, refused = await raw(
            "POST", f"/owner-actions/{card_id}/challenge", {"delegation": "full"}
        )
        assert status == 409 and refused["code"] == "device_registration_required", refused
        device = await Device.enroll(fixture)
        challenge = await fixture.request(
            "POST", f"/owner-actions/{card_id}/challenge", {"delegation": "full"}
        )
        gold_thread = await fixture.conversation(gold)
        async with db.sessions() as session:
            prepared_id = (await stored(card_id)).result["authority_id"]
            prepared = await session.get(AccountAuthorityRow, prepared_id)
            assert prepared is not None and prepared.status == "pending"
            envelope = prepared.envelope
        assert envelope["symbol_scope"] == "account" and envelope["symbols"] == [], envelope
        assert sorted(envelope["actions"]) == sorted(ALL_ACTIONS), envelope
        assert envelope["valid_until"] is None and envelope["allow_manual_positions"] is True
        assert envelope["management_mode"] == "full"
        assert all(
            envelope[name] is None
            for name in (
                "maximum_order_volume",
                "maximum_symbol_volume",
                "maximum_positions",
                "maximum_pending_orders",
                "maximum_actions",
                "minimum_equity",
            )
        ), envelope
        composer = await fixture.request(
            "POST",
            f"/agents/{gold['id']}/account-authorities",
            {
                "thread_id": gold_thread["id"],
                "account_id": account,
                "management_mode": "full",
                "symbol_scope": "account",
                "symbols": [],
                "actions": ALL_ACTIONS,
                "valid_until": None,
                "allow_manual_positions": True,
            },
        )
        # The permission composer's identical proposal is the very same pending envelope.
        assert composer["id"] == prepared_id, (composer["id"], prepared_id)
        print(
            "PASS a screen still showing Custom never signs Full (owner_action_card_changed, nothing prepared); Full needs the same passkey (enrolling first) and signs an account-wide envelope with every action, own positions, no expiry and no caps"
        )

        # 4. Switching after a challenge withdraws the proposal prepared for the other
        #    choice: a proof for it never confirms the card. A screen that still shows
        #    Full is refused the other way round, and prepares nothing.
        await choose(card_id, "custom")
        async with db.sessions() as session:
            withdrawn = await session.get(AccountAuthorityRow, prepared_id)
            assert withdrawn is not None and withdrawn.status == "revoked"
        status, refused = await raw(
            "POST", f"/owner-actions/{card_id}/challenge", {"delegation": "full"}
        )
        assert status == 409 and refused["code"] == "owner_action_card_changed", refused
        assert (await stored(card_id)).result == {}, "a stale challenge prepared a grant"
        status, refused = await raw(
            "POST",
            f"/owner-actions/{card_id}/decision",
            {
                "decision": "confirm",
                "proof": device.assertion(challenge, fixture.settings.allowed_origin),
            },
        )
        assert status == 409 and refused["code"] == "owner_action_challenge_required", refused
        assert (await card(lonora_thread["id"], card_id))["status"] == "pending"
        print(
            "PASS switching the choice withdraws a prepared proposal; its proof signs nothing, and a screen still showing the other choice is refused"
        )

        # 5. The owner signs Full: the grant is active, the card set no daily loss limit
        #    and the account's own limits stay exactly as they were, including a daily
        #    loss limit he set elsewhere before signing.
        await fixture.request(
            "PUT",
            policy_path,
            {
                "risk": {"currency": "USD", "max_trade_risk": "50", "max_daily_loss": "100"},
                "max_positions": 2,
            },
        )
        await choose(card_id, "full")
        challenge = await fixture.request(
            "POST", f"/owner-actions/{card_id}/challenge", {"delegation": "full"}
        )
        status, decided = await raw(
            "POST",
            f"/owner-actions/{card_id}/decision",
            {
                "decision": "confirm",
                "proof": device.assertion(challenge, fixture.settings.allowed_origin),
                # A Custom opt-out left over from before the switch means nothing here.
                "money_limit": "none",
            },
        )
        assert status == 200 and decided["status"] == "confirmed", decided
        assert decided["decided_via"] == "passkey"
        assert decided["result"]["money_limit"] == "apply", decided["result"]
        assert decided["result"]["delegation"] == "full" and decided["result"]["daily_loss"] is None
        assert Decimal(decided["result"]["daily_loss_kept"]) == 100, decided["result"]
        assert decided["facts"]["grant"]["delegation"] == "full"
        assert decided["facts"]["grant"]["allow_manual_positions"] is True
        assert Decimal(decided["facts"]["money"]["daily_loss"]["current"]) == 100
        policy = await fixture.request("GET", policy_path)
        assert Decimal(policy["risk"]["max_daily_loss"]) == 100, policy
        assert Decimal(policy["risk"]["max_trade_risk"]) == 50 and policy["max_positions"] == 2
        async with db.sessions() as session:
            active = list(
                await session.scalars(
                    select(AccountAuthorityRow).where(
                        AccountAuthorityRow.agent_id == gold["id"],
                        AccountAuthorityRow.status == "active",
                    )
                )
            )
            assert len(active) == 1 and active[0].envelope["symbol_scope"] == "account"
            line = await session.scalar(
                select(MessageRow)
                .where(MessageRow.thread_id == lonora_thread["id"], MessageRow.role == "assistant")
                .order_by(MessageRow.seq.desc())
                .limit(1)
            )
            assert line is not None
            assert "Full delegation" in line.content or "تفويض كامل" in line.content, line.content
            assert "passkey" in line.content or "مفتاح المرور" in line.content, line.content
            assert "As you chose" not in line.content and "كما اخترت" not in line.content
        print(
            "PASS signing Full activates the account-wide grant with one passkey tap; no daily loss limit came from the card and the account's limits, its daily loss limit included, are unchanged"
        )

        # 6. The status line and the permission frame show Full delegation.
        state = await fixture.request("GET", f"/agents/{gold['id']}/state")
        readiness = state["trading_readiness"]
        assert readiness["state"] == "on_its_own", readiness
        assert readiness["params"]["full_delegation"] is True, readiness["params"]
        assert readiness["params"]["symbol_scope"] == "account"
        assert readiness["grants"][0]["full_delegation"] is True, readiness["grants"]
        assert readiness["grants"][0]["allow_manual_positions"] is True
        async with db.sessions() as session:
            frame = await permission_context(session, fixture.owner, gold["id"])
        assert '"full_delegation": true' in frame, frame
        assert "full_delegation scope covers every pair" in frame
        print("PASS the readiness line and the permission frame say Full delegation")

        # 7. Under Full the agent trades any pair and manages the owner's own position
        #    with no card, while the account's money limit and position cap still refuse.
        gold_context, _ = await scripted_context(gold)
        before = await broker.snapshot()
        over = await call(
            gold_context,
            "trade_execute",
            action="buy",
            account_id=account,
            symbol=EURO,
            volume="0.1",
            stop_loss="90",
        )
        # Ask 101 to a 90 stop: 1100 ticks * 1 per lot * 0.1 lot = 110 > the 50 limit.
        assert over.get("status") == "failed" and over.get("code") == "risk_trade_limit", over
        assert await broker.snapshot() == before
        entry = await call(
            gold_context,
            "trade_execute",
            action="buy",
            account_id=account,
            symbol=EURO,
            volume="0.1",
            stop_loss="99.6",
        )
        assert entry.get("status") == "confirmed", entry
        assert entry.get("authorization") == "account_authority", entry
        before = await broker.snapshot()
        capped = await call(
            gold_context,
            "trade_execute",
            action="buy",
            account_id=account,
            symbol=GOLD,
            volume="0.1",
            stop_loss="99.6",
        )
        # The owner's max_positions 2 (their own position and the euro entry) still holds.
        assert capped.get("status") != "confirmed" and not capped.get("_runtime_wait"), capped
        assert "portfolio_position_limit" in str(capped), capped
        assert await broker.snapshot() == before
        tightened = await call(
            gold_context,
            "trade_execute",
            action="modify_position",
            account_id=account,
            symbol=GOLD,
            position_id="manual-ticket",
            stop_loss="85",
        )
        assert tightened.get("status") == "confirmed", tightened
        assert tightened.get("authorization") == "account_authority", tightened
        closed = await call(
            gold_context,
            "trade_execute",
            action="close_position",
            account_id=account,
            symbol=GOLD,
            position_id="manual-ticket",
        )
        assert closed.get("status") == "confirmed", closed
        assert closed.get("authorization") == "account_authority", closed
        async with db.sessions() as session:
            asked = await session.scalar(
                select(func.count())
                .select_from(TradeApprovalRow)
                .where(TradeApprovalRow.run_id == gold_context.lease.run_id)
            )
            assert asked == 0, asked
        # A losing day: the daily loss limit the owner set elsewhere refuses new risk under
        # Full, while closing what is open is still allowed.
        async with db.sessions() as session, session.begin():
            book = await session.get(TradingAccountRow, account, with_for_update=True)
            assert book is not None
            fresh = snapshot()["quotes"]
            book.payload = {
                **book.payload,
                "quotes": fresh,
                "history": [
                    *book.payload.get("history", []),
                    {"time": utcnow().isoformat(), "type": "DEAL_TYPE_SELL", "profit": "-1000"},
                ],
            }
        before = await broker.snapshot()
        # Not the refused entry above again (the same request in one Run replays its
        # result): 0.2 lot to a 99.6 stop risks 28, inside the per-trade limit of 50.
        losing = await call(
            gold_context,
            "trade_execute",
            action="buy",
            account_id=account,
            symbol=GOLD,
            volume="0.2",
            stop_loss="99.6",
        )
        assert losing.get("status") == "failed", losing
        assert losing.get("code") == "risk_daily_loss_limit", losing
        assert await broker.snapshot() == before
        euro = next(item for item in before["positions"] if item["symbol"] == EURO)
        exit_trade = await call(
            gold_context,
            "trade_execute",
            action="close_position",
            account_id=account,
            symbol=EURO,
            position_id=euro["id"],
        )
        assert exit_trade.get("status") == "confirmed", exit_trade
        print(
            "PASS under Full the agent trades another pair and manages the owner's own position with no card; the account's per-trade risk limit, position cap and daily loss limit still refuse, and exits stay allowed"
        )

        # 8. From the owner's own message, Lonora preselects Full; the owner still
        #    chooses and signs. A fixed-market agent is never offered Full.
        silver = await fixture.request(
            "POST",
            "/agents",
            {
                "name": "Silver " + uuid4().hex[:6],
                "scope_mode": "flexible",
                "trading_account_id": account,
                "trading_symbol": EURO,
            },
        )
        fixture.agents.append(silver["id"])
        asked_context, asked_thread = await owner_context(
            lonora, "فوّض وكيل الفضة تفويضًا كاملًا على حسابي"
        )
        preselected = await call(
            asked_context,
            "owner_action_propose",
            kind="grant_authority",
            agent_id=silver["id"],
            delegation="full",
        )
        assert preselected["delegation"] == "full", preselected
        assert "full_delegation_not_preselected" not in preselected
        silver_card = preselected["owner_action"]["id"]
        shown = await card(asked_thread["id"], silver_card)
        assert shown["status"] == "pending" and shown["facts"]["grant"]["delegation"] == "full"
        # The other agent already trading on its own here is named, as on every card.
        assert [item["agent_name"] for item in shown["facts"]["conflicts"]] == [gold["name"]]
        # The owner still chooses: Custom restores the Custom draft the server resolved.
        restored = await choose(silver_card, "custom")
        assert restored["facts"]["grant"]["symbols"] == [EURO], restored["facts"]["grant"]
        assert restored["facts"]["grant"]["allow_manual_positions"] is False
        await fixture.request(
            "POST", f"/owner-actions/{silver_card}/decision", {"decision": "cancel"}
        )
        # The server reads the owner's words itself: a message that asks only for trading
        # opens the card on Custom whatever the model passes.
        plain_context, plain_thread = await owner_context(lonora, "تداول الفضة عني من الآن")
        plain = await call(
            plain_context,
            "owner_action_propose",
            kind="grant_authority",
            agent_id=silver["id"],
            delegation="full",
        )
        assert plain["delegation"] == "custom", plain
        assert plain["full_delegation_not_preselected"] == "owner_did_not_ask_full_delegation"
        plain_card = plain["owner_action"]["id"]
        assert (await card(plain_thread["id"], plain_card))["facts"]["grant"][
            "delegation"
        ] == "custom"
        await fixture.request(
            "POST", f"/owner-actions/{plain_card}/decision", {"decision": "cancel"}
        )
        # Full delegation with a daily loss the owner named: Full sets no daily loss limit,
        # so the result says the limit needs its own card (Custom still carries it).
        limited_context, _ = await owner_context(
            lonora, "Give the silver agent full delegation with a 2% daily loss limit"
        )
        limited = await call(
            limited_context,
            "owner_action_propose",
            kind="grant_authority",
            agent_id=silver["id"],
            delegation="full",
            daily_loss_percent="2",
        )
        assert limited["delegation"] == "full", limited
        assert limited["requested_daily_loss_needs_limits_card"] is True, limited
        limited_row = await stored(limited["owner_action"]["id"])
        assert limited_row.payload["daily_loss"] is None, limited_row.payload
        assert limited_row.payload["custom"]["daily_loss"]["basis"] == "requested"
        assert Decimal(limited_row.payload["custom"]["daily_loss"]["percent"]) == 2
        await fixture.request(
            "POST",
            f"/owner-actions/{limited['owner_action']['id']}/decision",
            {"decision": "cancel"},
        )
        fixed_context, fixed_thread = await owner_context(
            lonora, "Give the fixed agent full delegation on my account"
        )
        offered = await call(
            fixed_context,
            "owner_action_propose",
            kind="grant_authority",
            agent_id=fixed["id"],
            delegation="full",
        )
        assert offered["delegation"] == "custom", offered
        assert offered["full_delegation_not_preselected"] == "fixed_market_agent", offered
        fixed_card = offered["owner_action"]["id"]
        assert (await card(fixed_thread["id"], fixed_card))["facts"]["grant"][
            "full_available"
        ] is False
        status, refused = await raw(
            "POST",
            f"/owner-actions/{fixed_card}/decision",
            {"decision": "choose", "delegation": "full"},
        )
        assert status == 409, (status, refused)
        assert refused["code"] == "owner_action_full_delegation_unavailable", refused
        print(
            "PASS from the owner's own words (checked by the server) Lonora preselects Full and the owner still chooses; a daily loss he named is flagged as needing its own card; a fixed-market agent is never offered Full"
        )

        # 9. Nothing changes for grants already signed, or for a card stored before the
        #    choice existed: it reads and signs as Custom.
        async with db.sessions() as session, session.begin():
            legacy = await session.get(OwnerActionRow, fixed_card, with_for_update=True)
            assert legacy is not None
            legacy.payload = {
                key: value
                for key, value in legacy.payload.items()
                if key not in {"delegation", "custom"}
            }
        legacy_card = await card(fixed_thread["id"], fixed_card)
        assert legacy_card["facts"]["grant"]["delegation"] == "custom", legacy_card
        assert legacy_card["facts"]["grant"]["symbols"] == [GOLD]
        async with db.sessions() as session:
            signed = await session.get(AccountAuthorityRow, active[0].id)
            assert signed is not None and signed.status == "active"
            assert signed.envelope == active[0].envelope
        print("PASS a card stored before the choice reads as Custom; signed grants stay as signed")
    finally:
        await save_controls(db, original)
        await fixture.close()


if __name__ == "__main__":
    asyncio.run(main())
