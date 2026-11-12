"""Attention items for the owner's events (mandate 11.4, 9.4): raised once, withdrawn
when the card ends or the problem clears.

PostgreSQL only (LONORA_DATABASE_URL): the real API, the attention projection and the
stored broker recovery state of a simulation connection.
"""

import asyncio
import os
import subprocess
import sys
from datetime import datetime, timedelta
from pathlib import Path
from uuid import uuid4

from check_streaming import Fixture
from lonora_adapter_kit.types import ToolCall
from lonora_contracts.broker_activity import BrokerRecoverySnapshot
from lonora_contracts.domain import utcnow
from lonora_db.personal_agent import ensure_personal_agent
from lonora_db.schema import AttentionRow, BrokerSessionRow, EventRow, OwnerActionRow
from lonora_db.threads import conversation_thread
from lonora_gateway.attention import attention_tick
from lonora_tools.loader import load_tools
from sqlalchemy import func, select, text

ROOT = Path(__file__).resolve().parents[1]


async def items(fixture: Fixture, code: str) -> list[AttentionRow]:
    async with fixture.runtime.db.sessions() as session:
        return list(
            await session.scalars(
                select(AttentionRow)
                .where(AttentionRow.owner_id == fixture.owner, AttentionRow.code == code)
                .order_by(AttentionRow.created_at)
            )
        )


async def ready_events(fixture: Fixture, item_id: str) -> int:
    async with fixture.runtime.db.sessions() as session:
        return int(
            await session.scalar(
                select(func.count())
                .select_from(EventRow)
                .where(
                    EventRow.owner_id == fixture.owner,
                    EventRow.kind == "attention.ready",
                    EventRow.payload["id"].as_string() == item_id,
                )
            )
            or 0
        )


async def tick(fixture: Fixture) -> None:
    await attention_tick(
        fixture.runtime.db, fixture.runtime.services(fixture.owner).brokers, fixture.owner
    )


async def secret_card(fixture: Fixture) -> None:
    agent = await fixture.agent("Secret asker")
    thread = await fixture.conversation(agent)
    context = await fixture.lease(await fixture.run(agent, thread))
    registry = load_tools()

    async def propose() -> str:
        card = await registry.execute(
            ToolCall(
                id="call-" + uuid4().hex,
                name="owner_action_propose",
                arguments={"kind": "connect_credential", "target": "mcp_server", "service": "x"},
            ),
            context,
        )
        return str(card["owner_action"]["id"])

    card_id = await propose()
    await tick(fixture)
    await tick(fixture)
    [item] = await items(fixture, "secret_requested")
    assert item.status == "ready" and item.importance == "action_required"
    assert item.agent_id == agent["id"] and item.thread_id == thread["id"]
    assert item.parameters["owner_action_id"] == card_id
    assert await ready_events(fixture, item.id) == 1
    print("PASS a pending Secret card is one ready item in its agent's conversation, once")

    await fixture.request("POST", f"/owner-actions/{card_id}/decision", {"decision": "cancel"})
    await tick(fixture)
    [item] = await items(fixture, "secret_requested")
    assert item.status == "suppressed"
    assert item.parameters["suppression_code"] == "attention_superseded_state"
    print("PASS the Secret card's item is withdrawn when the card ends")

    card_id = await propose()
    await tick(fixture)
    _, second = await items(fixture, "secret_requested")
    assert second.status == "ready" and second.parameters["owner_action_id"] == card_id
    # The owner looked at it; the card's lifetime then runs out with no event at all.
    await fixture.request("POST", "/attention/seen", {"notification_id": second.id})
    async with fixture.runtime.db.sessions() as session, session.begin():
        row = await session.get(OwnerActionRow, card_id)
        assert row is not None
        row.expires_at = utcnow() - timedelta(seconds=1)
    await tick(fixture)
    _, second = await items(fixture, "secret_requested")
    assert second.status == "suppressed"
    print("PASS a seen Secret item is withdrawn when the card's lifetime runs out")


async def set_recovery(
    fixture: Fixture,
    account: str,
    status: str,
    reason: str,
    since: datetime,
    *,
    enabled: bool = True,
) -> None:
    now = utcnow()
    snapshot = BrokerRecoverySnapshot(
        status=status,  # type: ignore[arg-type]
        reason_code=reason,
        since=since,
        observed_at=now,
    )
    async with fixture.runtime.db.sessions() as session, session.begin():
        row = await session.get(BrokerSessionRow, account, with_for_update=True)
        assert row is not None
        row.state = {**row.state, "broker_recovery": snapshot.model_dump(mode="json")}
        row.payload = {**row.payload, "enabled": enabled}


def outage(item: AttentionRow) -> datetime:
    """When the item's outage began: the same outage, not a new one."""
    return datetime.fromisoformat(item.parameters["since"])


async def broker_health(fixture: Fixture) -> None:
    account = (
        await fixture.request(
            "POST",
            "/trading/connections",
            {"provider": "simulation", "account_id": uuid4().hex, "enabled": True},
        )
    )["id"]
    async with fixture.runtime.db.sessions() as session, session.begin():
        lonora = await ensure_personal_agent(session, fixture.owner)
        lonora_thread = (await conversation_thread(session, fixture.owner, lonora.id)).id

    await set_recovery(fixture, account, "disconnected", "broker_credentials_rejected", utcnow())
    await tick(fixture)
    await tick(fixture)
    [token] = await items(fixture, "broker_token_rejected")
    assert token.status == "ready" and token.importance == "action_required"
    assert (token.agent_id, token.thread_id) == (lonora.id, lonora_thread)
    assert token.parameters["account_id"] == account
    assert token.parameters["reason_code"] == "broker_credentials_rejected"
    assert await ready_events(fixture, token.id) == 1
    print("PASS a rejected token is one item at once, in Lonora's conversation")

    await set_recovery(fixture, account, "connected", "broker_reconciled", utcnow())
    await tick(fixture)
    [token] = await items(fixture, "broker_token_rejected")
    assert token.status == "suppressed"
    print("PASS the item is withdrawn when the account connects again")

    await set_recovery(
        fixture,
        account,
        "disconnected",
        "broker_connection_timeout",
        utcnow() - timedelta(seconds=30),
    )
    await tick(fixture)
    assert await items(fixture, "broker_connection_lost") == []
    print("PASS a connection lost for 30 seconds is no item")

    await set_recovery(
        fixture,
        account,
        "disconnected",
        "broker_connection_closed",
        utcnow() - timedelta(minutes=3),
    )
    await tick(fixture)
    await tick(fixture)
    [lost] = await items(fixture, "broker_connection_lost")
    assert lost.status == "ready" and lost.parameters["reason_code"] == "broker_connection_closed"
    print("PASS a connection lost for more than 2 minutes is one item")

    # The same outage turns into an undeployed account: one item per problem.
    await set_recovery(fixture, account, "disconnected", "broker_account_undeployed", outage(lost))
    await tick(fixture)
    [lost] = await items(fixture, "broker_connection_lost")
    [undeployed] = await items(fixture, "broker_account_undeployed")
    assert lost.status == "suppressed" and undeployed.status == "ready"
    assert undeployed.parameters["since"] == lost.parameters["since"]
    print("PASS a changed problem withdraws the old item and raises its own")

    await set_recovery(
        fixture,
        account,
        "disconnected",
        "broker_account_undeployed",
        outage(undeployed),
        enabled=False,
    )
    await tick(fixture)
    [undeployed] = await items(fixture, "broker_account_undeployed")
    assert undeployed.status == "suppressed"
    await tick(fixture)
    assert len(await items(fixture, "broker_account_undeployed")) == 1
    print("PASS a disabled connection has no broker health item")


async def migration(fixture: Fixture) -> None:
    environment = {**os.environ}

    def alembic(action: str, revision: str) -> None:
        subprocess.run(
            [sys.executable, "-m", "alembic", "-c", "packages/db/alembic.ini", action, revision],
            check=True,
            cwd=ROOT,
            stdout=subprocess.DEVNULL,
            env=environment,
        )

    async with fixture.runtime.db.sessions() as session, session.begin():
        lonora = await ensure_personal_agent(session, fixture.owner)
        thread = (await conversation_thread(session, fixture.owner, lonora.id)).id
    await asyncio.to_thread(alembic, "downgrade", "0050_genui_state_and_origin")
    rows = {
        code + status: uuid4().hex[:32]
        for code in ("broker_degraded", "broker_recovered")
        for status in ("ready", "seen")
    }
    async with fixture.runtime.db.sessions() as session, session.begin():
        for key, identifier in rows.items():
            code, status = (key[:-5], "ready") if key.endswith("ready") else (key[:-4], "seen")
            await session.execute(
                text(
                    "INSERT INTO ln_attention (id, owner_id, agent_id, thread_id, logical_key, "
                    "coalesce_key, importance, code, status, parameters, source_events, "
                    "source_count, version, due_at, created_at, updated_at) VALUES (:id, :owner, "
                    ":agent, :thread, :id, :id, 'important_change', :code, :status, "
                    "CAST(:parameters AS JSON), CAST('[]' AS JSON), 1, 1, now(), now(), now())"
                ),
                {
                    "id": identifier,
                    "owner": fixture.owner,
                    "agent": lonora.id,
                    "thread": thread,
                    "code": code,
                    "status": status,
                    "parameters": '{"account_id": "acc", "execution_authorized": false}',
                },
            )
    await asyncio.to_thread(alembic, "upgrade", "head")
    async with fixture.runtime.db.sessions() as session:
        stored = {
            row.id: row
            for row in await session.scalars(
                select(AttentionRow).where(AttentionRow.id.in_(list(rows.values())))
            )
        }
    ready, seen = stored[rows["broker_degradedready"]], stored[rows["broker_degradedseen"]]
    assert (ready.code, ready.status, ready.version) == ("broker_connection_lost", "suppressed", 2)
    assert ready.parameters["suppression_code"] == "attention_superseded_state"
    assert (seen.code, seen.status, seen.version) == ("broker_connection_lost", "seen", 1)
    assert (
        rows["broker_recoveredready"] not in stored and rows["broker_recoveredseen"] not in stored
    )
    # Every stored row reads through the notification contract again.
    await fixture.request("GET", "/attention/history")
    print("PASS migration 0170 rewrites broker_degraded rows and deletes broker_recovered rows")


async def main() -> None:
    fixture = await Fixture().open()
    try:
        await secret_card(fixture)
        await broker_health(fixture)
        await migration(fixture)
    finally:
        await fixture.close()


if __name__ == "__main__":
    asyncio.run(main())
