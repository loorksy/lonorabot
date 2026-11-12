"""The Secret card's one submit (VISION.md 7.2, 10.3).

The owner's values go straight to the encrypted store and the card settles in the same
transaction. The card, its events, the conversation and the agent keep only the keys.
"""

from typing import Any

from fastapi import APIRouter, Depends, Request
from lonora_adapters.storage.secret_store import EncryptedSecretStore
from lonora_auth.identity import OwnerIdentity
from lonora_contracts.owner_actions import SecretCardSave
from lonora_core.user_error import LonoraError
from lonora_db.owner_actions import (
    confirm_in_thread,
    continue_after_card,
    live_status,
    lock_owner_actions,
    owned_card,
    owner_action_data,
    settle,
    supersede_subject,
)
from lonora_db.secret_cards import save_values

from ..middleware.auth import require_owner, runtime

router = APIRouter(prefix="/owner-actions")


@router.post("/{card_id}/secret")
async def save_secret(
    request: Request,
    card_id: str,
    body: SecretCardSave,
    owner: OwnerIdentity = Depends(require_owner),
) -> dict[str, Any]:
    rt = runtime(request)
    store = EncryptedSecretStore(rt.db, rt.settings.encryption_key.get_secret_value(), owner.id)
    async with rt.db.sessions() as session, session.begin():
        await lock_owner_actions(session, owner.id)
        row = await owned_card(session, owner.id, card_id, lock=True)
        if row.kind != "secret":
            raise LonoraError("owner_action_not_secret", 409)
        status = live_status(row)
        if status == "expired" and row.status == "pending":
            await settle(session, row, "expired", "expired")
        if status != "pending":
            # A second tap shows the card as it is; nothing is written again.
            return await owner_action_data(session, row)
        result = await save_values(session, row, body.values, store.write_in_session)
        await settle(session, row, "confirmed", None, via="tap", result=result)
        await supersede_subject(
            session,
            owner.id,
            row.kind,
            row.subject,
            "done_by_another_card",
            keep=row.id,
            effect=row.payload_hash,
        )
        await confirm_in_thread(session, row)
        # The agent that asked continues the work that needed the secret.
        await continue_after_card(session, row)
        return await owner_action_data(session, row)
