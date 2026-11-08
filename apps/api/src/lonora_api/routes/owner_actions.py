"""Owner action cards: list, passkey challenge and the owner's decision.

Owner session only; no agent tool reaches these routes or the decision below. A
confirmation re-validates the card against current state (a stale card is settled as
expired with its reason), is idempotent per card, and then runs the existing owner
function for its effect: Stop/Resume (``apply_controls``), lifting a restriction
(``revoke_restriction``), the owner attestation of an uncertain operation
(``attest_operation``) or the account's execution policy (``store_execution_policy``).
Raising or removing a money limit also needs a verified passkey assertion bound to the
card's payload hash; lowering a limit, lifting a pause and resuming are one tap.

A grant card signs through the existing account-authority ceremony: its challenge builds
the full-management proposal from the card's stored draft (``propose``) and returns the
WebAuthn options bound to that envelope (``begin_activation``); its confirmation verifies
the assertion (``finish_activation``). The card's other choices only narrow (the daily
loss limit, stopping another agent's grant) or widen nothing (Resume).
"""

from typing import Any

from fastapi import APIRouter, Body, Depends, Request
from lonora_auth.account_authority import begin_activation, finish_activation
from lonora_auth.devices import begin_bound_assertion, verify_bound_assertion
from lonora_auth.identity import OwnerIdentity
from lonora_contracts.domain import utcnow
from lonora_contracts.owner_actions import (
    CARD_ATTESTATION,
    GrantDraft,
    OwnerActionChallenge,
    OwnerActionDecision,
)
from lonora_contracts.trading import OperationResolution, TradingControl
from lonora_core.user_error import LonoraError
from lonora_db.account_authority import owned_authority, propose, revoke
from lonora_db.authority_lock import authority_lock
from lonora_db.owner_actions import (
    account_policy,
    agent_names,
    card_facts,
    confirm_in_thread,
    daily_loss_change,
    global_trading,
    grant_conflicts,
    grant_proposal,
    live_status,
    lock_owner_actions,
    owned_account,
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
from lonora_db.threads import conversation_thread
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
    request: Request,
    card_id: str,
    owner: OwnerIdentity = Depends(require_owner),
    body: OwnerActionChallenge | None = Body(default=None),
) -> dict[str, Any]:
    rt = runtime(request)
    async with rt.db.sessions() as session, session.begin():
        candidate = await owned_card(session, owner.id, card_id)
        if candidate.kind == "grant_authority":
            return await grant_challenge(
                session, rt, owner, card_id, body or OwnerActionChallenge()
            )
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
        await check_currency(rt, owner, card_id, body)
    async with rt.db.sessions() as session, session.begin():
        await lock_owner_actions(session, owner.id)
        row = await owned_card(session, owner.id, card_id, lock=True)
        await decide(session, rt, owner, row, body)
        return await owner_action_data(session, row)


async def grant_challenge(
    session: AsyncSession,
    rt: ApiRuntime,
    owner: OwnerIdentity,
    card_id: str,
    body: OwnerActionChallenge,
) -> dict[str, Any]:
    """Prepare the grant from the stored draft and ask for the passkey bound to it.

    The same locks, in the same order, as the decision: owner cards, the card, the
    owner's devices, then the agent (``propose``). Repeating it replaces the pending
    proposal; nothing is active until the decision verifies the assertion.
    """
    await lock_owner_actions(session, owner.id)
    row = await owned_card(session, owner.id, card_id, lock=True)
    if live_status(row) != "pending":
        raise LonoraError("owner_action_expired_or_decided", 409)
    reason = await stale_reason(session, owner.id, row.kind, row.payload)
    if reason is not None:
        raise LonoraError("owner_action_not_needed_" + reason, 409)
    await authority_lock(session, owner.id + ":devices")
    draft = GrantDraft.model_validate(row.payload)
    if body.allow_manual_positions is not None:
        # The owner's own switch on the card; it is part of what the passkey signs.
        draft = draft.model_copy(update={"allow_manual_positions": body.allow_manual_positions})
    # The grant belongs to the agent's own conversation, where its management Task runs.
    thread = await conversation_thread(session, owner.id, draft.agent_id)
    authority = await propose(session, owner.id, draft.agent_id, grant_proposal(draft, thread.id))
    row.result = {
        "authority_id": authority.id,
        "allow_manual_positions": draft.allow_manual_positions,
    }
    row.updated_at = utcnow()
    await session.flush()
    return await begin_activation(session, owner, authority.id, rt.settings.allowed_origin)


async def check_currency(
    rt: ApiRuntime, owner: OwnerIdentity, card_id: str, body: OwnerActionDecision
) -> None:
    """Broker IO before the transaction: a limit amount in another currency is refused."""
    async with rt.db.sessions() as session:
        row = await owned_card(session, owner.id, card_id)
        if live_status(row) != "pending":
            return
        if row.kind == "grant_authority":
            daily = GrantDraft.model_validate(row.payload).daily_loss
            if daily is not None and body.money_limit == "apply":
                await require_account_currency(
                    rt.services(owner.id).brokers,
                    owner.id,
                    row.payload["account_id"],
                    daily.currency,
                )
            return
        if row.kind != "set_account_limits":
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
        await withdraw_grant(session, owner, row)
        await settle(session, row, "cancelled", None, via="tap")
        return
    try:
        if row.kind == "set_account_limits":
            # The account lock the settings route takes before it reads: the change is
            # judged against, and merged into, the limits as they are now.
            await owned_account(session, owner.id, row.payload["account_id"], lock=True)
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
    elif row.kind == "grant_authority":
        if body.proof is None:
            raise LonoraError("owner_action_passkey_required", 403)
        result = await confirm_grant(session, rt, owner, row, body)
        via = "passkey"
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


async def withdraw_grant(session: AsyncSession, owner: OwnerIdentity, row: OwnerActionRow) -> None:
    """A dismissed grant card leaves no pending proposal behind."""
    identifier = row.result.get("authority_id") if row.kind == "grant_authority" else None
    if not isinstance(identifier, str):
        return
    pending = await owned_authority(session, owner.id, identifier)
    if pending.status == "pending":
        await revoke(session, owner.id, identifier)


async def confirm_grant(
    session: AsyncSession,
    rt: ApiRuntime,
    owner: OwnerIdentity,
    row: OwnerActionRow,
    body: OwnerActionDecision,
) -> dict[str, Any]:
    """Activate the card's own proposal with the owner's assertion, then the card's
    choices: stop other agents' grants there, resume, and the daily loss limit."""
    assert body.proof is not None
    identifier = row.result.get("authority_id")
    if not isinstance(identifier, str):
        raise LonoraError("owner_action_challenge_required", 409)
    authority = await finish_activation(
        session, owner, body.proof, rt.settings.allowed_origin, native_origins(rt.settings)
    )
    if authority.id != identifier:
        # An assertion for another grant never confirms this card (the transaction rolls back).
        raise LonoraError("device_proof_invalid", 403)
    draft = GrantDraft.model_validate(row.payload)
    conflicts = {item.id: item for item, _ in await grant_conflicts(session, owner.id, draft)}
    stopped: list[str] = []
    for other in sorted(set(body.stop_authorities)):
        if other not in conflicts:
            raise LonoraError("owner_action_conflict_not_found", 409)
        # Narrowing: that agent's whole grant on this account ends, every market of it.
        await revoke(session, owner.id, other)
        stopped.append(other)
    names = await agent_names(session, owner.id, {conflicts[item].agent_id for item in stopped})
    resumed = False
    if body.resume_trading and (await global_trading(session))["state"] == "stopped":
        await apply_controls(session, TradingControl(enabled=True, emergency_stop=False))
        resumed = True
    daily = kept = None
    # The account lock the settings route takes before it reads the limits.
    await owned_account(session, owner.id, draft.account_id, lock=True)
    policy = await account_policy(session, owner.id, draft.account_id)
    change = daily_loss_change(policy.risk, draft) if body.money_limit == "apply" else None
    if change is not None:
        if widens(policy.risk, change):
            raise LonoraError("owner_action_limits_invalid", 422)
        await store_execution_policy(
            session, owner.id, draft.account_id, policy.model_copy(update={"risk": change})
        )
        daily = str(change.max_daily_loss)
    elif policy.risk.max_daily_loss is not None:
        kept = str(policy.risk.max_daily_loss)
    return {
        "authority_id": authority.id,
        "allow_manual_positions": row.result.get("allow_manual_positions"),
        "resumed": resumed,
        "stopped_authorities": stopped,
        "stopped_agents": sorted(names.values()),
        "daily_loss": daily,
        # The account's own daily loss limit, unchanged by this card.
        "daily_loss_kept": kept,
        "money_limit": body.money_limit,
    }
