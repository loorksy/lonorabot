"""Validate signed account authority at the existing financial mutation boundary."""

from decimal import Decimal
from typing import Any

from lonora_contracts.domain import utcnow
from lonora_contracts.execution_quality import ExecutionSnapshot
from lonora_contracts.trading import TradeRequest
from lonora_core.user_error import LonoraError
from lonora_db.account_authority import require_authority
from lonora_db.schema import AccountAuthorityRow, RunRow, TradingJournalRow
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from .exposure import ENTRY_ACTIONS
from .manual_activity import material_state
from .ownership import lonora_opened, management_target

# The executor's refusals for a request outside a signed grant's own terms. Each one means
# the grant does not cover the request, so under "On its own" it asks the owner with an
# approval card instead (the ladder is monotonic; correction 6).
GRANT_TERM_REFUSALS = frozenset(
    {
        "account_authority_scope_mismatch",
        "account_authority_action_forbidden",
        "account_authority_action_limit",
        "account_authority_volume_limit",
        "account_authority_stop_loss_required",
        "account_authority_equity_floor",
        "account_authority_position_limit",
        "account_authority_pending_limit",
        "account_authority_symbol_volume_limit",
        "account_authority_manual_permission_required",
        "account_authority_protection_removal_forbidden",
        "account_authority_protection_expansion_forbidden",
    }
)


async def available_authority(
    session: AsyncSession, owner_id: str, run: RunRow, request: TradeRequest
) -> str | None:
    """The active grant whose account, market and action cover this request, or None.

    None never refuses the trade: the caller asks the owner for exact approval instead
    (the ladder is monotonic). A grant's management Run is held to its own grant.
    """
    management_id = run.model_metadata.get("account_management_id")
    # The mode task's Runs carry the agent's own id: they are ordinary Runs of the agent.
    if management_id and management_id != run.agent_id:
        _, envelope = await require_authority(session, owner_id, run.agent_id, management_id)
        if (
            request.account_id != envelope.account_id
            or not envelope.permits_symbol(request.symbol)
            or request.action not in envelope.actions
        ):
            return None
        return management_id
    rows = await session.scalars(
        select(AccountAuthorityRow)
        .where(
            AccountAuthorityRow.owner_id == owner_id,
            AccountAuthorityRow.agent_id == run.agent_id,
            AccountAuthorityRow.account_id == request.account_id,
            AccountAuthorityRow.status == "active",
            or_(
                AccountAuthorityRow.valid_until.is_(None),
                AccountAuthorityRow.valid_until > utcnow(),
            ),
        )
        .limit(2)
    )
    for row in rows:
        try:
            _, envelope = await require_authority(session, owner_id, run.agent_id, row.id)
        except LonoraError:
            continue
        if envelope.permits_symbol(request.symbol) and request.action in envelope.actions:
            return row.id
    return None


async def grant_covers(
    session: AsyncSession,
    owner_id: str,
    run: RunRow,
    request: TradeRequest,
    identifier: str,
    snapshot: ExecutionSnapshot,
) -> bool:
    """Whether every term of this signed grant admits the request on these broker facts.

    The executor's own check (``require_account_execution``) runs here read-only, before
    anything is asked or sent: volume, position, pending and symbol caps, the equity
    floor, the bounded stop-loss and protection rules, the action budget and the owner's
    own positions. A request a term refuses is not covered, so the caller asks the owner
    for exact approval instead of sending it under the grant to be refused. The executor
    repeats the same check at send.
    """
    target = management_target(snapshot, request)
    if (request.position_id or request.order_id) and target is None:
        # A ticket the broker no longer shows: the executor refuses it with its own code.
        return True
    try:
        await require_account_execution(
            session,
            owner_id,
            run,
            request,
            identifier,
            snapshot,
            material_state(target) if target is not None else None,
        )
    except LonoraError as error:
        if error.code in GRANT_TERM_REFUSALS:
            return False
        raise
    return True


async def require_account_execution(
    session: AsyncSession,
    owner_id: str,
    run: RunRow,
    request: TradeRequest,
    identifier: str,
    snapshot: ExecutionSnapshot,
    expected_target: dict[str, Any] | None,
) -> None:
    # The central permission gate additionally requires exact-operation owner
    # approval for provisional speech; a signed grant alone cannot spend it.
    if run.model_metadata.get("account_management_id") not in (None, identifier, run.agent_id):
        raise LonoraError("account_authority_scope_mismatch", 403)
    _, envelope = await require_authority(session, owner_id, run.agent_id, identifier)
    if request.account_id != envelope.account_id or not envelope.permits_symbol(request.symbol):
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
    if envelope.maximum_actions is not None and (count or 0) >= envelope.maximum_actions:
        raise LonoraError("account_authority_action_limit", 409)
    # Unresolved operations are scoped by the executor for every admission path
    # (lonora_trading.admission): they block new risk on the same market or ticket
    # and never trap an exit. A grant cannot widen that block's exceptions.
    if (
        request.volume is not None
        and envelope.maximum_order_volume is not None
        and request.volume > envelope.maximum_order_volume
    ):
        raise LonoraError("account_authority_volume_limit", 409)
    if request.action in ENTRY_ACTIONS:
        if envelope.management_mode == "bounded" and request.stop_loss is None:
            raise LonoraError("account_authority_stop_loss_required", 409)
        if (
            envelope.minimum_equity is not None
            and snapshot.account.equity <= envelope.minimum_equity
        ):
            raise LonoraError("account_authority_equity_floor", 409)
        # Orders can all fill. Reserve a future position slot for each pending entry.
        if (
            envelope.maximum_positions is not None
            and len(snapshot.positions) + len(snapshot.orders) >= envelope.maximum_positions
        ):
            raise LonoraError("account_authority_position_limit", 409)
        if (
            request.action not in {"buy", "sell"}
            and envelope.maximum_pending_orders is not None
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
        if (
            envelope.maximum_symbol_volume is not None
            and volume + (request.volume or 0) > envelope.maximum_symbol_volume
        ):
            raise LonoraError("account_authority_symbol_volume_limit", 409)
    target = management_target(snapshot, request)
    if request.position_id or request.order_id:
        if target is None or expected_target is None or material_state(target) != expected_target:
            # The door's own check says the same at send (6.6); one code for both.
            raise LonoraError("broker_state_changed", 409)
        if not envelope.allow_manual_positions and not await lonora_opened(
            session, owner_id, request, target
        ):
            raise LonoraError("account_authority_manual_permission_required", 403)
        if envelope.management_mode == "bounded" and request.clear_stop_loss:
            raise LonoraError("account_authority_protection_removal_forbidden", 403)
        if (
            envelope.management_mode == "bounded"
            and request.stop_loss is not None
            and target.stop_loss is not None
        ):
            buy = target.side.removeprefix("ORDER_TYPE_").casefold().startswith("buy")
            if (
                request.stop_loss < target.stop_loss
                if buy
                else request.stop_loss > target.stop_loss
            ):
                raise LonoraError("account_authority_protection_expansion_forbidden", 403)
