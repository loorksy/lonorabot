"""0087: execution caps and money limits end (mandate 14.2.2, 14.3.9).

On a disposable PostgreSQL already at head: step down below 0087 and seed an account's
stored execution policy with every cap and money limit next to tightened freshness
bounds, a pending and a confirmed ``set_account_limits`` card, grant cards carrying a
daily loss limit (two pending ones of one agent that differ only in it, and a confirmed
Full delegation whose Custom terms hold one), a ``resolve_operation`` card, and passkey
challenges of the execution-policy route and of a card. Upgrade and check that the
policy keeps exactly its freshness bounds, the limits cards and the policy challenge are
gone, the grant drafts lose their daily loss with a recomputed hash, the older of the two
now-identical pending grant cards is superseded, and everything else is untouched. The
downgrade changes no data and the upgrade runs again cleanly.
"""

import asyncio
import json
import subprocess
import sys
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import uuid4

from check_streaming import test_settings
from lonora_contracts.execution_quality import ExecutionPolicy
from lonora_contracts.owner_actions import GrantDraft
from lonora_db.owner_actions import payload_hash
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection, create_async_engine

ALEMBIC = [sys.executable, "-m", "alembic", "-c", "packages/db/alembic.ini"]
BEFORE = "0138_skill_package_files"
AGES = {"quote_max_age_seconds": 15, "account_max_age_seconds": 20}
OLD_POLICY = {
    **AGES,
    "max_spread": "0.5",
    "max_entry_drift_stop_fraction": "0.25",
    "max_positions": 3,
    "max_pending_orders": 2,
    "max_symbol_direction_volume": "1.0",
    "risk": {
        "currency": "USD",
        "max_trade_risk": "50",
        "max_trade_risk_equity_percent": None,
        "max_daily_loss": "200",
        "max_open_risk": None,
        "max_open_risk_equity_percent": None,
        "min_free_margin": None,
        "trading_day_timezone": "UTC",
    },
}
DAILY_LOSS = {"amount": "150", "currency": "USD", "basis": "requested", "percent": None}


def alembic(*arguments: str) -> None:
    subprocess.run([*ALEMBIC, *arguments], check=True, capture_output=True, text=True)


def loaded(value: Any) -> Any:
    return json.loads(value) if isinstance(value, str) else value


async def policy(connection: AsyncConnection, key: str) -> dict[str, Any]:
    return loaded(
        await connection.scalar(text("SELECT payload FROM ln_settings WHERE key = :k"), {"k": key})
    )


async def cards(connection: AsyncConnection, owner: str) -> dict[str, dict[str, Any]]:
    rows = await connection.execute(
        text(
            "SELECT id, kind, payload, payload_hash, status, status_reason FROM ln_owner_actions"
            " WHERE owner_id = :o"
        ),
        {"o": owner},
    )
    return {
        row.id: {
            "kind": row.kind,
            "payload": loaded(row.payload),
            "payload_hash": row.payload_hash,
            "status": row.status,
            "status_reason": row.status_reason,
        }
        for row in rows
    }


async def challenges(connection: AsyncConnection, owner: str) -> set[str]:
    rows = await connection.execute(
        text("SELECT kind FROM ln_device_challenges WHERE owner_id = :o"), {"o": owner}
    )
    return {row[0] for row in rows}


def check_upgraded(
    found: dict[str, dict[str, Any]], ids: dict[str, str], drafts: dict[str, dict[str, Any]]
) -> None:
    assert {card["kind"] for card in found.values()} == {"grant_authority", "resolve_operation"}
    for name, status in (
        ("grant_old", "superseded"),
        ("grant_new", "pending"),
        ("full", "confirmed"),
    ):
        card = found[ids[name]]
        assert card["payload"] == drafts[name], card
        assert card["payload_hash"] == payload_hash("grant_authority", drafts[name]), card
        assert card["status"] == status, card
        GrantDraft.model_validate(card["payload"])
    assert found[ids["grant_old"]]["status_reason"] == "same_choice_on_another_card"
    assert found[ids["grant_new"]]["status_reason"] is None
    resolve = found[ids["resolve"]]
    assert (resolve["payload"], resolve["payload_hash"], resolve["status"]) == (
        {},
        "hash",
        "pending",
    )


async def main() -> None:
    engine = create_async_engine(test_settings().database_url)
    now = datetime.now(UTC)
    ids = {
        name: str(uuid4())
        for name in (
            "owner",
            "agent",
            "limits_pending",
            "limits_confirmed",
            "grant_old",
            "grant_new",
            "full",
            "resolve",
        )
    }
    account = str(uuid4())
    key = "execution_policy:" + ids["owner"] + ":" + account
    custom = GrantDraft(
        agent_id=ids["agent"],
        account_id=account,
        symbol_scope="selected",
        symbols=["XAUUSD"],
        actions=["buy", "sell", "close_position"],
        duration="24h",
    )
    drafts = {
        "grant_old": custom.model_dump(mode="json"),
        "grant_new": custom.model_dump(mode="json"),
        "full": custom.with_delegation("full").model_dump(mode="json"),
    }
    # As the earlier contract stored them: the daily loss on the draft and its Custom terms.
    stored = {
        "grant_old": {**drafts["grant_old"], "daily_loss": DAILY_LOSS},
        "grant_new": {**drafts["grant_new"], "daily_loss": None},
        "full": {
            **drafts["full"],
            "daily_loss": None,
            "custom": {**drafts["full"]["custom"], "daily_loss": DAILY_LOSS},
        },
    }
    seeded: list[tuple[str, str, str, dict[str, Any], str, datetime]] = [
        ("limits_pending", "set_account_limits", "account:" + account, {}, "pending", now),
        ("limits_confirmed", "set_account_limits", "account:" + account, {}, "confirmed", now),
        *(
            (
                name,
                "grant_authority",
                "grant:" + ids["agent"] + ":" + account,
                stored[name],
                status,
                created,
            )
            for name, status, created in (
                ("grant_old", "pending", now - timedelta(hours=2)),
                ("grant_new", "pending", now - timedelta(hours=1)),
                ("full", "confirmed", now - timedelta(hours=3)),
            )
        ),
    ]
    try:
        await asyncio.to_thread(alembic, "downgrade", BEFORE)
        async with engine.begin() as connection:
            await connection.execute(
                text(
                    "INSERT INTO ln_owners (id, singleton, email, password_hash, created_at)"
                    " VALUES (:owner, 1, 'money-limits-removal@example.com', 'x', :now)"
                ),
                {**ids, "now": now},
            )
            await connection.execute(
                text(
                    "INSERT INTO ln_agents (id, owner_id, name, avatar, color, instructions,"
                    " paused, created_at) VALUES (:agent, :owner, 'Gold', '', '', '', false, :now)"
                ),
                {**ids, "now": now},
            )
            await connection.execute(
                text(
                    "INSERT INTO ln_settings (key, payload, updated_at)"
                    " VALUES (:key, CAST(:payload AS JSON), :now)"
                ),
                {"key": key, "payload": json.dumps(OLD_POLICY), "now": now},
            )
            for name, kind, subject, payload, status, created in seeded:
                await connection.execute(
                    text(
                        "INSERT INTO ln_owner_actions (id, owner_id, agent_id, source, kind,"
                        " subject, payload, payload_hash, status, expires_at, created_at,"
                        " updated_at) VALUES (:id, :owner, :agent, 'owner', :kind, :subject,"
                        " CAST(:payload AS JSON), :hash, :status, :expires, :created, :created)"
                    ),
                    {
                        **ids,
                        "id": ids[name],
                        "kind": kind,
                        "subject": subject,
                        "payload": json.dumps(payload),
                        "hash": payload_hash(kind, payload),
                        "status": status,
                        "expires": now + timedelta(hours=1),
                        "created": created,
                    },
                )
            await connection.execute(
                text(
                    "INSERT INTO ln_owner_actions (id, owner_id, agent_id, source, kind,"
                    " subject, payload, payload_hash, status, expires_at, created_at,"
                    " updated_at) VALUES (:resolve, :owner, :agent, 'system', 'resolve_operation',"
                    " 'operation:op1', '{}', 'hash', 'pending', :expires, :now, :now)"
                ),
                {**ids, "expires": now + timedelta(hours=1), "now": now},
            )
            for kind, request_id in (
                ("execution_policy", account),
                ("owner_action", ids["limits_pending"]),
                ("account_activate", ids["full"]),
            ):
                await connection.execute(
                    text(
                        "INSERT INTO ln_device_challenges (id, owner_id, session_hash, kind,"
                        " request_id, challenge, binding_hash, name, status, expires_at,"
                        " created_at) VALUES (:id, :owner, 's', :kind, :request, 'c', 'b', '',"
                        " 'pending', :expires, :now)"
                    ),
                    {
                        "id": str(uuid4()),
                        "owner": ids["owner"],
                        "kind": kind,
                        "request": request_id,
                        "expires": now + timedelta(minutes=5),
                        "now": now,
                    },
                )
        await engine.dispose()

        await asyncio.to_thread(alembic, "upgrade", "heads")
        async with engine.connect() as connection:
            stripped = await policy(connection, key)
            assert stripped == AGES, stripped
            assert ExecutionPolicy.model_validate(stripped) == ExecutionPolicy(**AGES)
            check_upgraded(await cards(connection, ids["owner"]), ids, drafts)
            assert await challenges(connection, ids["owner"]) == {"account_activate"}
        await engine.dispose()
        print(
            "PASS the policy keeps only its freshness bounds; limits cards and their challenges"
            " are deleted; grant drafts lose their daily loss with a recomputed hash and the"
            " older duplicate pending card is superseded; other cards stay"
        )

        await asyncio.to_thread(alembic, "downgrade", BEFORE)
        async with engine.connect() as connection:
            assert await policy(connection, key) == AGES
            check_upgraded(await cards(connection, ids["owner"]), ids, drafts)
            assert await challenges(connection, ids["owner"]) == {"account_activate"}
        await engine.dispose()
        await asyncio.to_thread(alembic, "upgrade", "heads")
        async with engine.begin() as connection:
            assert await policy(connection, key) == AGES
            check_upgraded(await cards(connection, ids["owner"]), ids, drafts)
            assert await challenges(connection, ids["owner"]) == {"account_activate"}
            await connection.execute(text("DELETE FROM ln_settings WHERE key = :key"), {"key": key})
            await connection.execute(text("DELETE FROM ln_owners WHERE id = :owner"), ids)
        print("PASS the downgrade restores nothing; the upgrade repeats cleanly")
    finally:
        await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
