"""One-sentence delegation and a monotonic ladder on disposable PostgreSQL (W15-3).

Exercises the grant card end to end with the simulation broker and a scripted
authenticator: the agent tool proposes a server-resolved draft (owner decision D1
defaults), the card's challenge builds the same envelope the permission composer does,
the owner's passkey activates it, and the card's own choices set the
daily loss limit and stop another agent's overlapping grant. Under "On its own" a trade
the grant does not cover becomes an approval card, never a refusal; repeating it reuses
that approval. It also covers the new ladder defaults, the explicit-level migration and
the passkey for raising a money limit through the execution-policy route. No live broker,
MetaApi key or real order is involved.
"""

import asyncio
import subprocess
import sys
from decimal import Decimal
from pathlib import Path
from typing import Any, cast
from uuid import uuid4

from check_streaming import Fixture
from device_fixture import Device
from lonora_adapter_kit.types import ToolCall
from lonora_adapters.brokers.simulation import SimulationBroker
from lonora_contracts.domain import AgentCreate, utcnow
from lonora_core.user_error import LonoraError
from lonora_db.agent_permissions import permission_key
from lonora_db.agents import create_agent
from lonora_db.personal_agent import ensure_personal_agent
from lonora_db.schema import (
    AccountAuthorityRow,
    MessageRow,
    OwnerActionRow,
    SettingRow,
    ThreadRow,
    TradeApprovalRow,
    TradingAccountRow,
)
from lonora_tools.context import ToolContext
from lonora_tools.loader import load_tools
from sqlalchemy import func, select

ROOT = Path(__file__).resolve().parents[1]
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
                "source": "explicit-grant-card-fixture",
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


async def alembic(action: str, revision: str) -> None:
    await asyncio.to_thread(
        subprocess.run,
        [sys.executable, "-m", "alembic", "-c", "packages/db/alembic.ini", action, revision],
        check=True,
        cwd=ROOT,
        stdout=subprocess.DEVNULL,
    )


async def main() -> None:
    fixture = await Fixture().open()
    db = fixture.runtime.db
    registry = load_tools()
    try:
        connection = await fixture.request(
            "POST",
            "/trading/connections",
            {"provider": "simulation", "account_id": "grant-" + uuid4().hex, "enabled": True},
        )
        account = cast(str, connection["id"])
        await fixture.request(
            "POST", f"/trading/connections/{account}/simulation", {"snapshot": snapshot()}
        )
        services = fixture.runtime.services(fixture.owner)
        broker = cast(SimulationBroker, await services.brokers.get(fixture.owner, account))
        # Snapshot import starts an empty ledger; model the owner's own MT5 position by
        # updating only this disposable fixture row.
        async with db.sessions() as session, session.begin():
            book = await session.get(TradingAccountRow, account, with_for_update=True)
            assert book is not None
            book.payload = {**book.payload, "positions": snapshot()["positions"]}

        async def raw(
            method: str, path: str, body: dict[str, Any] | None = None
        ) -> tuple[int, dict[str, Any]]:
            response = await fixture.client.request(method, "/api" + path, json=body)
            return response.status_code, response.json()

        async def level(agent_id: str) -> str:
            state = await fixture.request("GET", f"/agents/{agent_id}/permissions")
            return cast(str, state["effective_level"])

        async def context_for(agent: dict[str, Any]) -> tuple[ToolContext, dict[str, Any]]:
            thread = await fixture.conversation(agent)
            return await fixture.lease(await fixture.run(agent, thread)), thread

        async def call(context: ToolContext, name: str, **arguments: Any) -> dict[str, Any]:
            return await registry.execute(
                ToolCall(id=uuid4().hex, name=name, arguments=arguments), context
            )

        async def cards(thread_id: str) -> list[dict[str, Any]]:
            response = await fixture.client.get("/api/owner-actions?thread_id=" + thread_id)
            assert response.is_success, response.text
            return cast(list[dict[str, Any]], response.json())

        async def card(thread_id: str, card_id: str) -> dict[str, Any]:
            return next(row for row in await cards(thread_id) if row["id"] == card_id)

        # 1. Ladder defaults: Lonora and a trading agent start at Ask me; a general agent
        #    and a delegated helper start at No trading, and a helper can never trade.
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
        general = await fixture.request(
            "POST", "/agents", {"name": "Research " + uuid4().hex[:6], "scope_mode": "flexible"}
        )
        fixture.agents.append(general["id"])
        async with db.sessions() as session, session.begin():
            helper = await create_agent(
                session, fixture.owner, AgentCreate(name="Helper"), parent_id=general["id"]
            )
            helper_id = helper.id
        fixture.agents.append(helper_id)
        assert await level(lonora_id) == "supervised"
        assert await level(gold["id"]) == "supervised"
        assert await level(general["id"]) == "analysis"
        assert await level(helper_id) == "analysis"
        helper_state = await fixture.request("GET", f"/agents/{helper_id}/permissions")
        status, refused = await raw(
            "PUT",
            f"/agents/{helper_id}/permissions",
            {"level": "supervised", "expected_revision": helper_state["revision"]},
        )
        assert status == 403 and refused["code"] == "delegated_financial_authority_forbidden"
        # Editing a focus pair never moves an agent on the ladder.
        before = await fixture.request("GET", "/agents/" + general["id"])
        await fixture.request(
            "PATCH",
            "/agents/" + general["id"],
            {
                "scope_mode": "flexible",
                "trading_account_id": account,
                "trading_symbol": EURO,
                "expected_scope_revision": before["scope_revision"],
            },
        )
        assert await level(general["id"]) == "analysis"
        print(
            "PASS Lonora and trading agents start at Ask me, others at No trading; a helper never trades and a focus edit keeps the level"
        )

        # 2. One sentence: Lonora proposes the grant card for the gold agent with the
        #    owner's 2% daily loss; the server resolves the account, pair and D1 defaults.
        lonora_context, lonora_thread = await context_for(lonora)
        gold_context, gold_thread = await context_for(gold)
        proposed = await call(
            lonora_context,
            "owner_action_propose",
            kind="grant_authority",
            agent_id=gold["id"],
            daily_loss_percent="2",
        )
        assert proposed["passkey_required"] is True and proposed["execution_authorized"] is False
        card_id = proposed["owner_action"]["id"]
        again = await call(
            lonora_context,
            "owner_action_propose",
            kind="grant_authority",
            agent_id=gold["id"],
            daily_loss_percent="2",
        )
        assert again["already_shown"] is True and again["owner_action"]["id"] == card_id
        shown = await card(lonora_thread["id"], card_id)
        grant = shown["facts"]["grant"]
        assert grant["agent_name"] == gold["name"] and grant["symbol_scope"] == "selected"
        assert grant["symbols"] == [GOLD] and grant["all_actions"] is True
        assert grant["duration"] == "until_stopped" and grant["allow_manual_positions"] is False
        daily = shown["facts"]["money"]["daily_loss"]
        assert daily["proposed"] == "200.00" and daily["current"] is None, daily
        assert daily["basis"] == "requested" and daily["currency"] == "USD"
        assert shown["facts"]["conflicts"] == [] and shown["facts"]["first_grant"] is True
        assert shown["requires_passkey"] is True
        # Another agent cannot raise a grant card for someone else.
        try:
            await call(
                gold_context, "owner_action_propose", kind="grant_authority", agent_id=lonora_id
            )
        except LonoraError as error:
            assert error.code == "owner_action_grant_agent_forbidden", error.code
        else:
            raise AssertionError("an agent proposed a grant for another agent")
        print(
            "PASS the grant card is a server-resolved draft: this account, gold only, every action, until stopped, own positions excluded, 2% daily loss from the sentence"
        )

        # 3. Confirming needs the passkey; the first time on this device it asks for the
        #    enrollment first. The challenge builds exactly the composer's envelope.
        status, refused = await raw(
            "POST", f"/owner-actions/{card_id}/decision", {"decision": "confirm"}
        )
        assert status == 403 and refused["code"] == "owner_action_passkey_required", refused
        status, refused = await raw("POST", f"/owner-actions/{card_id}/challenge", {})
        assert status == 409 and refused["code"] == "device_registration_required", refused
        device = await Device.enroll(fixture)
        challenge = await fixture.request("POST", f"/owner-actions/{card_id}/challenge", {})
        async with db.sessions() as session:
            stored = await session.get(OwnerActionRow, card_id)
            assert stored is not None
            pending_id = stored.result["authority_id"]
            pending = await session.get(AccountAuthorityRow, pending_id)
            assert pending is not None and pending.status == "pending"
            assert pending.agent_id == gold["id"] and pending.thread_id == gold_thread["id"]
            envelope_hash = pending.envelope_hash
        composer = await fixture.request(
            "POST",
            f"/agents/{gold['id']}/account-authorities",
            {
                "thread_id": gold_thread["id"],
                "account_id": account,
                "management_mode": "full",
                "symbol_scope": "selected",
                "symbols": [GOLD],
                "actions": ALL_ACTIONS,
                "maximum_order_volume": None,
                "maximum_symbol_volume": None,
                "maximum_positions": None,
                "maximum_pending_orders": None,
                "maximum_actions": None,
                "minimum_equity": None,
                "valid_until": None,
                "allow_manual_positions": False,
            },
        )
        # The composer's identical proposal is the very same pending envelope.
        assert composer["id"] == pending_id, (composer["id"], pending_id)
        async with db.sessions() as session:
            same = await session.get(AccountAuthorityRow, composer["id"])
            assert same is not None and same.envelope_hash == envelope_hash
        print(
            "PASS a grant card needs the passkey (enrolling the device first) and its challenge signs the same envelope the composer builds"
        )

        status, decided = await raw(
            "POST",
            f"/owner-actions/{card_id}/decision",
            {
                "decision": "confirm",
                "proof": device.assertion(challenge, fixture.settings.allowed_origin),
            },
        )
        assert status == 200 and decided["status"] == "confirmed", decided
        assert decided["decided_via"] == "passkey"
        assert decided["result"]["daily_loss"] == "200.00"
        assert await level(gold["id"]) == "autonomous"
        policy = await fixture.request("GET", f"/trading/accounts/{account}/execution-policy")
        assert Decimal(policy["risk"]["max_daily_loss"]) == 200
        assert policy["risk"]["currency"] == "USD"
        status, repeated = await raw(
            "POST",
            f"/owner-actions/{card_id}/decision",
            {
                "decision": "confirm",
                "proof": device.assertion(challenge, fixture.settings.allowed_origin),
            },
        )
        assert status == 200 and repeated["status"] == "confirmed"
        async with db.sessions() as session:
            line = await session.scalar(
                select(MessageRow)
                .where(MessageRow.thread_id == lonora_thread["id"], MessageRow.role == "assistant")
                .order_by(MessageRow.seq.desc())
                .limit(1)
            )
            assert line is not None
            assert "approval card" in line.content or "بطاقة موافقة" in line.content, line.content
        print(
            "PASS one passkey tap activates the grant and sets the 2% daily loss limit; repeating the tap changes nothing"
        )

        # 4. Monotonic ladder: under "On its own", a trade the grant does not cover asks
        #    the owner with an approval card; nothing reaches the broker before the tap.
        gold_context, gold_thread = await context_for(gold)
        before = await broker.snapshot()
        euro_args = {
            "action": "buy",
            "account_id": account,
            "symbol": EURO,
            "volume": "0.1",
            "stop_loss": "90",
        }
        outside = await call(gold_context, "trade_execute", **euro_args)
        assert outside.get("_runtime_wait") and outside.get("approval_id"), outside
        assert await broker.snapshot() == before
        # Asked again while the card waits: the same card, never a second one.
        waiting = await call(gold_context, "trade_execute", **euro_args)
        assert waiting.get("_runtime_wait"), waiting
        assert waiting["approval_id"] == outside["approval_id"], waiting
        await fixture.request(
            "POST", f"/trading/approvals/{outside['approval_id']}/decision", {"decision": "approve"}
        )
        approved = await call(gold_context, "trade_execute", **euro_args)
        assert approved.get("status") == "confirmed", approved
        assert approved["approval_id"] == outside["approval_id"]
        # The same exact request again in this Run reuses that approval: no second card.
        repeat = await call(gold_context, "trade_execute", **euro_args)
        assert repeat["approval_id"] == outside["approval_id"], repeat
        async with db.sessions() as session:
            count = await session.scalar(
                select(func.count())
                .select_from(TradeApprovalRow)
                .where(TradeApprovalRow.run_id == gold_context.lease.run_id)
            )
            assert count == 1, count
        # The owner's own position is excluded from the grant: closing it asks too.
        before = await broker.snapshot()
        manual = await call(
            gold_context,
            "trade_execute",
            action="close_position",
            account_id=account,
            symbol=GOLD,
            position_id="manual-ticket",
        )
        assert manual.get("_runtime_wait") and manual.get("approval_id"), manual
        assert await broker.snapshot() == before
        await fixture.request(
            "POST", f"/trading/approvals/{manual['approval_id']}/decision", {"decision": "reject"}
        )
        manual_args = {
            "action": "close_position",
            "account_id": account,
            "symbol": GOLD,
            "position_id": "manual-ticket",
        }
        # The same request right after the owner refused it returns that refusal.
        refused_again = await call(gold_context, "trade_execute", **manual_args)
        assert refused_again.get("status") == "rejected", refused_again
        assert refused_again["approval_id"] == manual["approval_id"], refused_again
        # Once the owner writes again in the conversation, it may ask once more.
        async with db.sessions() as session, session.begin():
            decided = await session.get(TradeApprovalRow, manual["approval_id"])
            assert decided is not None and decided.thread_id is not None
            conversation = await session.get(ThreadRow, decided.thread_id, with_for_update=True)
            assert conversation is not None
            session.add(
                MessageRow(
                    thread_id=conversation.id,
                    seq=conversation.next_seq,
                    role="user",
                    content="Close my own gold position after all.",
                )
            )
            conversation.next_seq += 1
        asked = await call(gold_context, "trade_execute", **manual_args)
        assert asked.get("_runtime_wait") and asked["approval_id"] != manual["approval_id"], asked
        assert await broker.snapshot() == before
        await fixture.request(
            "POST", f"/trading/approvals/{asked['approval_id']}/decision", {"decision": "reject"}
        )
        print(
            "PASS under On its own an out-of-grant trade and the owner's own position become one approval card, reused while it waits, after approval and right after a refusal, never a refusal"
        )

        # 5. Two agents on one market: the card says so and can stop the other agent.
        silver = await fixture.request(
            "POST",
            "/agents",
            {
                "name": "Gold two " + uuid4().hex[:6],
                "scope_mode": "flexible",
                "trading_account_id": account,
                "trading_symbol": GOLD,
            },
        )
        fixture.agents.append(silver["id"])
        lonora_context, lonora_thread = await context_for(lonora)
        second = await call(
            lonora_context, "owner_action_propose", kind="grant_authority", agent_id=silver["id"]
        )
        second_id = second["owner_action"]["id"]
        shown = await card(lonora_thread["id"], second_id)
        conflicts = shown["facts"]["conflicts"]
        assert [item["agent_name"] for item in conflicts] == [gold["name"]], conflicts
        # The account already has the owner's 200 limit: nothing is suggested over it.
        daily = shown["facts"]["money"]["daily_loss"]
        assert Decimal(daily["current"]) == 200 and daily["proposed"] is None, daily
        assert daily["basis"] is None and shown["facts"]["first_grant"] is False
        challenge = await fixture.request("POST", f"/owner-actions/{second_id}/challenge", {})
        status, decided = await raw(
            "POST",
            f"/owner-actions/{second_id}/decision",
            {
                "decision": "confirm",
                "proof": device.assertion(challenge, fixture.settings.allowed_origin),
                "stop_authorities": [conflicts[0]["authority_id"]],
            },
        )
        assert status == 200 and decided["status"] == "confirmed", decided
        assert decided["result"]["stopped_agents"] == [gold["name"]]
        assert await level(silver["id"]) == "autonomous"
        assert await level(gold["id"]) == "supervised"
        try:
            await call(
                lonora_context,
                "owner_action_propose",
                kind="grant_authority",
                agent_id=silver["id"],
            )
        except LonoraError as error:
            assert error.code == "owner_action_not_needed_grant_already_active", error.code
        else:
            raise AssertionError("a card was raised for authority that is already signed")
        print(
            "PASS a second agent's grant card names the agent already trading gold and can stop it there; signed authority raises no new card"
        )

        # 6. Lonora's own card preselects all pairs on the account; dismissing it
        #    withdraws the proposal its challenge prepared.
        own = await call(lonora_context, "owner_action_propose", kind="grant_authority")
        own_id = own["owner_action"]["id"]
        shown = await card(lonora_thread["id"], own_id)
        assert shown["facts"]["grant"]["symbol_scope"] == "account"
        assert shown["facts"]["grant"]["agent_is_personal"] is True
        await fixture.request(
            "POST", f"/owner-actions/{own_id}/challenge", {"allow_manual_positions": True}
        )
        async with db.sessions() as session:
            stored = await session.get(OwnerActionRow, own_id)
            assert stored is not None
            prepared = await session.get(AccountAuthorityRow, stored.result["authority_id"])
            assert prepared is not None and prepared.envelope["symbol_scope"] == "account"
            assert prepared.envelope["allow_manual_positions"] is True
            prepared_id = prepared.id
        status, cancelled = await raw(
            "POST", f"/owner-actions/{own_id}/decision", {"decision": "cancel"}
        )
        assert status == 200 and cancelled["status"] == "cancelled"
        async with db.sessions() as session:
            withdrawn = await session.get(AccountAuthorityRow, prepared_id)
            assert withdrawn is not None and withdrawn.status == "revoked"
        assert await level(lonora_id) == "supervised"
        print(
            "PASS Lonora's grant card preselects all pairs; the owner's switch for own positions is signed, and dismissing withdraws the proposal"
        )

        # 6b. Replacing a capped grant: the card lists every cap, protection and market
        #     the old grant had; the owner's daily loss lowers the limit only when lower.
        gold_state = await fixture.request("GET", f"/agents/{gold['id']}/permissions")
        capped = await fixture.request(
            "POST",
            f"/agents/{gold['id']}/account-authorities?permission_revision={gold_state['revision']}",
            {
                "thread_id": gold_thread["id"],
                "account_id": account,
                "management_mode": "full",
                "symbol_scope": "selected",
                "symbols": [GOLD, EURO],
                "actions": ["buy", "sell", "close_position"],
                "maximum_order_volume": "0.5",
                "maximum_positions": 3,
                "valid_until": None,
                "allow_manual_positions": False,
            },
        )
        signed = await fixture.request("POST", f"/account-authorities/{capped['id']}/challenge", {})
        await fixture.request(
            "POST",
            "/account-authorities/verify",
            device.assertion(signed, fixture.settings.allowed_origin),
        )
        higher = await call(
            lonora_context,
            "owner_action_propose",
            kind="grant_authority",
            agent_id=gold["id"],
            symbols=[GOLD],
            daily_loss_amount="900",
        )
        # A higher daily loss than the owner's own limit is never raised by a grant card.
        assert higher["daily_loss_above_current_needs_limits_card"] is True, higher
        replace_id = higher["owner_action"]["id"]
        shown = await card(lonora_thread["id"], replace_id)
        replaced = shown["facts"]["replaces"]
        assert replaced["symbols"] == [GOLD, EURO] and replaced["all_actions"] is False, replaced
        assert replaced["maximum_order_volume"] == "0.5" and replaced["maximum_positions"] == 3
        assert replaced["management_mode"] == "full" and replaced["valid_until"] is None
        daily = shown["facts"]["money"]["daily_loss"]
        assert daily["proposed"] is None and daily["requested_above"] == "900", daily
        await fixture.request(
            "POST", f"/owner-actions/{replace_id}/decision", {"decision": "cancel"}
        )
        lower = await call(
            lonora_context,
            "owner_action_propose",
            kind="grant_authority",
            agent_id=gold["id"],
            symbols=[GOLD],
            daily_loss_amount="120",
        )
        assert "daily_loss_above_current_needs_limits_card" not in lower
        lower_id = lower["owner_action"]["id"]
        daily = (await card(lonora_thread["id"], lower_id))["facts"]["money"]["daily_loss"]
        assert daily["current"] is not None and Decimal(daily["current"]) == 200, daily
        assert daily["proposed"] == "120", daily
        challenge = await fixture.request("POST", f"/owner-actions/{lower_id}/challenge", {})
        status, decided = await raw(
            "POST",
            f"/owner-actions/{lower_id}/decision",
            {
                "decision": "confirm",
                "proof": device.assertion(challenge, fixture.settings.allowed_origin),
                "money_limit": "none",
            },
        )
        # "Keep my current limit": the grant is signed and the 200 limit stays.
        assert status == 200 and decided["status"] == "confirmed", decided
        assert decided["result"]["daily_loss"] is None
        assert Decimal(decided["result"]["daily_loss_kept"]) == 200
        policy = await fixture.request("GET", f"/trading/accounts/{account}/execution-policy")
        assert Decimal(policy["risk"]["max_daily_loss"]) == 200
        async with db.sessions() as session:
            grants = list(
                await session.scalars(
                    select(AccountAuthorityRow).where(
                        AccountAuthorityRow.agent_id == gold["id"],
                        AccountAuthorityRow.status == "active",
                    )
                )
            )
            assert len(grants) == 1 and grants[0].id != capped["id"], grants
            assert grants[0].envelope["maximum_order_volume"] is None
            assert grants[0].envelope["symbols"] == [GOLD]
            old_grant = await session.get(AccountAuthorityRow, capped["id"])
            assert old_grant is not None and old_grant.status == "revoked"
            line = await session.scalar(
                select(MessageRow)
                .where(MessageRow.thread_id == lonora_thread["id"], MessageRow.role == "assistant")
                .order_by(MessageRow.seq.desc())
                .limit(1)
            )
            assert line is not None
            assert "stays as it was" in line.content or "بقي حد" in line.content, line.content
        print(
            "PASS replacing a capped grant lists its caps and markets; a higher daily loss is never raised by the card and keeping the current limit keeps it"
        )

        # 7. Moving down the ladder revokes the signed grant (a new signature is needed).
        state = await fixture.request("GET", f"/agents/{silver['id']}/permissions")
        lowered = await fixture.request(
            "PUT",
            f"/agents/{silver['id']}/permissions",
            {"level": "supervised", "expected_revision": state["revision"]},
        )
        assert lowered["effective_level"] == "supervised" and not lowered["active_authorities"]
        print("PASS moving down the ladder revokes the signed grant")

        # 8. The raw execution-policy route: lowering is one request; raising needs the
        #    passkey bound to the exact policy.
        path = f"/trading/accounts/{account}/execution-policy"
        lower = {"risk": {"currency": "USD", "max_daily_loss": "150"}}
        assert Decimal((await fixture.request("PUT", path, lower))["risk"]["max_daily_loss"]) == 150
        higher = {"risk": {"currency": "USD", "max_daily_loss": "500"}}
        status, refused = await raw("PUT", path, higher)
        assert status == 403 and refused["code"] == "execution_policy_passkey_required", refused
        status, refused = await raw("POST", path + "/challenge", lower)
        assert status == 409 and refused["code"] == "execution_policy_passkey_not_needed"
        signed = await fixture.request("POST", path + "/challenge", higher)
        proof = device.assertion(signed, fixture.settings.allowed_origin)
        status, forged = await raw(
            "POST",
            path + "/verify",
            {"policy": {"risk": {"currency": "USD", "max_daily_loss": "900"}}, "proof": proof},
        )
        assert status == 403 and forged["code"] == "device_proof_invalid", forged
        signed = await fixture.request("POST", path + "/challenge", higher)
        proof = device.assertion(signed, fixture.settings.allowed_origin)
        stored_policy = await fixture.request(
            "POST", path + "/verify", {"policy": higher, "proof": proof}
        )
        assert Decimal(stored_policy["risk"]["max_daily_loss"]) == 500
        status, _ = await raw("POST", path + "/verify", {"policy": higher, "proof": proof})
        assert status in {403, 409}  # A used challenge never authorizes again.
        # The executor's execution caps are limits too: adding one is one request, and
        # raising or removing one needs the passkey like a money limit.
        capped = {**higher, "max_positions": 1, "max_symbol_direction_volume": "0.1"}
        assert (await fixture.request("PUT", path, capped))["max_positions"] == 1
        for widened in (
            higher,
            {**capped, "max_positions": 3},
            {**capped, "max_symbol_direction_volume": None},
        ):
            status, refused = await raw("PUT", path, widened)
            assert status == 403 and refused["code"] == "execution_policy_passkey_required", (
                widened,
                refused,
            )
        stored = await fixture.request("GET", path)
        assert stored["max_positions"] == 1 and stored["max_symbol_direction_volume"] == "0.1"
        signed = await fixture.request("POST", path + "/challenge", higher)
        proof = device.assertion(signed, fixture.settings.allowed_origin)
        removed = await fixture.request(
            "POST", path + "/verify", {"policy": higher, "proof": proof}
        )
        assert removed["max_positions"] is None
        print(
            "PASS lowering a limit or adding a cap through the policy route is one request; raising or removing one needs a passkey bound to that exact policy"
        )

        # 9. The migration writes an explicit level for every agent without one: Lonora
        #    Ask me, the others No trading; its downgrade removes only untouched rows.
        async with db.sessions() as session, session.begin():
            for agent_id in (lonora_id, general["id"], helper_id):
                row = await session.get(SettingRow, permission_key(fixture.owner, agent_id))
                if row is not None:
                    await session.delete(row)
        await alembic("downgrade", "0039_owner_profile_memory_revisions")
        await alembic("upgrade", "head")
        await alembic("downgrade", "0039_owner_profile_memory_revisions")
        await alembic("upgrade", "head")
        async with db.sessions() as session:
            for agent_id, expected in (
                (lonora_id, "supervised"),
                (general["id"], "analysis"),
                (helper_id, "analysis"),
            ):
                row = await session.get(SettingRow, permission_key(fixture.owner, agent_id))
                assert row is not None and row.payload["fallback_level"] == expected, agent_id
                assert row.payload["revision"] == 0
            # Rows the owner changed (revision above 0) were never touched.
            changed = await session.get(SettingRow, permission_key(fixture.owner, silver["id"]))
            assert changed is not None and changed.payload["revision"] > 0
        assert await level(lonora_id) == "supervised"
        print(
            "PASS the migration stores Lonora at Ask me and every other existing agent at No trading; it is reversible and idempotent"
        )
    finally:
        await fixture.close()


if __name__ == "__main__":
    asyncio.run(main())
