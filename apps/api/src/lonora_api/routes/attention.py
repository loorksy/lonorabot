from typing import Any

from fastapi import APIRouter, Depends, Request
from lonora_auth.identity import OwnerIdentity
from lonora_contracts.attention import AttentionPolicy, AttentionSeen
from lonora_contracts.domain import utcnow
from lonora_db.attention import (
    acknowledge,
    acknowledge_all,
    attention_data,
    attention_view,
    policy,
    still_current,
)
from lonora_db.schema import AttentionRow, EffectReceiptRow
from lonora_db.transactions import SettingsRepository
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..middleware.auth import require_owner, runtime

router = APIRouter(prefix="/attention")


@router.get("/audit")
async def audit(request: Request, owner: OwnerIdentity = Depends(require_owner)):
    async with runtime(request).db.sessions() as session:
        rows = await session.scalars(
            select(EffectReceiptRow)
            .where(EffectReceiptRow.key.startswith("attention-source:" + owner.id + ":"))
            .order_by(EffectReceiptRow.created_at.desc())
            .limit(100)
        )
        return [row.result for row in rows]


async def shown(session: AsyncSession, owner_id: str, statuses: list[str]) -> list[dict[str, Any]]:
    """What the owner is shown: within their policy, still valid, each fact once (newest)."""
    settings = await policy(session, owner_id)
    query = select(AttentionRow).where(
        AttentionRow.owner_id == owner_id,
        AttentionRow.status.in_(statuses),
        or_(
            AttentionRow.parameters["valid_until"].as_string().is_(None),
            AttentionRow.parameters["valid_until"].as_string() > utcnow().isoformat(),
        ),
        or_(
            AttentionRow.importance != "opportunity",
            AttentionRow.parameters["valid_until"].as_string() > utcnow().isoformat(),
        ),
    )
    if not settings.opportunities:
        query = query.where(AttentionRow.importance != "opportunity")
    if not settings.informational:
        query = query.where(AttentionRow.importance != "informational")
    query = query.order_by(AttentionRow.updated_at.desc(), AttentionRow.id)
    rows: list[dict[str, Any]] = []
    facts: set[tuple[str, str]] = set()
    offset = 0
    # Up to 50 shown rows: repeated or cleared facts do not use up the cap.
    while True:
        page = (await session.scalars(query.offset(offset).limit(50))).all()
        for row in page:
            if (row.code, row.coalesce_key) in facts:
                continue
            facts.add((row.code, row.coalesce_key))
            if await still_current(session, row):
                rows.append(attention_data(row))
                if len(rows) == 50:
                    return rows
        if len(page) < 50:
            return rows
        offset += 50


@router.get("/view")
async def view(request: Request, owner: OwnerIdentity = Depends(require_owner)):
    """«يحتاج انتباهك»: what needs the owner across all agents (mandate 11.7)."""
    async with runtime(request).db.sessions() as session:
        return await attention_view(session, owner.id)


@router.get("/history")
async def history(request: Request, owner: OwnerIdentity = Depends(require_owner)):
    async with runtime(request).db.sessions() as session:
        return await shown(session, owner.id, ["pending", "ready", "seen"])


@router.get("")
async def inbox(request: Request, owner: OwnerIdentity = Depends(require_owner)):
    async with runtime(request).db.sessions() as session:
        return await shown(session, owner.id, ["pending", "ready"])


@router.post("/seen")
async def seen(
    request: Request, body: AttentionSeen, owner: OwnerIdentity = Depends(require_owner)
):
    async with runtime(request).db.sessions() as session, session.begin():
        return attention_data(await acknowledge(session, owner.id, body.notification_id))


@router.post("/seen-all")
async def seen_all(request: Request, owner: OwnerIdentity = Depends(require_owner)):
    """«تحديد الكل كمقروء»: every open item except the critical and action-required ones."""
    async with runtime(request).db.sessions() as session, session.begin():
        return {"seen": await acknowledge_all(session, owner.id)}


@router.get("/policy")
async def read_policy(request: Request, owner: OwnerIdentity = Depends(require_owner)):
    async with runtime(request).db.sessions() as session:
        return await policy(session, owner.id)


@router.put("/policy")
async def save_policy(
    request: Request, body: AttentionPolicy, owner: OwnerIdentity = Depends(require_owner)
):
    async with runtime(request).db.sessions() as session, session.begin():
        await SettingsRepository().put(
            session, "attention-policy:" + owner.id, body.model_dump(mode="json")
        )
    return body
