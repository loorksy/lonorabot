"""A pause card as a team supervisor raised it before supervision grants were deleted.

Nothing in production raises ``supervision_paused`` any more (Lonora's pause raises no
card, and no team agent pauses another). Rows stored before migration 0127 still render
and resume with the owner's tap; the tests seed such a row with this helper.
"""

from lonora_db.owner_actions import card_thread, create_card, lock_owner_actions
from lonora_db.schema import OwnerActionRow, SupervisionHoldRow
from lonora_session.idempotency import stable_id
from sqlalchemy.ext.asyncio import AsyncSession


async def raise_supervision_pause_card(
    session: AsyncSession, hold: SupervisionHoldRow, *, run_id: str | None
) -> OwnerActionRow:
    """The card an earlier supervisor's pause raised in the paused agent's conversation:
    who paused which work, with one-tap Resume; one per hold."""
    await lock_owner_actions(session, hold.owner_id)
    subject = "supervision-hold:" + hold.id
    card_id = stable_id(hold.owner_id, "owner-action:supervision_paused:" + subject)
    existing = await session.get(OwnerActionRow, card_id)
    if existing is not None:
        return existing
    thread = await card_thread(session, hold.owner_id, hold.agent_id, None)
    return await create_card(
        session,
        hold.owner_id,
        card_id=card_id,
        agent_id=hold.agent_id,
        thread=thread,
        run_id=run_id,
        source="system",
        kind="supervision_paused",
        subject=subject,
        payload={"hold_id": hold.id},
    )
