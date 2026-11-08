"""The owner's own financial settings and attestations, shared by the owner routes.

Each function is the single implementation behind one owner-session action, whether the
owner reaches it from a settings page, the API or a card in the conversation. None of
them is reachable from an agent tool.
"""

from typing import Any

from lonora_adapters.brokers.base import BrokerManager
from lonora_contracts.domain import utcnow
from lonora_contracts.execution_quality import ExecutionPolicy
from lonora_contracts.trading import OperationResolution
from lonora_core.user_error import LonoraError
from lonora_db.broker_sessions import BrokerSessionRepository
from lonora_db.events import emit
from lonora_db.schema import TradingJournalRow
from lonora_db.trading_journal import resolve_operation
from lonora_db.transactions import SettingsRepository
from sqlalchemy.ext.asyncio import AsyncSession

from .execution_quality import policy_key
from .operation_events import resolution_event


async def require_account_currency(
    brokers: BrokerManager, owner_id: str, account_id: str, currency: str | None
) -> None:
    """Amounts are never converted: refuse a currency the account does not report.

    An unreachable broker does not block saving; enforcement checks it again.
    """
    if currency is None:
        return
    try:
        broker = await brokers.get(owner_id, account_id)
        reported = (await broker.account()).currency
    except Exception:
        reported = None
    if reported is not None and reported != currency:
        raise LonoraError("risk_limit_currency_mismatch", 409)


async def store_execution_policy(
    session: AsyncSession, owner_id: str, account_id: str, policy: ExecutionPolicy
) -> ExecutionPolicy:
    await BrokerSessionRepository().get(session, owner_id, account_id, lock=True)
    key = policy_key(owner_id, account_id)
    previous = ExecutionPolicy.model_validate(await SettingsRepository().get(session, key))
    await SettingsRepository().put(session, key, policy.model_dump(mode="json"))
    if previous != policy:
        # Durable owner configuration fact for later "what changed" summaries.
        emit(
            session,
            owner_id,
            "trading.execution_policy_updated",
            payload={
                "account_id": account_id,
                "risk": policy.risk.model_dump(mode="json"),
                "risk_limits_configured": policy.risk.configured,
                "transition_id": utcnow().isoformat(),
            },
        )
    return policy


async def attest_operation(
    session: AsyncSession,
    owner_id: str,
    operation_id: str,
    resolution: OperationResolution,
    actor: dict[str, Any],
) -> TradingJournalRow:
    """Owner attestation for an uncertain operation; it clears the block, never resends.

    The original receipt and evidence stay on the row and the attestation is a durable
    event (``trading.operation_resolved``).
    """
    from .opportunities import sync_opportunity_execution

    row = await resolve_operation(session, owner_id, operation_id, resolution, actor)
    await resolution_event(session, row)
    if row.request.get("thesis_id"):
        # Release or settle the thesis link now, not on the next maintenance pass.
        try:
            await sync_opportunity_execution(session, row)
        except LonoraError as error:
            if error.code != "opportunity_not_found":
                raise
    return row
