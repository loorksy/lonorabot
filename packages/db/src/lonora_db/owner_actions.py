"""Owner action cards: durable, single-use owner actions shown inside the conversation.

A card stores the exact effect it performs (``payload``, hashed) and the record it acts
on (``subject``). Agents propose cards through a tool and the runtime raises some from
events (an operation that became uncertain); only the owner's session
confirms one, through the existing owner function for that effect (see the owner
actions API route). Everything the owner sees on a card is derived here from the records
it names, at read time: never model text.
The one exception is a creation card's stored task, the exact standing instruction the
tap keeps, which the card quotes labelled as the agent's task.

A card is pending until it is confirmed, cancelled, superseded (its record changed, or
another card did the same thing) or expired. Expiry needs no scheduler: a pending card
past ``expires_at`` reads as expired and is settled as expired when next touched.
"""

from datetime import datetime, timedelta
from decimal import Decimal
from typing import Any, cast

from lonora_contracts.account_authority import (
    ALL_AUTHORITY_ACTIONS,
    AccountAuthorityEnvelope,
    AccountAuthorityProposal,
    AuthorityAction,
    full_delegation,
)
from lonora_contracts.domain import new_id, utcnow
from lonora_contracts.execution_quality import ExecutionPolicy
from lonora_contracts.owner_actions import (
    GrantDelegation,
    GrantDraft,
    OwnerActionProposal,
)
from lonora_contracts.risk_limits import MonetaryRiskLimits
from lonora_contracts.trading import UNRESOLVED_STATUSES, TradingControl
from lonora_core.user_error import LonoraError, ToolRefusal
from lonora_session.idempotency import request_hash, stable_id
from pydantic import ValidationError
from sqlalchemy import ColumnElement, func, or_, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from .events import emit
from .schema import (
    AccountAuthorityRow,
    AgentRow,
    AttentionRow,
    BrokerSessionRow,
    OwnerActionRow,
    RunRow,
    SupervisionGrantRow,
    SupervisionHoldRow,
    ThreadRow,
    TradingJournalRow,
)
from .trading_readiness import RISK_LIMIT_NAMES, global_trading, risk_limit_frame
from .transactions import SettingsRepository, execution_policy_key, owned_thread

# How long a card stays usable.
LIFETIME = {
    "resume_trading": timedelta(hours=24),
    "resolve_operation": timedelta(days=7),
    "set_account_limits": timedelta(hours=24),
    "grant_authority": timedelta(hours=24),
    # An agent's proposal to create an agent, and the Undo card after a creation.
    "create_agent": timedelta(hours=24),
    "agent_created": timedelta(days=7),
    # An agent's proposal to set supervision, the Undo card after one is set, and the
    # Restore card after supervision was stopped from chat.
    "supervise": timedelta(hours=24),
    "supervision_created": timedelta(days=7),
    "supervision_stopped": timedelta(days=7),
    # A supervisor paused an agent's work: who did it, with Resume, while it holds.
    "supervision_paused": timedelta(days=31),
    # Add a source to the trusted list, or connect an account or credential (W15-8).
    "trust_source": timedelta(days=7),
    "connect_credential": timedelta(days=7),
    # Changes an agent made without asking (Q31): Undo of an extended watch, and the
    # notice of a tightened stop (recorded settled, nothing to tap).
    "watch_changed": timedelta(days=7),
    "stop_tightened": timedelta(days=7),
}
GRANT_HOURS = {"until_stopped": None, "12h": 12, "24h": 24, "7d": 168}
ALL_ACTIONS: tuple[AuthorityAction, ...] = ALL_AUTHORITY_ACTIONS
# Pending cards one agent may have proposed at once; runtime cards do not count.
MAXIMUM_PENDING_PER_AGENT = 5
# What an agent reads when it has that many cards waiting already.
CARDS_WAITING: dict[str, Any] = {
    "class": "permission",
    "retryable": False,
    "hint": "Enough cards are already waiting for the owner. Raise no more now: point the "
    "owner to the ones waiting, or come back to it once one is decided.",
}
UPPER_LIMITS = (
    "max_trade_risk",
    "max_trade_risk_equity_percent",
    "max_daily_loss",
    "max_open_risk",
    "max_open_risk_equity_percent",
)
# Every field a limits card can change, in the order its lines show them. A card shows a
# line for each one that differs, so it never signs an effect the owner did not see.
LIMIT_CHANGE_NAMES = ("currency", *RISK_LIMIT_NAMES, "trading_day_timezone")


def payload_hash(kind: str, payload: dict[str, Any]) -> str:
    return request_hash({"kind": kind, "payload": payload})


def live_status(row: OwnerActionRow, now: datetime | None = None) -> str:
    if row.status == "pending" and row.expires_at <= (now or utcnow()):
        return "expired"
    return row.status


def proposed_limits(current: MonetaryRiskLimits, payload: dict[str, Any]) -> MonetaryRiskLimits:
    """The account's limits after the card's exact changes; other limits stay as they are."""
    values = current.model_dump()
    values.update({name: Decimal(str(value)) for name, value in payload["set"].items()})
    values.update({name: None for name in payload["remove"]})
    for name in ("currency", "trading_day_timezone"):
        if payload.get(name) is not None:
            values[name] = payload[name]
    try:
        return MonetaryRiskLimits.model_validate(values)
    except ValidationError as error:
        raise LonoraError("owner_action_limits_invalid", 422) from error


def widens(current: MonetaryRiskLimits, proposed: MonetaryRiskLimits) -> bool:
    """Whether new limits admit more risk anywhere: raising or removing a ceiling, lowering
    or removing the free-margin floor, re-denominating set amounts or moving the day."""
    for name in UPPER_LIMITS:
        old, new = getattr(current, name), getattr(proposed, name)
        if old is not None and (new is None or new > old):
            return True
    floor, new_floor = current.min_free_margin, proposed.min_free_margin
    if floor is not None and (new_floor is None or new_floor < floor):
        return True
    amounts = any(
        getattr(current, name) is not None
        for name in ("max_trade_risk", "max_daily_loss", "max_open_risk", "min_free_margin")
    )
    if amounts and proposed.currency != current.currency:
        return True
    return (
        current.max_daily_loss is not None
        and proposed.trading_day_timezone != current.trading_day_timezone
    )


# Execution caps the executor enforces next to the money limits: raising or removing one
# admits more risk too (exposure and execution-quality gates).
POLICY_CEILINGS = (
    "max_spread",
    "max_entry_drift_stop_fraction",
    "max_positions",
    "max_pending_orders",
    "max_symbol_direction_volume",
)
# Freshness bounds: a larger age accepts staler quotes and account state.
POLICY_AGES = ("quote_max_age_seconds", "account_max_age_seconds")


def policy_widens(current: ExecutionPolicy, proposed: ExecutionPolicy) -> bool:
    """Whether a new execution policy admits more risk anywhere: a money limit
    (``widens``), an execution cap raised or removed, or an older quote or account
    accepted."""
    if widens(current.risk, proposed.risk):
        return True
    for name in POLICY_CEILINGS:
        old, new = getattr(current, name), getattr(proposed, name)
        if old is not None and (new is None or new > old):
            return True
    return any(getattr(proposed, name) > getattr(current, name) for name in POLICY_AGES)


async def account_policy(session: AsyncSession, owner_id: str, account_id: str) -> ExecutionPolicy:
    return ExecutionPolicy.model_validate(
        await SettingsRepository().get(session, execution_policy_key(owner_id, account_id))
    )


async def owned_account(
    session: AsyncSession, owner_id: str, account_id: str, *, lock: bool = False
) -> BrokerSessionRow:
    row = await session.get(
        BrokerSessionRow, account_id, with_for_update=lock, populate_existing=lock
    )
    if row is None or row.owner_id != owner_id:
        raise LonoraError("broker_session_not_found", 404)
    return row


def _mapping(value: Any) -> dict[str, Any]:
    return cast(dict[str, Any], value) if isinstance(value, dict) else {}


def account_facts(row: BrokerSessionRow | None, account_id: str) -> dict[str, Any]:
    """The broker identity the owner recognizes; no connection secret or raw state."""
    label = None
    identity = _mapping(row.state.get("broker_identity")) if row else {}
    if row is not None and identity.get("connection_version") == row.version:
        parts: list[Any] = [identity.get(key) for key in ("broker", "login", "server")]
        label = " · ".join(str(part) for part in parts if isinstance(part, str) and part) or None
    return {
        "id": account_id,
        "label": label,
        "provider": row.payload.get("provider") if row else None,
    }


async def stale_reason(
    session: AsyncSession, owner_id: str, kind: str, payload: dict[str, Any]
) -> str | None:
    """Why the card's effect no longer applies to current state, or None if it does.

    Raises when the record it names is not the owner's: such a card is never created.
    """
    if kind == "resume_trading":
        return (
            "trading_already_running"
            if (await global_trading(session))["state"] == "running"
            else None
        )
    if kind == "resolve_operation":
        operation = await session.get(TradingJournalRow, payload["operation_id"])
        if operation is None or operation.owner_id != owner_id:
            raise LonoraError("operation_not_found", 404)
        return None if operation.status == "ambiguous" else "operation_already_settled"
    if kind == "set_account_limits":
        await owned_account(session, owner_id, payload["account_id"])
        current = (await account_policy(session, owner_id, payload["account_id"])).risk
        return "limits_already_set" if proposed_limits(current, payload) == current else None
    if kind == "grant_authority":
        from .agent_binding import (
            account_wide_scope,
            assert_market_binding,
            require_financial_agent,
        )

        draft = GrantDraft.model_validate(payload)
        agent = await require_financial_agent(session, owner_id, draft.agent_id)
        await owned_account(session, owner_id, draft.account_id)
        # The same scope rules the signed envelope is held to (validate_scope).
        if draft.symbol_scope == "account" and not account_wide_scope(agent):
            raise LonoraError("account_authority_scope_mismatch", 403)
        for symbol in draft.symbols:
            assert_market_binding(agent, draft.account_id, symbol)
        covered = await covering_grant(session, owner_id, draft)
        return "grant_already_active" if covered is not None else None
    if kind == "create_agent":
        from .agent_creation import check_creation, existing_creation

        spec = payload["spec"]
        # The owner already had it created another way (said yes in chat, another card).
        if await existing_creation(session, owner_id, spec["template"], spec["name"]):
            return "agent_already_created"
        try:
            await check_creation(session, owner_id, spec)
        except LonoraError as error:
            return CREATION_STALE.get(error.code, "agent_creation_unavailable")
        return None
    if kind == "agent_created":
        agent = await session.get(AgentRow, payload["agent_id"])
        return "agent_already_removed" if agent is None or agent.owner_id != owner_id else None
    if kind == "supervise":
        from .supervision import supervises

        supervisor = str(payload["supervisor_id"])
        wanted = [str(item) for item in payload["supervised_ids"]]
        names = await agent_names(session, owner_id, {supervisor, *wanted})
        if any(item not in names for item in (supervisor, *wanted)):
            return "supervision_agent_missing"
        for item in wanted:
            if not await supervises(session, owner_id, supervisor, item):
                return None
        return "supervision_already_set"
    if kind == "supervision_created":
        return None if await _active_grants(session, owner_id, payload) else "supervision_ended"
    if kind == "supervision_stopped":
        grants = await _stopped_grants(session, owner_id, payload)
        if not grants:
            return "supervision_agent_missing"
        return None if await _restorable(session, owner_id, grants) else "supervision_already_set"
    if kind in {"trust_source", "connect_credential"}:
        from .capability_cards import stale_reason as capability_stale

        return await capability_stale(session, owner_id, kind, payload)
    if kind == "watch_changed":
        from .notice_cards import watch_change_stale

        return await watch_change_stale(session, owner_id, payload)
    if kind == "stop_tightened":
        return "nothing_to_undo"
    if kind == "supervision_paused":
        hold = await _live_pause(session, owner_id, payload)
        if hold is None:
            return "supervision_pause_ended"
        if hold.target_kind == "watch":
            from .market_watches import watch_past_expiry

            # Resuming it needs a later expiry first (the watch list), not this card.
            if await watch_past_expiry(session, hold.target_id):
                return "watch_expired"
        return None
    raise LonoraError("owner_action_kind_unsupported", 422)


async def active_grants(
    session: AsyncSession, owner_id: str, account_id: str
) -> list[tuple[AccountAuthorityRow, AccountAuthorityEnvelope]]:
    """Every signed grant in force on the account, each re-validated as the executor does."""
    from .account_authority import require_authority

    rows = await session.scalars(
        select(AccountAuthorityRow)
        .where(
            AccountAuthorityRow.owner_id == owner_id,
            AccountAuthorityRow.account_id == account_id,
            AccountAuthorityRow.status == "active",
        )
        .order_by(AccountAuthorityRow.created_at, AccountAuthorityRow.id)
    )
    result: list[tuple[AccountAuthorityRow, AccountAuthorityEnvelope]] = []
    for row in rows:
        try:
            result.append(await require_authority(session, owner_id, row.agent_id, row.id))
        except LonoraError:
            continue
    return result


def covers_draft(envelope: AccountAuthorityEnvelope, draft: GrantDraft) -> bool:
    """Whether a signed grant already allows everything the draft would."""
    hours = GRANT_HOURS[draft.duration]
    return (
        envelope.management_mode == "full"
        and all(
            getattr(envelope, name) is None
            for name in (
                "maximum_order_volume",
                "maximum_symbol_volume",
                "maximum_positions",
                "maximum_pending_orders",
                "maximum_actions",
                "minimum_equity",
            )
        )
        and (
            envelope.symbol_scope == "account"
            or draft.symbol_scope == "selected"
            and set(draft.symbols) <= set(envelope.symbols)
        )
        and set(draft.actions) <= set(envelope.actions)
        and (envelope.allow_manual_positions or not draft.allow_manual_positions)
        and (
            envelope.valid_until is None
            or hours is not None
            and envelope.valid_until >= utcnow() + timedelta(hours=hours)
        )
    )


def overlaps_draft(envelope: AccountAuthorityEnvelope, draft: GrantDraft) -> bool:
    if envelope.symbol_scope == "account" or draft.symbol_scope == "account":
        return True
    mine = {symbol.casefold() for symbol in draft.symbols}
    return any(symbol.casefold() in mine for symbol in envelope.symbols)


async def covering_grant(
    session: AsyncSession, owner_id: str, draft: GrantDraft
) -> AccountAuthorityRow | None:
    """The agent's own grant that already covers the draft: no card is needed."""
    for row, envelope in await active_grants(session, owner_id, draft.account_id):
        if row.agent_id == draft.agent_id and covers_draft(envelope, draft):
            return row
    return None


async def grant_conflicts(
    session: AsyncSession, owner_id: str, draft: GrantDraft
) -> list[tuple[AccountAuthorityRow, AccountAuthorityEnvelope]]:
    """Other agents' grants in force on the same account and an overlapping market."""
    return [
        (row, envelope)
        for row, envelope in await active_grants(session, owner_id, draft.account_id)
        if row.agent_id != draft.agent_id and overlaps_draft(envelope, draft)
    ]


def full_delegation_available(agent: AgentRow) -> bool:
    """Full delegation covers every pair on the account: only an agent whose grant may
    be account-wide (Lonora, or a flexible root agent) can be offered it."""
    from .agent_binding import account_wide_scope

    return account_wide_scope(agent)


async def choose_delegation(
    session: AsyncSession, row: OwnerActionRow, choice: GrantDelegation
) -> bool:
    """The owner's choice on a pending grant card, stored in its draft: the card's
    payload (and its hash) become the chosen draft, so the next challenge builds the
    envelope from it. Returns whether anything changed. The caller holds the owner cards
    lock and the card, and withdraws a proposal an earlier challenge prepared."""
    from .agent_binding import require_financial_agent

    draft = GrantDraft.model_validate(row.payload)
    if draft.delegation == choice:
        return False
    if choice == "full":
        agent = await require_financial_agent(session, row.owner_id, draft.agent_id)
        if not full_delegation_available(agent):
            raise LonoraError("owner_action_full_delegation_unavailable", 409)
    chosen = draft.with_delegation(choice)
    payload = chosen.model_dump(mode="json")
    digest = payload_hash(row.kind, payload)
    # The same agent's other pending card that already asks for exactly this: one card
    # per effect, so that one gives way to the card the owner is choosing on.
    duplicate = await pending_effect(session, row.agent_id, row.kind, digest)
    if duplicate is not None and duplicate.id != row.id:
        await settle(session, duplicate, "superseded", "same_choice_on_another_card")
    row.payload = payload
    row.payload_hash = digest
    row.result = {}
    row.updated_at = utcnow()
    await session.flush()
    await owner_action_event(session, row)
    return True


def grant_proposal(
    draft: GrantDraft, thread_id: str, now: datetime | None = None
) -> AccountAuthorityProposal:
    """The exact full-management proposal the card signs: built from the stored draft
    only, the same shape the permission composer sends for the same choices."""
    hours = GRANT_HOURS[draft.duration]
    return AccountAuthorityProposal(
        thread_id=thread_id,
        account_id=draft.account_id,
        management_mode="full",
        symbol_scope=draft.symbol_scope,
        symbols=list(draft.symbols),
        actions=list(draft.actions),
        valid_until=None if hours is None else (now or utcnow()) + timedelta(hours=hours),
        allow_manual_positions=draft.allow_manual_positions,
    )


def daily_loss_change(current: MonetaryRiskLimits, draft: GrantDraft) -> MonetaryRiskLimits | None:
    """The account limits after the card's daily loss limit, or None when it changes
    nothing. A suggested limit is set only where the account has none; a limit from the
    owner's own words may also lower the current one. It never raises one, so it never
    widens, and it never tightens a limit the owner set without being asked."""
    daily = draft.daily_loss
    if daily is None:
        return None
    if current.currency is not None and current.currency != daily.currency:
        return None
    if current.max_daily_loss is not None and (
        daily.basis != "requested" or daily.amount >= current.max_daily_loss
    ):
        return None
    return current.model_copy(update={"max_daily_loss": daily.amount, "currency": daily.currency})


def requested_above(current: MonetaryRiskLimits, draft: GrantDraft) -> Decimal | None:
    """The owner's own daily loss amount when it is above the account's current limit:
    the grant card keeps the current limit, and raising it needs a limits card."""
    daily = draft.daily_loss
    if (
        daily is None
        or daily.basis != "requested"
        or current.max_daily_loss is None
        or current.currency not in {None, daily.currency}
        or daily.amount <= current.max_daily_loss
    ):
        return None
    return daily.amount


def grant_terms(envelope: AccountAuthorityEnvelope) -> dict[str, Any]:
    """Everything a signed grant allows, for the card that replaces it: its markets,
    actions, caps, protections, expiry and the owner's own positions."""
    return {
        "management_mode": envelope.management_mode,
        "symbol_scope": envelope.symbol_scope,
        "symbols": list(envelope.symbols),
        "actions": list(envelope.actions),
        "all_actions": set(envelope.actions) == set(ALL_ACTIONS),
        **{
            name: None if getattr(envelope, name) is None else str(getattr(envelope, name))
            for name in ("maximum_order_volume", "maximum_symbol_volume", "minimum_equity")
        },
        "maximum_positions": envelope.maximum_positions,
        "maximum_pending_orders": envelope.maximum_pending_orders,
        "maximum_actions": envelope.maximum_actions,
        "valid_until": None if envelope.valid_until is None else envelope.valid_until.isoformat(),
        "allow_manual_positions": envelope.allow_manual_positions,
        "full_delegation": full_delegation(envelope.model_dump()),
    }


async def _stopped_grants(
    session: AsyncSession, owner_id: str, payload: dict[str, Any]
) -> list[SupervisionGrantRow]:
    """The revoked grants a Restore card names (a deleted agent's grants are gone)."""
    ids = [str(item) for item in payload.get("grant_ids", [])]
    if not ids:
        return []
    return list(
        await session.scalars(
            select(SupervisionGrantRow)
            .where(SupervisionGrantRow.owner_id == owner_id, SupervisionGrantRow.id.in_(ids))
            .order_by(SupervisionGrantRow.created_at, SupervisionGrantRow.id)
        )
    )


async def _restorable(
    session: AsyncSession, owner_id: str, grants: list[SupervisionGrantRow]
) -> list[SupervisionGrantRow]:
    """The stopped grants whose pair is not supervised again by now."""
    from .supervision import supervises

    return [
        grant
        for grant in grants
        if not await supervises(
            session, owner_id, grant.supervisor_agent_id, grant.supervised_agent_id
        )
    ]


async def _live_pause(
    session: AsyncSession, owner_id: str, payload: dict[str, Any]
) -> SupervisionHoldRow | None:
    """The hold a pause card names while it still holds paused work."""
    from .supervision import work_paused

    hold = await session.get(SupervisionHoldRow, payload["hold_id"])
    if hold is None or hold.owner_id != owner_id or hold.released_at is not None:
        return None
    return hold if await work_paused(session, hold.target_kind, hold.target_id) else None


async def _active_grants(
    session: AsyncSession, owner_id: str, payload: dict[str, Any]
) -> list[SupervisionGrantRow]:
    """The grants a supervision card set that are still in force."""
    ids = [str(item) for item in payload.get("grant_ids", [])]
    if not ids:
        return []
    return list(
        await session.scalars(
            select(SupervisionGrantRow)
            .where(
                SupervisionGrantRow.owner_id == owner_id,
                SupervisionGrantRow.id.in_(ids),
                SupervisionGrantRow.revoked_at.is_(None),
            )
            .order_by(SupervisionGrantRow.created_at, SupervisionGrantRow.id)
        )
    )


# Why a creation card no longer applies, by the refusal its re-check raised.
CREATION_STALE = {
    "agent_not_found": "agent_report_to_missing",
    "agent_report_to_invalid": "agent_report_to_missing",
    "agent_supervises_missing": "supervision_agent_missing",
    "broker_sessions_not_found": "broker_connection_changed",
    "broker_connection_changed": "broker_connection_changed",
}


def proposal_payload(
    proposal: OwnerActionProposal, grant: GrantDraft | None = None
) -> tuple[str, dict[str, Any]]:
    """The card's exact stored effect and the record it acts on."""
    if proposal.kind == "grant_authority":
        if grant is None:
            raise LonoraError("owner_action_fields_invalid", 422)
        return "grant:" + grant.agent_id + ":" + grant.account_id, grant.model_dump(mode="json")
    if proposal.kind == "resume_trading":
        return "trading", TradingControl(enabled=True, emergency_stop=False).model_dump()
    if proposal.kind == "resolve_operation":
        assert proposal.operation_id is not None
        return "operation:" + proposal.operation_id, {"operation_id": proposal.operation_id}
    if proposal.kind in {"trust_source", "connect_credential"}:
        from .capability_cards import credential_payload, source_payload, trust_subject

        if proposal.kind == "connect_credential":
            assert proposal.target is not None
            return credential_payload(proposal.target, proposal.service)
        # An MCP server's card carries the tools read from the server (``propose_capability``).
        if proposal.source_kind == "mcp_server" or proposal.identifier is None:
            raise LonoraError("owner_action_fields_invalid", 422)
        assert proposal.source_kind is not None
        return trust_subject(proposal.source_kind, proposal.identifier), source_payload(
            proposal.source_kind, proposal.identifier
        )
    assert proposal.account_id is not None
    return "account:" + proposal.account_id, {
        "account_id": proposal.account_id,
        "set": {name: str(value) for name, value in sorted(proposal.set_limits.items())},
        "remove": sorted(set(proposal.remove_limits)),
        "currency": proposal.currency,
        "trading_day_timezone": proposal.trading_day_timezone,
    }


async def agent_names(
    session: AsyncSession, owner_id: str, ids: set[str] | set[str | None]
) -> dict[str, str]:
    wanted = sorted({identifier for identifier in ids if identifier})
    if not wanted:
        return {}
    rows = await session.scalars(
        select(AgentRow).where(AgentRow.owner_id == owner_id, AgentRow.id.in_(wanted))
    )
    return {row.id: row.name for row in rows}


async def several_accounts(session: AsyncSession, owner_id: str) -> bool:
    count = await session.scalar(
        select(func.count())
        .select_from(BrokerSessionRow)
        .where(BrokerSessionRow.owner_id == owner_id)
    )
    return (count or 0) > 1


def _execution_agent(row: TradingJournalRow) -> str | None:
    agent = _mapping(_mapping(row.result.get("details")).get("execution")).get("agent_id")
    return agent if isinstance(agent, str) else None


async def card_facts(
    session: AsyncSession, row: OwnerActionRow, now: datetime
) -> tuple[dict[str, Any], bool]:
    """Server facts the card shows, read now from the records it names; and whether the
    owner's confirmation needs a passkey (widening money limits)."""
    owner_id, payload = row.owner_id, row.payload
    facts: dict[str, Any] = {"several_accounts": await several_accounts(session, owner_id)}
    if row.kind == "resume_trading":
        facts["global_trading"] = await global_trading(session)
        return facts, False
    if row.kind == "resolve_operation":
        operation = await session.get(TradingJournalRow, payload["operation_id"])
        if operation is None:
            return facts, False
        request = operation.request
        producer = _execution_agent(operation)
        names = await agent_names(session, owner_id, {producer} if producer else set())
        facts["account"] = account_facts(
            await session.get(BrokerSessionRow, operation.account_id), operation.account_id
        )
        facts["operation"] = {
            "operation_id": operation.operation_id,
            "action": request.get("action"),
            "symbol": request.get("symbol"),
            "volume": None if request.get("volume") is None else str(request["volume"]),
            "price": None if request.get("price") is None else str(request["price"]),
            "has_ticket": bool(request.get("position_id") or request.get("order_id")),
            "status": operation.status,
            "submitted_at": operation.submitted_at.isoformat() if operation.submitted_at else None,
            "by_agent_name": names.get(producer or ""),
            "by_owner": producer is None,
        }
        facts["blocks"] = "new_risk_on_this_symbol_or_ticket"
        return facts, False
    if row.kind == "grant_authority":
        return await grant_facts(session, row, facts), True
    if row.kind in {"create_agent", "agent_created"}:
        return await creation_facts(session, row, facts), False
    if row.kind in {"supervise", "supervision_created", "supervision_stopped"}:
        return await supervision_facts(session, row, facts), False
    if row.kind == "supervision_paused":
        return await pause_facts(session, row, facts), False
    if row.kind in {"watch_changed", "stop_tightened"}:
        from .notice_cards import notice_facts

        return await notice_facts(session, row, facts), False
    if row.kind in {"trust_source", "connect_credential"}:
        from .capability_cards import card_facts as capability_facts

        return await capability_facts(session, row, facts), False
    account_id = payload["account_id"]
    facts["account"] = account_facts(await session.get(BrokerSessionRow, account_id), account_id)
    current = (await account_policy(session, owner_id, account_id)).risk
    facts["current"] = risk_limit_frame(account_id, ExecutionPolicy(risk=current))
    try:
        proposed = proposed_limits(current, payload)
    except LonoraError:
        # The limits changed since the card was raised and its change no longer fits
        # them: confirming only settles it, so no passkey ceremony is asked for.
        facts["no_longer_applies"] = True
        return facts, False
    facts["proposed"] = risk_limit_frame(account_id, ExecutionPolicy(risk=proposed))
    facts["changes"] = limit_changes(current, proposed)
    return facts, widens(current, proposed)


async def grant_facts(
    session: AsyncSession, row: OwnerActionRow, facts: dict[str, Any]
) -> dict[str, Any]:
    """What the owner signs, read now: the agent, account, markets, actions, duration,
    their own positions, the account's money limits and daily loss line, Stop new
    trading, other agents already trading that market and the grant it replaces.

    Once signed the card shows what was signed, as stored at that moment
    (``signed_facts``): later limits or grants never rewrite it, it never names the
    grant it created as the one it replaced, and the daily loss line is the limit the
    owner's choice left in force (applied, kept or none)."""
    signed = row.result.get("signed_facts")
    if row.status != "pending" and isinstance(signed, dict):
        facts.update(cast(dict[str, Any], signed))
        return facts
    owner_id = row.owner_id
    draft = GrantDraft.model_validate(row.payload)
    conflicts = await grant_conflicts(session, owner_id, draft)
    names = await agent_names(
        session, owner_id, {draft.agent_id, *(item.agent_id for item, _ in conflicts)}
    )
    grantee = await session.get(AgentRow, draft.agent_id)
    account = await session.get(BrokerSessionRow, draft.account_id)
    facts["account"] = account_facts(account, draft.account_id)
    known: dict[str, Any] = account.state.get("contracts", {}) if account is not None else {}
    # Full delegation always includes the owner's own positions; under Custom the
    # owner's switch, once sent with a challenge, is what is signed.
    allow_manual = (
        True
        if draft.delegation == "full"
        else row.result.get("allow_manual_positions", draft.allow_manual_positions)
    )
    facts["grant"] = {
        "agent_name": names.get(draft.agent_id),
        "agent_is_personal": grantee is not None and grantee.role == "personal",
        "symbol_scope": draft.symbol_scope,
        "symbols": list(draft.symbols),
        # The broker's own specification of each named symbol, as read for this account.
        "contracts": [known[symbol] for symbol in draft.symbols if symbol in known],
        "actions": list(draft.actions),
        "all_actions": set(draft.actions) == set(ALL_ACTIONS),
        "duration": draft.duration,
        "allow_manual_positions": bool(allow_manual),
        # The card's one choice, and whether Full delegation can be offered at all: a
        # fixed-market agent's grant never covers every pair on the account.
        "delegation": draft.delegation,
        "full_available": grantee is not None and full_delegation_available(grantee),
    }
    policy = await account_policy(session, owner_id, draft.account_id)
    change = daily_loss_change(policy.risk, draft)
    above = requested_above(policy.risk, draft)
    daily = draft.daily_loss
    facts["money"] = {
        "limits": risk_limit_frame(draft.account_id, policy),
        "daily_loss": {
            "current": None
            if policy.risk.max_daily_loss is None
            else str(policy.risk.max_daily_loss),
            "proposed": None if change is None or daily is None else str(daily.amount),
            "currency": policy.risk.currency or (daily.currency if daily else None),
            "basis": daily.basis if daily else None,
            "percent": None if daily is None or daily.percent is None else str(daily.percent),
            # The owner asked for more than the current limit: the card keeps it.
            "requested_above": None if above is None else str(above),
        },
    }
    facts["global_trading"] = await global_trading(session)
    facts["conflicts"] = [
        {
            "authority_id": item.id,
            "agent_name": names.get(item.agent_id),
            "symbol_scope": envelope.symbol_scope,
            "symbols": list(envelope.symbols),
        }
        for item, envelope in conflicts
    ]
    own = [
        envelope
        for item, envelope in await active_grants(session, owner_id, draft.account_id)
        if item.agent_id == draft.agent_id
    ]
    # Everything the replaced grant allowed, so the card shows each effect of replacing it.
    facts["replaces"] = grant_terms(own[0]) if own else None
    signed = await session.scalar(
        select(AccountAuthorityRow.id)
        .where(AccountAuthorityRow.owner_id == owner_id, AccountAuthorityRow.device_id.is_not(None))
        .limit(1)
    )
    # The one rule is shown on the owner's first grant card.
    facts["first_grant"] = signed is None
    return facts


async def creation_facts(
    session: AsyncSession, row: OwnerActionRow, facts: dict[str, Any]
) -> dict[str, Any]:
    """What a creation card shows: the agent's name, template, focus pair and ladder,
    whom it reports to, and its task exactly as stored. That task becomes the agent's
    standing instructions, so the owner sees every word the tap commits to; the client
    shows it isolated and labelled as the agent's task, never as Lonora's words."""
    from lonora_contracts.agent_creation import TEMPLATE_LEVEL

    from .agent_creation import agent_origin, report_targets, undo_plan
    from .agent_permissions import effective_permission

    owner_id = row.owner_id
    if row.kind == "create_agent":
        spec = row.payload["spec"]
        report_to = [str(item) for item in spec.get("report_to", [])]
        supervises = [str(item) for item in spec.get("supervises", [])]
        names = await agent_names(session, owner_id, {*report_to, *supervises})
        account_id = spec.get("account_id")
        if account_id:
            facts["account"] = account_facts(
                await session.get(BrokerSessionRow, account_id), account_id
            )
        model = spec.get("model")
        facts["agent"] = {
            "exists": False,
            "name": spec["name"],
            "template": spec["template"],
            "symbol": spec.get("symbol"),
            "level": TEMPLATE_LEVEL[spec["template"]],
            "paused": False,
            "report_to": [names[item] for item in report_to if item in names],
            "supervises": [names[item] for item in supervises if item in names],
            "model": cast(dict[str, Any], model).get("model") if isinstance(model, dict) else None,
            "responsibility": str(spec.get("responsibility") or "") or None,
        }
        return facts
    agent_id = row.payload["agent_id"]
    agent = await session.get(AgentRow, agent_id)
    if agent is None or agent.owner_id != owner_id:
        facts["agent"] = {"exists": False, "name": row.result.get("agent_name")}
        return facts
    from .supervision import supervised_ids

    origin = await agent_origin(session, owner_id, agent_id)
    report_to = report_targets(origin)
    supervises = await supervised_ids(session, owner_id, agent_id)
    names = await agent_names(session, owner_id, {*report_to, *supervises})
    if agent.trading_account_id:
        facts["account"] = account_facts(
            await session.get(BrokerSessionRow, agent.trading_account_id),
            agent.trading_account_id,
        )
    facts["agent"] = {
        "exists": True,
        "name": agent.name,
        "template": origin.get("template"),
        "symbol": agent.trading_symbol,
        "level": await effective_permission(session, owner_id, agent_id),
        "paused": agent.paused,
        "report_to": [names[item] for item in report_to if item in names],
        "supervises": [names[item] for item in supervises if item in names],
        "model": None,
        "responsibility": agent.instructions or None,
    }
    facts["undo"] = await undo_plan(session, owner_id, agent_id)
    return facts


async def supervision_facts(
    session: AsyncSession, row: OwnerActionRow, facts: dict[str, Any]
) -> dict[str, Any]:
    """Who supervises whom: names read now from the agents (never model text), and for an
    Undo card which of its grants are still in force."""
    owner_id = row.owner_id
    if row.kind == "supervise":
        supervisor = str(row.payload["supervisor_id"])
        wanted = [str(item) for item in row.payload["supervised_ids"]]
        names = await agent_names(session, owner_id, {supervisor, *wanted})
        facts["supervision"] = {
            "supervisor_name": names.get(supervisor),
            "supervised_names": [names[item] for item in wanted if item in names],
            "active": False,
        }
        return facts
    grants = (
        await _restorable(session, owner_id, await _stopped_grants(session, owner_id, row.payload))
        if row.kind == "supervision_stopped"
        else await _active_grants(session, owner_id, row.payload)
    )
    supervisor = grants[0].supervisor_agent_id if grants else row.result.get("supervisor_id")
    names = await agent_names(
        session,
        owner_id,
        {item.supervised_agent_id for item in grants}
        | ({str(supervisor)} if supervisor else set()),
    )
    facts["supervision"] = {
        "supervisor_name": names.get(str(supervisor)) if supervisor else None,
        "supervised_names": [
            names[item.supervised_agent_id] for item in grants if item.supervised_agent_id in names
        ],
        "active": bool(grants),
    }
    return facts


# How much of a paused item's own text (a routine's prompt, a watch's market, a Task's
# title) the pause card quotes, isolated, so the owner can tell which one it is.
PAUSE_LABEL_CHARS = 80


async def pause_label(session: AsyncSession, hold: SupervisionHoldRow) -> str | None:
    from .schema import MarketWatchRow, RoutineRow, TicketRow

    label: str = ""
    if hold.target_kind == "routine":
        routine = await session.get(RoutineRow, hold.target_id)
        label = routine.prompt if routine else ""
    elif hold.target_kind == "watch":
        watch = await session.get(MarketWatchRow, hold.target_id)
        label = str(watch.payload.get("symbol") or "") if watch else ""
    elif hold.target_kind == "task":
        task = await session.get(TicketRow, hold.target_id)
        label = str(task.payload.get("title") or "") if task else ""
    label = " ".join(label.split())
    if len(label) > PAUSE_LABEL_CHARS:
        label = label[:PAUSE_LABEL_CHARS].rstrip() + "…"
    return label or None


async def pause_facts(
    session: AsyncSession, row: OwnerActionRow, facts: dict[str, Any]
) -> dict[str, Any]:
    """Who paused which work of which agent: names read now from the agents; and
    whether the pause still holds (the card offers Resume only then)."""
    hold = await session.get(SupervisionHoldRow, row.payload["hold_id"])
    if hold is None or hold.owner_id != row.owner_id:
        facts["supervision"] = {"supervisor_name": None, "supervised_names": [], "active": False}
        return facts
    names = await agent_names(session, row.owner_id, {hold.holder_agent_id, hold.agent_id})
    facts["supervision"] = {
        # None once the supervisor is deleted: its pause stays, as the owner's.
        "supervisor_name": names.get(hold.holder_agent_id or ""),
        "supervised_names": [names[hold.agent_id]] if hold.agent_id in names else [],
        "active": await _live_pause(session, row.owner_id, row.payload) is not None,
        "target": hold.target_kind,
        "target_label": await pause_label(session, hold),
        "from_owner_message": hold.source == "owner_message",
        # The owner paused the same work too: the pause is the owner's now.
        "owner_holds": hold.source == "owner",
    }
    return facts


def limit_changes(
    current: MonetaryRiskLimits, proposed: MonetaryRiskLimits
) -> list[dict[str, Any]]:
    """One line per changed field: limits, their currency and the trading-day zone."""
    return [
        {
            "name": name,
            "from": None if getattr(current, name) is None else str(getattr(current, name)),
            "to": None if getattr(proposed, name) is None else str(getattr(proposed, name)),
        }
        for name in LIMIT_CHANGE_NAMES
        if getattr(current, name) != getattr(proposed, name)
    ]


async def owner_action_data(
    session: AsyncSession, row: OwnerActionRow, now: datetime | None = None
) -> dict[str, Any]:
    moment = now or utcnow()
    facts, passkey = await card_facts(session, row, moment)
    status = live_status(row, moment)
    return {
        "id": row.id,
        "kind": row.kind,
        "status": status,
        "status_reason": "expired"
        if status == "expired" and row.status == "pending"
        else (row.status_reason),
        # The newer card that replaced this one («عرض الأحدث»), or None.
        "superseded_by": row.superseded_by,
        "source": row.source,
        "agent_id": row.agent_id,
        "thread_id": row.thread_id,
        "run_id": row.run_id,
        "timeline_seq": row.timeline_seq,
        "facts": facts,
        "requires_passkey": passkey,
        "result": row.result,
        "expires_at": row.expires_at.isoformat(),
        "decided_at": row.decided_at.isoformat() if row.decided_at else None,
        "decided_via": row.decided_via,
        "created_at": row.created_at.isoformat(),
        "updated_at": row.updated_at.isoformat(),
    }


async def owner_action_event(session: AsyncSession, row: OwnerActionRow) -> None:
    emit(
        session,
        row.owner_id,
        "owner_action.updated",
        thread_id=row.thread_id,
        agent_id=row.agent_id,
        run_id=row.run_id,
        payload={
            "id": row.id,
            "kind": row.kind,
            "status": row.status,
            "status_reason": row.status_reason,
            "thread_id": row.thread_id,
            "transition_id": row.id + ":" + row.status,
        },
    )


async def settle(
    session: AsyncSession,
    row: OwnerActionRow,
    status: str,
    reason: str | None,
    *,
    via: str | None = None,
    result: dict[str, Any] | None = None,
    by: str | None = None,
) -> OwnerActionRow:
    """``by`` names the newer card that replaces this one (``superseded_by``)."""
    now = utcnow()
    row.status, row.status_reason, row.updated_at = status, reason, now
    if by is not None:
        row.superseded_by = by
    if status in {"confirmed", "cancelled"}:
        row.decided_at, row.decided_via = now, via
    if result is not None:
        row.result = result
    await session.flush()
    await owner_action_event(session, row)
    return row


async def lock_owner_actions(session: AsyncSession, owner_id: str) -> None:
    """Serialize card creation and settlement per owner (dedupe, cap, subject supersede)."""
    if session.get_bind().dialect.name == "postgresql":
        await session.execute(
            text("SELECT pg_advisory_xact_lock(hashtextextended(:key, 0))"),
            {"key": "owner-actions:" + owner_id},
        )


async def supersede_subject(
    session: AsyncSession,
    owner_id: str,
    kind: str,
    subject: str,
    reason: str,
    *,
    keep: str | None = None,
    effect: str | None = None,
    skip_locked: bool = False,
    by: str | None = None,
) -> list[OwnerActionRow]:
    """Settle every other pending card for the same record: its effect is done or gone.

    ``effect`` narrows it to cards with that exact payload hash (the same change proposed
    twice); a different change to the same account's limits stays on its card.
    ``skip_locked`` leaves a card the owner is deciding at this moment to its decision,
    which re-checks it (a delete holding the agent's lock never waits on a tap).
    ``by`` is the newer card replacing them, recorded on each (``superseded_by``).
    """
    query = select(OwnerActionRow).where(
        OwnerActionRow.owner_id == owner_id,
        OwnerActionRow.kind == kind,
        OwnerActionRow.subject == subject,
        OwnerActionRow.status == "pending",
    )
    if effect is not None:
        query = query.where(OwnerActionRow.payload_hash == effect)
    rows = list(
        await session.scalars(
            query.order_by(OwnerActionRow.created_at, OwnerActionRow.id).with_for_update(
                skip_locked=skip_locked
            )
        )
    )
    settled: list[OwnerActionRow] = []
    for row in rows:
        if row.id == keep:
            continue
        expired = row.expires_at <= utcnow()
        settled.append(
            await settle(session, row, "expired" if expired else "superseded", reason, by=by)
        )
    return settled


async def card_thread(
    session: AsyncSession, owner_id: str, agent_id: str, thread_id: str | None
) -> ThreadRow:
    """The owner's conversation that shows the card: the given one when it is a
    conversation, otherwise the agent's own conversation."""
    from .threads import conversation_thread

    thread = await session.get(ThreadRow, thread_id) if thread_id else None
    if (
        thread is None
        or thread.owner_id != owner_id
        or thread.purpose != "conversation"
        or (thread.agent_id not in {agent_id, None})
    ):
        thread = await conversation_thread(session, owner_id, agent_id)
    return await owned_thread(session, owner_id, thread.id, lock=True)


def expiry(kind: str, now: datetime) -> datetime:
    return now + LIFETIME[kind]


async def create_card(
    session: AsyncSession,
    owner_id: str,
    *,
    card_id: str,
    agent_id: str,
    thread: ThreadRow,
    run_id: str | None,
    source: str,
    kind: str,
    subject: str,
    payload: dict[str, Any],
    status: str = "pending",
) -> OwnerActionRow:
    """``status`` "confirmed" records a notice that offers nothing to decide."""
    now = utcnow()
    row = OwnerActionRow(
        id=card_id,
        owner_id=owner_id,
        agent_id=agent_id,
        thread_id=thread.id,
        run_id=run_id,
        source=source,
        kind=kind,
        subject=subject,
        payload=payload,
        payload_hash=payload_hash(kind, payload),
        status=status,
        result={},
        # The card sits after everything already in the conversation, like an approval.
        timeline_seq=thread.next_seq,
        expires_at=expiry(kind, now),
        created_at=now,
        updated_at=now,
    )
    session.add(row)
    await session.flush()
    await owner_action_event(session, row)
    return row


async def pending_effect(
    session: AsyncSession, agent_id: str, kind: str, digest: str
) -> OwnerActionRow | None:
    return await session.scalar(
        select(OwnerActionRow)
        .where(
            OwnerActionRow.agent_id == agent_id,
            OwnerActionRow.kind == kind,
            OwnerActionRow.payload_hash == digest,
            OwnerActionRow.status == "pending",
        )
        .with_for_update()
    )


async def propose(
    session: AsyncSession,
    owner_id: str,
    proposal: OwnerActionProposal,
    *,
    card_id: str,
    agent_id: str,
    thread_id: str | None,
    run_id: str | None,
    grant: GrantDraft | None = None,
) -> tuple[OwnerActionRow, bool]:
    """An agent's card: validated against current state, deduplicated, capped.

    Returns the card and whether it is new. A repeated proposal of the same effect by
    the same agent returns the pending card it already raised. A grant card carries the
    draft the tool resolved (``grant``).
    """
    await lock_owner_actions(session, owner_id)
    existing = await session.get(OwnerActionRow, card_id)
    if existing is not None:
        if existing.owner_id != owner_id or existing.agent_id != agent_id:
            raise LonoraError("owner_action_not_found", 404)
        return existing, False
    subject, payload = proposal_payload(proposal, grant)
    return await propose_effect(
        session,
        owner_id,
        proposal.kind,
        subject,
        payload,
        card_id=card_id,
        agent_id=agent_id,
        thread_id=thread_id,
        run_id=run_id,
    )


async def propose_effect(
    session: AsyncSession,
    owner_id: str,
    kind: str,
    subject: str,
    payload: dict[str, Any],
    *,
    card_id: str,
    agent_id: str,
    thread_id: str | None,
    run_id: str | None,
) -> tuple[OwnerActionRow, bool]:
    """An agent's card for one validated effect: deduplicated per agent, capped. The
    caller holds the owner-actions lock and has checked the card id is new."""
    reason = await stale_reason(session, owner_id, kind, payload)
    if reason is None and kind == "connect_credential":
        from .capability_cards import credential_not_needed

        reason = await credential_not_needed(session, owner_id, payload)
    if reason is not None:
        raise LonoraError("owner_action_not_needed_" + reason, 409)
    current = await pending_effect(session, agent_id, kind, payload_hash(kind, payload))
    if current is not None:
        if current.thread_id is not None and current.expires_at > utcnow():
            return current, False
        # An expired card, or one whose conversation was deleted, gives way to a new one.
        await settle(
            session,
            current,
            "expired" if current.expires_at <= utcnow() else "superseded",
            "expired" if current.expires_at <= utcnow() else "conversation_deleted",
            by=card_id,
        )
    pending = await session.scalar(
        select(func.count())
        .select_from(OwnerActionRow)
        .where(
            OwnerActionRow.owner_id == owner_id,
            OwnerActionRow.agent_id == agent_id,
            OwnerActionRow.source == "agent",
            OwnerActionRow.status == "pending",
            OwnerActionRow.expires_at > utcnow(),
        )
    )
    if (pending or 0) >= MAXIMUM_PENDING_PER_AGENT:
        raise ToolRefusal("owner_action_limit", 429, details=CARDS_WAITING)
    thread = await card_thread(session, owner_id, agent_id, thread_id)
    row = await create_card(
        session,
        owner_id,
        card_id=card_id,
        agent_id=agent_id,
        thread=thread,
        run_id=run_id,
        source="agent",
        kind=kind,
        subject=subject,
        payload=payload,
    )
    return row, True


async def propose_creation(
    session: AsyncSession,
    owner_id: str,
    spec: dict[str, Any],
    *,
    card_id: str,
    agent_id: str,
    thread_id: str | None,
    run_id: str | None,
) -> tuple[OwnerActionRow, bool]:
    """A creation card when no owner message asked for the agent: the owner's tap
    creates it. A repeated proposal of the same agent returns the card shown."""
    await lock_owner_actions(session, owner_id)
    existing = await session.get(OwnerActionRow, card_id)
    if existing is not None:
        if existing.owner_id != owner_id or existing.agent_id != agent_id:
            raise LonoraError("owner_action_not_found", 404)
        return existing, False
    return await propose_effect(
        session,
        owner_id,
        "create_agent",
        "agent-create",
        {"spec": spec},
        card_id=card_id,
        agent_id=agent_id,
        thread_id=thread_id,
        run_id=run_id,
    )


async def settle_created_proposals(
    session: AsyncSession,
    owner_id: str,
    template: str,
    name: str,
    *,
    keep: str | None = None,
) -> list[OwnerActionRow]:
    """Pending creation cards for an agent that now exists (same template and name) no
    longer apply: tapping one would create a second agent. The caller holds the
    owner-actions lock, so no tap is deciding one of them at this moment."""
    wanted = " ".join(name.split()).casefold()
    rows = await session.scalars(
        select(OwnerActionRow)
        .where(
            OwnerActionRow.owner_id == owner_id,
            OwnerActionRow.kind == "create_agent",
            OwnerActionRow.status == "pending",
        )
        .order_by(OwnerActionRow.created_at, OwnerActionRow.id)
        .with_for_update()
    )
    settled: list[OwnerActionRow] = []
    for row in list(rows):
        spec = row.payload["spec"]
        if row.id == keep or spec["template"] != template:
            continue
        if str(spec["name"]).casefold() != wanted:
            continue
        expired = row.expires_at <= utcnow()
        settled.append(
            await settle(
                session,
                row,
                "expired" if expired else "superseded",
                "expired" if expired else "agent_already_created",
            )
        )
    return settled


async def raise_created_card(
    session: AsyncSession,
    owner_id: str,
    created_agent: AgentRow,
    *,
    agent_id: str,
    thread_id: str | None,
    run_id: str | None,
) -> OwnerActionRow:
    """The one-line result card of a creation, with Undo; one per created agent."""
    await lock_owner_actions(session, owner_id)
    subject = "agent:" + created_agent.id
    card_id = stable_id(owner_id, "owner-action:agent_created:" + subject)
    existing = await session.get(OwnerActionRow, card_id)
    if existing is not None:
        return existing
    thread = await card_thread(session, owner_id, agent_id, thread_id)
    row = await create_card(
        session,
        owner_id,
        card_id=card_id,
        agent_id=agent_id,
        thread=thread,
        run_id=run_id,
        source="system",
        kind="agent_created",
        subject=subject,
        payload={"agent_id": created_agent.id},
    )
    row.result = {"agent_name": created_agent.name}
    return row


async def propose_supervision(
    session: AsyncSession,
    owner_id: str,
    supervisor_id: str,
    supervised_ids: list[str],
    *,
    card_id: str,
    agent_id: str,
    thread_id: str | None,
    run_id: str | None,
) -> tuple[OwnerActionRow, bool]:
    """A supervision card when no owner message asked for it: the owner's tap sets it.
    A repeated proposal of the same supervision returns the card shown."""
    await lock_owner_actions(session, owner_id)
    existing = await session.get(OwnerActionRow, card_id)
    if existing is not None:
        if existing.owner_id != owner_id or existing.agent_id != agent_id:
            raise LonoraError("owner_action_not_found", 404)
        return existing, False
    return await propose_effect(
        session,
        owner_id,
        "supervise",
        "supervision:" + supervisor_id,
        {"supervisor_id": supervisor_id, "supervised_ids": sorted(set(supervised_ids))},
        card_id=card_id,
        agent_id=agent_id,
        thread_id=thread_id,
        run_id=run_id,
    )


async def propose_capability(
    session: AsyncSession,
    owner_id: str,
    kind: str,
    subject: str,
    payload: dict[str, Any],
    *,
    card_id: str,
    agent_id: str,
    thread_id: str | None,
    run_id: str | None,
) -> tuple[OwnerActionRow, bool]:
    """A trust or credential card on an agent's behalf, with the effect built on the
    server (an MCP server's card carries the tools read from it). Deduplicated per agent
    and capped like every proposal; a repeated call returns the card shown."""
    await lock_owner_actions(session, owner_id)
    existing = await session.get(OwnerActionRow, card_id)
    if existing is not None:
        if existing.owner_id != owner_id or existing.agent_id != agent_id:
            raise LonoraError("owner_action_not_found", 404)
        return existing, False
    return await propose_effect(
        session,
        owner_id,
        kind,
        subject,
        payload,
        card_id=card_id,
        agent_id=agent_id,
        thread_id=thread_id,
        run_id=run_id,
    )


async def raise_review_card(
    session: AsyncSession,
    owner_id: str,
    subject: str,
    payload: dict[str, Any],
    *,
    agent_id: str,
    thread_id: str | None,
    run_id: str | None,
) -> OwnerActionRow | None:
    """An MCP server's tools to trust, raised by the server with no model involved: a
    trusted server whose tools changed (re-review), or one the owner just connected. The
    same tools already shown, or declined in the last week, raise none; tools already
    trusted exactly raise none; a newer review replaces an older one still waiting."""
    await lock_owner_actions(session, owner_id)
    if not await review_card_wanted(session, owner_id, payload):
        return None
    # One review waits per server: a server that keeps changing never stacks up cards.
    card_id = new_id()
    await supersede_subject(
        session, owner_id, "trust_source", subject, "server_changed_again", by=card_id
    )
    thread = await card_thread(session, owner_id, agent_id, thread_id)
    return await create_card(
        session,
        owner_id,
        card_id=card_id,
        agent_id=agent_id,
        thread=thread,
        run_id=run_id,
        source="system",
        kind="trust_source",
        subject=subject,
        payload=payload,
    )


async def review_card_wanted(session: AsyncSession, owner_id: str, payload: dict[str, Any]) -> bool:
    """Whether ``raise_review_card`` would raise this review now: not the same tools
    already waiting or declined in the last week, not tools already trusted exactly."""
    digest = payload_hash("trust_source", payload)
    shown = await session.scalar(
        select(OwnerActionRow)
        .where(
            OwnerActionRow.owner_id == owner_id,
            OwnerActionRow.kind == "trust_source",
            OwnerActionRow.payload_hash == digest,
            OwnerActionRow.status.in_(["pending", "cancelled"]),
        )
        .order_by(OwnerActionRow.created_at.desc())
        .limit(1)
    )
    now = utcnow()
    if shown is not None and (
        (shown.status == "pending" and shown.expires_at > now)
        or (
            shown.status == "cancelled"
            and (shown.decided_at or now) > now - LIFETIME["trust_source"]
        )
    ):
        return False
    return await stale_reason(session, owner_id, "trust_source", payload) is None


async def raise_supervision_card(
    session: AsyncSession,
    owner_id: str,
    grant_ids: list[str],
    *,
    card_key: str,
    agent_id: str,
    thread_id: str | None,
    run_id: str | None,
) -> OwnerActionRow | None:
    """The one-line result card of new supervision grants, with Undo; one per change.
    Grants that existed before are never on it, so Undo takes back only this change."""
    if not grant_ids:
        return None
    await lock_owner_actions(session, owner_id)
    subject = "supervision-grants:" + card_key
    card_id = stable_id(owner_id, "owner-action:supervision_created:" + subject)
    existing = await session.get(OwnerActionRow, card_id)
    if existing is not None:
        return existing
    grants = await _active_grants(session, owner_id, {"grant_ids": grant_ids})
    thread = await card_thread(session, owner_id, agent_id, thread_id)
    row = await create_card(
        session,
        owner_id,
        card_id=card_id,
        agent_id=agent_id,
        thread=thread,
        run_id=run_id,
        source="system",
        kind="supervision_created",
        subject=subject,
        payload={"grant_ids": sorted(grant_ids)},
    )
    row.result = {"supervisor_id": grants[0].supervisor_agent_id} if grants else {}
    return row


async def raise_supervision_stopped_card(
    session: AsyncSession,
    owner_id: str,
    grant_ids: list[str],
    *,
    card_key: str,
    agent_id: str,
    thread_id: str | None,
    run_id: str | None,
) -> OwnerActionRow | None:
    """The one-line result card of supervision stopped from chat, with Restore; one per
    change. Restore sets again only the grants this change ended."""
    if not grant_ids:
        return None
    await lock_owner_actions(session, owner_id)
    subject = "supervision-stopped:" + card_key
    card_id = stable_id(owner_id, "owner-action:supervision_stopped:" + subject)
    existing = await session.get(OwnerActionRow, card_id)
    if existing is not None:
        return existing
    grants = await _stopped_grants(session, owner_id, {"grant_ids": grant_ids})
    thread = await card_thread(session, owner_id, agent_id, thread_id)
    row = await create_card(
        session,
        owner_id,
        card_id=card_id,
        agent_id=agent_id,
        thread=thread,
        run_id=run_id,
        source="system",
        kind="supervision_stopped",
        subject=subject,
        payload={"grant_ids": sorted(grant_ids)},
    )
    row.result = {"supervisor_id": grants[0].supervisor_agent_id} if grants else {}
    return row


async def raise_supervision_pause_card(
    session: AsyncSession, hold: SupervisionHoldRow, *, run_id: str | None
) -> OwnerActionRow:
    """The card a supervisor's pause raises in the paused agent's conversation: who
    paused which work, with one-tap Resume; one per hold. The caller holds the
    owner-actions lock before the work's locks, the order a card decision takes."""
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


async def raise_system_card(
    session: AsyncSession,
    owner_id: str,
    proposal: OwnerActionProposal,
    *,
    agent_id: str,
    thread_id: str | None,
    run_id: str | None,
) -> OwnerActionRow | None:
    """A card raised from a runtime event, with no model involved; one per record.

    The id is derived from the record, so replaying the event never adds a second card,
    and an effect that no longer applies raises none.
    """
    await lock_owner_actions(session, owner_id)
    subject, payload = proposal_payload(proposal)
    card_id = stable_id(owner_id, "owner-action:" + proposal.kind + ":" + subject)
    if await session.get(OwnerActionRow, card_id) is not None:
        return None
    if await stale_reason(session, owner_id, proposal.kind, payload) is not None:
        return None
    if await pending_effect(session, agent_id, proposal.kind, payload_hash(proposal.kind, payload)):
        return None
    thread = await card_thread(session, owner_id, agent_id, thread_id)
    return await create_card(
        session,
        owner_id,
        card_id=card_id,
        agent_id=agent_id,
        thread=thread,
        run_id=run_id,
        source="system",
        kind=proposal.kind,
        subject=subject,
        payload=payload,
    )


async def owned_card(
    session: AsyncSession, owner_id: str, card_id: str, *, lock: bool = False
) -> OwnerActionRow:
    row = await session.get(OwnerActionRow, card_id, with_for_update=lock, populate_existing=lock)
    if row is None or row.owner_id != owner_id:
        raise LonoraError("owner_action_not_found", 404)
    return row


async def draft_grant_card(
    session: AsyncSession, owner_id: str, draft: GrantDraft, thread_id: str | None
) -> OwnerActionRow:
    """The owner's own grant card from the mandate sheet: the resolved draft stored on a
    pending grant card in the agent's conversation, exactly like an agent's proposal. It
    grants nothing: only the card's passkey ceremony (challenge, then the decision with
    the device proof bound to the envelope built from this draft) activates a grant.

    The same draft twice returns the card already shown; a different one replaces the
    agent's other pending grant cards for that account (``superseded_by``) and withdraws
    a proposal their challenge prepared."""
    from .account_authority import owned_authority, revoke

    await lock_owner_actions(session, owner_id)
    payload = draft.model_dump(mode="json")
    reason = await stale_reason(session, owner_id, "grant_authority", payload)
    if reason is not None:
        raise LonoraError("owner_action_not_needed_" + reason, 409)
    card_id = new_id()
    current = await pending_effect(
        session, draft.agent_id, "grant_authority", payload_hash("grant_authority", payload)
    )
    if current is not None and current.thread_id is not None and current.expires_at > utcnow():
        return current
    subject = "grant:" + draft.agent_id + ":" + draft.account_id
    for replaced in await supersede_subject(
        session, owner_id, "grant_authority", subject, "replaced_by_owner_draft", by=card_id
    ):
        prepared = replaced.result.get("authority_id")
        if isinstance(prepared, str):
            authority = await owned_authority(session, owner_id, prepared)
            if authority.status == "pending":
                await revoke(session, owner_id, prepared)
    thread = await card_thread(session, owner_id, draft.agent_id, thread_id)
    return await create_card(
        session,
        owner_id,
        card_id=card_id,
        agent_id=draft.agent_id,
        thread=thread,
        run_id=None,
        source="owner",
        kind="grant_authority",
        subject=subject,
        payload=payload,
    )


# Cards «طلب جديد» can raise again once expired: decisions the runtime asks for whose
# record may still need one. Undo and notice cards keep their own window and never come
# back; an agent's proposal is the agent's to make again.
RENEWABLE_KINDS = frozenset({"resolve_operation", "resume_trading"})


async def renew_card(session: AsyncSession, owner_id: str, card_id: str) -> OwnerActionRow:
    """«طلب جديد»: a fresh pending card of the same kind for an expired card whose record
    still needs the owner's decision, with a fresh server lifetime; the old card names
    it (``superseded_by``). Refused (``owner_action_not_renewable``) for a card still
    waiting, decided, already replaced, of another kind, or whose record moved on."""
    from .personal_agent import ensure_personal_agent

    await lock_owner_actions(session, owner_id)
    row = await owned_card(session, owner_id, card_id, lock=True)
    if (
        row.kind not in RENEWABLE_KINDS
        or live_status(row) != "expired"
        or row.superseded_by is not None
    ):
        raise LonoraError("owner_action_not_renewable", 409)
    try:
        reason = await stale_reason(session, owner_id, row.kind, row.payload)
    except LonoraError:
        reason = "record_missing"
    newer = await session.scalar(
        select(OwnerActionRow.id).where(
            OwnerActionRow.owner_id == owner_id,
            OwnerActionRow.kind == row.kind,
            OwnerActionRow.subject == row.subject,
            OwnerActionRow.status == "pending",
            OwnerActionRow.expires_at > utcnow(),
        )
    )
    if reason is not None or newer is not None:
        raise LonoraError("owner_action_not_renewable", 409)
    agent = await session.get(AgentRow, row.agent_id)
    agent_id = (
        agent.id
        if agent is not None and agent.owner_id == owner_id
        else (await ensure_personal_agent(session, owner_id)).id
    )
    fresh_id = new_id()
    await settle(session, row, "expired", row.status_reason or "expired", by=fresh_id)
    thread = await card_thread(session, owner_id, agent_id, row.thread_id)
    return await create_card(
        session,
        owner_id,
        card_id=fresh_id,
        agent_id=agent_id,
        thread=thread,
        run_id=row.run_id,
        source=row.source,
        kind=row.kind,
        subject=row.subject,
        payload=row.payload,
    )


async def thread_cards(
    session: AsyncSession, owner_id: str, thread_id: str, limit: int = 50
) -> list[OwnerActionRow]:
    rows = await session.scalars(
        select(OwnerActionRow)
        .where(OwnerActionRow.owner_id == owner_id, OwnerActionRow.thread_id == thread_id)
        .order_by(OwnerActionRow.created_at.desc(), OwnerActionRow.id)
        .limit(limit)
    )
    return list(reversed(list(rows)))


def confirmation_code(row: OwnerActionRow) -> str:
    if row.kind == "resolve_operation":
        return "owner_action_resolve_" + str(row.result.get("outcome", "unknown"))
    if row.kind == "agent_created":
        return "owner_action_undo_" + str(row.result.get("undo", "paused"))
    if row.kind == "trust_source" and row.payload.get("source_kind") == "mcp_server":
        # Trusted for reading while some tools may change something: those wait.
        if row.result.get("tier") == "read" and row.result.get("writes"):
            return "owner_action_trust_source_mcp_read"
        return "owner_action_trust_source_mcp"
    if row.kind == "connect_credential" and row.payload.get("target") == "mcp_server":
        # Whether the trust card for the connected server follows (MCP_REVIEW_LINES).
        return MCP_REVIEW_LINES.get(
            str(row.result.get("review", "raised")), "owner_action_connect_credential"
        )
    return "owner_action_" + row.kind


async def grant_notes(session: AsyncSession, row: OwnerActionRow) -> list[str]:
    """The grant's one-line confirmation: what else the card did, and Stop if it holds."""
    result = row.result
    notes: list[str] = []
    if result.get("delegation") == "full":
        # What Full delegation signed, and that the account's own limits still apply.
        notes.append("owner_action_grant_full")
    if result.get("daily_loss") is not None:
        notes.append("owner_action_grant_daily_loss")
    elif result.get("money_limit") == "none":
        notes.append(
            "owner_action_grant_kept_limit"
            if result.get("daily_loss_kept") is not None
            else "owner_action_grant_no_money_limit"
        )
    stopped = cast(list[str], result.get("stopped_authorities") or [])
    if stopped:
        notes.append(
            "owner_action_grant_stopped_other"
            if len(stopped) == 1
            else "owner_action_grant_stopped_others"
        )
    if result.get("resumed"):
        notes.append("owner_action_grant_resumed")
    elif (await global_trading(session))["state"] == "stopped":
        notes.append("owner_action_still_stopped")
    return notes


# What a credential card for an MCP server says once the form connected it: its trust
# card follows; its tools could not be read; none can be trusted; or (operator deny
# override) only declared tools run, said as a plain connection.
MCP_REVIEW_LINES = {
    "raised": "owner_action_connect_credential_mcp",
    "unread": "owner_action_connect_credential_mcp_unread",
    "nothing_to_trust": "owner_action_connect_credential_mcp_blocked",
}


async def still_holding(session: AsyncSession, row: OwnerActionRow) -> list[str]:
    """What still holds new risk where an answer just released it, read after the effect:
    Stop new trading, or another trade there without a confirmed broker outcome. One
    fixed clause each."""
    if row.kind == "grant_authority":
        return await grant_notes(session, row)
    if row.kind != "resolve_operation":
        return []
    operation = await session.get(TradingJournalRow, row.payload["operation_id"])
    if operation is None:
        return []
    account, answered_id = operation.account_id, operation.operation_id
    symbol = cast(str | None, operation.request.get("symbol"))
    tickets = [
        str(operation.request[key])
        for key in ("position_id", "order_id")
        if operation.request.get(key)
    ]
    notes: list[str] = []
    if (await global_trading(session))["state"] == "stopped":
        notes.append("owner_action_still_stopped")
    scope: list[ColumnElement[bool]] = []
    if symbol is not None:
        scope.append(func.lower(TradingJournalRow.request["symbol"].as_string()) == symbol.lower())
    scope.extend(
        TradingJournalRow.request[key].as_string() == ticket
        for key in ("position_id", "order_id")
        for ticket in tickets
    )
    unresolved = select(TradingJournalRow.operation_id).where(
        TradingJournalRow.owner_id == row.owner_id,
        TradingJournalRow.account_id == account,
        TradingJournalRow.status.in_(sorted(UNRESOLVED_STATUSES)),
        TradingJournalRow.operation_id != answered_id,
    )
    if scope:
        unresolved = unresolved.where(or_(*scope))
    if await session.scalar(unresolved.limit(1)) is not None:
        notes.append("owner_action_still_unresolved")
    return notes


async def confirmation_agent(session: AsyncSession, row: OwnerActionRow) -> str | None:
    """Who speaks the confirmation: the card's agent while it exists (held against a
    concurrent delete), otherwise Lonora."""
    present = await session.scalar(
        select(AgentRow.id)
        .where(AgentRow.id == row.agent_id, AgentRow.owner_id == row.owner_id)
        .with_for_update(key_share=True)
    )
    if present is not None:
        return present
    return await session.scalar(
        select(AgentRow.id).where(AgentRow.owner_id == row.owner_id, AgentRow.role == "personal")
    )


async def confirm_in_thread(session: AsyncSession, row: OwnerActionRow) -> None:
    """One server-written line in the card's conversation saying what changed, and what
    still holds new risk there (``still_holding``), read after the effect.

    The clauses are fixed texts in the conversation's language; posting is idempotent
    per card, and a card whose conversation is gone posts nothing.
    """
    from lonora_bus.attention import attention_text

    from .conversation_locale import conversation_locale
    from .messages import message_data
    from .schema import EffectReceiptRow, MessageRow

    if row.status != "confirmed" or row.thread_id is None:
        return
    key = "owner-action-ack:" + row.id
    if await session.get(EffectReceiptRow, key):
        return
    # The agent before its conversation: the order a delete of that agent locks them in.
    speaker = await confirmation_agent(session, row)
    thread = await session.get(
        ThreadRow, row.thread_id, with_for_update=True, populate_existing=True
    )
    if thread is None or thread.owner_id != row.owner_id:
        return  # Deleted while the owner tapped: the effect stands, nothing to post in.
    locale = await conversation_locale(session, row.owner_id, thread.id)
    codes = [confirmation_code(row), *await still_holding(session, row)]
    message = MessageRow(
        id=stable_id(row.id, "owner-action-ack"),
        thread_id=thread.id,
        agent_id=speaker,
        seq=thread.next_seq,
        role="assistant",
        content=" ".join(attention_text(code, locale) for code in codes),
    )
    thread.next_seq += 1
    session.add(message)
    await session.flush()
    session.add(EffectReceiptRow(key=key, result={"message_id": message.id, "locale": locale}))
    emit(
        session,
        row.owner_id,
        "message.created",
        thread_id=thread.id,
        agent_id=message.agent_id,
        payload=message_data(message),
    )


# The run that tells the agent behind a trust or credential card that the owner tapped it.
CONTINUE_TRIGGER = "owner_card"


def continue_prompt(row: OwnerActionRow) -> str:
    """Fixed text and server-checked identifiers only (a repository slug, a host name,
    a connection id, a target name): nothing the model wrote reaches the system role."""
    if row.kind == "connect_credential":
        review = row.result.get("review")
        if row.payload["target"] == "mcp_server" and review in {"unread", "nothing_to_trust"}:
            reason = (
                "its tools could not be read yet"
                if review == "unread"
                else "none of its tools can be trusted (a tool that can trade or move money "
                "never runs)"
            )
            return (
                "The owner connected an MCP server (connection_id="
                f"{row.result.get('connection_id')}) on your card; its credential stays on "
                f"the server. No review card followed: {reason}. Check it with mcp_tools now: "
                "if it lists tools to review, propose trust_source for this connection_id; "
                "otherwise tell the owner in one line what is wrong."
            )
        return (
            f"The owner connected {row.payload['target']} on your card; it is configured on "
            "the server and you never see its value. Continue the work that needed it now, "
            "then tell the owner in one line what you did."
        )
    kind, identifier = row.payload["source_kind"], row.payload["identifier"]
    named = (
        f"the MCP server (connection_id={identifier}) at tier {row.result.get('tier', 'read')}"
        if kind == "mcp_server"
        else f"{kind} {identifier}"
    )
    return (
        f"The owner trusted {named} on your card; it is now in the trusted list. Continue the "
        "work that needed it now (retry what was waiting), then tell the owner in one line "
        "what you did."
    )


async def continue_after_card(session: AsyncSession, row: OwnerActionRow) -> RunRow | None:
    """One run for the card's agent in the card's conversation, so the work that needed
    the source or credential goes on without the owner asking again. None when the agent
    is gone or paused (it then waits for the owner)."""
    from lonora_contracts.runs import RunRequest

    from .runs import create_run
    from .threads import conversation_thread

    run_id = stable_id(row.id, "continue-after-card")
    if await session.get(RunRow, run_id) is not None:
        return None
    agent = await session.get(AgentRow, row.agent_id)
    if agent is None or agent.owner_id != row.owner_id or agent.paused or agent.role == "delegated":
        return None
    thread = await session.get(ThreadRow, row.thread_id) if row.thread_id else None
    if (
        thread is None
        or thread.owner_id != row.owner_id
        or thread.purpose != "conversation"
        or thread.agent_id != agent.id
        or thread.group_id
    ):
        thread = await conversation_thread(session, row.owner_id, agent.id)
    return await create_run(
        session,
        row.owner_id,
        RunRequest(
            thread_id=thread.id,
            agent_id=agent.id,
            trigger=CONTINUE_TRIGGER,
            prompt=continue_prompt(row),
            metadata={"owner_action_id": row.id},
        ),
        run_id,
    )


async def awaiting_owner_answer(session: AsyncSession, owner_id: str, operation_id: str) -> bool:
    """The owner already has this uncertain operation in front of them: its resolve card
    waits for an answer, or its "operation_uncertain" item is still open. A later aging
    alert for the same operation would only repeat that fact."""
    card = await session.scalar(
        select(OwnerActionRow.id)
        .where(
            OwnerActionRow.owner_id == owner_id,
            OwnerActionRow.kind == "resolve_operation",
            OwnerActionRow.subject == "operation:" + operation_id,
            OwnerActionRow.status == "pending",
            OwnerActionRow.expires_at > utcnow(),
        )
        .limit(1)
    )
    if card is not None:
        return True
    item = await session.scalar(
        select(AttentionRow.id)
        .where(
            AttentionRow.owner_id == owner_id,
            AttentionRow.code == "operation_uncertain",
            AttentionRow.status.in_(["pending", "ready"]),
            AttentionRow.parameters["operation_id"].as_string() == operation_id,
        )
        .limit(1)
    )
    return item is not None


async def card_account(session: AsyncSession, row: OwnerActionRow) -> str | None:
    if row.kind in {"set_account_limits", "grant_authority"}:
        return cast(str, row.payload["account_id"])
    if row.kind == "create_agent":
        return cast(str | None, row.payload["spec"].get("account_id"))
    if row.kind == "resolve_operation":
        operation = await session.get(TradingJournalRow, row.payload["operation_id"])
        return operation.account_id if operation else None
    return None


async def settle_for_delete(
    session: AsyncSession,
    owner_id: str,
    *,
    agent_id: str | None = None,
    thread_id: str | None = None,
    account_id: str | None = None,
) -> None:
    """Pending cards of a deleted agent or conversation, or about a deleted account, no
    longer apply: they are superseded with the reason, never left waiting to expire.

    A card the owner is deciding at this moment is skipped (its decision finishes on its
    own and posts nothing in a conversation that is gone), so the delete never waits on
    or deadlocks with a tap.
    """
    query = select(OwnerActionRow).where(
        OwnerActionRow.owner_id == owner_id, OwnerActionRow.status == "pending"
    )
    if agent_id is not None:
        # The agent's own cards and grant cards that would sign authority for it.
        query = query.where(
            or_(
                OwnerActionRow.agent_id == agent_id,
                OwnerActionRow.subject.startswith("grant:" + agent_id + ":"),
            )
        )
    if thread_id is not None:
        query = query.where(OwnerActionRow.thread_id == thread_id)
    rows = list(
        await session.scalars(
            query.order_by(OwnerActionRow.created_at, OwnerActionRow.id).with_for_update(
                skip_locked=True
            )
        )
    )
    reason = (
        "agent_deleted"
        if agent_id is not None
        else "conversation_deleted"
        if thread_id is not None
        else "account_deleted"
    )
    for row in rows:
        if account_id is not None and await card_account(session, row) != account_id:
            continue
        await settle(session, row, "superseded", reason)
