"""Propose an owner action card in the conversation. Agents propose; only the owner acts.

The card is validated against current state, deduplicated per agent and effect, and
capped per agent. What the owner sees on it is derived on the server from the records it
names; nothing the agent writes appears on it. No tool can confirm a card: the owner's
tap goes to an owner-session route that runs the existing owner function, and widening
money authority (a grant, or raising a money limit) needs the owner's passkey there.
"""

from decimal import ROUND_DOWN, Decimal
from typing import Any

from lonora_adapter_kit.broker import BrokerAdapter
from lonora_contracts.owner_actions import DailyLossDraft, GrantDraft, OwnerActionProposal
from lonora_core.user_error import LonoraError
from lonora_db.agent_binding import account_wide_scope, agent_binding, require_financial_agent
from lonora_db.owner_actions import ALL_ACTIONS, account_policy, card_facts, live_status, propose
from lonora_db.runs import require_lease
from lonora_db.schema import BrokerSessionRow
from lonora_db.transactions import owned_thread
from sqlalchemy import select

from .base import Tool
from .context import ToolContext
from .symbols import canonical_broker_symbol

# The daily loss limit a grant card suggests when the owner named none (owner decision D1).
SUGGESTED_DAILY_LOSS_PERCENT = Decimal(3)


async def grant_draft(context: ToolContext, proposal: OwnerActionProposal) -> GrantDraft:
    """Resolve the obvious defaults on the server: whose grant, the account, its markets
    and the daily loss limit. Nothing here grants anything; the owner signs the card."""
    grantee = proposal.agent_id or context.agent_id
    async with context.db.sessions() as session:
        proposer = await agent_binding(session, context.owner_id, context.agent_id)
        if grantee != context.agent_id and proposer.role != "personal":
            # Lonora routes grants for any agent; every other agent asks for its own.
            raise LonoraError("owner_action_grant_agent_forbidden", 403)
        agent = await require_financial_agent(session, context.owner_id, grantee)
        account_id = proposal.account_id or agent.trading_account_id
        if account_id is None:
            accounts = list(
                await session.scalars(
                    select(BrokerSessionRow.id)
                    .where(BrokerSessionRow.owner_id == context.owner_id)
                    .order_by(BrokerSessionRow.created_at, BrokerSessionRow.id)
                    .limit(2)
                )
            )
            if len(accounts) != 1:
                # Several accounts: one focused question to the owner decides which.
                raise LonoraError("owner_action_account_required", 409)
            account_id = accounts[0]
        risk = (await account_policy(session, context.owner_id, account_id)).risk
    broker = await context.brokers.get(context.owner_id, account_id)
    if proposal.symbols:
        symbols = [
            await canonical_broker_symbol(broker, symbol, require_exists=True)
            for symbol in proposal.symbols
        ]
        scope = "selected"
    elif proposal.all_pairs or agent.role == "personal":
        symbols, scope = [], "account"
    elif agent.trading_symbol and agent.trading_account_id == account_id:
        symbols, scope = [agent.trading_symbol], "selected"
    elif account_wide_scope(agent):
        symbols, scope = [], "account"
    else:
        raise LonoraError("owner_action_grant_markets_required", 409)
    requested = proposal.daily_loss_amount is not None or proposal.daily_loss_percent is not None
    if not requested and risk.max_daily_loss is not None:
        # The account already has the owner's own daily loss limit: the card shows it
        # and changes nothing, so there is nothing to suggest.
        daily_loss = None
    else:
        daily_loss = await daily_loss_draft(proposal, broker, risk.currency)
    return GrantDraft(
        agent_id=grantee,
        account_id=account_id,
        symbol_scope=scope,
        symbols=symbols,
        actions=list(proposal.actions or ALL_ACTIONS),
        duration=proposal.duration or "until_stopped",
        allow_manual_positions=bool(proposal.allow_manual_positions),
        daily_loss=daily_loss,
    )


async def daily_loss_draft(
    proposal: OwnerActionProposal, broker: BrokerAdapter, account_currency: str | None
) -> DailyLossDraft:
    """The owner's own daily loss (an amount, or a percentage of equity now), or the
    suggested 3% of equity (owner decision D1), in the account currency."""
    equity = currency = None
    try:
        state = await broker.account()
        equity, currency = state.equity, state.currency
    except Exception:
        pass
    currency = currency or account_currency
    if proposal.daily_loss_amount is not None:
        amount, percent, basis = proposal.daily_loss_amount, None, "requested"
    else:
        percent = proposal.daily_loss_percent or SUGGESTED_DAILY_LOSS_PERCENT
        basis = "requested" if proposal.daily_loss_percent is not None else "suggested"
        if equity is None or equity <= 0:
            raise LonoraError("owner_action_equity_unavailable", 503)
        amount = (equity * percent / 100).quantize(Decimal("0.01"), rounding=ROUND_DOWN)
    if currency is None or amount <= 0:
        raise LonoraError("owner_action_equity_unavailable", 503)
    return DailyLossDraft(
        amount=amount,
        currency=currency,
        basis=basis,
        percent=percent,
        equity=equity if percent is not None else None,
    )


async def propose_card(context: ToolContext, args: dict[str, Any]) -> dict[str, Any]:
    proposal = OwnerActionProposal.model_validate(args)
    grant = await grant_draft(context, proposal) if proposal.kind == "grant_authority" else None
    async with context.db.sessions() as session, session.begin():
        run = await require_lease(session, context.lease)
        if run.agent_id != context.agent_id:
            raise LonoraError("agent_run_mismatch", 409)
        origin = run.model_metadata.get("origin_thread_id") or context.thread_id
        thread = await owned_thread(session, context.owner_id, origin)
        if thread.agent_id not in {context.agent_id, None}:
            raise LonoraError("agent_thread_mismatch", 409)
        row, created = await propose(
            session,
            context.owner_id,
            proposal,
            card_id=context.resource_id,
            agent_id=context.agent_id,
            thread_id=thread.id,
            run_id=run.id,
            grant=grant,
        )
        # Fenced after the conversation lock: the thread-before-run order of message admission.
        await require_lease(session, context.lease, lock=True)
        facts, passkey = await card_facts(session, row, row.updated_at)
        above = facts.get("money", {}).get("daily_loss", {}).get("requested_above")
        return {
            "owner_action": {
                "id": row.id,
                "kind": row.kind,
                "status": live_status(row),
                "expires_at": row.expires_at.isoformat(),
            },
            "already_shown": not created,
            "shown_in_conversation": row.thread_id == thread.id,
            # The owner decides on the card; nothing has changed yet.
            "owner_must_tap": True,
            "passkey_required": passkey,
            "execution_authorized": False,
            # A grant card never raises the account's daily loss limit; the owner asked
            # for more, so a set_account_limits card is the way to raise it.
            **({"daily_loss_above_current_needs_limits_card": True} if above else {}),
        }


def tools() -> list[Tool]:
    return [
        Tool(
            "owner_action_propose",
            "Put a one-tap owner action card in this conversation for an action only the "
            "owner may take; nothing changes until the owner taps it. Kinds: resume_trading "
            "(only when the owner asks to resume: Stop is the owner's brake), "
            "lift_restriction (restriction_id of an active or scheduled pause the owner asks "
            "to lift), resolve_operation (operation_id of an ambiguous operation; the owner "
            "answers executed / not executed / unknown, and any answer releases its hold), "
            "set_account_limits (account_id with set_limits amounts in the account "
            "currency or percentages, and/or remove_limits; currency when setting an amount "
            "for the first time) and grant_authority (the owner wants an agent to trade on "
            "its own and no active grant covers it: optional agent_id, account_id, symbols "
            "or all_pairs, actions, duration, allow_manual_positions, and the owner's daily "
            "loss as daily_loss_percent or daily_loss_amount, which the card only sets or "
            "lowers; omit what the owner did not say and the server fills the obvious "
            "defaults). Lowering or adding a limit is one "
            "tap; a grant, raising or removing a limit, or moving the currency or trading day "
            "of set limits needs the owner's passkey. The card shows only server facts; say "
            "in one line what it does. A repeated proposal returns the card already shown; "
            "at most five of yours wait at once.",
            OwnerActionProposal,
            propose_card,
            replay_safe=True,
        ),
    ]
