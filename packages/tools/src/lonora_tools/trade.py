from typing import Any

from lonora_contracts.account import Order, Position
from lonora_contracts.domain import Contract, utcnow
from lonora_contracts.shadow import ExecutionMode
from lonora_contracts.trading import TradeRequest, TradeResult, TradingControl
from lonora_core.trading_control import require_trading
from lonora_core.user_error import LonoraError
from lonora_db.account_authority import require_authority
from lonora_db.agent_binding import (
    agent_binding,
    require_financial_agent,
)
from lonora_db.agent_permissions import effective_permission
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
from lonora_db.trade_approvals import approval_event
from lonora_db.transactions import owned_thread
from lonora_session.idempotency import request_hash, stable_id
from lonora_trading.account_authority import (
    available_authority,
    covering_authority,
    provisional_voice,
)
from lonora_trading.admission import may_reduce_risk
from lonora_trading.idempotency import trade_fingerprint
from lonora_trading.journal import record_excerpt
from lonora_trading.manual_activity import material_state
from lonora_trading.restrictions import require_unrestricted
from pydantic import Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from .base import Tool, eager_for
from .context import ToolContext
from .symbols import canonical_broker_symbol

# Results whose operation reached, or may have reached, the broker: never asked twice.
REACHED_BROKER = {"confirmed", "submitted", "ambiguous", "resolved"}


class ClosePositions(Contract):
    account_id: str
    symbol: str | None = None


async def trading_permission_available(context: ToolContext) -> str | None:
    """Presentation only: live financial tools of an analysis-only Agent.

    Every financial handler rechecks current permission before it prepares or
    sends anything, so this grants and removes nothing; a permission raised
    later in the Run still works through tool_call. Shadow execution does not
    depend on the live permission level and stays available.
    """
    async with context.db.sessions() as session:
        agent = await agent_binding(session, context.owner_id, context.agent_id)
        run = await require_lease(session, context.lease)
        if agent.execution_mode == "shadow" or run.model_metadata.get("execution_mode") == "shadow":
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
                MessageRow.created_at > row.updated_at,
            )
            .limit(1)
        )
    ) is not None


async def refuse_braked_entries(
    session: AsyncSession, context: ToolContext, requests: list[TradeRequest]
) -> None:
    """Never ask the owner to approve new risk a brake in force would refuse at send.

    Stop new trading and a pause (``no_new_entries`` and stronger) hold every entry, so an
    approval card for one could only fail after the owner's tap. The boundary's own codes
    (``trading_disabled``, ``emergency_stop``, ``trading_restriction_active``) come back
    instead, and the agent offers the owner's Resume or Lift card. Only actions that can
    never reduce risk are checked here (``may_reduce_risk``); a close, cancel or stop
    change is still asked and decided by the executor against the fresh broker target,
    which repeats every check at the moment of sending. This only refuses earlier.
    """
    entries = [request for request in requests if not may_reduce_risk(request)]
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
    context: ToolContext, requests: list[TradeRequest], *, gate_only: bool = False
) -> dict[str, Any]:
    approval_id = stable_id(context.lease.run_id, "approval:" + context.call_id)
    level = "analysis"
    provisional = False
    async with context.db.sessions() as reader:
        origin = await require_lease(reader, context.lease)
        mode = (
            "shadow"
            if gate_only and origin.model_metadata.get("execution_mode") == "shadow"
            else "live"
        )
        await require_financial_agent(
            reader, context.owner_id, context.agent_id, execution_mode=mode
        )
        previous = await reader.get(TradeApprovalRow, approval_id)
        if mode == "live" and (previous is None or previous.status != "completed"):
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
            if mode == "live" and not gate_only and level == "autonomous"
            else []
        )
    if grants and all(grants) and not provisional:
        grants = await covering_grants(context, origin, authority_requests, grants)
    if not all(grants):
        # The ladder is monotonic: a trade no active grant covers asks the owner with an
        # approval card, exactly like "Ask me", instead of being refused.
        grants = []
    if grants and not provisional:
        return await account_authorized_execution(context, authority_requests, grants)
    if mode == "shadow" and previous is None:
        from lonora_trading.shadow import ShadowReadView

        initial_snapshot: dict[str, Any] = {}
        for request in requests:
            view = ShadowReadView(
                context.db, context.brokers, context.owner_id, context.agent_id, request.account_id
            )
            targets = (
                await view.positions()
                if request.position_id
                else await view.orders()
                if request.order_id
                else []
            )
            target_id = request.position_id or request.order_id
            if target_id:
                target = next((item for item in targets if item.id == target_id), None)
                key = (
                    request.account_id
                    + (":position:" if request.position_id else ":order:")
                    + target_id
                )
                initial_snapshot[key] = material_state(target) if target else None
    else:
        initial_snapshot = await management_snapshot(context, requests) if previous is None else {}
    async with context.db.sessions() as session, session.begin():
        current = await require_lease(session, context.lease)
        if current.agent_id != context.agent_id:
            raise LonoraError("agent_run_mismatch", 409)
        await require_financial_agent(
            session, context.owner_id, current.agent_id, execution_mode=mode
        )
        visible_thread_id = current.model_metadata.get("origin_thread_id") or context.thread_id
        thread = await owned_thread(session, context.owner_id, visible_thread_id, lock=True)
        if thread.agent_id != context.agent_id and not thread.group_id:
            raise LonoraError("agent_thread_mismatch", 409)
        await require_lease(session, context.lease, lock=True)
        row = await session.get(TradeApprovalRow, approval_id)
        if row is None and mode == "live" and not gate_only:
            row = await reviewed_approval(session, context, requests)
            if row is not None:
                approval_id = row.id
        if row is None:
            if mode == "live" and not gate_only:
                await refuse_braked_entries(session, context, requests)
            row = TradeApprovalRow(
                id=approval_id,
                owner_id=context.owner_id,
                run_id=context.lease.run_id,
                thread_id=thread.id,
                agent_id=context.agent_id,
                call_id=context.call_id,
                timeline_seq=thread.next_seq,
                broker_snapshot={**initial_snapshot, "execution_mode": {"value": mode}},
                requests=[r.model_dump(mode="json") for r in requests],
                status="pending",
                results=[],
            )
            session.add(row)
            await session.flush()
            approval_event(session, row)
        if row.owner_id != context.owner_id or row.run_id != context.lease.run_id:
            raise LonoraError("trade_approval_mismatch", 409)
        if row.status == "pending":
            return {
                "_runtime_wait": True,
                "_runtime_retry": True,
                "question": "",
                "approval_id": row.id,
            }
        if row.status == "rejected":
            return {"status": "rejected", "code": "trade_approval_rejected", "approval_id": row.id}
        if row.status == "completed":
            return {
                "approval_id": row.id,
                "results": row.results,
                **(row.results[0] if len(row.results) == 1 else {}),
            }
        if row.status != "approved":
            raise LonoraError("trade_approval_unavailable", 409)
        frozen = [TradeRequest.model_validate(item) for item in row.requests]
        expected_snapshot = row.broker_snapshot
        if gate_only:
            if await user_interrupt_pending(session, context.lease.run_id):
                raise LonoraError("tool_call_superseded", 409)
            if [trade_fingerprint(TradeRequest.model_validate(item)) for item in row.requests] != [
                trade_fingerprint(r) for r in requests
            ]:
                raise LonoraError("trade_approval_request_changed", 409)
            return {"approved": True, "approval_id": row.id}

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
    """Drop a grant that does not cover the ticket it would manage (the owner's own
    position under a grant that excludes them); that request then asks the owner."""
    excluded: set[str] = set()
    async with context.db.sessions() as session:
        for request, identifier in zip(requests, grants, strict=True):
            if identifier and (request.position_id or request.order_id):
                _, envelope = await require_authority(
                    session, context.owner_id, context.agent_id, identifier
                )
                if not envelope.allow_manual_positions:
                    excluded.add(target_key(request))
    if not excluded:
        return grants
    targets = await management_targets(
        context, [request for request in requests if target_key(request) in excluded]
    )
    async with context.db.sessions() as session:
        return [
            await covering_authority(
                session, context.owner_id, origin, request, targets.get(target_key(request))
            )
            if identifier and target_key(request) in excluded
            else identifier
            for request, identifier in zip(requests, grants, strict=True)
        ]


async def account_authorized_execution(
    context: ToolContext, requests: list[TradeRequest], grants: list[str | None]
) -> dict[str, Any]:
    """Standing authority uses the same executor, journal and independent verification."""
    expected = await management_snapshot(context, requests)
    results: list[dict[str, Any]] = []
    independent = independent_exits(requests)
    for index, (request, identifier) in enumerate(zip(requests, grants, strict=True)):
        assert identifier is not None

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
            )
        except LonoraError as error:
            result = TradeResult(
                operation_id=request.operation_id, status="failed", code=error.code
            )
        results.append(result.model_dump(mode="json"))
        if result.status != "confirmed" and not independent:
            # Never advance a dependent batch after uncertain/blocked financial state.
            results.extend(halted_receipts(requests[index + 1 :], result))
            break
    return {
        "results": results,
        **(results[0] if len(results) == 1 else {}),
        "authorization": "account_authority",
    }


async def execute(context: ToolContext, args: dict[str, Any]) -> dict[str, Any]:
    args = dict(args)
    args.pop("operation_id", None)
    if args.get("thesis_id") is None:
        args.pop("thesis_id", None)
    for field in ("clear_stop_loss", "clear_take_profit"):
        if args.get(field) is False:
            args.pop(field)
    async with context.db.sessions() as session:
        from lonora_db.agent_binding import agent_binding

        agent = await agent_binding(session, context.owner_id, context.agent_id)
        run = await require_lease(session, context.lease)
        shadow = (
            agent.execution_mode == "shadow" or run.model_metadata.get("execution_mode") == "shadow"
        )
    if (
        args.get("symbol")
        and args.get("account_id")
        and not (shadow and args.get("action") == "cancel_order")
    ):
        broker = await context.brokers.get(context.owner_id, str(args["account_id"]))
        args["symbol"] = await canonical_broker_symbol(broker, str(args["symbol"]))
    args["operation_id"] = stable_id(
        context.lease.run_id, ("shadow:" if shadow else "trade:") + request_hash(args)
    )
    if shadow:
        from lonora_trading.shadow import execute_shadow

        result = await execute_shadow(
            context.db,
            context.brokers,
            context.owner_id,
            context.agent_id,
            context.thread_id,
            context.lease,
            TradeRequest.model_validate(args),
        )
        data = result.model_dump(mode="json")
        return {"mode": "shadow", "results": [data], **data}
    return await approved_execution(context, [TradeRequest.model_validate(args)])


async def close_positions(context: ToolContext, args: dict[str, Any]) -> dict[str, Any]:
    async with context.db.sessions() as session:
        from lonora_db.agent_binding import agent_binding

        agent = await agent_binding(session, context.owner_id, context.agent_id)
        run = await require_lease(session, context.lease)
    if agent.execution_mode == "shadow" or run.model_metadata.get("execution_mode") == "shadow":
        from lonora_trading.shadow import execute_shadow, shadow_rows

        key = "shadow-close-all:" + context.effect_key
        intent = request_hash(args)
        async with context.db.sessions() as session, session.begin():
            await require_lease(session, context.lease, lock=True)
            receipt = await session.get(EffectReceiptRow, key)
            if receipt and receipt.result.get("intent") != intent:
                raise LonoraError("operation_id_conflict", 409)
            if receipt is None:
                rows = await shadow_rows(
                    context.db,
                    context.owner_id,
                    context.agent_id,
                    args["account_id"],
                    args.get("symbol"),
                )
                requests = [
                    TradeRequest(
                        account_id=row.account_id,
                        symbol=row.symbol,
                        action="close_position",
                        position_id=row.id,
                        operation_id=stable_id(context.resource_id, "shadow-close:" + row.id),
                    )
                    for row in rows
                    if row.status == "open"
                ]
                session.add(
                    EffectReceiptRow(
                        key=key,
                        result={
                            "intent": intent,
                            "requests": [request.model_dump(mode="json") for request in requests],
                        },
                    )
                )
            else:
                requests = [
                    TradeRequest.model_validate(value) for value in receipt.result["requests"]
                ]
        results: list[dict[str, Any]] = []
        for request in requests:
            result = await execute_shadow(
                context.db,
                context.brokers,
                context.owner_id,
                context.agent_id,
                context.thread_id,
                context.lease,
                request,
            )
            results.append(result.model_dump(mode="json"))
        return {"mode": "shadow", "results": results}
    approval_id = stable_id(context.lease.run_id, "approval:" + context.call_id)
    async with context.db.sessions() as session:
        previous = await session.get(TradeApprovalRow, approval_id)
        if previous:
            requests = [TradeRequest.model_validate(item) for item in previous.requests]
        else:
            requests = []
    if previous is None:
        broker = await context.brokers.get(context.owner_id, args["account_id"])
        positions = await broker.positions()
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
            if args.get("symbol") is None or p.symbol == args["symbol"]
        ]
        if not requests:
            return {"results": [], "code": "no_positions"}
    return await approved_execution(context, requests)


class TradeRecordReference(Contract):
    operation_id: str = Field(min_length=1, max_length=80)


class TradeRecordHistory(Contract):
    account_id: str | None = None
    symbol: str | None = None
    execution_mode: ExecutionMode | None = None
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
        if params.execution_mode:
            query = query.where(TradingJournalRow.execution_mode == params.execution_mode)
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
                    "execution_mode": row.execution_mode,
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


def tools() -> list[Tool]:
    return [
        Tool(
            "trade_record_history",
            "Find actual durable live/Shadow execution receipts and failures by bound account/symbol. Use trade_record_read for the recorded evidence; never reconstruct past decisions from current prices. This does not authorize execution.",
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
            "Execute a broker trade: buy or sell to open a position, place a pending limit/stop order, close or modify a position, or modify/cancel an order. Use an active signed account grant without per-order confirmation. "
            "Otherwise propose the immutable operation using the real financial Approve and Reject controls "
            "in chat or voice and wait for confirmation; spoken or typed agreement is not approval. "
            "The server validates current authority, broker preflight and the actual broker result. "
            "Reconcile ambiguous execution before retrying. When an immutable "
            "trading market is bound, omit account_id and symbol or pass that bound pair; never ask "
            "which pair or ask the owner to retype the symbol. Read broker positions/orders first, "
            "including manually opened tickets. Saved goals use goal_step_execute instead.",
            TradeRequest,
            execute,
            financial=True,
            replay_safe=True,
            legacy_replay_safe=True,
            eager=eager_for("market"),
            availability=trading_permission_available,
        ),
        Tool(
            "trade_close_positions",
            "Close currently open broker positions, or only an exact symbol, within an active signed "
            "account grant without per-order confirmation. Otherwise propose the current ticket set "
            "using the real Approve and Reject controls; approval freezes that reviewed set. "
            "Each ticket has an independent durable receipt, and a failed or uncertain close never "
            "holds back the other tickets. Never silently extend a reviewed operation to later "
            "positions. Reconcile an uncertain ticket before retrying it.",
            ClosePositions,
            close_positions,
            financial=True,
            replay_safe=True,
            legacy_replay_safe=True,
            availability=trading_permission_available,
        ),
    ]
