"""Notices of a change an agent made without asking (Q31), as one-line cards.

``watch_changed``: an agent moved one of its watches' expiry later (or removed it). The
card offers Undo, which puts the earlier expiry back while the watch is still exactly as
the agent left it (its revision matches); one use, and only the latest change of a
watch can be undone. ``stop_tightened``: an agent tightened a stop loss under its grant.
It is recorded settled, with nothing to tap: undoing it would be a new financial
modification, which only an order through the executor can make.

The caller holds the owner-actions lock before the watch's lock (the order an Undo
takes them in).
"""

from datetime import datetime
from typing import Any

from lonora_session.idempotency import stable_id
from sqlalchemy.ext.asyncio import AsyncSession

from .schema import MarketWatchRow, OwnerActionRow


def extended(previous: str | None, current: str | None) -> bool:
    """Whether the expiry moved later: a later time, or none any more."""
    if previous is None:
        return False
    if current is None:
        return True
    return datetime.fromisoformat(current) > datetime.fromisoformat(previous)


async def raise_watch_changed(
    session: AsyncSession,
    owner_id: str,
    watch: MarketWatchRow,
    previous_expires_at: str | None,
    *,
    agent_id: str,
    thread_id: str | None,
    run_id: str | None,
) -> OwnerActionRow | None:
    """The Undo notice of an agent's extension of a watch; None when it did not extend."""
    from .owner_actions import card_thread, create_card, supersede_subject

    current = watch.payload.get("expires_at")
    if not extended(previous_expires_at, current):
        return None
    subject = "watch:" + watch.id
    card_id = stable_id(owner_id, "owner-action:watch_changed:" + subject + f":{watch.version}")
    existing = await session.get(OwnerActionRow, card_id)
    if existing is not None:
        return existing
    # Only the latest change of this watch can be undone.
    await supersede_subject(
        session, owner_id, "watch_changed", subject, "watch_changed_again", by=card_id
    )
    thread = await card_thread(session, owner_id, agent_id, thread_id)
    return await create_card(
        session,
        owner_id,
        card_id=card_id,
        agent_id=agent_id,
        thread=thread,
        run_id=run_id,
        source="system",
        kind="watch_changed",
        subject=subject,
        payload={
            "watch_id": watch.id,
            "previous_expires_at": previous_expires_at,
            "expires_at": current,
            "revision": watch.version,
        },
    )


async def raise_stop_tightened(
    session: AsyncSession,
    owner_id: str,
    *,
    operation_id: str,
    account_id: str,
    symbol: str,
    position_id: str,
    previous_stop_loss: str | None,
    stop_loss: str,
    agent_id: str,
    thread_id: str | None,
    run_id: str | None,
) -> OwnerActionRow:
    """The notice of a stop loss an agent tightened; recorded settled, no Undo."""
    from .owner_actions import card_thread, create_card, lock_owner_actions

    await lock_owner_actions(session, owner_id)
    card_id = stable_id(owner_id, "owner-action:stop_tightened:" + operation_id)
    existing = await session.get(OwnerActionRow, card_id)
    if existing is not None:
        return existing
    thread = await card_thread(session, owner_id, agent_id, thread_id)
    return await create_card(
        session,
        owner_id,
        card_id=card_id,
        agent_id=agent_id,
        thread=thread,
        run_id=run_id,
        source="system",
        kind="stop_tightened",
        subject="position:" + account_id + ":" + position_id,
        payload={
            "operation_id": operation_id,
            "account_id": account_id,
            "symbol": symbol,
            "position_id": position_id,
            "previous_stop_loss": previous_stop_loss,
            "stop_loss": stop_loss,
        },
        status="confirmed",
    )


async def watch_change_stale(
    session: AsyncSession, owner_id: str, payload: dict[str, Any]
) -> str | None:
    """Why Undo no longer applies: the watch is gone or changed since the agent's change."""
    row = await session.get(MarketWatchRow, payload["watch_id"])
    if row is None or row.owner_id != owner_id:
        return "watch_removed"
    if row.version != payload["revision"]:
        return "watch_changed_again"
    return None


async def undo_watch_change(
    session: AsyncSession, owner_id: str, payload: dict[str, Any]
) -> dict[str, Any]:
    """Undo: the expiry the watch had before the agent's change, as it was."""
    from .market_watches import restore_expiry

    row = await restore_expiry(
        session, owner_id, payload["watch_id"], payload["previous_expires_at"], payload["revision"]
    )
    return {"undone": True, "expires_at": row.payload.get("expires_at")}


async def notice_facts(
    session: AsyncSession, row: OwnerActionRow, facts: dict[str, Any]
) -> dict[str, Any]:
    payload = row.payload
    if row.kind == "stop_tightened":
        facts["stop"] = {
            "symbol": payload["symbol"],
            "position_id": payload["position_id"],
            "previous_stop_loss": payload["previous_stop_loss"],
            "stop_loss": payload["stop_loss"],
        }
        return facts
    watch = await session.get(MarketWatchRow, payload["watch_id"])
    owned = watch is not None and watch.owner_id == row.owner_id
    facts["watch"] = {
        "symbol": watch.payload.get("symbol") if owned and watch else None,
        "kind": watch.payload.get("kind", "price") if owned and watch else None,
        "previous_expires_at": payload["previous_expires_at"],
        "expires_at": payload["expires_at"],
        # Undo still puts the earlier expiry back (the watch is as the agent left it).
        "active": await watch_change_stale(session, row.owner_id, payload) is None,
    }
    return facts
