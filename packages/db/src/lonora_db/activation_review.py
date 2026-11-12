"""One recovery-safe readiness review after the owner signs a grant.

A grant with full management starts its continuous management Task when it is signed,
so only a bounded grant (selected markets with explicit limits) gets this review: one
observe-only work Run that inspects the account and arms the follow-up it needs. It never
trades; the agent trades later, inside the grant, from its normal Runs and wakes.
"""

from lonora_contracts.domain import ThreadCreate
from lonora_contracts.runs import RunRequest
from lonora_core.user_error import LonoraError
from lonora_session.idempotency import stable_id
from sqlalchemy import exists, literal, select
from sqlalchemy.ext.asyncio import AsyncSession

from .account_authority import require_authority
from .authority_lock import authority_lock
from .client import Database
from .conversation_locale import conversation_locale
from .item_failures import ItemGuard, blocked
from .runs import create_run
from .schema import AccountAuthorityRow, AgentRow, EffectReceiptRow
from .threads import create_thread


def review_key(grant_id: str) -> str:
    return "activation-review:" + grant_id


async def dispatch_activation_reviews(db: Database) -> int:
    key = literal("activation-review:") + AccountAuthorityRow.id
    async with db.sessions() as session:
        candidates = list(
            await session.execute(
                select(AccountAuthorityRow.id, AccountAuthorityRow.owner_id)
                .join(AgentRow, AgentRow.id == AccountAuthorityRow.agent_id)
                .where(
                    AgentRow.paused.is_(False),
                    AccountAuthorityRow.status == "active",
                    ~exists(select(EffectReceiptRow.key).where(EffectReceiptRow.key == key)),
                    ~blocked("activation_review", AccountAuthorityRow.id),
                )
                .order_by(AccountAuthorityRow.created_at)
                .limit(20)
            )
        )
    guard = ItemGuard(db, "activation_review", quarantine=skip_review)
    await guard.prepare(identifier for identifier, _ in candidates)
    count = 0
    for identifier, owner_id in candidates:

        async def review(identifier: str = identifier) -> bool:
            async with db.sessions() as session, session.begin():
                return await review_one(session, identifier)

        count += int(bool(await guard.run(identifier, owner_id, review)))
    return count


async def skip_review(session: AsyncSession, identifier: str) -> bool:
    """Quarantine: a readiness review that keeps failing is recorded as skipped."""
    key = review_key(identifier)
    if await session.get(EffectReceiptRow, key) is None:
        session.add(EffectReceiptRow(key=key, result={"skipped": "review_quarantined"}))
    return True


async def review_one(session: AsyncSession, identifier: str) -> bool:
    candidate = await session.get(AccountAuthorityRow, identifier)
    if candidate is None:
        return False
    await authority_lock(session, candidate.agent_id)
    receipt = review_key(candidate.id)
    if await session.get(EffectReceiptRow, receipt):
        return False
    agent = await session.get(AgentRow, candidate.agent_id)
    if agent is None or agent.paused:
        return False
    try:
        row, envelope = await require_authority(
            session, candidate.owner_id, candidate.agent_id, candidate.id
        )
    except LonoraError as error:
        session.add(EffectReceiptRow(key=receipt, result={"skipped": error.code}))
        return False
    if envelope.management_mode == "full":
        # A full grant starts no work of its own: the agent's one continuous
        # account-management Task comes with Full mode (4.5.1).
        session.add(EffectReceiptRow(key=receipt, result={"skipped": "management_task"}))
        return False
    if row.thread_id is None:
        # The owner deleted the conversation the grant was signed in.
        session.add(EffectReceiptRow(key=receipt, result={"skipped": "origin_thread_unavailable"}))
        return False
    thread = await create_thread(
        session, row.owner_id, ThreadCreate(agent_id=row.agent_id), purpose="work"
    )
    locale = await conversation_locale(session, row.owner_id, row.thread_id)
    run = await create_run(
        session,
        row.owner_id,
        RunRequest(
            agent_id=row.agent_id,
            thread_id=thread.id,
            trigger="activation",
            prompt=(
                "The owner has just signed a grant for you to trade this account on your own, "
                "inside its markets, actions and limits. Review readiness with actual account "
                "and exact-symbol market evidence. This is an internal observe-only review; the "
                "owner already has the confirmation. Do not ask whether the grant works or ask "
                "for permission to perform this review. Do not trade during it; persist a watch "
                "or schedule when a later entry condition justifies one. Record a concise factual "
                "readiness result, at most three sentences, without an unsolicited follow-up "
                "question. The grant alone is not an entry signal. "
                + ("Write only in Arabic." if locale == "ar" else "Write only in English.")
            ),
            metadata={
                "authority": "observe_only",
                "origin_thread_id": row.thread_id,
                "account_authority_id": row.id,
                "account_id": row.account_id,
                "reply_locale": locale,
            },
        ),
        stable_id(row.id, "activation-review"),
    )
    session.add(EffectReceiptRow(key=receipt, result={"run_id": run.id}))
    return True
