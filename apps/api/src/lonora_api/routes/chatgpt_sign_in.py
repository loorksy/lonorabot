"""Sign in with ChatGPT from the Secret card (VISION Amendment 4; proposal section 4.4).

``start`` gives the card OpenAI's authorization address for one attempt (or, on the
owner's "Use a different ChatGPT account", a new registration). The owner signs in in the
browser, which then lands on OpenAI's loopback callback, an address that does not open on
a server: the owner pastes it into the card and ``finish`` checks it, exchanges its code
and verifies the account, with no lock held, before the card settles the way a saved key
does (the router record, the default model, the agent woken). Both answer only while the
card waits. Sign-out revokes the session at OpenAI and clears the tokens either way. With
``LONORA_CHATGPT_SIGN_IN=off`` start and finish answer ``chatgpt_sign_in_unavailable``;
sign-out still works, so a sign-in made before is never left at rest.
"""

from typing import Any

from fastapi import APIRouter, Depends, Request
from lonora_adapters.storage.secret_store import EncryptedSecretStore
from lonora_auth.identity import OwnerIdentity
from lonora_contracts.domain import Contract
from lonora_core.user_error import LonoraError
from lonora_db.model_credentials import CONNECTION_SETTING
from lonora_db.owner_actions import (
    continue_after_card,
    live_status,
    owned_card,
    owner_action_data,
)
from lonora_db.schema import OwnerActionRow, SecretRow
from lonora_db.transactions import SettingsRepository
from lonora_providers.catalog import read_catalog
from lonora_providers.chatgpt_sign_in import PROVIDER, ChatGptSignIn, require_enabled
from pydantic import Field
from sqlalchemy import select

from ..middleware.auth import require_owner, runtime
from .model_router import answer_unconfigured
from .secret_cards import pending_card, settle_saved

router = APIRouter()


class ChatGptStart(Contract):
    """The owner's "Use a different ChatGPT account": a new registration, not the saved one."""

    new_account: bool = False


class ChatGptFinish(Contract):
    """The address the browser landed on after OpenAI's sign-in, pasted by the owner."""

    address: str = Field(min_length=1, max_length=16384)


def sign_in(request: Request, owner: OwnerIdentity) -> ChatGptSignIn:
    rt = runtime(request)
    return ChatGptSignIn(
        EncryptedSecretStore(rt.db, rt.settings.encryption_key.get_secret_value(), owner.id)
    )


async def waiting_chatgpt_card(
    request: Request, owner: OwnerIdentity, card_id: str
) -> OwnerActionRow:
    """The owner's ChatGPT Secret card while it waits: a card no longer pending is never
    replayed, so nothing is started, exchanged or saved for it."""
    async with runtime(request).db.sessions() as session:
        row = await owned_card(session, owner.id, card_id)
    if (
        row.kind != "secret"
        or row.payload.get("connect") != "model_provider"
        or row.payload["details"].get("provider") != PROVIDER
    ):
        raise LonoraError("owner_action_not_chatgpt", 409)
    if live_status(row) != "pending":
        raise LonoraError("owner_action_already_decided", 409)
    return row


@router.post("/owner-actions/{card_id}/chatgpt/start")
async def start(
    request: Request,
    card_id: str,
    body: ChatGptStart | None = None,
    owner: OwnerIdentity = Depends(require_owner),
) -> dict[str, Any]:
    require_enabled()
    await waiting_chatgpt_card(request, owner, card_id)
    return await sign_in(request, owner).start(card_id, new_account=bool(body and body.new_account))


@router.post("/owner-actions/{card_id}/chatgpt/finish")
async def finish(
    request: Request,
    card_id: str,
    body: ChatGptFinish,
    owner: OwnerIdentity = Depends(require_owner),
) -> dict[str, Any]:
    require_enabled()
    rt = runtime(request)
    await waiting_chatgpt_card(request, owner, card_id)
    # OpenAI is asked with no lock held; the card settles after.
    account = await sign_in(request, owner).finish(card_id, body.address)
    # Lonora's listed plan models the account offers; unknown when its list was not read.
    models = None if account["offered"] is None else len(await read_catalog(rt.db, PROVIDER))
    async with rt.db.sessions() as session, session.begin():
        row = await pending_card(session, owner, card_id)
        if row is None:
            return await owner_action_data(session, await owned_card(session, owner.id, card_id))
        secret_id = await session.scalar(
            select(SecretRow.id).where(
                SecretRow.owner_id == owner.id,
                SecretRow.scope == "provider",
                SecretRow.name == PROVIDER,
            )
        )
        # The router's record, as a saved key has one; the credential is read by its id.
        await SettingsRepository().put(
            session, CONNECTION_SETTING + PROVIDER, {"secret_id": secret_id, "url": None}
        )
        await settle_saved(
            session,
            owner,
            row,
            {
                "target": "model_provider",
                "provider": PROVIDER,
                "configured": True,
                "saved": [],
                "account": account["email"],
                "models": models,
            },
        )
        await continue_after_card(session, row)
        data = await owner_action_data(session, row)
    await answer_unconfigured(request, owner)
    return data


@router.post("/providers/openai_chatgpt/sign-out")
async def sign_out(
    request: Request, owner: OwnerIdentity = Depends(require_owner)
) -> dict[str, Any]:
    # Always offered, the sign-in turned off included: a sign-in made before is revoked
    # and cleared rather than left at rest.
    return await sign_in(request, owner).sign_out()
