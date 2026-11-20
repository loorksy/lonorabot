"""Owner action cards: list, an agent's live Mandate card, passkey challenge and the
owner's decision.

Owner session only; no agent tool reaches these routes or the decision below. A
confirmation re-validates the card against current state (a stale card is settled as
expired with its reason), is idempotent per card, and then runs the existing owner
function for its effect: the owner attestation of an uncertain operation
(``attest_operation``) and the owner's own resume of paused work
(``lonora_db.pauses``; never money authority). A Secret card's values never come here:
the card has its own route (``secret_cards``). Resuming is one tap.

There is no grant card. A passkey challenge is not how any remaining card is confirmed.
"""

from typing import Any

from fastapi import APIRouter, Depends, Request
from lonora_auth.identity import OwnerIdentity
from lonora_contracts.domain import utcnow
from lonora_contracts.owner_actions import CARD_ATTESTATION, OwnerActionDecision
from lonora_contracts.trading import OperationResolution
from lonora_core.user_error import LonoraError
from lonora_db.owner_actions import (
    confirm_in_thread,
    keep_pending,
    live_status,
    lock_owner_actions,
    mandate_card,
    owned_card,
    owner_action_data,
    renew_card,
    settle,
    stale_reason,
    supersede_subject,
    thread_cards,
)
from lonora_db.pauses import owner_resumes
from lonora_db.schema import OwnerActionRow
from lonora_db.trading_mode import change_trading_mode
from lonora_db.transactions import owned_agent, owned_thread
from lonora_trading.owner_controls import attest_operation
from sqlalchemy.ext.asyncio import AsyncSession

from ..middleware.auth import require_owner, runtime

router = APIRouter(prefix="/owner-actions")


@router.get("")
async def cards(
    request: Request, thread_id: str, owner: OwnerIdentity = Depends(require_owner)
) -> list[dict[str, Any]]:
    async with runtime(request).db.sessions() as session:
        await owned_thread(session, owner.id, thread_id)
        return [
            await owner_action_data(session, row)
            for row in await thread_cards(session, owner.id, thread_id)
        ]


@router.get("/mandate")
async def mandate(
    request: Request, agent_id: str, owner: OwnerIdentity = Depends(require_owner)
) -> dict[str, Any] | None:
    """The agent's live Mandate card wherever it was raised: the newest pending or tapped
    one, or null when it has none. Reading never raises one."""
    async with runtime(request).db.sessions() as session:
        await owned_agent(session, owner.id, agent_id)
        row = await mandate_card(session, owner.id, agent_id)
        return await owner_action_data(session, row) if row is not None else None


@router.post("/{card_id}/challenge")
async def challenge(
    request: Request,
    card_id: str,
    owner: OwnerIdentity = Depends(require_owner),
) -> dict[str, Any]:
    async with runtime(request).db.sessions() as session:
        candidate = await owned_card(session, owner.id, card_id)
        if live_status(candidate) != "pending":
            raise LonoraError("owner_action_expired_or_decided", 409)
        # No remaining card is confirmed with a passkey.
        raise LonoraError("owner_action_passkey_not_needed", 409)


@router.post("/{card_id}/decision")
async def decision(
    request: Request,
    card_id: str,
    body: OwnerActionDecision,
    owner: OwnerIdentity = Depends(require_owner),
) -> dict[str, Any]:
    async with runtime(request).db.sessions() as session, session.begin():
        await lock_owner_actions(session, owner.id)
        row = await owned_card(session, owner.id, card_id, lock=True)
        await decide(session, owner, row, body)
        return await owner_action_data(session, row)


@router.post("/{card_id}/renew")
async def renew(
    request: Request, card_id: str, owner: OwnerIdentity = Depends(require_owner)
) -> dict[str, Any]:
    """«طلب جديد»: a fresh card for an expired one whose record still needs a decision
    (``owner_action_not_renewable`` otherwise). It decides nothing."""
    async with runtime(request).db.sessions() as session, session.begin():
        return await owner_action_data(session, await renew_card(session, owner.id, card_id))


async def decide_trading_mode(
    session: AsyncSession, owner: OwnerIdentity, row: OwnerActionRow, body: OwnerActionDecision
) -> None:
    """The Mandate card (10.3): the tap applies the mode its button showed at the moment of
    the tap, never a toggle of whatever is stored now. The card stays the agent's switch
    after a tap; only the owner's tap sets Full (4.2.1)."""
    if body.decision != "confirm":
        raise LonoraError("owner_action_decision_unsupported", 422)
    if body.trading_mode is None:
        raise LonoraError("owner_action_trading_mode_required", 422)
    if row.status not in {"pending", "confirmed"}:
        return  # Expired or superseded: the same answer from the record.
    reason = await stale_reason(session, owner.id, row.kind, row.payload)
    if reason is not None:
        await settle(session, row, "expired", reason)
        return
    mode, withdrawn = await change_trading_mode(
        session, owner.id, row.payload["agent_id"], body.trading_mode, by="owner_tap"
    )
    # How many pending Trade Approval cards this tap withdrew, counted by the server (0 for
    # Ask, or when none was waiting).
    await settle(
        session,
        row,
        "confirmed",
        None,
        via="tap",
        result={"trading_mode": mode, "withdrawn": withdrawn},
    )


async def decide(
    session: AsyncSession,
    owner: OwnerIdentity,
    row: OwnerActionRow,
    body: OwnerActionDecision,
) -> None:
    if row.kind == "grant_authority":
        # The kind is gone. A leftover row is not signed.
        raise LonoraError("owner_action_kind_unsupported", 422)
    if row.kind == "trading_mode":
        await decide_trading_mode(session, owner, row, body)
        return
    if row.kind == "settle_operation" and (body.decision != "confirm" or body.outcome is None):
        # Settle Uncertain Operation: exactly Executed / Not executed / Unknown (10.3).
        raise LonoraError("owner_action_outcome_required", 422)
    desired = "confirmed" if body.decision == "confirm" else "cancelled"
    if row.status != "pending":
        # Idempotent per card: the same decision again answers from the record.
        if row.status == desired or row.status in {"expired", "superseded"}:
            return
        raise LonoraError("owner_action_already_decided", 409)
    if row.expires_at <= utcnow():
        await settle(session, row, "expired", "expired")
        return
    if desired == "cancelled":
        await settle(session, row, "cancelled", None, via="tap")
        return
    try:
        reason = await stale_reason(session, owner.id, row.kind, row.payload)
    except LonoraError as error:
        reason = error.code
    if reason is not None:
        await settle(session, row, "expired", reason)
        return
    if row.kind == "secret":
        # Its values come only through the card's own submit (``secret_cards``).
        raise LonoraError("owner_action_secret_values_required", 422)
    via = "tap"
    result: dict[str, Any] = {}
    if row.kind == "settle_operation":
        assert body.outcome is not None  # refused above without one
        if body.outcome == "unknown" and row.result.get("outcome") == "unknown":
            return  # Unknown again: already recorded; the card stays as it is.
        await attest_operation(
            session,
            owner.id,
            row.payload["operation_id"],
            OperationResolution(
                outcome=body.outcome,
                statement=CARD_ATTESTATION,
            ),
            {
                "kind": "owner",
                "owner_id": owner.id,
                "authentication": "owner_session",
                "session_ref": owner.token_hash[:16],
                "via": "owner_action_card",
                "owner_action_id": row.id,
            },
        )
        result = {"outcome": body.outcome}
        if body.outcome == "unknown":
            # Still uncertain, still held, still reconciled (6.3): the card stays the
            # owner's way to answer Executed or Not executed later (6.8).
            await keep_pending(session, row, {**row.result, **result})
            return
    elif row.kind == "supervision_paused":
        result = {"resumed": await owner_resumes(session, owner.id, row.payload["hold_id"])}
    await settle(session, row, "confirmed", None, via=via, result={**row.result, **result})
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
