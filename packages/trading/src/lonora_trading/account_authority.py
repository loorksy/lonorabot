"""Validate signed account authority at the existing financial mutation boundary."""

from decimal import Decimal
from typing import Any

from lonora_contracts.account import Order, Position
from lonora_contracts.domain import utcnow
from lonora_contracts.execution_quality import ExecutionSnapshot
from lonora_contracts.trading import TradeRequest
from lonora_core.user_error import LonoraError
from lonora_db.account_authority import require_authority
from lonora_db.schema import AccountAuthorityRow, RunRow, TradingJournalRow
from lonora_session.idempotency import broker_operation_tag
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from .exposure import ENTRY_ACTIONS
from .manual_activity import material_state


async def provisional_voice(session: AsyncSession, run: RunRow) -> bool:
    """A provisional handoff and its descendants cannot spend standing authority."""
    seen: set[str] = set()
    for _ in range(16):
        if run.id in seen:
            raise LonoraError("goal_run_ancestry_invalid", 409)
        seen.add(run.id)
        if run.model_metadata.get("voice_handoff", {}).get("finalized") is False:
            return True
        if not run.parent_run_id:
            return False
        parent = await session.get(RunRow, run.parent_run_id)
        if parent is None:
            raise LonoraError("goal_run_ancestry_invalid", 409)
        run = parent
    raise LonoraError("goal_run_ancestry_invalid", 409)


async def available_authority(
    session: AsyncSession, owner_id: str, run: RunRow, request: TradeRequest
) -> str | None:
    if run.model_metadata.get("goal_id") or await provisional_voice(session, run):
        return None  # Existing Goal-bound permissions and explicit approvals remain separate.
    rows = await session.scalars(
        select(AccountAuthorityRow)
        .where(
            AccountAuthorityRow.owner_id == owner_id,
            AccountAuthorityRow.agent_id == run.agent_id,
            AccountAuthorityRow.account_id == request.account_id,
            AccountAuthorityRow.status == "active",
            AccountAuthorityRow.valid_until > utcnow(),
        )
        .limit(2)
    )
    for row in rows:
        try:
            _, envelope = await require_authority(session, owner_id, run.agent_id, row.id)
        except LonoraError:
            continue
        if request.symbol in envelope.symbols and request.action in envelope.actions:
            return row.id
    return None


def management_target(
    snapshot: ExecutionSnapshot, request: TradeRequest
) -> Position | Order | None:
    if request.position_id:
        return next((p for p in snapshot.positions if p.id == request.position_id), None)
    if request.order_id:
        return next((o for o in snapshot.orders if o.id == request.order_id), None)
    return None


async def require_account_execution(
    session: AsyncSession,
    owner_id: str,
    run: RunRow,
    request: TradeRequest,
    identifier: str,
    snapshot: ExecutionSnapshot,
    expected_target: dict[str, Any] | None,
) -> None:
    if run.model_metadata.get("goal_id") or await provisional_voice(session, run):
        raise LonoraError("trade_approval_required", 409)
    _, envelope = await require_authority(session, owner_id, run.agent_id, identifier)
    if request.account_id != envelope.account_id or request.symbol not in envelope.symbols:
        raise LonoraError("account_authority_scope_mismatch", 403)
    if request.action not in envelope.actions:
        raise LonoraError("account_authority_action_forbidden", 403)
    if snapshot.account.id != request.account_id:
        raise LonoraError("account_authority_scope_mismatch", 403)
    count = await session.scalar(
        select(func.count())
        .select_from(TradingJournalRow)
        .where(
            TradingJournalRow.owner_id == owner_id,
            TradingJournalRow.operation_id != request.operation_id,
            TradingJournalRow.result["details"]["execution"]["account_authority_id"].as_string()
            == identifier,
            or_(
                TradingJournalRow.status.in_(["submitted", "ambiguous", "confirmed"]),
                TradingJournalRow.result["details"]["execution"]["send_authorized"]
                .as_boolean()
                .is_(True),
            ),
        )
    )
    if (count or 0) >= envelope.maximum_actions:
        raise LonoraError("account_authority_action_limit", 409)
    unresolved = await session.scalar(
        select(TradingJournalRow.operation_id)
        .where(
            TradingJournalRow.owner_id == owner_id,
            TradingJournalRow.account_id == request.account_id,
            TradingJournalRow.execution_mode == "live",
            TradingJournalRow.operation_id != request.operation_id,
            TradingJournalRow.status.in_(["submitted", "ambiguous"]),
        )
        .limit(1)
    )
    if unresolved:
        raise LonoraError("broker_reconciliation_required", 409)
    if request.volume is not None and request.volume > envelope.maximum_order_volume:
        raise LonoraError("account_authority_volume_limit", 409)
    if request.action in ENTRY_ACTIONS:
        if request.stop_loss is None:
            raise LonoraError("account_authority_stop_loss_required", 409)
        if snapshot.account.equity <= envelope.minimum_equity:
            raise LonoraError("account_authority_equity_floor", 409)
        # Orders can all fill. Reserve a future position slot for each pending entry.
        if len(snapshot.positions) + len(snapshot.orders) >= envelope.maximum_positions:
            raise LonoraError("account_authority_position_limit", 409)
        if (
            request.action not in {"buy", "sell"}
            and len(snapshot.orders) >= envelope.maximum_pending_orders
        ):
            raise LonoraError("account_authority_pending_limit", 409)
        volume = sum(
            (
                p.volume
                for p in [*snapshot.positions, *snapshot.orders]
                if p.symbol == request.symbol
            ),
            Decimal(0),
        )
        if volume + (request.volume or 0) > envelope.maximum_symbol_volume:
            raise LonoraError("account_authority_symbol_volume_limit", 409)
    target = management_target(snapshot, request)
    if request.position_id or request.order_id:
        if target is None or expected_target is None or material_state(target) != expected_target:
            raise LonoraError("account_authority_broker_state_changed", 409)
        # Attribute by the existing journal and broker identity, never ticket format.
        # Bounded history is not proof of external ownership; default to requiring
        # explicit manual permission whenever a matching origin is unavailable.
        entries = await session.scalars(
            select(TradingJournalRow)
            .where(
                TradingJournalRow.owner_id == owner_id,
                TradingJournalRow.account_id == request.account_id,
                TradingJournalRow.execution_mode == "live",
                TradingJournalRow.status == "confirmed",
                TradingJournalRow.request["symbol"].as_string() == request.symbol,
                TradingJournalRow.request["action"].as_string().in_(sorted(ENTRY_ACTIONS)),
            )
            .order_by(TradingJournalRow.updated_at.desc())
            .limit(1000)
        )
        owned = False
        for entry in entries:
            details = entry.result.get("details", {})
            kind = "position_id" if request.position_id else "order_id"
            safe_id = entry.result.get("broker_id") if details.get("simulation") else None
            if target.operation_id in {
                entry.operation_id,
                broker_operation_tag(entry.operation_id),
            } or target.id in {details.get(kind), safe_id}:
                owned = True
                break
        if not owned and not envelope.allow_manual_positions:
            raise LonoraError("account_authority_manual_permission_required", 403)
        if request.clear_stop_loss:
            raise LonoraError("account_authority_protection_removal_forbidden", 403)
        if request.stop_loss is not None and target.stop_loss is not None:
            buy = target.side.removeprefix("ORDER_TYPE_").casefold().startswith("buy")
            if (
                request.stop_loss < target.stop_loss
                if buy
                else request.stop_loss > target.stop_loss
            ):
                raise LonoraError("account_authority_protection_expansion_forbidden", 403)
