from fastapi import APIRouter, Depends, Request
from lonora_auth.identity import OwnerIdentity
from lonora_contracts.attention import AttentionPolicy, AttentionSeen
from lonora_contracts.domain import utcnow
from lonora_db.attention import acknowledge, attention_data, policy
from lonora_db.schema import AttentionRow, EffectReceiptRow
from lonora_db.transactions import SettingsRepository
from sqlalchemy import or_, select

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


@router.get("/history")
async def history(request: Request, owner: OwnerIdentity = Depends(require_owner)):
    async with runtime(request).db.sessions() as session:
        rows = await session.scalars(
            select(AttentionRow)
            .where(AttentionRow.owner_id == owner.id)
            .order_by(AttentionRow.updated_at.desc())
            .limit(50)
        )
        return [attention_data(row) for row in rows]


@router.get("")
async def inbox(request: Request, owner: OwnerIdentity = Depends(require_owner)):
    async with runtime(request).db.sessions() as session:
        settings = await policy(session, owner.id)
        query = select(AttentionRow).where(
            AttentionRow.owner_id == owner.id,
            AttentionRow.status.in_(["pending", "ready"]),
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
        rows = await session.scalars(query.order_by(AttentionRow.updated_at.desc()).limit(50))
        return [attention_data(row) for row in rows]


@router.post("/seen")
async def seen(
    request: Request, body: AttentionSeen, owner: OwnerIdentity = Depends(require_owner)
):
    async with runtime(request).db.sessions() as session, session.begin():
        return attention_data(await acknowledge(session, owner.id, body.notification_id))


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
