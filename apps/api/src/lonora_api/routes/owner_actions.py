"""Owner action cards: list, passkey challenge and the owner's decision.

Owner session only; no agent tool reaches these routes or the decision below. A
confirmation re-validates the card against current state (a stale card is settled as
expired with its reason), is idempotent per card, and then runs the existing owner
function for its effect: Stop/Resume (``apply_controls``), lifting a restriction
(``revoke_restriction``), the owner attestation of an uncertain operation
(``attest_operation``), the account's execution policy (``store_execution_policy``),
an agent's model choice (``apply_agent_model``, W15-10: using a model, or Undo),
creating an agent (the creation service; never a grant), undoing a creation (the
owner's delete for an agent that has done nothing yet, otherwise a pause), setting,
undoing or restoring supervision, and the owner's own resume of work a supervisor
paused (``lonora_db.supervision``; never money authority), adding a source to the
trusted list (``lonora_db.trusted_sources``; an MCP server at the tier the owner picks,
with exactly the tools the card listed) and recording what a credential card's secure
form connected (only which resource; the value went straight to the owner API). A newly
connected MCP server's trust card follows in the same conversation; when its tools could
not be read or none can be trusted, the line says so and the agent that asked is woken
to check it, so nothing waits for a card that never comes.
Raising or removing a money limit also needs a verified passkey assertion bound to the
card's payload hash; lowering a limit, lifting a pause, resuming, creating an agent,
setting supervision, choosing a model and Undo are one tap.

A grant card signs through the existing account-authority ceremony: its challenge builds
the full-management proposal from the card's stored draft (``propose``) and returns the
WebAuthn options bound to that envelope (``begin_activation``); its confirmation verifies
the assertion (``finish_activation``). The card's other choices only narrow (the daily
loss limit, stopping another agent's grant) or widen nothing (Resume). Its one choice,
Custom or Full delegation, is a ``choose`` decision: it rewrites the stored draft the
next challenge signs and withdraws a proposal an earlier challenge prepared; it settles
nothing and grants nothing, and Full needs the same passkey confirmation as Custom. The
challenge names the choice the owner's card showed and is refused
(``owner_action_card_changed``) when another screen changed the stored choice since, so
the passkey never signs a choice the owner's screen did not show.
"""

from dataclasses import dataclass
from datetime import timedelta
from typing import Any, Literal

from fastapi import APIRouter, Body, Depends, Request
from lonora_auth.account_authority import begin_activation, finish_activation
from lonora_auth.devices import begin_bound_assertion, verify_bound_assertion
from lonora_auth.identity import OwnerIdentity
from lonora_contracts.domain import utcnow
from lonora_contracts.mcp import McpConnection
from lonora_contracts.owner_actions import (
    CARD_ATTESTATION,
    MODEL_CARD_KINDS,
    GrantDraft,
    OwnerActionChallenge,
    OwnerActionDecision,
)
from lonora_contracts.trading import OperationResolution, TradingControl
from lonora_core.user_error import LonoraError
from lonora_db.account_authority import owned_authority, propose, revoke
from lonora_db.agent_creation import (
    cancel_first_task,
    pause_agent,
    start_first_task,
    undo_plan,
)
from lonora_db.authority_lock import authority_lock
from lonora_db.capability_cards import connected_result, review_writes
from lonora_db.integrations import subscribe_feed
from lonora_db.model_cards import confirm_model_card, supersede_agent_model_cards
from lonora_db.notice_cards import undo_watch_change
from lonora_db.owner_actions import (
    account_policy,
    agent_names,
    card_facts,
    choose_delegation,
    confirm_in_thread,
    continue_after_card,
    daily_loss_change,
    global_trading,
    grant_conflicts,
    grant_facts,
    grant_proposal,
    live_status,
    lock_owner_actions,
    owned_account,
    owned_card,
    owner_action_data,
    proposed_limits,
    raise_created_card,
    raise_review_card,
    raise_supervision_card,
    renew_card,
    review_card_wanted,
    settle,
    stale_reason,
    supersede_subject,
    thread_cards,
    widens,
)
from lonora_db.schema import AgentRow, McpConnectionRow, OwnerActionRow, TradingJournalRow
from lonora_db.supervision import (
    grant_supervision,
    owned_grant,
    owner_resumes,
    revoke_supervision,
)
from lonora_db.threads import conversation_thread
from lonora_db.trading_readiness import risk_limit_frame
from lonora_db.trading_restrictions import create_restriction, revoke_restriction
from lonora_db.transactions import owned_thread
from lonora_db.trusted_sources import trust_source
from lonora_session.idempotency import stable_id
from lonora_tools.mcp import advertised_tools, review_payload
from lonora_trading.controls import apply_controls
from lonora_trading.owner_controls import (
    attest_operation,
    require_account_currency,
    store_execution_policy,
)
from lonora_trading.risk_limits import trading_day_start
from sqlalchemy.ext.asyncio import AsyncSession

from ..device_metadata import native_origins
from ..middleware.auth import require_owner, runtime
from ..runtime import ApiRuntime

router = APIRouter(prefix="/owner-actions")


@dataclass(frozen=True)
class ServerReview:
    """What the server just connected by a credential card offers to trust, read before
    the transaction: ``review`` (a trust card can follow), ``unread`` (its tools could not
    be read now), ``nothing_to_trust`` (every tool can move money or is unsupported) or
    ``disabled`` (the operator's deny override: only declared tools run)."""

    state: Literal["review", "unread", "nothing_to_trust", "disabled"]
    subject: str = ""
    payload: dict[str, Any] | None = None


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
    review: ServerReview | None = None
    if body.decision == "confirm":
        await check_currency(rt, owner, card_id, body)
        review = await connected_server_review(rt, owner, card_id, body)
    async with rt.db.sessions() as session, session.begin():
        await lock_owner_actions(session, owner.id)
        row = await owned_card(session, owner.id, card_id, lock=True)
        await decide(session, rt, owner, row, body, review)
        return await owner_action_data(session, row)


@router.post("/{card_id}/renew")
async def renew(
    request: Request, card_id: str, owner: OwnerIdentity = Depends(require_owner)
) -> dict[str, Any]:
    """«طلب جديد»: a fresh card for an expired one whose record still needs a decision
    (``owner_action_not_renewable`` otherwise). It decides nothing."""
    async with runtime(request).db.sessions() as session, session.begin():
        return await owner_action_data(session, await renew_card(session, owner.id, card_id))


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
    # The choice the owner's card showed: the one it names, or Custom when it sent the
    # own-positions switch only Custom shows. Another screen may have changed the stored
    # choice since (or the answer to a choice was lost): the passkey then signs nothing
    # and the card is read again, so it never signs Full while the card shows Custom.
    shown = body.delegation or ("custom" if body.allow_manual_positions is not None else None)
    if shown is not None and shown != draft.delegation:
        raise LonoraError("owner_action_card_changed", 409)
    if draft.delegation == "full":
        # Full delegation always includes the owner's own positions: the card says so
        # and shows no switch, so the passkey never signs anything else under it.
        if body.allow_manual_positions is not None:
            raise LonoraError("owner_action_full_delegation_terms_fixed", 422)
    elif body.allow_manual_positions is not None:
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


async def connected_server_review(
    rt: ApiRuntime, owner: OwnerIdentity, card_id: str, body: OwnerActionDecision
) -> ServerReview | None:
    """Before the transaction (network IO): the tools of the MCP server a credential
    card's form just connected, for the trust card that follows. None when this is not
    such a card; otherwise what can follow (``ServerReview``)."""
    connected = body.connected
    if connected is None or connected.resource != "mcp":
        return None
    async with rt.db.sessions() as session:
        row = await owned_card(session, owner.id, card_id)
        if row.kind != "connect_credential" or live_status(row) != "pending":
            return None
        if not rt.settings.mcp_owner_trust:
            return ServerReview("disabled")
        server = await session.get(McpConnectionRow, connected.id)
        if server is None or server.owner_id != owner.id:
            return None  # The decision refuses it (connected_result).
        config = McpConnection.model_validate(server.payload)
    if not config.enabled or config.transport != "http" or not config.url:
        return ServerReview("unread")
    try:
        tools = await advertised_tools(rt.services(owner.id).secrets, config)
        subject, payload = review_payload(connected.id, config.url, tools)
    except LonoraError:
        # Unreachable, a missing or wrong token, a timeout or an invalid list.
        return ServerReview("unread")
    if not payload["tools"]:
        return ServerReview("nothing_to_trust")
    return ServerReview("review", subject, payload)


async def review_state(session: AsyncSession, owner_id: str, review: ServerReview | None) -> str:
    """What the confirmation line and the agent learn about the connected server's
    review: ``raised`` when its trust card follows now."""
    if review is None:
        return "unread"
    if review.state != "review" or review.payload is None:
        return review.state
    return "raised" if await review_card_wanted(session, owner_id, review.payload) else "already"


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
    review: ServerReview | None = None,
) -> None:
    if body.decision == "choose":
        await choose(session, owner, row, body)
        return
    if body.pause_new_today and row.kind != "resolve_operation":
        raise LonoraError("owner_action_pause_unsupported", 422)
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
        first = (await global_trading(session))["changed_by"] == "default"
        controls = await apply_controls(session, TradingControl.model_validate(row.payload))
        result = {
            "global_trading": "running" if controls.enabled else "stopped",
            # Trading had never been started: the card said Start, its line says so too.
            "started": first,
        }
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
        if body.pause_new_today:
            # «أوقف الصفقات الجديدة اليوم» (Q11): the owner's own pause on the account
            # until the trading day ends there. It only narrows; one tap lifts it.
            result["restriction_id"] = await pause_new_today(session, owner, row)
    elif row.kind in MODEL_CARD_KINDS:
        result = await confirm_model_card(session, row)
    elif row.kind == "grant_authority":
        if body.proof is None:
            raise LonoraError("owner_action_passkey_required", 403)
        result = await confirm_grant(session, rt, owner, row, body)
        via = "passkey"
    elif row.kind == "create_agent":
        created = await create_agent_from_card(session, owner, row)
        result = {"agent_id": created.id, "agent_name": created.name}
    elif row.kind == "agent_created":
        undone = await undo_creation(session, owner, row)
        if undone is None:
            # Deleted by the owner while this tap waited: nothing is left to undo.
            await settle(session, row, "expired", "agent_already_removed")
            return
        result = undone
    elif row.kind == "supervise":
        granted = await supervise_from_card(session, owner, row)
        result = {"grant_ids": granted, "supervisor_id": row.payload["supervisor_id"]}
    elif row.kind == "supervision_created":
        revoked = await undo_supervision(session, owner, row)
        result = {"revoked": revoked}
    elif row.kind == "supervision_stopped":
        result = {"restored": await restore_supervision(session, owner, row)}
    elif row.kind == "supervision_paused":
        result = {"resumed": await owner_resumes(session, owner.id, row.payload["hold_id"])}
    elif row.kind == "watch_changed":
        # Undo: the expiry the watch had before the agent extended it (owner only).
        result = await undo_watch_change(session, owner.id, row.payload)
    elif row.kind == "trust_source":
        result = await trust_from_card(session, rt, owner, row, body)
    elif row.kind == "connect_credential":
        if body.connected is None:
            raise LonoraError("owner_action_connection_required", 422)
        result = await connected_result(
            session, owner.id, row.payload, body.connected.resource, body.connected.id
        )
        if row.payload["target"] == "mcp_server":
            result["review"] = await review_state(session, owner.id, review)
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
    await settle(session, row, "confirmed", None, via=via, result={**row.result, **result})
    created_agent = (
        await session.get(AgentRow, result["agent_id"]) if row.kind == "create_agent" else None
    )
    if row.kind == "supervise":
        # The same one-line result with Undo as a grant set from the owner's message.
        await raise_supervision_card(
            session,
            owner.id,
            result["grant_ids"],
            card_key=row.id,
            agent_id=row.agent_id,
            thread_id=row.thread_id,
            run_id=row.run_id,
        )
    if created_agent is not None:
        await raise_created_card(
            session,
            owner.id,
            created_agent,
            agent_id=row.agent_id,
            thread_id=row.thread_id,
            run_id=row.run_id,
        )
    await supersede_subject(
        session,
        owner.id,
        row.kind,
        row.subject,
        "done_by_another_card",
        keep=row.id,
        effect=row.payload_hash,
    )
    if row.kind in MODEL_CARD_KINDS:
        # The owner chose this agent's model: other requests and Undo about it end.
        await supersede_agent_model_cards(
            session, owner.id, row.payload["agent_id"], "owner_changed_model", keep=row.id
        )
    await confirm_in_thread(session, row)
    if created_agent is not None:
        # The agent that proposed it hands it its first task, after the line above.
        await start_first_task(session, row, created_agent)
    if row.kind == "connect_credential" and result.get("review") == "raised" and review:
        # The server the owner just connected: its tools on the next card to trust; the
        # agent continues once the owner taps it.
        await raise_review_card(
            session,
            owner.id,
            review.subject,
            review.payload or {},
            agent_id=row.agent_id,
            thread_id=row.thread_id,
            run_id=row.run_id,
        )
    elif row.kind in {"trust_source", "connect_credential"}:
        # The agent that asked continues the work that needed this source (or checks a
        # server whose tools could not be reviewed).
        await continue_after_card(session, row)


async def pause_new_today(session: AsyncSession, owner: OwnerIdentity, row: OwnerActionRow) -> str:
    """No new entries by any agent on the operation's account until the end of the
    account's trading day (its ``trading_day_timezone``); once per card."""
    operation = await session.get(TradingJournalRow, row.payload["operation_id"])
    assert operation is not None  # The attestation above read it.
    zone = (await account_policy(session, owner.id, operation.account_id)).risk
    day_end = trading_day_start(utcnow(), zone.trading_day_timezone) + timedelta(days=1)
    restriction = await create_restriction(
        session,
        owner.id,
        account_id=operation.account_id,
        action_class="no_new_entries",
        source="owner_ui",
        created_by_agent_id=None,
        valid_until=day_end,
        reason="Paused new trades for today from an uncertain trade's card",
        restriction_id=stable_id(row.id, "pause-new-today"),
    )
    return restriction.id


async def choose(
    session: AsyncSession, owner: OwnerIdentity, row: OwnerActionRow, body: OwnerActionDecision
) -> None:
    """The owner's choice on a pending grant card (Custom or Full delegation), stored in
    its draft. Nothing is signed or settled: the next challenge builds the envelope from
    the chosen draft, and a proposal prepared for the other choice is withdrawn."""
    if row.kind != "grant_authority":
        raise LonoraError("owner_action_choice_unsupported", 422)
    if body.delegation is None:
        raise LonoraError("owner_action_delegation_required", 422)
    if row.status != "pending":
        raise LonoraError("owner_action_expired_or_decided", 409)
    if row.expires_at <= utcnow():
        await settle(session, row, "expired", "expired")
        return
    if GrantDraft.model_validate(row.payload).delegation == body.delegation:
        return  # Already chosen: idempotent.
    await withdraw_grant(session, owner, row)
    await choose_delegation(session, row, body.delegation)


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
    # What the owner signs, read before the grant replaces the agent's current one: the
    # settled card keeps showing exactly this, with the choices applied below.
    signed = await grant_facts(session, row, {})
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
    # Full delegation has no daily loss line to opt out of: the account's own limits stay
    # as they are either way, and the confirmation says so once.
    money_limit = "apply" if draft.delegation == "full" else body.money_limit
    # The account lock the settings route takes before it reads the limits.
    await owned_account(session, owner.id, draft.account_id, lock=True)
    policy = await account_policy(session, owner.id, draft.account_id)
    change = daily_loss_change(policy.risk, draft) if money_limit == "apply" else None
    if change is not None:
        if widens(policy.risk, change):
            raise LonoraError("owner_action_limits_invalid", 422)
        await store_execution_policy(
            session, owner.id, draft.account_id, policy.model_copy(update={"risk": change})
        )
        daily = str(change.max_daily_loss)
    elif policy.risk.max_daily_loss is not None:
        kept = str(policy.risk.max_daily_loss)
    after = await account_policy(session, owner.id, draft.account_id)
    signed["money"] = {
        "limits": risk_limit_frame(draft.account_id, after),
        "daily_loss": {
            # The limit in force once signed: applied, kept, or none by the owner's choice.
            "current": None
            if after.risk.max_daily_loss is None
            else str(after.risk.max_daily_loss),
            "proposed": None,
            "currency": after.risk.currency,
            "basis": None,
            "percent": None,
            "requested_above": None,
        },
    }
    signed["grant"] = {
        **signed["grant"],
        "allow_manual_positions": bool(row.result.get("allow_manual_positions")),
    }
    signed["global_trading"] = await global_trading(session)
    # Decided now: the stopped agents are named in the result, the rest stay as they were.
    signed["conflicts"] = []
    return {
        "signed_facts": signed,
        "authority_id": authority.id,
        "delegation": draft.delegation,
        "allow_manual_positions": row.result.get("allow_manual_positions"),
        "resumed": resumed,
        "stopped_authorities": stopped,
        "stopped_agents": sorted(names.values()),
        "daily_loss": daily,
        # The account's own daily loss limit, unchanged by this card.
        "daily_loss_kept": kept,
        "money_limit": money_limit,
    }


async def trust_from_card(
    session: AsyncSession,
    rt: ApiRuntime,
    owner: OwnerIdentity,
    row: OwnerActionRow,
    body: OwnerActionDecision,
) -> dict[str, Any]:
    """The owner's tap adds the card's source to the trusted list (an MCP server with
    exactly the tools the card listed, at the tier the owner chose) and, for a feed
    domain, subscribes the feed the card names."""
    payload = row.payload
    kind = payload["source_kind"]
    if kind == "mcp_server":
        if not rt.settings.mcp_owner_trust:
            raise LonoraError("mcp_owner_trust_disabled", 403)
        if body.tier is None:
            raise LonoraError("owner_action_tier_required", 422)
        await trust_source(
            session,
            owner.id,
            kind,
            payload["identifier"],
            via="owner_card",
            tier=body.tier,
            agent_id=row.agent_id,
            card_id=row.id,
            endpoint_sha256=payload["endpoint_sha256"],
            tool_hashes=payload["tools"],
            read_only_tools=payload.get("read_only", []),
            blocked_tools=payload["blocked"],
        )
        return {
            "tier": body.tier,
            "tools": len(payload["tools"]),
            "writes": len(review_writes(payload)),
        }
    await trust_source(
        session,
        owner.id,
        kind,
        payload["identifier"],
        via="owner_card",
        agent_id=row.agent_id,
        card_id=row.id,
    )
    subscribe = payload.get("subscribe")
    if subscribe is None:
        return {"tier": "read"}
    _, created = await subscribe_feed(session, owner.id, subscribe["url"], subscribe["name"])
    return {"tier": "read", "subscribed": True, "subscription_created": created}


async def create_agent_from_card(
    session: AsyncSession, owner: OwnerIdentity, row: OwnerActionRow
) -> AgentRow:
    """The owner's tap creates the agent the card names, once (its id comes from the card)."""
    from lonora_agent.collaboration.agent_create import create_from_spec

    created, _ = await create_from_spec(
        session,
        owner.id,
        row.payload["spec"],
        agent_id=stable_id(row.id, "created-agent"),
        created_via="owner_card",
        created_by_agent_id=row.agent_id,
        source_message_id=None,
        run_id=row.run_id,
        card_id=row.id,
    )
    return created


async def supervise_from_card(
    session: AsyncSession, owner: OwnerIdentity, row: OwnerActionRow
) -> list[str]:
    """The owner's tap sets the supervision the card names; pairs already set stay as
    they are and are not part of this change (its Undo never takes them back)."""
    created: list[str] = []
    for agent_id in row.payload["supervised_ids"]:
        grant, new = await grant_supervision(
            session,
            owner.id,
            row.payload["supervisor_id"],
            agent_id,
            via="owner_card",
            created_by_agent_id=row.agent_id,
        )
        if new:
            created.append(grant.id)
    return created


async def restore_supervision(
    session: AsyncSession, owner: OwnerIdentity, row: OwnerActionRow
) -> int:
    """Restore: the grants stopped from chat are set again by the owner's tap; a pair
    supervised again meanwhile stays as it is."""
    restored = 0
    for grant_id in row.payload["grant_ids"]:
        stopped = await owned_grant(session, owner.id, grant_id)
        _, new = await grant_supervision(
            session,
            owner.id,
            stopped.supervisor_agent_id,
            stopped.supervised_agent_id,
            via="owner_card",
            created_by_agent_id=row.agent_id,
        )
        restored += new
    return restored


async def undo_supervision(session: AsyncSession, owner: OwnerIdentity, row: OwnerActionRow) -> int:
    """Undo: the grants this change set end now; reads and control stop at once."""
    revoked = 0
    for grant_id in row.payload["grant_ids"]:
        grant = await owned_grant(session, owner.id, grant_id)
        if grant.revoked_at is None:
            await revoke_supervision(session, owner.id, grant_id, via="owner_card")
            revoked += 1
    return revoked


async def undo_creation(
    session: AsyncSession, owner: OwnerIdentity, row: OwnerActionRow
) -> dict[str, Any] | None:
    """Undo: remove an agent that has done nothing yet, pause one that has. None when
    the owner deleted it while this tap waited for its lock."""
    from lonora_agent.collaboration.agent_create import delete_created_agent

    agent_id = row.payload["agent_id"]
    # Lock it first: a run or watch that starts now waits on this lock, so the plan below
    # never deletes work begun meanwhile.
    await authority_lock(session, agent_id)
    agent = await session.get(AgentRow, agent_id, with_for_update=True, populate_existing=True)
    if agent is None or agent.owner_id != owner.id:
        return None
    name = agent.name
    # The proposing agent's first-task run has not started: it never hands out a task.
    await cancel_first_task(session, owner.id, agent_id)
    if await undo_plan(session, owner.id, agent_id) == "delete":
        await delete_created_agent(session, owner.id, agent_id, keep_card=row.id)
        return {"undo": "deleted", "agent_name": name}
    await pause_agent(session, owner.id, agent_id)
    return {"undo": "paused", "agent_name": name}
