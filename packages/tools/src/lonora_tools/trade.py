from decimal import Decimal
from typing import Any

from lonora_contracts.account import Order, Position
from lonora_contracts.domain import Contract, utcnow
from lonora_contracts.trading import (
    AnnotatedTradeRequest,
    TradeAnnotation,
    TradeRequest,
    TradeResult,
    TradingControl,
)
from lonora_core.trading_control import require_trading
from lonora_core.user_error import LonoraError, ToolRefusal
from lonora_db.agent_binding import (
    agent_binding,
    require_financial_agent,
)
from lonora_db.agent_permissions import effective_permission
from lonora_db.authority_lock import authority_lock
from lonora_db.notice_cards import raise_stop_tightened
from lonora_db.runs import require_lease
from lonora_db.schema import (
    EffectReceiptRow,
    MessageRow,
    RunRow,
    SettingRow,
    TradeApprovalRow,
    TradingJournalRow,
)
from lonora_db.steering import user_interrupt_pending
from lonora_db.threads import report_thread
from lonora_db.trade_approvals import (
    approval_event,
    drifted_prompt,
    expire_if_due,
    withdraw_own,
    withdrawn_prompt,
)
from lonora_db.trading_mode import set_trading_mode, trading_mode
from lonora_db.transactions import owned_thread
from lonora_session.idempotency import request_hash, stable_id
from lonora_trading.account_authority import (
    authority_snapshot,
    available_authority,
    grant_covers,
    provisional_voice,
    ticket_agent,
)
from lonora_trading.admission import may_reduce_risk, risk_reducing
from lonora_trading.exposure import direction
from lonora_trading.idempotency import trade_fingerprint
from lonora_trading.journal import record_excerpt
from lonora_trading.manual_activity import material_state
from lonora_trading.restrictions import require_unrestricted
from pydantic import Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from .base import Tool, eager_for
from .context import ToolContext
from .resolve import Option, resolve
from .symbols import canonical_broker_symbol, order_symbol

# Results whose operation reached, or may have reached, the broker: never asked twice.
REACHED_BROKER = {"confirmed", "submitted", "ambiguous", "resolved"}


class ClosePositions(Contract):
    account_id: str
    symbol: str | None = None


async def trading_permission_available(context: ToolContext) -> str | None:
    """Presentation only: live financial tools of an analysis-only Agent.

    Every financial handler rechecks current permission before it prepares or
    sends anything, so this grants and removes nothing; a permission raised
    later in the Run still works through tool_call.
    """
    async with context.db.sessions() as session:
        await agent_binding(session, context.owner_id, context.agent_id)
        if await trading_mode(session, context.owner_id, context.agent_id) == "full":
            return None
        level = await effective_permission(session, context.owner_id, context.agent_id)
    return "agent_analysis_only" if level == "analysis" else None


def target_key(request: TradeRequest) -> str:
    return (
        request.account_id
        + (":position:" if request.position_id else ":order:")
        + str(request.position_id or request.order_id or "")
    )


async def management_targets(
    context: ToolContext, requests: list[TradeRequest]
) -> dict[str, Position | Order | None]:
    """The broker's current ticket for each request that manages one (None: not found)."""
    result: dict[str, Position | Order | None] = {}
    for account_id in sorted(
        {request.account_id for request in requests if request.position_id or request.order_id}
    ):
        broker = await context.brokers.get(context.owner_id, account_id)
        selected = [request for request in requests if request.account_id == account_id]
        if any(request.position_id for request in selected):
            positions = {item.id: item for item in await broker.positions()}
            for request in selected:
                if request.position_id:
                    result[target_key(request)] = positions.get(request.position_id)
        if any(request.order_id for request in selected):
            orders = {item.id: item for item in await broker.orders()}
            for request in selected:
                if request.order_id:
                    result[target_key(request)] = orders.get(request.order_id)
    return result


async def management_snapshot(context: ToolContext, requests: list[TradeRequest]) -> dict[str, Any]:
    return {
        key: material_state(target) if target else None
        for key, target in (await management_targets(context, requests)).items()
    }


async def require_ticket(context: ToolContext, request: TradeRequest) -> None:
    """Refuse a first request for a ticket the call named and the account does not hold.

    The executor refuses it in any case; said here, before any card, with the tickets
    the account does hold, the next call names a real one. Nothing is put in the place
    of the ticket named. A call that already has a record is answered from it, never by
    this check, and an account that cannot be read leaves the request to the executor.
    """
    named = request.position_id or request.order_id
    if not named or not await never_recorded(context, request.operation_id):
        return
    try:
        broker = await context.brokers.get(context.owner_id, request.account_id)
        held = await (broker.positions() if request.position_id else broker.orders())
    except Exception:
        return
    if any(item.id == named for item in held):
        return
    kind = "position" if request.position_id else "order"
    resolve(
        request.symbol,
        [
            Option(
                item.id,
                (item.symbol,),
                item.model_dump(
                    mode="json",
                    include={"symbol", "side", "volume", "open_price", "price", "profit"},
                ),
            )
            for item in held
        ],
        missing=kind + "_not_found",
        argument=kind + "_id",
        use="refuse",
        listing="account_read",
    )


async def reviewed_contracts(
    context: ToolContext, requests: list[TradeRequest]
) -> list[dict[str, Any]]:
    """The broker's own specification of each symbol an approval card asks about: the
    real symbol and what one lot of it is, as the owner reviews it. A specification the
    broker cannot give is left out; the executor's preflight still requires it."""
    contracts: list[dict[str, Any]] = []
    for account_id, symbol in sorted({(r.account_id, r.symbol) for r in requests}):
        try:
            broker = await context.brokers.get(context.owner_id, account_id)
            instrument = await broker.instrument(symbol)
        except Exception:
            continue
        contracts.append({"account_id": account_id, **instrument.model_dump(mode="json")})
    return contracts


async def reviewed_approval(
    session: AsyncSession, context: ToolContext, requests: list[TradeRequest]
) -> TradeApprovalRow | None:
    """The approval card this Run already holds for the same exact operations, newest
    first: one still waiting for the owner, one approved, one whose operations reached
    the broker, or one the owner rejected with no word from the owner since.

    A repeated request in another call of the same Run (identical operation ids and
    fingerprints) answers from that card instead of asking the owner again: it waits on
    the same card, or returns the owner's rejection. A result that never reached the
    broker (a pause that has since been lifted), or a rejection the owner has spoken
    after in the conversation, asks again.
    """
    expected = [trade_fingerprint(request) for request in requests]
    rows = await session.scalars(
        select(TradeApprovalRow)
        .where(
            TradeApprovalRow.owner_id == context.owner_id,
            TradeApprovalRow.agent_id == context.agent_id,
            TradeApprovalRow.run_id == context.lease.run_id,
            TradeApprovalRow.status.in_(["pending", "approved", "completed", "rejected"]),
        )
        .order_by(TradeApprovalRow.created_at.desc(), TradeApprovalRow.id.desc())
    )
    for row in rows:
        if row.broker_snapshot.get("execution_mode", {}).get("value", "live") != "live":
            continue
        if [trade_fingerprint(TradeRequest.model_validate(item)) for item in row.requests] != (
            expected
        ):
            continue
        if row.status in {"pending", "approved"}:
            return row
        if row.status == "rejected":
            if not await owner_spoke_since(session, row):
                return row
            continue
        if all(result.get("status") in REACHED_BROKER for result in row.results):
            return row
    return None


async def owner_spoke_since(session: AsyncSession, row: TradeApprovalRow) -> bool:
    """Whether the owner wrote in the card's conversation after deciding it."""
    if row.thread_id is None:
        return False
    return (
        await session.scalar(
            select(MessageRow.id)
            .where(
                MessageRow.thread_id == row.thread_id,
                MessageRow.role == "user",
                # A card submission is not the owner speaking after a rejected trade card.
                MessageRow.origin == "owner",
                MessageRow.created_at > row.updated_at,
            )
            .limit(1)
        )
    ) is not None


async def new_risk_requests(
    context: ToolContext, requests: list[TradeRequest]
) -> list[TradeRequest]:
    """The requests that add risk on the broker's current facts.

    Entries always do. A close, cancel or stop change is classified the way the executor
    classifies it (``risk_reducing``) against the ticket the broker shows now, so a stop
    moved further away counts as new risk. A ticket the broker no longer shows is left
    to the executor, which refuses it with its own code.
    """
    result = [request for request in requests if not may_reduce_risk(request)]
    managing = [request for request in requests if may_reduce_risk(request)]
    if not managing:
        return result
    facts: dict[str, tuple[list[Position], list[Order]]] = {}
    for account_id in sorted({request.account_id for request in managing}):
        broker = await context.brokers.get(context.owner_id, account_id)
        orders = (
            await broker.orders()
            if any(r.order_id for r in managing if r.account_id == account_id)
            else []
        )
        facts[account_id] = (await broker.positions(), orders)
    for request in managing:
        positions, orders = facts[request.account_id]
        target: Position | Order | None = (
            next((item for item in positions if item.id == request.position_id), None)
            if request.position_id
            else next((item for item in orders if item.id == request.order_id), None)
            if request.order_id
            else None
        )
        if target is not None and not risk_reducing(request, target, positions=positions):
            result.append(request)
    return result


async def reused_card(context: ToolContext, requests: list[TradeRequest]) -> bool:
    """Whether this Run already holds a card for these exact requests: it answers again."""
    async with context.db.sessions() as session:
        return await reviewed_approval(session, context, requests) is not None


async def unjournaled(context: ToolContext, requests: list[TradeRequest]) -> list[TradeRequest]:
    async with context.db.sessions() as session:
        recorded = set(
            await session.scalars(
                select(TradingJournalRow.operation_id).where(
                    TradingJournalRow.owner_id == context.owner_id,
                    TradingJournalRow.operation_id.in_([r.operation_id for r in requests]),
                )
            )
        )
    return [request for request in requests if request.operation_id not in recorded]


async def foreign_tickets(context: ToolContext, requests: list[TradeRequest]) -> list[TradeRequest]:
    """The requests on a ticket the agent's own journaled order did not open: the owner's
    own position or another agent's. A ticket the broker no longer shows is left to the
    executor, which refuses it with its own code."""
    managing = [request for request in requests if request.position_id or request.order_id]
    if not managing:
        return []
    targets = await management_targets(context, managing)
    result: list[TradeRequest] = []
    async with context.db.sessions() as session:
        for request in managing:
            target = targets.get(target_key(request))
            if target is not None and (
                await ticket_agent(session, context.owner_id, request, target) != context.agent_id
            ):
                result.append(request)
    return result


async def start_trading_card(context: ToolContext) -> dict[str, Any]:
    """New trading was never started on this install (not the owner's Stop): nothing is
    sent and no approval is asked, but the owner gets the one-tap Start trading card in
    the conversation at once, instead of a bare refusal to find the safety sheet for."""
    from lonora_contracts.owner_actions import OwnerActionProposal
    from lonora_db.owner_actions import live_status, propose

    async with context.db.sessions() as session, session.begin():
        # The order every card takes them in: the owner's cards, then the Run.
        run = await require_lease(session, context.lease)
        card, created = await propose(
            session,
            context.owner_id,
            OwnerActionProposal(kind="resume_trading"),
            card_id=context.resource_id,
            agent_id=context.agent_id,
            thread_id=run.model_metadata.get("origin_thread_id") or context.thread_id,
            run_id=run.id,
        )
        await require_lease(session, context.lease, lock=True)
        return {
            "status": "failed",
            "code": "trading_not_started",
            "details": {"send_state": "not_sent"},
            "owner_action": {
                "id": card.id,
                "kind": card.kind,
                "status": live_status(card),
                "already_shown": not created,
            },
            "recovery": "Say in one line that trading has not been started and that the "
            "owner's one tap on the card starts it; ask again after the tap.",
        }


async def reference_quote(context: ToolContext, request: TradeRequest) -> dict[str, Any]:
    """The executable side now: ask for a buy, bid for a sell (10.3.1). A change to an
    existing ticket reads the side that closes it."""
    buy = request.action.startswith("buy")
    if request.position_id or request.order_id:
        target = (await management_targets(context, [request])).get(target_key(request))
        side = direction(str(target.side)) if target is not None else ""
        buy = side == "sell" if request.position_id else side == "buy"
    broker = await context.brokers.get(context.owner_id, request.account_id)
    quote = await broker.quote(request.symbol)
    return {
        "account_id": request.account_id,
        "symbol": request.symbol,
        "side": "ask" if buy else "bid",
        "price": str((quote.ask if buy else quote.bid).normalize()),
    }


class ModeChangedToFull(Exception):
    """The agent's mode became Full before its card was raised."""


async def never_started(context: ToolContext) -> bool:
    """No stored control: trading was never started on this install (it starts stopped),
    unlike the owner's own Stop."""
    async with context.db.sessions() as reader:
        return await reader.get(SettingRow, "trading_control") is None


async def refuse_braked_entries(
    session: AsyncSession, context: ToolContext, requests: list[TradeRequest]
) -> None:
    """Never ask the owner to approve new risk a brake in force would refuse at send.

    Stop new trading and a pause (``no_new_entries`` and stronger) hold every entry, so an
    approval card for one could only fail after the owner's tap. The boundary's own codes
    (``trading_disabled``, ``emergency_stop``, ``trading_restriction_active``) come back
    instead, and the agent offers the owner's Resume or Lift card. ``requests`` are the
    ones that add risk on the broker's current facts (``new_risk_requests``); a close,
    cancel or tightening is still asked and decided by the executor against the fresh
    broker target, which repeats every check at the moment of sending. This only
    refuses earlier.
    """
    entries = requests
    if not entries:
        return
    stored = await session.get(SettingRow, "trading_control", populate_existing=True)
    require_trading(TradingControl.model_validate(stored.payload if stored else {}))
    for request in entries:
        await require_unrestricted(
            session, context.owner_id, request, agent_id=context.agent_id, reducing=False
        )


def independent_exits(requests: list[TradeRequest]) -> bool:
    """Whether a batch is only full closes of distinct positions.

    No such close depends on another: each one is admitted again against its own fresh
    broker target under the send lock, and admission never blocks a risk-reducing exit.
    A failed, blocked or uncertain close must therefore never hold back the other
    approved exits (for example a close-all during an Emergency Stop).
    """
    positions = [request.position_id for request in requests]
    return all(
        request.action == "close_position"
        and request.volume is None
        and request.position_id is not None
        for request in requests
    ) and len(set(positions)) == len(positions)


def halted_receipts(remaining: list[TradeRequest], after: TradeResult) -> list[dict[str, Any]]:
    """Known not-sent receipts for the rest of a batch stopped by an unsettled result.

    A dependent sequence never continues after an operation that is not confirmed: the
    remaining operations may depend on it, so they are reported as never reaching the
    broker. Independent exits (see ``independent_exits``) never stop.
    """
    return [
        TradeResult(
            operation_id=request.operation_id,
            status="failed",
            code="batch_halted_after_unconfirmed_result",
            details={"send_state": "not_sent", "halted_after": after.operation_id},
        ).model_dump(mode="json")
        for request in remaining
    ]


async def approved_execution(
    context: ToolContext,
    requests: list[TradeRequest],
    *,
    gate_only: bool = False,
    named_ticket: bool = False,
    annotation: TradeAnnotation | None = None,
) -> dict[str, Any]:
    """``named_ticket``: the call itself named the ticket it manages (``trade_execute``).
    A batch built from the account's own list never is: its exits are never held back.
    ``annotation``: the agent's reason, label and tolerance, stored beside the requests."""
    approval_id = stable_id(context.lease.run_id, "approval:" + context.call_id)
    level = "analysis"
    provisional = False
    async with context.db.sessions() as reader:
        origin = await require_lease(reader, context.lease)
        # Shadow trading is removed (Q57): a Run started in it never asks or sends.
        if origin.model_metadata.get("execution_mode", "live") != "live":
            raise LonoraError("shadow_execution_forbidden", 403)
        await require_financial_agent(reader, context.owner_id, context.agent_id)
        previous = await reader.get(TradeApprovalRow, approval_id)
        mode = await trading_mode(reader, context.owner_id, context.agent_id)
        if mode != "full" and (previous is None or previous.status != "completed"):
            level = await effective_permission(reader, context.owner_id, context.agent_id)
            if level == "analysis":
                raise LonoraError("agent_analysis_only", 403)
            provisional = await provisional_voice(reader, origin)
        authority_requests = (
            [TradeRequest.model_validate(item) for item in previous.requests]
            if previous is not None
            else requests
        )
        grants = (
            [
                await available_authority(reader, context.owner_id, origin, request)
                for request in authority_requests
            ]
            if not gate_only and level == "autonomous"
            else []
        )
    if grants and all(grants) and not provisional:
        grants = await covering_grants(context, origin, authority_requests, grants)
    if not all(grants) or provisional:
        # The ladder is monotonic: a trade no active grant covers asks the owner with an
        # approval card, exactly like "Ask me", instead of being refused. Provisional
        # speech never spends standing authority: the owner's exact approval is the only
        # authority its operations are sent under.
        grants = []
    if named_ticket and previous is None:
        await require_ticket(context, requests[0])
    if grants:
        return await direct_execution(context, authority_requests, grants, annotation=annotation)
    adding: list[TradeRequest] = []
    foreign: list[TradeRequest] = []
    if previous is None and not gate_only and not await reused_card(context, requests):
        # Full executes on its own; Ask asks only for requests that add risk (4.1). A
        # ticket the agent's own order did not open is always the owner's exact approval.
        # A request already journaled is answered from its record (the door's idempotency),
        # never classified again against a ticket it may itself have changed.
        unrecorded = await unjournaled(context, requests)
        adding = await new_risk_requests(context, unrecorded)
        foreign = await foreign_tickets(context, unrecorded)
        if (mode == "full" or not adding) and not foreign:
            if adding and await never_started(context):
                return await start_trading_card(context)
            return await direct_execution(context, requests, annotation=annotation)
    initial_snapshot = await management_snapshot(context, requests) if previous is None else {}
    contracts = await reviewed_contracts(context, requests) if previous is None else []
    if adding:
        if await never_started(context):
            return await start_trading_card(context)
    validity: dict[str, Any] = {}
    if previous is None and not gate_only and adding:
        # Every card for new risk carries a tolerance; its reference is read now (10.3.1).
        if annotation is None or annotation.tolerance is None:
            async with context.db.sessions() as reader:
                # A brake in force answers first: no card could be raised anyway.
                await refuse_braked_entries(reader, context, adding)
            raise ToolRefusal(
                "tolerance_required",
                details={
                    "class": "input",
                    "retryable": True,
                    "hint": "Nothing was sent and no card was raised. Ask again with "
                    "tolerance: the price distance from the current executable price beyond "
                    "which the owner's approval no longer holds.",
                },
            )
        validity = {
            "tolerance": str(annotation.tolerance.normalize()),
            "reference": await reference_quote(context, adding[0]),
        }
    try:
        async with context.db.sessions() as session, session.begin():
            current = await require_lease(session, context.lease)
            if current.agent_id != context.agent_id:
                raise LonoraError("agent_run_mismatch", 409)
            await require_financial_agent(session, context.owner_id, current.agent_id)
            visible_thread_id = current.model_metadata.get("origin_thread_id") or context.thread_id
            # The order a mode change takes them in: authority, conversation, run.
            await authority_lock(session, context.agent_id)
            thread = await owned_thread(session, context.owner_id, visible_thread_id, lock=True)
            if thread.agent_id != context.agent_id and not thread.group_id:
                raise LonoraError("agent_thread_mismatch", 409)
            await require_lease(session, context.lease, lock=True)
            row = await session.get(TradeApprovalRow, approval_id)
            if row is None and not gate_only:
                row = await reviewed_approval(session, context, requests)
                if row is not None:
                    approval_id = row.id
            if row is None:
                if (
                    not gate_only
                    and mode != "full"
                    and not foreign
                    and await trading_mode(session, context.owner_id, context.agent_id) == "full"
                ):
                    raise ModeChangedToFull
                if not gate_only:
                    await refuse_braked_entries(session, context, adding)
                created = utcnow()
                row = TradeApprovalRow(
                    id=approval_id,
                    owner_id=context.owner_id,
                    run_id=context.lease.run_id,
                    thread_id=thread.id,
                    agent_id=context.agent_id,
                    call_id=context.call_id,
                    timeline_seq=thread.next_seq,
                    broker_snapshot={
                        **initial_snapshot,
                        "execution_mode": {"value": "live"},
                        "contracts": contracts,
                    },
                    requests=[r.model_dump(mode="json") for r in requests],
                    status="pending",
                    results=[],
                    created_at=created,
                    updated_at=created,
                    # No time limit (10.3.1): drift, a decision or a withdrawal ends it.
                    expires_at=None,
                    reason=annotation.reason if annotation else "",
                    label=annotation.label if annotation else None,
                    validity=validity,
                )
                session.add(row)
                await session.flush()
                approval_event(session, row)
            if row.owner_id != context.owner_id or row.run_id != context.lease.run_id:
                raise LonoraError("trade_approval_mismatch", 409)
            await expire_if_due(session, row)
            if row.status == "expired":
                # Its lifetime ended unapproved: nothing is sent. Ask again only when the
                # owner asks for a new request («طلب جديد»), which starts a new run.
                return {
                    "status": "expired",
                    "code": "trade_approval_expired",
                    "approval_id": row.id,
                }
            if row.status == "pending":
                return {
                    "_runtime_wait": True,
                    "_runtime_retry": True,
                    "question": "",
                    "approval_id": row.id,
                }
            if row.status == "rejected":
                return {
                    "status": "rejected",
                    "code": "trade_approval_rejected",
                    "approval_id": row.id,
                }
            if row.status == "drifted":
                # The quote left reference ± tolerance: nothing was sent.
                return {
                    "status": "drifted",
                    "code": "trade_approval_drifted",
                    "approval_id": row.id,
                    "recovery": drifted_prompt(row),
                }
            if row.status == "withdrawn":
                # Nothing was sent; the agent decides again under its current mode.
                return {
                    "status": "withdrawn",
                    "code": "trade_approval_withdrawn",
                    "approval_id": row.id,
                    "recovery": withdrawn_prompt(row, mode),
                }
            if row.status == "completed":
                return {
                    "approval_id": row.id,
                    "results": row.results,
                    **(row.results[0] if len(row.results) == 1 else {}),
                }
            if row.status != "approved":
                raise LonoraError("trade_approval_unavailable", 409)
            frozen = [TradeRequest.model_validate(item) for item in row.requests]
            card_annotation = TradeAnnotation(
                reason=row.reason,
                label=row.label,
                tolerance=row.validity.get("tolerance"),
            )
            expected_snapshot = row.broker_snapshot
            if gate_only:
                if await user_interrupt_pending(session, context.lease.run_id):
                    raise LonoraError("tool_call_superseded", 409)
                if [
                    trade_fingerprint(TradeRequest.model_validate(item)) for item in row.requests
                ] != [trade_fingerprint(r) for r in requests]:
                    raise LonoraError("trade_approval_request_changed", 409)
                return {"approved": True, "approval_id": row.id}
    except ModeChangedToFull:
        # The owner switched this agent to Full while the request was prepared: it is
        # decided again under Full, never parked on a card the switch cannot withdraw.
        return await approved_execution(
            context, requests, gate_only=gate_only, named_ticket=named_ticket
        )

    results: list[dict[str, Any]] = []
    independent = independent_exits(frozen)
    for index, request in enumerate(frozen):

        async def authorize(request: TradeRequest = request) -> None:
            async with context.db.sessions() as session:
                await require_lease(session, context.lease)
                approval = await session.get(TradeApprovalRow, approval_id)
                if (
                    approval is None
                    or approval.status != "approved"
                    or approval.owner_id != context.owner_id
                ):
                    raise LonoraError("trade_approval_unavailable", 409)
                if not any(
                    trade_fingerprint(TradeRequest.model_validate(item))
                    == trade_fingerprint(request)
                    for item in approval.requests
                ):
                    raise LonoraError("trade_approval_request_changed", 409)
                if await user_interrupt_pending(session, context.lease.run_id):
                    raise LonoraError("tool_call_superseded", 409)
            # Current owner intervention invalidates this management proposal.
            # Never restore old SL/TP/volume merely because an old card was approved.
            observed = await management_snapshot(context, [request])
            for key, value in observed.items():
                if key in expected_snapshot and expected_snapshot[key] != value:
                    raise LonoraError("trade_approval_broker_state_changed", 409)

        try:
            result = await context.trading.execute(
                context.owner_id,
                request,
                context.lease,
                authorization=authorize,
                account_authority_id=grants[index] if grants else None,
                expected_target=expected_snapshot.get(target_key(request)),
                annotation=card_annotation,
            )
        except LonoraError as error:
            result = TradeResult(
                operation_id=request.operation_id, status="failed", code=error.code
            )
        results.append(result.model_dump(mode="json"))
        stop = result.status != "confirmed" and not independent
        if stop:
            # Same rule as standing authority: never advance a dependent approved
            # sequence past an uncertain, failed or blocked operation.
            results.extend(halted_receipts(frozen[index + 1 :], result))
        async with context.db.sessions() as session, session.begin():
            await require_lease(session, context.lease, lock=True)
            current = await session.get(TradeApprovalRow, approval_id, with_for_update=True)
            assert current is not None
            if current.status != "approved":
                raise LonoraError("trade_approval_unavailable", 409)
            current.results = list(results)
            current.updated_at = utcnow()
            approval_event(session, current)
        if stop:
            break

    async with context.db.sessions() as session, session.begin():
        await require_lease(session, context.lease, lock=True)
        row = await session.scalar(
            select(TradeApprovalRow).where(TradeApprovalRow.id == approval_id).with_for_update()
        )
        assert row is not None
        row.status, row.results, row.updated_at = "completed", results, utcnow()
        approval_event(session, row)
    return {
        "approval_id": approval_id,
        "results": results,
        **(results[0] if len(results) == 1 else {}),
    }


async def covering_grants(
    context: ToolContext,
    origin: RunRow,
    requests: list[TradeRequest],
    grants: list[str | None],
) -> list[str | None]:
    """Drop a grant whose own terms refuse its request (``grant_covers``): a cap, the
    equity floor, the bounded stop rules, the owner's own position under a grant that
    excludes them. That request then asks the owner instead of being refused."""
    snapshots = {
        account_id: await authority_snapshot(
            await context.brokers.get(context.owner_id, account_id), account_id
        )
        for account_id in sorted({request.account_id for request in requests})
    }
    async with context.db.sessions() as session:
        return [
            identifier
            if identifier
            and await grant_covers(
                session,
                context.owner_id,
                origin,
                request,
                identifier,
                snapshots[request.account_id],
            )
            else None
            for request, identifier in zip(requests, grants, strict=True)
        ]


def tightened_stop(request: TradeRequest, before: dict[str, Any] | None) -> bool:
    """A stop loss moved toward the price (or set where there was none) on a position."""
    if (
        request.action != "modify_position"
        or request.stop_loss is None
        or request.clear_stop_loss
        or before is None
    ):
        return False
    previous = before.get("stop_loss")
    if previous is None:
        return True
    side = direction(str(before.get("side", "")))
    if side == "buy":
        return request.stop_loss > Decimal(str(previous))
    return side == "sell" and request.stop_loss < Decimal(str(previous))


async def stop_notice(
    context: ToolContext, request: TradeRequest, before: dict[str, Any] | None
) -> None:
    """The one-line notice of a stop the agent tightened under its grant (Q31): no Undo.
    The trade is already confirmed, so a lost lease only skips the notice."""
    assert request.position_id is not None and request.stop_loss is not None
    try:
        async with context.db.sessions() as session, session.begin():
            run = await require_lease(session, context.lease)
            await raise_stop_tightened(
                session,
                context.owner_id,
                operation_id=request.operation_id,
                account_id=request.account_id,
                symbol=request.symbol,
                position_id=request.position_id,
                previous_stop_loss=None if before is None else before.get("stop_loss"),
                stop_loss=str(request.stop_loss.normalize()),
                agent_id=context.agent_id,
                thread_id=await report_thread(session, run),
                run_id=run.id,
            )
    except LonoraError:
        return


async def direct_execution(
    context: ToolContext,
    requests: list[TradeRequest],
    grants: list[str | None] | None = None,
    *,
    annotation: TradeAnnotation | None = None,
) -> dict[str, Any]:
    """Execution without a card: an agent in Full, a risk-reducing request in Ask, or a
    standing grant (``grants``, until grants are removed). The same executor, journal and
    independent verification; the door rechecks the mode at send."""
    expected = await management_snapshot(context, requests)
    results: list[dict[str, Any]] = []
    independent = independent_exits(requests)
    for index, (request, identifier) in enumerate(
        zip(requests, grants or [None] * len(requests), strict=True)
    ):

        async def current() -> None:
            async with context.db.sessions() as session:
                await require_lease(session, context.lease)
                if await user_interrupt_pending(session, context.lease.run_id):
                    raise LonoraError("tool_call_superseded", 409)

        try:
            result = await context.trading.execute(
                context.owner_id,
                request,
                context.lease,
                authorization=current,
                account_authority_id=identifier,
                expected_target=expected.get(target_key(request)),
                annotation=annotation,
            )
        except LonoraError as error:
            result = TradeResult(
                operation_id=request.operation_id, status="failed", code=error.code
            )
        results.append(result.model_dump(mode="json"))
        before = expected.get(target_key(request))
        if identifier and result.status == "confirmed" and tightened_stop(request, before):
            await stop_notice(context, request, before)
        if result.status != "confirmed" and not independent:
            # Never advance a dependent batch after uncertain/blocked financial state.
            results.extend(halted_receipts(requests[index + 1 :], result))
            break
    return {
        "results": results,
        **(results[0] if len(results) == 1 else {}),
        "authorization": "account_authority" if grants else "trading_mode",
    }


ORDER_SIZE_HINT = (
    "This contract takes sizes from {minimum} to {maximum} in steps of {step}. Nothing "
    "was sent. Do not choose another size for the owner: say the smallest size in one "
    "plain line and ask, unless the owner or the signed mandate already gave a size that fits."
)


async def require_order_size(broker: Any, symbol: str, volume: Any) -> None:
    """Refuse a new order whose size the contract cannot take, with the contract's limits.

    The model then corrects the request itself instead of reporting a failed order. The
    executor's own check still decides; when the specification cannot be read here, it
    answers alone. Only a first attempt is checked (`never_recorded`).
    """
    try:
        instrument = await broker.instrument(symbol)
        size = Decimal(str(volume))
    except Exception:
        return
    minimum, maximum, step = instrument.volume_min, instrument.volume_max, instrument.volume_step
    if minimum <= size <= maximum and (size - minimum) % step == 0:
        return
    raise ToolRefusal(
        "volume_out_of_range" if not minimum <= size <= maximum else "volume_step_mismatch",
        details={
            "class": "input",
            "retryable": False,
            "hint": ORDER_SIZE_HINT.format(minimum=minimum, maximum=maximum, step=step),
            "limits": {
                "volume_min": str(minimum),
                "volume_max": str(maximum),
                "volume_step": str(step),
            },
        },
    )


async def never_recorded(context: ToolContext, operation_id: str) -> bool:
    """True while this call has left neither an approval card nor a journal entry.

    A call that comes back after the owner's approval, after a restart or to reconcile an
    unknown outcome is answered from its record, never by a fresh check.
    """
    approval_id = stable_id(context.lease.run_id, "approval:" + context.call_id)
    async with context.db.sessions() as session:
        return (
            await session.get(TradeApprovalRow, approval_id) is None
            and await session.get(TradingJournalRow, operation_id) is None
        )


async def execute(context: ToolContext, args: dict[str, Any]) -> dict[str, Any]:
    args = dict(args)
    args.pop("operation_id", None)
    # Beside the request, never inside it: the operation id is the request's alone.
    annotation = TradeAnnotation(
        reason=str(args.pop("reason", "") or ""),
        label=args.pop("label", None),
        tolerance=args.pop("tolerance", None),
    )
    if args.get("thesis_id") is None:
        args.pop("thesis_id", None)
    for field in ("clear_stop_loss", "clear_take_profit"):
        if args.get(field) is False:
            args.pop(field)
    async with context.db.sessions() as session:
        await agent_binding(session, context.owner_id, context.agent_id)
        await require_lease(session, context.lease)
    sized = None
    managing = args.get("position_id") or args.get("order_id")
    if args.get("symbol") and args.get("account_id"):
        broker = await context.brokers.get(context.owner_id, str(args["account_id"]))
        # A new order names the catalogue's exact symbol. An exit or a change to an
        # existing ticket is never held back by the catalogue: preflight requires the
        # ticket's own symbol.
        args["symbol"] = await (canonical_broker_symbol if managing else order_symbol)(
            broker, str(args["symbol"])
        )
        if not managing and args.get("volume") is not None:
            sized = broker
    args["operation_id"] = stable_id(context.lease.run_id, "trade:" + request_hash(args))
    if sized is not None and await never_recorded(context, args["operation_id"]):
        await require_order_size(sized, args["symbol"], args["volume"])
    return await approved_execution(
        context,
        [TradeRequest.model_validate(args)],
        named_ticket=bool(managing),
        annotation=annotation,
    )


async def close_positions(context: ToolContext, args: dict[str, Any]) -> dict[str, Any]:
    async with context.db.sessions() as session:
        await agent_binding(session, context.owner_id, context.agent_id)
        await require_lease(session, context.lease)
    approval_id = stable_id(context.lease.run_id, "approval:" + context.call_id)
    # The ticket set this call read is frozen with the call, card or not: a replay of the
    # same call never silently extends it to positions opened later.
    frozen_key = "trade-close-set:" + approval_id
    async with context.db.sessions() as session:
        previous = await session.get(TradeApprovalRow, approval_id)
        frozen = await session.get(EffectReceiptRow, frozen_key)
        if previous:
            requests = [TradeRequest.model_validate(item) for item in previous.requests]
        elif frozen:
            requests = [TradeRequest.model_validate(item) for item in frozen.result["requests"]]
        else:
            requests = []
    if previous is None and frozen is None:
        broker = await context.brokers.get(context.owner_id, args["account_id"])
        positions = await broker.positions()
        symbol = args.get("symbol")
        if symbol is not None and not any(p.symbol == symbol for p in positions):
            # No open position under that name: the catalogue's spelling, or the
            # account's real candidates. A listed position is never held back.
            symbol = await order_symbol(broker, symbol)
        requests = [
            TradeRequest(
                account_id=args["account_id"],
                symbol=p.symbol,
                action="close_position",
                position_id=p.id,
                operation_id=stable_id(
                    context.lease.run_id, "close:" + context.call_id + ":" + p.id
                ),
            )
            for p in sorted(positions, key=lambda p: p.id)
            if symbol is None or p.symbol == symbol
        ]
        if not requests:
            return {"results": [], "code": "no_positions"}
        async with context.db.sessions() as session, session.begin():
            await require_lease(session, context.lease, lock=True)
            stored = await session.get(EffectReceiptRow, frozen_key)
            if stored is not None:
                # A concurrent replay of this call froze its set first: that set stands.
                requests = [TradeRequest.model_validate(item) for item in stored.result["requests"]]
            else:
                session.add(
                    EffectReceiptRow(
                        key=frozen_key,
                        result={"requests": [r.model_dump(mode="json") for r in requests]},
                    )
                )
    return await approved_execution(context, requests)


class TradeRecordReference(Contract):
    operation_id: str = Field(min_length=1, max_length=80)


class TradeRecordHistory(Contract):
    account_id: str | None = None
    symbol: str | None = None
    limit: int = Field(default=5, ge=1, le=10)


async def read_record(context: ToolContext, args: dict[str, Any]) -> dict[str, Any]:
    async with context.db.sessions() as session:
        await agent_binding(session, context.owner_id, context.agent_id)
        row = await session.get(TradingJournalRow, args["operation_id"])
        if row is None or row.owner_id != context.owner_id:
            raise LonoraError("operation_not_found", 404)
        # Trading records on owner accounts are shared operational records.
        return record_excerpt(row, symbol=None)


async def record_history(context: ToolContext, args: dict[str, Any]) -> dict[str, Any]:
    params = TradeRecordHistory.model_validate(args)
    async with context.db.sessions() as session:
        agent = await agent_binding(session, context.owner_id, context.agent_id)
        account_id = params.account_id or agent.trading_account_id
        symbol = params.symbol or (
            agent.trading_symbol
            if not params.account_id or params.account_id == agent.trading_account_id
            else None
        )
        query = select(TradingJournalRow).where(TradingJournalRow.owner_id == context.owner_id)
        if account_id:
            query = query.where(TradingJournalRow.account_id == account_id)
        if symbol:
            query = query.where(TradingJournalRow.request["symbol"].as_string() == symbol)
        rows = list(
            await session.scalars(
                query.order_by(
                    TradingJournalRow.updated_at.desc(), TradingJournalRow.operation_id
                ).limit(params.limit + 1)
            )
        )
        return {
            "records": [
                {
                    "operation_id": row.operation_id,
                    "symbol": row.request.get("symbol"),
                    "account_id": row.account_id,
                    "action": row.request.get("action"),
                    "status": row.status,
                    "code": row.result.get("code"),
                    "recorded_at": row.updated_at.isoformat(),
                    "historical_evidence_available": bool(
                        row.result.get("details", {}).get("execution_evidence")
                    ),
                }
                for row in rows[: params.limit]
            ],
            "more_available": len(rows) > params.limit,
            "details_tool": "trade_record_read",
            "execution_authorized": False,
        }


class ApprovalReference(Contract):
    approval_id: str = Field(min_length=1, max_length=36)


async def withdraw_card(context: ToolContext, args: dict[str, Any]) -> dict[str, Any]:
    params = ApprovalReference.model_validate(args)
    async with context.db.sessions() as session, session.begin():
        await require_lease(session, context.lease)
        row = await withdraw_own(session, context.owner_id, context.agent_id, params.approval_id)
        await require_lease(session, context.lease, lock=True)
    return {"approval_id": row.id, "status": row.status}


class TradingModeAsk(Contract):
    agent_id: str | None = Field(default=None, min_length=1, max_length=36)


async def switch_to_ask(context: ToolContext, args: dict[str, Any]) -> dict[str, Any]:
    """Any agent may switch itself to Ask; Lonora may switch a team agent (4.2.2)."""
    target = TradingModeAsk.model_validate(args).agent_id or context.agent_id
    async with context.db.sessions() as session, session.begin():
        await require_lease(session, context.lease)
        caller = await agent_binding(session, context.owner_id, context.agent_id)
        if target != context.agent_id and caller.role != "personal":
            raise LonoraError("trading_mode_other_agent_forbidden", 403)
        mode = await set_trading_mode(
            session,
            context.owner_id,
            target,
            "ask",
            by="agent" if target == context.agent_id else "lonora",
        )
        await require_lease(session, context.lease, lock=True)
    return {"agent_id": target, "trading_mode": mode}


def tools() -> list[Tool]:
    return [
        Tool(
            "trade_record_history",
            "Find actual durable execution receipts and failures by bound account/symbol. Use trade_record_read for the recorded evidence; never reconstruct past decisions from current prices. This does not authorize execution.",
            TradeRecordHistory,
            record_history,
            True,
        ),
        Tool(
            "trade_record_read",
            "Read one owned historical trade request, exact outcome, Goal lineage and original planned/final preflight evidence. Missing legacy evidence stays unavailable. Never resubmit a trade from this record.",
            TradeRecordReference,
            read_record,
            True,
            poller=True,
        ),
        Tool(
            "trade_execute",
            "Buy, sell, pending orders; close, modify or cancel positions/orders. In Full, or "
            "for a risk-reducing request, it executes at once, except on a ticket you did not "
            "open. In Ask, a request that adds risk (outside an active signed grant) waits for a "
            "Trade Approval card; chat agreement is not approval. Reconcile an ambiguous result "
            "before retrying. With a bound market, omit account_id and symbol. A card needs "
            "tolerance.",
            AnnotatedTradeRequest,
            execute,
            financial=True,
            replay_safe=True,
            legacy_replay_safe=True,
            eager=eager_for("market"),
            availability=trading_permission_available,
        ),
        Tool(
            "trade_close_positions",
            "Close currently open broker positions, or only an exact symbol. A close reduces risk, so "
            "it executes without a card in Full and in Ask, except on a ticket your own order did not open. "
            "Each ticket has an independent durable receipt, and a failed or uncertain close never "
            "holds back the other tickets; a repeat never adds later positions. Reconcile an "
            "uncertain ticket before retrying it.",
            ClosePositions,
            close_positions,
            financial=True,
            replay_safe=True,
            legacy_replay_safe=True,
            eager=eager_for("market"),
            availability=trading_permission_available,
        ),
        Tool(
            "trade_approval_withdraw",
            "Withdraw your own pending Trade Approval card when its reason no longer holds; "
            "nothing is sent. Tell the owner in one line why.",
            ApprovalReference,
            withdraw_card,
            replay_safe=True,
        ),
        Tool(
            "trading_mode_ask",
            "Switch to Ask: from now on every request that adds risk waits for the owner's "
            "Trade Approval card. Omit agent_id for yourself; Lonora may name a team agent. "
            "Tell the owner in one line why. Only the owner sets Full.",
            TradingModeAsk,
            switch_to_ask,
            replay_safe=True,
        ),
    ]
