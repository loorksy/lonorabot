import hashlib
import json
from typing import Any

from lonora_contracts.opportunity import (
    OpportunityCreate,
    OpportunityList,
    OpportunityReference,
    OpportunityUpdate,
    OpportunityVersion,
)
from lonora_core.user_error import LonoraError
from lonora_db.agent_binding import agent_binding
from lonora_db.genui_taint import taint_row_from
from lonora_db.runs import require_lease
from lonora_db.schema import EffectReceiptRow, TradingOpportunityRow
from lonora_db.trading_opportunities import (
    create_opportunity,
    opportunity_data,
    opportunity_history,
    opportunity_summary,
    owned_opportunity,
)
from lonora_trading.opportunities import refresh_opportunity, update_opportunity
from sqlalchemy import select

from .base import Tool
from .context import ToolContext


async def create(context: ToolContext, args: dict[str, Any]) -> dict[str, Any]:
    async with context.db.sessions() as session, session.begin():
        run = await require_lease(session, context.lease, lock=True)
        row = await create_opportunity(
            session,
            context.owner_id,
            context.agent_id,
            run.model_metadata.get("origin_thread_id") or context.thread_id,
            OpportunityCreate.model_validate(args),
        )
        # An opportunity tainted work saved wakes tainted (docs/genui.md, review round 4).
        await taint_row_from(session, run, "opportunity", row.id)
        return opportunity_data(row)


async def read(context: ToolContext, args: dict[str, Any]) -> dict[str, Any]:
    async with context.db.sessions() as session, session.begin():
        await agent_binding(session, context.owner_id, context.agent_id)
        row = await owned_opportunity(session, context.owner_id, args["opportunity_id"], lock=True)
        await refresh_opportunity(session, row)
        history = await opportunity_history(session, context.owner_id, row.id)
        return {
            **opportunity_data(row),
            "history": [
                {
                    key: item.get(key)
                    for key in (
                        "observed_at",
                        "previous_status",
                        "status",
                        "reason_code",
                        "version",
                    )
                }
                | {
                    "supporting_decision_ids": item.get("definition", {}).get(
                        "supporting_decision_ids", []
                    ),
                    "contradicting_decision_ids": item.get("definition", {}).get(
                        "contradicting_decision_ids", []
                    ),
                    "direction": item.get("definition", {}).get("definition", {}).get("direction"),
                }
                for item in history[:10]
            ],
            "history_returned": min(len(history), 10),
        }


async def update(context: ToolContext, args: dict[str, Any]) -> dict[str, Any]:
    async with context.db.sessions() as session, session.begin():
        run = await require_lease(session, context.lease, lock=True)
        key = context.effect_key + ":opportunity-update"
        intent = hashlib.sha256(json.dumps(args, sort_keys=True).encode()).hexdigest()
        prior = await session.get(EffectReceiptRow, key)
        if prior:
            if prior.result.get("intent") != intent:
                raise LonoraError("opportunity_intent_conflict", 409)
            row = await owned_opportunity(session, context.owner_id, args["opportunity_id"])
            return opportunity_data(row)
        updated = await update_opportunity(
            session, context.owner_id, context.agent_id, OpportunityUpdate.model_validate(args)
        )
        await taint_row_from(session, run, "opportunity", updated.id)
        data = opportunity_data(updated)
        session.add(
            EffectReceiptRow(key=key, result={"intent": intent, "version": data["version"]})
        )
        return data


async def list_opportunities(context: ToolContext, args: dict[str, Any]) -> dict[str, Any]:
    params = OpportunityList.model_validate(args)
    async with context.db.sessions() as session:
        agent = await agent_binding(session, context.owner_id, context.agent_id)
        query = select(TradingOpportunityRow).where(
            TradingOpportunityRow.owner_id == context.owner_id,
            TradingOpportunityRow.agent_id == context.agent_id,
        )
        # The focus account and symbol are defaults for an unscoped list, never a fence.
        account_id = params.account_id or agent.trading_account_id
        symbol = params.symbol or (
            agent.trading_symbol
            if not params.account_id or params.account_id == agent.trading_account_id
            else None
        )
        if account_id:
            query = query.where(TradingOpportunityRow.account_id == account_id)
        if symbol:
            query = query.where(TradingOpportunityRow.symbol == symbol)
        rows = await session.scalars(
            query.order_by(TradingOpportunityRow.updated_at.desc()).limit(params.limit)
        )
        return {"opportunities": [opportunity_summary(row) for row in rows]}


async def historical_version(context: ToolContext, args: dict[str, Any]) -> dict[str, Any]:
    async with context.db.sessions() as session:
        await agent_binding(session, context.owner_id, context.agent_id)
        row = await owned_opportunity(session, context.owner_id, args["opportunity_id"])
        from lonora_db.schema import EventRow

        version = await session.scalar(
            select(EventRow).where(
                EventRow.owner_id == context.owner_id,
                EventRow.kind == "opportunity.transition",
                EventRow.payload["id"].as_string() == row.id,
                EventRow.payload["version"].as_integer() == args["version"],
            )
        )
        if version is None:
            raise LonoraError("thesis_version_not_found", 404)
        return {
            "observed_at": version.created_at.isoformat(),
            **{key: value for key, value in version.payload.items() if not key.startswith("_ln_")},
        }


def tools() -> list[Tool]:
    return [
        Tool(
            "market_opportunity_version",
            "Read one exact historical thesis version and its recorded evidence, without replacing it with the current thesis or market.",
            OpportunityVersion,
            historical_version,
            True,
        ),
        Tool(
            "market_opportunity_create",
            "Persist one exact scoped setup/thesis across wakes. References must be real recorded decisions/watch; creating a thesis never authorizes trading.",
            OpportunityCreate,
            create,
        ),
        Tool(
            "market_opportunity_read",
            "Inspect the same evolving opportunity and its immutable reason-for-change history. Refresh expiry/data freshness; never substitute today's facts for historical decisions.",
            OpportunityReference,
            read,
            True,
            poller=True,
        ),
        Tool(
            "market_opportunity_update",
            "Version-check a thesis update using actual evidence IDs. Confirmation requires fresh matching evidence; expiry/invalidation needs a recorded rule/evidence. Cannot forge execution or revive an ended thesis.",
            OpportunityUpdate,
            update,
        ),
        Tool(
            "market_opportunity_list",
            "List bounded relevant saved opportunities before creating a duplicate setup on a wake.",
            OpportunityList,
            list_opportunities,
            True,
        ),
    ]
