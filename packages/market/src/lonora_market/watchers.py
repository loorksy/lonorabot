from datetime import datetime, timedelta
from decimal import Decimal

from lonora_adapters.brokers.base import BrokerManager
from lonora_contracts.domain import utcnow
from lonora_contracts.market_watch import Watch
from lonora_contracts.runs import RunRequest
from lonora_core.market_watch import condition_met
from lonora_core.user_error import LonoraError
from lonora_db.client import Database
from lonora_db.runs import create_run
from lonora_db.schema import MarketWakeReceiptRow, MarketWatchRow
from lonora_session.idempotency import stable_id
from sqlalchemy import select

from .watch_control import watch_can_trigger


async def check_watches(db: Database, brokers: BrokerManager) -> int:
    async with db.sessions() as session:
        watches = list((await session.scalars(select(MarketWatchRow).limit(100))).all())
    triggered = 0
    for original in watches:
        config = Watch.model_validate(original.payload)
        if not config.enabled or not original.agent_id or not original.thread_id:
            continue
        try:
            broker = await brokers.get(original.owner_id, config.account_id)
            quote = await broker.quote(config.symbol)
        except LonoraError:
            continue
        now = utcnow()
        async with db.sessions() as session, session.begin():
            row = await session.get(MarketWatchRow, original.id, with_for_update=True)
            if row is None:
                continue
            previous = (
                Decimal(str(row.state["last_value"]))
                if row.state.get("last_value") is not None
                else None
            )
            last_triggered = (
                datetime.fromisoformat(row.state["last_triggered"])
                if row.state.get("last_triggered")
                else None
            )
            current = quote.bid
            matched = condition_met(config.condition, config.level, current, previous)
            next_check = (
                datetime.fromisoformat(row.state["next_check"])
                if row.state.get("next_check")
                else None
            )
            if next_check and next_check > now:
                continue
            state = {
                **row.state,
                "last_value": str(current),
                "next_check": (now + timedelta(seconds=config.interval_seconds)).isoformat(),
            }
            if matched and watch_can_trigger(
                config.enabled, last_triggered, config.cooldown_seconds, now
            ):
                receipt_id = stable_id(
                    row.id, quote.observed_at.isoformat() + ":" + config.condition
                )
                if await session.get(MarketWakeReceiptRow, receipt_id) is None:
                    run = await create_run(
                        session,
                        row.owner_id,
                        RunRequest(
                            thread_id=row.thread_id or "",
                            agent_id=row.agent_id or "",
                            trigger="watch",
                            prompt=config.prompt,
                            metadata={
                                "watch_id": row.id,
                                "symbol": quote.symbol,
                                "observed_at": quote.observed_at.isoformat(),
                                "quote": quote.model_dump(mode="json"),
                            },
                        ),
                    )
                    session.add(
                        MarketWakeReceiptRow(
                            id=receipt_id,
                            owner_id=row.owner_id,
                            agent_id=row.agent_id,
                            thread_id=row.thread_id,
                            payload={"watch_id": row.id, "run_id": run.id},
                        )
                    )
                    state["last_triggered"] = now.isoformat()
                    triggered += 1
            row.state = state
    return triggered
