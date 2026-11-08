"""Owner action cards: list, passkey challenge and the owner's decision.

Owner session only; no agent tool reaches these routes or the decision below. A
confirmation re-validates the card against current state (a stale card is settled as
expired with its reason), is idempotent per card, and then runs the existing owner
function for its effect: Stop/Resume (``apply_controls``), lifting a restriction
(``revoke_restriction``), the owner attestation of an uncertain operation
(``attest_operation``) or the account's execution policy (``store_execution_policy``).
Raising or removing a money limit also needs a verified passkey assertion bound to the
card's payload hash; lowering a limit, lifting a pause and resuming are one tap.
"""

from typing import Any

from fastapi import APIRouter, Depends, Request
from lonora_auth.devices import begin_bound_assertion, verify_bound_assertion
from lonora_auth.identity import OwnerIdentity
from lonora_contracts.domain import utcnow
from lonora_contracts.owner_actions import CARD_ATTESTATION, OwnerActionDecision
from lonora_contracts.trading import OperationResolution, TradingControl
from lonora_core.user_error import LonoraError
from lonora_db.owner_actions import (
    account_policy,
    card_facts,
    confirm_in_thread,
    live_status,
    lock_owner_actions,
    owned_card,
    owner_action_data,
    proposed_limits,
    settle,
    stale_reason,
    supersede_subject,
    thread_cards,
    widens,
)
from lonora_db.schema import OwnerActionRow
from lonora_db.super_bot import authority_lock
from lonora_db.trading_readiness import risk_limit_frame
from lonora_db.trading_restrictions import revoke_restriction
from lonora_db.transactions import owned_thread
from lonora_trading.controls import apply_controls
from lonora_trading.owner_controls import (
    attest_operation,
    require_account_currency,
    store_execution_policy,
)
from sqlalchemy.ext.asyncio import AsyncSession

from ..device_metadata import native_origins
from ..middleware.auth import require_owner, runtime
from ..runtime import ApiRuntime

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


@router.post("/{card_id}/challenge")
async def challenge(
    request: Request, card_id: str, owner: OwnerIdentity = Depends(require_owner)
) -> dict[str, Any]:
    rt = runtime(request)
    async with rt.db.sessions() as session, session.begin():
        await authority_lock(session, owner.id + ":devices")
        row = await owned_card(session, owner.id, card_id)
        if live_status(row) != "pending":
            raise LonoraError("owner_action_expired_or_decided", 409)
        _, passkey = await card_facts(session, row, utcnow())
        if not passkey:
            raise LonoraError("owner_action_passkey_not_needed", 409)
        return await begin_bound_assertion(
            session, owner, "owner_action", row.id, row.payload_hash, rt.settings.allowed_origin
        )


@router.post("/{card_id}/decision")
async def decision(
    request: Request,
    card_id: str,
    body: OwnerActionDecision,
    owner: OwnerIdentity = Depends(require_owner),
) -> dict[str, Any]:
    rt = runtime(request)
    if body.decision == "confirm":
        await check_currency(rt, owner, card_id)
    async with rt.db.sessions() as session, session.begin():
        await lock_owner_actions(session, owner.id)
        row = await owned_card(session, owner.id, card_id, lock=True)
        await decide(session, rt, owner, row, body)
        return await owner_action_data(session, row)


async def check_currency(rt: ApiRuntime, owner: OwnerIdentity, card_id: str) -> None:
    """Broker IO before the transaction: a limit amount in another currency is refused."""
    async with rt.db.sessions() as session:
        row = await owned_card(session, owner.id, card_id)
        if row.kind != "set_account_limits" or live_status(row) != "pending":
            return
        account_id = row.payload["account_id"]
        current = (await account_policy(session, owner.id, account_id)).risk
        try:
            currency = proposed_limits(current, row.payload).currency
        except LonoraError:
            return  # The decision settles an invalid change as expired.
    await require_account_currency(rt.services(owner.id).brokers, owner.id, account_id, currency)


async def decide(
    session: AsyncSession,
    rt: ApiRuntime,
    owner: OwnerIdentity,
    row: OwnerActionRow,
    body: OwnerActionDecision,
) -> None:
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
    via = "tap"
    result: dict[str, Any] = {}
    if row.kind == "resume_trading":
        controls = await apply_controls(session, TradingControl.model_validate(row.payload))
        result = {"global_trading": "running" if controls.enabled else "stopped"}
    elif row.kind == "lift_restriction":
        await revoke_restriction(
            session, owner.id, row.payload["restriction_id"], "Lifted by the owner from a card"
        )
    elif row.kind == "resolve_operation":
        if body.outcome is None:
            raise LonoraError("owner_action_outcome_required", 422)
        await attest_operation(
            session,
            owner.id,
            row.payload["operation_id"],
            OperationResolution(
                outcome=body.outcome,
                statement=(body.note or "").strip() or CARD_ATTESTATION,
                broker_reference=body.broker_reference,
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
    else:
        account_id = row.payload["account_id"]
        policy = await account_policy(session, owner.id, account_id)
        proposed = proposed_limits(policy.risk, row.payload)
        if widens(policy.risk, proposed):
            # Raising or removing a money limit widens what may be lost: passkey only.
            if body.proof is None:
                raise LonoraError("owner_action_passkey_required", 403)
            await verify_bound_assertion(
                session,
                owner,
                body.proof,
                "owner_action",
                row.id,
                row.payload_hash,
                rt.settings.allowed_origin,
                native_origins(rt.settings),
            )
            via = "passkey"
        stored = await store_execution_policy(
            session, owner.id, account_id, policy.model_copy(update={"risk": proposed})
        )
        result = {"limits": risk_limit_frame(account_id, stored)}
    await settle(session, row, "confirmed", None, via=via, result=result)
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
