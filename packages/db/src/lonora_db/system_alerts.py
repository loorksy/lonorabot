"""Lonora receives the system alerts (mandate 3.1.5, 9.4): a broker health problem and
an uncertain operation each wake Lonora once.

The wake runs in a work thread with fixed server text that names only server values
(codes, ids, times), never text from a model, a peer or a page. Its result is copied
into Lonora's own conversation (``outcome_return``, trigger ``broker_event``). The wake
keeps Lonora's normal authority: it is not observe-only. A paused Lonora is not woken
(4.7: a paused agent takes no new work); the owner still has the attention item.
"""

from typing import Any

from lonora_contracts.domain import ThreadCreate
from lonora_contracts.runs import RunRequest
from lonora_session.idempotency import stable_id
from sqlalchemy.ext.asyncio import AsyncSession

from .personal_agent import ensure_personal_agent
from .schema import AttentionRow, RunRow
from .threads import conversation_thread, create_thread

PROBLEMS = {
    "broker_token_rejected": "MetaApi rejected the access token",
    "broker_account_undeployed": "the account is not deployed on MetaApi, or no longer exists there",
    "broker_connection_lost": "the connection has been lost for more than two minutes",
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


async def wake_lonora(session: AsyncSession, item: AttentionRow) -> RunRow | None:
    """Wake Lonora once for a system alert item; None when there is nothing to wake."""
    prompt = alert_prompt(item)
    if prompt is None:
        return None
    run_id = stable_id(item.owner_id, "system-alert:" + item.id)
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
