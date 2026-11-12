"""Where an MCP server's authorization server sends the owner's browser back after a
sign-in he started from a Secret card (VISION.md 13.1, 7.2, 10.3).

The browser may be the phone's own, with no Lonora session, so the sign-in's state is
what identifies it: random, kept only as a digest, used once and only within ten
minutes. The callback exchanges the code with the PKCE verifier (no lock held), then, in
one transaction, keeps the tokens as workspace secrets, connects the server and settles
the card; the agent that asked is woken. A sign-in that does not finish (declined,
another issuer, a refused exchange) leaves the card waiting, and the card says so. The
browser always goes back to the app: the web app's conversation, or the mobile app.
"""

from fastapi import APIRouter, Request
from fastapi.responses import RedirectResponse
from lonora_adapters.mcp.oauth import Client, exchange_code, issuer_matches
from lonora_adapters.storage.secret_store import EncryptedSecretStore
from lonora_core.user_error import LonoraError
from lonora_db.mcp_sign_ins import fail_sign_in, hidden_values, take_sign_in
from lonora_db.owner_actions import continue_after_card, settle
from lonora_db.schema import OwnerActionRow
from lonora_db.secret_cards import secret_stale_reason
from lonora_security.secrets import SecretCipher

from ..env import Settings
from ..middleware.auth import runtime
from .secret_cards import SignedIn, pending_card, save_server, settle_saved

router = APIRouter(prefix="/mcp/oauth")
# The mobile app's own scheme (packages/ui-tokens/src/brand.ts).
APP_SCHEME = "lonora://"


def back_to(settings: Settings, return_to: str | None, card: OwnerActionRow | None) -> str:
    """The app the owner started from, at the card's conversation when it is known."""
    origin = settings.allowed_origin.rstrip("/")
    if return_to == "app":
        return APP_SCHEME + (f"thread?id={card.thread_id}" if card and card.thread_id else "")
    if return_to == "web" and card is not None and card.agent_id:
        return f"{origin}/app/{card.agent_id}"
    return origin + "/app"


@router.get("/callback")
async def callback(
    request: Request,
    state: str = "",
    code: str = "",
    iss: str | None = None,
    error: str | None = None,
) -> RedirectResponse:
    rt = runtime(request)
    key = rt.settings.encryption_key.get_secret_value()
    async with rt.db.sessions() as session, session.begin():
        sign_in = await take_sign_in(session, state)
        if sign_in is None:
            # Unknown, used or late: nothing to finish.
            return RedirectResponse(back_to(rt.settings, None, None), 303)
        plan, owner_id, card_id = dict(sign_in.plan), sign_in.owner_id, sign_in.card_id
        back = RedirectResponse(
            back_to(rt.settings, plan["return_to"], await session.get(OwnerActionRow, card_id)),
            303,
        )
        if error is not None or not code:
            sign_in.failure = "mcp_sign_in_declined"
            return back
        if not issuer_matches(plan["issuer"], plan["iss_parameter"], iss):
            # Another authorization server's answer (a mix-up): its code is never used.
            sign_in.failure = "mcp_sign_in_failed"
            return back
        hidden = hidden_values(SecretCipher(key), sign_in)
        sign_in_id = sign_in.id
    client = Client(plan["client_id"], hidden.get("client_secret"), plan["client_method"])
    try:
        tokens = await exchange_code(
            plan["token_endpoint"],
            hidden["resource"],
            client,
            code,
            hidden["verifier"],
            plan["redirect_uri"],
        )
    except LonoraError as refused:
        async with rt.db.sessions() as session, session.begin():
            await fail_sign_in(session, sign_in_id, refused.code)
        return back
    store = EncryptedSecretStore(rt.db, key, owner_id)
    async with rt.db.sessions() as session, session.begin():
        row = await pending_card(session, owner_id, card_id)
        if row is None:
            return back  # Settled meanwhile: nothing is saved.
        reason = await secret_stale_reason(session, owner_id, row.payload)
        if reason is not None:
            await settle(session, row, "expired", reason)
            return back
        signed_in = SignedIn(
            tokens, client, plan["issuer"], plan["token_endpoint"], hidden["resource"]
        )
        result = await save_server(
            session, store, owner_id, row, hidden["address"], None, signed_in
        )
        await settle_saved(session, owner_id, row, result)
        await continue_after_card(session, row)
    return back
