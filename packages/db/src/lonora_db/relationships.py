"""Derived relationship evidence shares the immutable event/receipt ledger."""

from typing import Any

from lonora_contracts.relationships import MarketRelationship
from lonora_core.user_error import LonoraError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from .events import emit
from .schema import EffectReceiptRow, EventRow


def relationship_summary(value: MarketRelationship) -> dict[str, Any]:
    return value.model_dump(mode="json", exclude={"samples"})


async def read_relationship(
    session: AsyncSession, owner_id: str, identifier: str
) -> MarketRelationship:
    event = await session.scalar(
        select(EventRow).where(
            EventRow.owner_id == owner_id,
            EventRow.kind == "market.relationship_recorded",
            EventRow.payload["relationship"]["id"].as_string() == identifier,
        )
    )
    if event is None:
        raise LonoraError("relationship_not_found", 404)
    return MarketRelationship.model_validate(event.payload["relationship"])


async def save_relationship(
    session: AsyncSession, value: MarketRelationship, *, intent: str, thread_id: str, run_id: str
) -> MarketRelationship:
    receipt = await session.get(EffectReceiptRow, "relationship:" + value.id)
    if receipt:
        if receipt.result["intent"] != intent:
            raise LonoraError("relationship_intent_conflict", 409)
        return MarketRelationship.model_validate(receipt.result["relationship"])
    data = value.model_dump(mode="json")
    emit(
        session,
        value.owner_id,
        "market.relationship_recorded",
        agent_id=value.agent_id,
        thread_id=thread_id,
        run_id=run_id,
        payload={"relationship": data},
    )
    session.add(
        EffectReceiptRow(
            key="relationship:" + value.id, result={"intent": intent, "relationship": data}
        )
    )
    return value
