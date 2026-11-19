"""Lonora receives the system alerts (mandate 3.1.5, 9.4): a broker health problem and
an uncertain operation each wake Lonora once.

The wake runs in a work thread with fixed server text that names only server values
(codes, ids, times), never text from a model, a peer or a page. Its result is copied
into Lonora's own conversation (``outcome_return``, trigger ``broker_event``). The wake
keeps Lonora's normal authority: it is not observe-only. A paused Lonora is not woken
(4.7: a paused agent takes no new work); the owner still has the attention item, and
Lonora is woken for it once resumed.
"""

import logging
from typing import Any

from lonora_contracts.domain import ThreadCreate
from lonora_contracts.runs import RunRequest
from lonora_session.idempotency import stable_id
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from .personal_agent import ensure_personal_agent
from .schema import AttentionRow, RunRow
from .threads import conversation_thread, create_thread

logger = logging.getLogger(__name__)

PROBLEMS = {
    "broker_token_rejected": "MetaApi rejected the access token",
    "broker_account_undeployed": "the account is not deployed on MetaApi, or no longer exists there",
    "broker_connection_lost": "the connection has been lost for more than two minutes",
    "broker_rate_limited": "MetaApi has been throttling the account's requests for more than "
    "two minutes (the account itself is fine); the adapter retries at the time MetaApi gives",
}


def alert_prompt(item: AttentionRow) -> str | None:
    """The fixed wake text for an item, or None when the item is no system alert."""
    values: dict[str, Any] = item.parameters
    if item.code in PROBLEMS:
        return (
            "System alert from the server: broker account account_id="
            + str(values["account_id"])
            + " has a health problem: "
            + PROBLEMS[item.code]
            + " (adapter reason "
            + str(values["reason_code"])
            + ", disconnected since "
            + str(values["since"])
            + "). The owner already has it as a needs-your-attention item. Inspect the "
            "account and decide what the owner needs to hear from you."
        )
    if item.code == "operation_uncertain" and values.get("operation_id"):
        return (
            "System alert from the server: operation_id="
            + str(values["operation_id"])
            + " on account_id="
            + str(values.get("account_id"))
            + " has no confirmed outcome at the broker. It is never resent: the server "
            "keeps reconciling it, and the owner can settle it on its Settle card. Inspect "
            "it and decide what the owner needs to hear from you."
        )
    return None


ALERT_CODES = (*PROBLEMS, "operation_uncertain")
ALERT_PAGE = 50


def alert_key(item: AttentionRow) -> str | None:
    """What one wake is for: a broker problem of one outage (an item raised again for it,
    after the connection was disabled and enabled, is the same problem), or one
    uncertain operation."""
    values: dict[str, Any] = item.parameters
    if item.code in PROBLEMS:
        return item.code + ":" + str(values["account_id"]) + ":" + str(values["since"])
    if item.code == "operation_uncertain" and values.get("operation_id"):
        return "operation_uncertain:" + str(values["operation_id"])
    return None


async def wake_for_alerts(session: AsyncSession, owner_id: str) -> int:
    """Wake Lonora for every open system alert it has not been woken for yet.

    Run on every attention tick, so an alert that arrived while Lonora was paused, or
    whose wake failed, reaches Lonora on a later tick. An uncertain operation delivered
    without its record (its projection kept failing, ``quarantine_event``) names no
    operation, so nothing can wake Lonora for it; the owner still has the item.
    Returns how many wakes were started.
    """
    from .attention import lock_attention, mandatory_current

    await lock_attention(session, owner_id)
    query = (
        select(AttentionRow)
        .where(
            AttentionRow.owner_id == owner_id,
            AttentionRow.code.in_(ALERT_CODES),
            AttentionRow.status.in_(["pending", "ready"]),
        )
        .order_by(AttentionRow.created_at, AttentionRow.id)
    )
    # Every open alert is looked at, page by page: alerts Lonora was already woken for
    # stay open, so a fixed window of the oldest would starve the newer ones.
    count = 0
    offset = 0
    while True:
        page = list(await session.scalars(query.offset(offset).limit(ALERT_PAGE)))
        for item in page:
            key = alert_key(item)
            if key is None or await session.get(RunRow, stable_id(owner_id, "system-alert:" + key)):
                continue
            if await mandatory_current(session, item):
                count += await wake_lonora(session, item) is not None
        if len(page) < ALERT_PAGE:
            return count
        offset += ALERT_PAGE


async def wake_lonora(session: AsyncSession, item: AttentionRow) -> RunRow | None:
    """Wake Lonora once for a system alert; None when there is nothing to wake.

    One wake per ``alert_key``. Only an item that is still open wakes Lonora. The wake
    runs in a savepoint: if it fails, the owner's item still stands, the failure is
    logged, and a later tick tries again.
    """
    if item.status not in {"pending", "ready"}:
        return None
    prompt = alert_prompt(item)
    if prompt is None:
        return None
    try:
        async with session.begin_nested():
            return await start_wake(session, item, prompt)
    except Exception:
        logger.exception("system_alert_wake_failed code=%s", item.code)
        return None


async def start_wake(session: AsyncSession, item: AttentionRow, prompt: str) -> RunRow | None:
    run_id = stable_id(item.owner_id, "system-alert:" + str(alert_key(item)))
    if await session.get(RunRow, run_id) is not None:
        return None
    lonora = await ensure_personal_agent(session, item.owner_id)
    if lonora.paused:
        return None
    from .runs import create_run

    conversation = await conversation_thread(session, item.owner_id, lonora.id)
    work = await create_thread(
        session, item.owner_id, ThreadCreate(agent_id=lonora.id), purpose="work"
    )
    return await create_run(
        session,
        item.owner_id,
        RunRequest(
            thread_id=work.id,
            agent_id=lonora.id,
            trigger="broker_event",
            prompt=prompt,
            metadata={
                "origin_thread_id": conversation.id,
                "system_alert": item.code,
                "attention_id": item.id,
                **(
                    {"account_id": item.parameters["account_id"]}
                    if item.parameters.get("account_id")
                    else {}
                ),
            },
        ),
        run_id,
    )
