from typing import Any

from lonora_contracts.domain import Contract, utcnow
from lonora_contracts.trading import TradeRequest, TradeResult
from lonora_core.user_error import LonoraError
from lonora_db.agent_binding import require_financial_agent
from lonora_db.runs import require_lease
from lonora_db.schema import TradeApprovalRow
from lonora_db.steering import user_interrupt_pending
from lonora_db.trade_approvals import approval_event
from lonora_db.transactions import owned_thread
from lonora_session.idempotency import request_hash, stable_id
from lonora_trading.idempotency import trade_fingerprint
from lonora_trading.manual_activity import material_state
from sqlalchemy import select

from .base import Tool
from .context import ToolContext
from .symbols import canonical_broker_symbol


class ClosePositions(Contract):
    account_id: str
    symbol: str | None = None


async def management_snapshot(context: ToolContext, requests: list[TradeRequest]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for account_id in sorted(
        {request.account_id for request in requests if request.position_id or request.order_id}
    ):
        broker = await context.brokers.get(context.owner_id, account_id)
        selected = [request for request in requests if request.account_id == account_id]
        if any(request.position_id for request in selected):
            positions = {item.id: item for item in await broker.positions()}
            for request in selected:
                if request.position_id:
                    position = positions.get(request.position_id)
                    result[account_id + ":position:" + request.position_id] = (
                        material_state(position) if position else None
                    )
        if any(request.order_id for request in selected):
            orders = {item.id: item for item in await broker.orders()}
            for request in selected:
                if request.order_id:
                    order = orders.get(request.order_id)
                    result[account_id + ":order:" + request.order_id] = (
                        material_state(order) if order else None
                    )
    return result


async def approved_execution(
    context: ToolContext, requests: list[TradeRequest], *, gate_only: bool = False
) -> dict[str, Any]:
    approval_id = stable_id(context.lease.run_id, "approval:" + context.call_id)
    async with context.db.sessions() as reader:
        await require_financial_agent(reader, context.owner_id, context.agent_id)
        previous = await reader.get(TradeApprovalRow, approval_id)
    initial_snapshot = await management_snapshot(context, requests) if previous is None else {}
    async with context.db.sessions() as session, session.begin():
        current = await require_lease(session, context.lease)
        if current.agent_id != context.agent_id:
            raise LonoraError("agent_run_mismatch", 409)
        await require_financial_agent(session, context.owner_id, current.agent_id)
        visible_thread_id = current.model_metadata.get("origin_thread_id") or context.thread_id
        thread = await owned_thread(session, context.owner_id, visible_thread_id, lock=True)
        if thread.agent_id != context.agent_id and not thread.group_id:
            raise LonoraError("agent_thread_mismatch", 409)
        await require_lease(session, context.lease, lock=True)
        row = await session.get(TradeApprovalRow, approval_id)
        if row is None:
            row = TradeApprovalRow(
                id=approval_id,
                owner_id=context.owner_id,
                run_id=context.lease.run_id,
                thread_id=thread.id,
                agent_id=context.agent_id,
                call_id=context.call_id,
                timeline_seq=thread.next_seq,
                broker_snapshot=initial_snapshot,
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
            return {"approval_id": row.id, "results": row.results}
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
    for request in frozen:

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
                context.owner_id, request, context.lease, authorization=authorize
            )
        except LonoraError as error:
            result = TradeResult(
                operation_id=request.operation_id, status="failed", code=error.code
            )
        results.append(result.model_dump(mode="json"))
        async with context.db.sessions() as session, session.begin():
            await require_lease(session, context.lease, lock=True)
            current = await session.get(TradeApprovalRow, approval_id, with_for_update=True)
            assert current is not None
            if current.status != "approved":
                raise LonoraError("trade_approval_unavailable", 409)
            current.results = list(results)
            current.updated_at = utcnow()
            approval_event(session, current)

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


async def execute(context: ToolContext, args: dict[str, Any]) -> dict[str, Any]:
    args = dict(args)
    args.pop("operation_id", None)
    if args.get("thesis_id") is None:
        args.pop("thesis_id", None)
    if args.get("symbol") and args.get("account_id"):
        broker = await context.brokers.get(context.owner_id, str(args["account_id"]))
        args["symbol"] = await canonical_broker_symbol(broker, str(args["symbol"]))
    for field in ("clear_stop_loss", "clear_take_profit"):
        if args.get(field) is False:
            args.pop(field)
    args["operation_id"] = stable_id(context.lease.run_id, "trade:" + request_hash(args))
    return await approved_execution(context, [TradeRequest.model_validate(args)])


async def close_positions(context: ToolContext, args: dict[str, Any]) -> dict[str, Any]:
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


def tools() -> list[Tool]:
    return [
        Tool(
            "trade_execute",
            "Propose a broker operation for the Approve and Reject buttons on the card inside the call. "
            "Wait for that button; a spoken or typed yes is not approval. The same worker then executes "
            "the immutable approved request and returns the actual broker result. When an immutable "
            "trading market is bound, omit account_id and symbol or pass that bound pair; never ask "
            "which pair or ask the owner to retype the symbol. Read broker positions/orders first, "
            "including manually opened tickets. Saved goals use goal_step_execute instead.",
            TradeRequest,
            execute,
        ),
        Tool(
            "trade_close_positions",
            "Propose closing all currently open broker positions, or only an exact symbol. Approval freezes the ticket set; each ticket has an independent durable receipt. Never include later positions without new approval.",
            ClosePositions,
            close_positions,
        ),
    ]
