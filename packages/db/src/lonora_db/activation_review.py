"""One recovery-safe observe-only work Run after a verified activation."""

from lonora_contracts.domain import ThreadCreate
from lonora_contracts.runs import RunRequest
from lonora_core.user_error import LonoraError
from lonora_session.idempotency import stable_id
from sqlalchemy import exists, literal, select

from .client import Database
from .conversation_locale import conversation_locale
from .runs import create_run
from .schema import AgentRow, EffectReceiptRow, SuperBotRequestRow
from .super_bot import authority_lock, owned_request, require_goal_authority, stop_request
from .threads import create_thread
from .trading_goals import owned_goal


async def dispatch_activation_reviews(db: Database) -> int:
    key = literal("activation-review:") + SuperBotRequestRow.id
    async with db.sessions() as session:
        candidates = list(
            await session.scalars(
                select(SuperBotRequestRow.id)
                .join(AgentRow, AgentRow.id == SuperBotRequestRow.agent_id)
                .where(
                    AgentRow.paused.is_(False),
                    SuperBotRequestRow.status == "activated",
                    ~exists(select(EffectReceiptRow.key).where(EffectReceiptRow.key == key)),
                )
                .order_by(SuperBotRequestRow.created_at)
                .limit(20)
            )
        )
    count = 0
    for identifier in candidates:
        async with db.sessions() as session, session.begin():
            candidate = await session.get(SuperBotRequestRow, identifier)
            if candidate is None:
                continue
            await authority_lock(session, candidate.agent_id)
            goal = await owned_goal(session, candidate.owner_id, candidate.goal_id, True)
            row = await owned_request(session, candidate.owner_id, identifier, lock=True)
            receipt = "activation-review:" + row.id
            if row.status != "activated" or await session.get(EffectReceiptRow, receipt):
                continue
            agent = await session.get(AgentRow, row.agent_id)
            if agent is None or agent.paused:
                continue
            if goal.state.get("status") not in {"active", "waiting", "blocked"}:
                # Never resume paused/terminal work. A blocked goal may be inspected read-only.
                session.add(EffectReceiptRow(key=receipt, result={"skipped": "goal_not_active"}))
                continue
            # Advisory is also a signed grant; validate its current scope/device.
            try:
                await require_goal_authority(session, goal, mode=row.mode)
            except LonoraError as error:
                await stop_request(session, row, "paused")
                session.add(EffectReceiptRow(key=receipt, result={"skipped": error.code}))
                continue
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
                        "Review the verified activated goal using actual account and exact-symbol market evidence. "
                        "This is an internal observe-only readiness review; the owner has already received activation confirmation. "
                        "Do not ask whether activation succeeded or ask for permission to perform this review. "
                        "Do not execute, delegate financial execution, promise profit or claim ongoing monitoring without a persisted watch. "
                        "Record a concise factual readiness result, at most three sentences, without an unsolicited follow-up question. "
                        "Activation alone is not an entry signal. "
                        + ("Write only in Arabic." if locale == "ar" else "Write only in English.")
                    ),
                    metadata={
                        "authority": "observe_only",
                        "origin_thread_id": row.thread_id,
                        "super_bot_request_id": row.id,
                        "review_goal_id": goal.id,
                        "account_id": row.envelope["account_id"],
                        "symbol": row.envelope["symbol"],
                        "reply_locale": locale,
                    },
                ),
                stable_id(row.id, "activation-review"),
            )
            session.add(EffectReceiptRow(key=receipt, result={"run_id": run.id}))
            count += 1
    return count
