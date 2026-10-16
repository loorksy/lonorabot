"""Virtual positions on real broker evidence; no live mutation method is reachable."""

from collections.abc import Awaitable, Callable
from decimal import Decimal
from typing import Any

from lonora_adapters.brokers.base import BrokerManager
from lonora_contracts.account import Order, Position
from lonora_contracts.domain import utcnow
from lonora_contracts.runs import Lease
from lonora_contracts.trading import TradeRequest, TradeResult
from lonora_contracts.trading_goal import GoalExecution
from lonora_core.user_error import LonoraError
from lonora_db.agent_binding import agent_binding, assert_market_binding
from lonora_db.client import Database
from lonora_db.events import emit
from lonora_db.runs import require_lease
from lonora_db.schema import ShadowTradeRow, TradingJournalRow, TradingOpportunityRow
from lonora_db.shadow_positions import shadow_order, shadow_position, shadow_rows
from lonora_db.trade_approvals import require_approved_target_current
from lonora_db.trading_decisions import decision_history, read_decision
from lonora_db.trading_journal import persist_result, reserve_operation
from lonora_db.transactions import resource_data
from lonora_market.health import assess_quote, require_healthy
from lonora_market.relationships import relationship_usable
from lonora_session.idempotency import request_hash, stable_id
from sqlalchemy import select, text

from .idempotency import trade_fingerprint
from .journal import execution_evidence
from .manual_activity import material_state
from .preflight import preflight

ENTRY = {"buy", "sell", "buy_limit", "sell_limit", "buy_stop", "sell_stop"}


class ShadowReadView:
    """Read-only broker projection for the shared preflight and goal calculations."""

    def __init__(
        self, db: Database, brokers: BrokerManager, owner_id: str, agent_id: str, account_id: str
    ):
        self.db, self.brokers, self.owner_id, self.agent_id, self.account_id = (
            db,
            brokers,
            owner_id,
            agent_id,
            account_id,
        )

    async def account(self):
        return await (await self.brokers.get(self.owner_id, self.account_id)).account()

    async def quote(self, symbol: str):
        return await (await self.brokers.get(self.owner_id, self.account_id)).quote(symbol)

    async def candles(self, symbol: str, timeframe: str, limit: int):
        return await (await self.brokers.get(self.owner_id, self.account_id)).candles(
            symbol, timeframe, limit
        )

    async def instrument(self, symbol: str):
        return await (await self.brokers.get(self.owner_id, self.account_id)).instrument(symbol)

    async def positions(self) -> list[Position]:
        return [
            shadow_position(row)
            for row in await shadow_rows(
                self.db, self.owner_id, self.agent_id, self.account_id, statuses=("open",)
            )
            if row.status == "open"
        ]

    async def orders(self) -> list[Order]:
        return [
            shadow_order(row)
            for row in await shadow_rows(
                self.db, self.owner_id, self.agent_id, self.account_id, statuses=("pending",)
            )
            if row.status == "pending"
        ]

    async def execute(self, *args: Any, **kwargs: Any):
        raise LonoraError("shadow_broker_mutation_forbidden", 403)


def shadow_data(row: ShadowTradeRow) -> dict[str, Any]:
    return {
        **resource_data(row),
        "mode": "shadow",
        "account_id": row.account_id,
        "symbol": row.symbol,
        "status": row.status,
        "decision_id": row.decision_id,
        "thesis_id": row.thesis_id,
        "monetary_pnl": None,
        "monetary_pnl_code": "contract_currency_valuation_unavailable",
    }


async def execute_shadow(
    db: Database,
    brokers: BrokerManager,
    owner_id: str,
    agent_id: str,
    thread_id: str,
    lease: Lease,
    request: TradeRequest,
    decision_id: str | None = None,
    *,
    goal: GoalExecution | None = None,
    authorization: Callable[[], Awaitable[None]] | None = None,
) -> TradeResult:
    from .execution import require_goal_lineage
    from .goals import guard_goal_execution

    async with db.sessions() as session:
        run = await require_lease(session, lease)
        await require_goal_lineage(session, lease, goal, owner_id, request, execution_mode="shadow")
        if run.agent_id != agent_id or run.thread_id != thread_id:
            raise LonoraError("agent_run_mismatch", 409)
        agent = await agent_binding(session, owner_id, agent_id)
        if agent.execution_mode != "shadow":
            raise LonoraError("shadow_mode_required", 409)
        assert_market_binding(agent, request.account_id, request.symbol)
        prior = await session.get(TradingJournalRow, request.operation_id)
        if prior:
            if (
                prior.owner_id != owner_id
                or prior.execution_mode != "shadow"
                or prior.request_hash != trade_fingerprint(request)
            ):
                raise LonoraError("operation_id_conflict", 409)
            return TradeResult.model_validate(prior.result)
    if authorization:
        await authorization()
    view = ShadowReadView(db, brokers, owner_id, agent_id, request.account_id)
    # Cancelling a virtual pending order only changes our own durable state.
    # It must remain possible while the broker is unavailable.
    cancel = request.action == "cancel_order"
    quote = None
    snapshot = None
    if not cancel:
        snapshot = await preflight(view, request, financial_authority=False)
        quote = await view.quote(request.symbol)
        require_healthy(
            assess_quote(
                quote,
                account_id=request.account_id,
                symbol=request.symbol,
                now=utcnow(),
                maximum_age_seconds=30,
            )
        )
    evidence = None
    if request.action in ENTRY:
        async with db.sessions() as session:
            records = await decision_history(
                session,
                owner_id,
                agent_id=agent_id,
                account_id=request.account_id,
                symbol=request.symbol,
                limit=1,
            )
            evidence = (
                await read_decision(session, owner_id, decision_id)
                if decision_id
                else records[0]
                if records
                else None
            )
        if (
            evidence is None
            or evidence.action != ("BUY" if request.action.startswith("buy") else "SELL")
            or evidence.gate_codes
        ):
            raise LonoraError("shadow_decision_required", 409)
        if (evidence.account_id, evidence.symbol) != (request.account_id, request.symbol):
            raise LonoraError("shadow_evidence_scope_mismatch", 409)
        if any(
            not relationship_usable(value, utcnow()) for value in evidence.evidence.relationships
        ):
            raise LonoraError("relationship_evidence_unreliable", 409)
        require_healthy(
            assess_quote(
                evidence.evidence.quote,
                account_id=request.account_id,
                symbol=request.symbol,
                now=utcnow(),
                maximum_age_seconds=30,
            )
        )
    if authorization:
        await authorization()
    goal_evidence = None
    if goal:
        from .goals_market import fresh_goal_evidence

        goal_evidence = await fresh_goal_evidence(
            db, brokers, owner_id, goal.goal_id, goal.step_id, lease.run_id
        )
    async with db.sessions() as session, session.begin():
        await session.execute(
            text("SELECT pg_advisory_xact_lock(hashtextextended(:key,0))"),
            {"key": "shadow:" + owner_id + ":" + agent_id + ":" + request.account_id},
        )
        if quote is not None:
            require_healthy(
                assess_quote(
                    quote,
                    account_id=request.account_id,
                    symbol=request.symbol,
                    now=utcnow(),
                    maximum_age_seconds=30,
                )
            )
        if evidence is not None:
            require_healthy(
                assess_quote(
                    evidence.evidence.quote,
                    account_id=request.account_id,
                    symbol=request.symbol,
                    now=utcnow(),
                    maximum_age_seconds=30,
                )
            )
            if any(
                not relationship_usable(value, utcnow())
                for value in evidence.evidence.relationships
            ):
                raise LonoraError("relationship_evidence_unreliable", 409)
        run = await require_lease(session, lease, lock=True)
        await require_goal_lineage(session, lease, goal, owner_id, request, execution_mode="shadow")
        if goal:
            await guard_goal_execution(session, owner_id, goal, request, lease, goal_evidence)
        run.model_metadata = {**run.model_metadata, "execution_mode": "shadow"}
        agent = await agent_binding(session, owner_id, agent_id)
        if agent.execution_mode != "shadow":
            raise LonoraError("shadow_mode_changed", 409)
        thesis = None
        if request.thesis_id:
            thesis = await session.get(TradingOpportunityRow, request.thesis_id)
            if thesis is None or (
                thesis.owner_id,
                thesis.agent_id,
                thesis.account_id,
                thesis.symbol,
            ) != (owner_id, agent_id, request.account_id, request.symbol):
                raise LonoraError("shadow_thesis_scope_mismatch", 409)
            if request.action in ENTRY and (
                thesis.status != "confirmed" or thesis.expires_at <= utcnow()
            ):
                raise LonoraError("shadow_thesis_not_confirmed", 409)
        journal, created = await reserve_operation(
            session,
            owner_id,
            request.operation_id,
            request.account_id,
            trade_fingerprint(request),
            request.model_dump(mode="json"),
            execution_mode="shadow",
        )
        if not created:
            return TradeResult.model_validate(journal.result)
        captured = (
            execution_evidence(
                snapshot, request, mode="shadow", phase="virtual_preflight", goal=goal
            )
            if snapshot
            else {
                "schema_version": 1,
                "logic_version": "execution-boundary-v1",
                "phase": "local_virtual_cancel",
                "execution_mode": "shadow",
                "snapshot": None,
                "missing_code": "broker_read_not_required_for_virtual_cancel",
                "goal": goal.model_dump(mode="json") if goal else None,
            }
        )
        journal.result = {
            "details": {
                "execution_evidence": {"before_send": captured},
                "execution": {"run_id": run.id, "agent_id": agent_id, "execution_mode": "shadow"},
            }
        }
        row: ShadowTradeRow | None = None
        if request.action in ENTRY:
            assert request.volume is not None and evidence is not None and quote is not None
            market = request.action in {"buy", "sell"}
            price = quote.ask if request.action.startswith("buy") else quote.bid
            row = ShadowTradeRow(
                id=stable_id(request.operation_id, "virtual-position"),
                owner_id=owner_id,
                agent_id=agent_id,
                thread_id=thread_id,
                account_id=request.account_id,
                symbol=request.symbol,
                status="open" if market else "pending",
                decision_id=evidence.id,
                thesis_id=request.thesis_id,
                payload={
                    **request.model_dump(mode="json"),
                    "side": "buy" if request.action.startswith("buy") else "sell",
                    "mode": "shadow",
                    "goal": goal.model_dump(mode="json") if goal else None,
                    "source_observed_at": quote.observed_at.isoformat(),
                    "entry_quote": quote.model_dump(mode="json"),
                    "evidence_schema_version": evidence.schema_version,
                    "logic_version": evidence.logic_version,
                    "timeframe": evidence.timeframe,
                    "strategy_version": thesis.payload["definition"]["strategy_version"]
                    if thesis
                    else None,
                    "setup_key": thesis.setup_key if thesis else None,
                    "thesis_version": thesis.version if thesis else None,
                    "thesis_snapshot": {"definition": thesis.payload, "state": thesis.state}
                    if thesis
                    else None,
                    "fill_model": "sampled_top_of_book_no_depth",
                },
                state={
                    "entry_quote": quote.model_dump(mode="json") if market else None,
                    "remaining_volume": str(request.volume),
                    "entry_price": str(price) if market else None,
                    "stop_loss": str(request.stop_loss) if request.stop_loss else None,
                    "take_profit": str(request.take_profit) if request.take_profit else None,
                    "entry_at": quote.observed_at.isoformat() if market else None,
                    "monetary_pnl": None,
                    "quality": {
                        "analysis": {
                            "state": "source_evidence_available",
                            "decision_id": evidence.id,
                        },
                        "entry": {
                            "state": "sampled_quote_assumption",
                            "source_age_seconds": (utcnow() - quote.observed_at).total_seconds(),
                        },
                        "management": {"state": "not_observed"},
                        "execution": {"state": "virtual_fill", "live_slippage": None},
                    },
                },
            )
            session.add(row)
        else:
            identifier = request.position_id or request.order_id
            row = await session.get(ShadowTradeRow, identifier or "", with_for_update=True)
            if (
                row is None
                or row.owner_id != owner_id
                or row.agent_id != agent_id
                or row.account_id != request.account_id
                or row.symbol != request.symbol
            ):
                raise LonoraError("shadow_position_not_found", 404)
            if row.status not in {"open", "pending"}:
                raise LonoraError("shadow_trade_terminal", 409)
            if request.action in {"cancel_order", "modify_order"} and row.status != "pending":
                raise LonoraError("shadow_order_not_pending", 409)
            if request.action in {"close_position", "modify_position"} and row.status != "open":
                raise LonoraError("shadow_position_not_open", 409)
            target = shadow_position(row) if row.status == "open" else shadow_order(row)
            if cancel:
                journal.result = {
                    "details": {
                        **journal.result["details"],
                        "execution_evidence": {
                            "before_send": {
                                **captured,
                                "observed_at": utcnow().isoformat(),
                                "target": target.model_dump(mode="json"),
                            }
                        },
                    }
                }
            await require_approved_target_current(
                session, owner_id, lease.run_id, request, material_state(target)
            )
            state = dict(row.state)
            if request.action == "cancel_order":
                if row.status != "pending":
                    raise LonoraError("shadow_order_not_pending", 409)
                row.status = "cancelled"
            elif request.action == "close_position":
                assert quote is not None
                volume = Decimal(state["remaining_volume"])
                closed = request.volume or volume
                if closed > volume:
                    raise LonoraError("position_volume_exceeded", 409)
                exit_price = quote.bid if row.payload["side"] == "buy" else quote.ask
                signed = (exit_price - Decimal(state["entry_price"])) * (
                    1 if row.payload["side"] == "buy" else -1
                )
                price_return = signed / Decimal(state["entry_price"])
                cumulative = Decimal(state.get("realized_price_return_fraction", "0")) + (
                    price_return * closed / Decimal(row.payload["volume"])
                )
                state.update(
                    remaining_volume=str(volume - closed),
                    exit_price=str(exit_price),
                    exit_at=quote.observed_at.isoformat(),
                    last_exit_return_fraction=str(price_return),
                    realized_price_return_fraction=str(cumulative),
                    price_return_fraction=str(cumulative),
                    closed_volume=str(Decimal(row.payload["volume"]) - volume + closed),
                )
                row.status = "closed" if closed == volume else "open"
                state["quality"] = {
                    **state.get("quality", {}),
                    "management": {
                        "state": "explicit_virtual_close",
                        "operation_id": request.operation_id,
                    },
                }
            else:
                if request.action == "modify_order" and request.price is not None:
                    row.payload = {**row.payload, "price": str(request.price)}
                for name in ("stop_loss", "take_profit"):
                    if getattr(request, "clear_" + name):
                        state[name] = None
                    elif getattr(request, name) is not None:
                        state[name] = str(getattr(request, name))
                state["quality"] = {
                    **state.get("quality", {}),
                    "management": {
                        "state": "protection_revised",
                        "operation_id": request.operation_id,
                    },
                }
            row.state, row.version, row.updated_at = state, row.version + 1, utcnow()
        assert row is not None
        await session.flush()
        result = TradeResult(
            operation_id=request.operation_id,
            status="confirmed",
            broker_id=row.id,
            code="shadow_virtual_result",
            details={
                "mode": "shadow",
                "goal_id": goal.goal_id if goal else None,
                "step_id": goal.step_id if goal else None,
                "virtual_id": row.id,
                "price": row.state.get("exit_price") or row.state.get("entry_price"),
                "symbol": row.symbol,
                "virtual_status": row.status,
                "monetary_pnl": None,
                "fill_model": "sampled_top_of_book_no_depth",
            },
        )
        await persist_result(
            session, request.operation_id, "confirmed", result.model_dump(mode="json")
        )
        # The first caller and an idempotent replay must receive the same durable
        # server-owned attribution/evidence, not the pre-persistence adapter view.
        result = TradeResult.model_validate(journal.result)
        emit(
            session,
            owner_id,
            "shadow.trade_updated",
            agent_id=agent_id,
            thread_id=thread_id,
            run_id=lease.run_id,
            payload={"id": row.id, "version": row.version, "status": row.status, "mode": "shadow"},
        )
        return result


async def advance_shadow(db: Database, brokers: BrokerManager, owner_id: str) -> int:
    """Deterministic virtual fills/protection on sampled real quotes, no model per tick."""
    async with db.sessions() as session:
        rows = list(
            await session.scalars(
                select(ShadowTradeRow)
                .where(
                    ShadowTradeRow.owner_id == owner_id,
                    ShadowTradeRow.status.in_(["pending", "open"]),
                )
                .order_by(ShadowTradeRow.updated_at)
                .limit(100)
            )
        )
    changed = 0
    for original in rows:
        try:
            broker = await brokers.get(owner_id, original.account_id)
            quote = await broker.quote(original.symbol)
            require_healthy(
                assess_quote(
                    quote,
                    account_id=original.account_id,
                    symbol=original.symbol,
                    now=utcnow(),
                    maximum_age_seconds=30,
                )
            )
        except LonoraError:
            continue
        async with db.sessions() as session, session.begin():
            row = await session.get(ShadowTradeRow, original.id, with_for_update=True)
            if row is None or row.status not in {"pending", "open"}:
                continue
            from datetime import datetime

            from lonora_db.schema import TradingOpportunityRow

            last = row.state.get("last_quote_at")
            if last and datetime.fromisoformat(last) >= quote.observed_at:
                continue
            state: dict[str, Any] = {**row.state, "last_quote_at": quote.observed_at.isoformat()}
            side = row.payload["side"]
            buy = side == "buy"
            market = quote.ask if buy else quote.bid
            reason: str | None = None
            thesis = (
                await session.get(TradingOpportunityRow, row.thesis_id) if row.thesis_id else None
            )
            invalid = thesis is not None and (
                thesis.status in {"invalidated", "expired"} or thesis.expires_at <= utcnow()
            )
            if row.status == "pending":
                price = Decimal(row.payload["price"])
                kind = row.payload["action"]
                met = market <= price if kind in {"buy_limit", "sell_stop"} else market >= price
                if invalid:
                    row.status, reason = "expired", "thesis_expired_or_invalidated"
                elif met:
                    row.status, reason = "open", "virtual_pending_entry"
                    state.update(
                        entry_price=str(market),
                        entry_at=quote.observed_at.isoformat(),
                        entry_quote=quote.model_dump(mode="json"),
                    )
                    state["quality"] = {
                        **state.get("quality", {}),
                        "entry": {
                            "state": "sampled_quote_assumption",
                            "planned_price": str(price),
                            "observed_price": str(market),
                            "price_difference": str(market - price),
                        },
                    }
            else:
                entry = Decimal(state["entry_price"])
                exit_price = quote.bid if buy else quote.ask
                price_return = (exit_price - entry) * (1 if buy else -1) / entry
                state.update(
                    peak_return_fraction=str(
                        max(Decimal(state.get("peak_return_fraction", "0")), price_return)
                    ),
                    worst_return_fraction=str(
                        min(Decimal(state.get("worst_return_fraction", "0")), price_return)
                    ),
                )
                stop = Decimal(state["stop_loss"]) if state.get("stop_loss") else None
                target = Decimal(state["take_profit"]) if state.get("take_profit") else None
                stopped = stop is not None and (exit_price <= stop if buy else exit_price >= stop)
                reached = target is not None and (
                    exit_price >= target if buy else exit_price <= target
                )
                if stopped or reached or invalid:
                    row.status = "closed"
                    reason = (
                        "virtual_stop"
                        if stopped
                        else "virtual_target"
                        if reached
                        else "thesis_expired_or_invalidated"
                    )
                    state.update(
                        exit_price=str(exit_price),
                        exit_at=quote.observed_at.isoformat(),
                        exit_reason=reason,
                        last_exit_return_fraction=str(price_return),
                        price_return_fraction=str(
                            Decimal(state.get("realized_price_return_fraction", "0"))
                            + price_return
                            * Decimal(state["remaining_volume"])
                            / Decimal(row.payload["volume"])
                        ),
                        closed_volume=row.payload["volume"],
                        remaining_volume="0",
                    )
                    state["realized_price_return_fraction"] = state["price_return_fraction"]
                    state["quality"] = {
                        **state.get("quality", {}),
                        "management": {"state": reason, "source_at": quote.observed_at.isoformat()},
                    }
            row.state, row.updated_at = state, utcnow()
            if reason is None:
                continue
            row.version += 1
            operation_id = stable_id(row.id, "shadow-transition:" + str(row.version) + ":" + reason)
            request = {
                "mode": "shadow",
                "virtual_id": row.id,
                "reason_code": reason,
                "quote": quote.model_dump(mode="json"),
                "decision_id": row.decision_id,
            }
            _, new = await reserve_operation(
                session,
                owner_id,
                operation_id,
                row.account_id,
                request_hash(request),
                request,
                execution_mode="shadow",
            )
            if new:
                result = TradeResult(
                    operation_id=operation_id,
                    status="confirmed",
                    broker_id=row.id,
                    code=reason,
                    details={
                        "mode": "shadow",
                        "virtual_status": row.status,
                        "exit_price": row.state.get("exit_price"),
                        "price_return_fraction": row.state.get("price_return_fraction"),
                        "monetary_pnl": None,
                        "fill_model": "sampled_top_of_book_no_depth",
                    },
                )
                await persist_result(
                    session, operation_id, "confirmed", result.model_dump(mode="json")
                )
            emit(
                session,
                owner_id,
                "shadow.trade_updated",
                agent_id=row.agent_id,
                thread_id=row.thread_id,
                payload={
                    "id": row.id,
                    "version": row.version,
                    "status": row.status,
                    "mode": "shadow",
                    "reason_code": reason,
                },
            )
            changed += 1
    return changed
