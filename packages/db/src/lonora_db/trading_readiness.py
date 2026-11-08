"""Presentation-only trading readiness: can this agent trade now, and what stops it.

One bounded projection for the owner's header safety pill, its sheet and the agent's
status line. It is built from the same records the financial boundary reads: the
agent's ladder level and signed grants, global trading, restrictions in force, each
account's money limits and unresolved operations with their scoped block.

It is never consulted for enforcement. The single executor re-reads every one of
these at the moment of sending (``lonora_trading.execution``), so a stale or wrong
projection can at most show the owner an outdated line; it can never admit a trade.
"""

from datetime import datetime
from typing import Any, cast

from lonora_contracts.domain import utcnow
from lonora_contracts.execution_quality import ExecutionPolicy
from lonora_contracts.trading import UNRESOLVED_STATUSES, TradingControl
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from .agent_binding import fixed_market
from .agent_permissions import permission_state
from .schema import AgentRow, BrokerSessionRow, SettingRow, TradingJournalRow
from .trading_restrictions import list_restrictions, relevant_to, restriction_state
from .transactions import SettingsRepository, execution_policy_key

RISK_LIMIT_NAMES = (
    "max_trade_risk",
    "max_trade_risk_equity_percent",
    "max_daily_loss",
    "max_open_risk",
    "max_open_risk_equity_percent",
    "min_free_margin",
)
ACCOUNT_LIMIT = 10
LIST_LIMIT = 5
# Most restrictive first: the headline names the strongest pause in force.
RESTRICTION_ORDER = ("all_mutations", "no_risk_increase", "no_new_entries")


def risk_limit_frame(account_id: str, policy: ExecutionPolicy) -> dict[str, Any]:
    """An account's owner money limits; a limit that is not configured is not enforced."""
    limits = policy.risk
    values = {name: getattr(limits, name) for name in RISK_LIMIT_NAMES}
    return {
        "account_id": account_id,
        "configured": limits.configured,
        "currency": limits.currency,
        "limits": {name: str(value) for name, value in values.items() if value is not None},
        "not_configured": [name for name, value in values.items() if value is None],
        **(
            {"trading_day_timezone": limits.trading_day_timezone}
            if limits.max_daily_loss is not None
            else {}
        ),
    }


async def account_money_limits(
    session: AsyncSession, owner_id: str, account_id: str
) -> dict[str, Any]:
    policy = ExecutionPolicy.model_validate(
        await SettingsRepository().get(session, execution_policy_key(owner_id, account_id))
    )
    return risk_limit_frame(account_id, policy)


async def global_trading(session: AsyncSession) -> dict[str, Any]:
    """Stop new trading / Resume. Trading starts stopped until the owner resumes it.

    Trading OFF and the legacy Emergency Stop flag are both "stopped": either blocks new
    risk for every agent and the owner's manual orders, and neither traps an exit. Only
    the owner's session can change it, so a stored change is always the owner's.
    """
    row = await session.get(SettingRow, "trading_control", populate_existing=True)
    control = TradingControl.model_validate(row.payload if row else {})
    return {
        "state": "stopped" if control.emergency_stop or not control.enabled else "running",
        "since": row.updated_at.isoformat() if row else None,
        "changed_by": "owner" if row else "default",
    }


def _iso(value: datetime | None) -> str | None:
    return value.isoformat() if value else None


def _producer(row: TradingJournalRow) -> str | None:
    """The agent the executor recorded for this operation; None for the owner's own."""
    details: Any = row.result.get("details")
    execution: Any = (
        cast(dict[str, Any], details).get("execution") if isinstance(details, dict) else None
    )
    agent_id: Any = (
        cast(dict[str, Any], execution).get("agent_id") if isinstance(execution, dict) else None
    )
    return agent_id if isinstance(agent_id, str) else None


async def trading_readiness(
    session: AsyncSession, owner_id: str, agent: AgentRow
) -> dict[str, Any]:
    now = utcnow()
    permission = await permission_state(session, owner_id, agent.id)
    level: str = permission["effective_level"]
    grants: list[dict[str, Any]] = []
    for row in permission["active_authorities"][:3]:
        envelope: dict[str, Any] = row["envelope"]
        grants.append(
            {
                "account_id": row["account_id"],
                "symbol_scope": envelope.get("symbol_scope", "selected"),
                "symbols": list(envelope.get("symbols", []))[:20],
                "actions": list(envelope.get("actions", []))[:10],
                "allow_manual_positions": bool(envelope.get("allow_manual_positions")),
                "valid_until": row["valid_until"],
            }
        )
    trading = await global_trading(session)
    accounts_query = (
        select(BrokerSessionRow.id)
        .where(BrokerSessionRow.owner_id == owner_id)
        .order_by(BrokerSessionRow.created_at, BrokerSessionRow.id)
    )
    if fixed_market(agent):
        accounts_query = accounts_query.where(BrokerSessionRow.id == agent.trading_account_id)
    accounts = list(await session.scalars(accounts_query.limit(ACCOUNT_LIMIT)))
    restrictions: list[dict[str, Any]] = []
    for row in await list_restrictions(session, owner_id, agent_id=agent.id, limit=20, now=now):
        if not relevant_to(row, agent):
            continue
        restrictions.append(
            {
                "id": row.id,
                "account_id": row.account_id,
                "symbol": row.symbol,
                "action_class": row.action_class,
                "state": restriction_state(row, now),
                "applies_to": "all_agents" if row.agent_id is None else "this_agent",
                "includes_owner_manual": row.applies_to_owner_manual,
                "valid_from": _iso(row.valid_from),
                "valid_until": _iso(row.valid_until),
                # owner_ui: the owner set it; owner_message: an agent recorded the owner's
                # words; agent: an agent narrowed on its own. Only the owner lifts any.
                "source": row.source,
                "created_by_agent_id": row.created_by_agent_id,
            }
        )
    restrictions.sort(
        key=lambda item: (item["state"] != "active", RESTRICTION_ORDER.index(item["action_class"]))
    )
    money_limits = [
        await account_money_limits(session, owner_id, account_id) for account_id in accounts
    ]
    operations: list[dict[str, Any]] = []
    unresolved_count = 0
    if accounts:
        scope = [
            TradingJournalRow.owner_id == owner_id,
            TradingJournalRow.execution_mode == "live",
            TradingJournalRow.account_id.in_(accounts),
            TradingJournalRow.status.in_(sorted(UNRESOLVED_STATUSES)),
        ]
        if fixed_market(agent):
            scope.append(
                func.lower(TradingJournalRow.request["symbol"].as_string())
                == (agent.trading_symbol or "").casefold()
            )
        unresolved_count = int(
            await session.scalar(select(func.count()).select_from(TradingJournalRow).where(*scope))
            or 0
        )
        for row in await session.scalars(
            select(TradingJournalRow)
            .where(*scope)
            .order_by(TradingJournalRow.submitted_at, TradingJournalRow.operation_id)
            .limit(LIST_LIMIT)
        ):
            operations.append(
                {
                    "operation_id": row.operation_id,
                    "account_id": row.account_id,
                    "symbol": str(row.request.get("symbol", ""))[:80],
                    "action": str(row.request.get("action", ""))[:24],
                    "status": row.status,
                    "submitted_at": _iso(row.submitted_at),
                    "this_agent": _producer(row) == agent.id,
                    # The scoped block: new risk on this market or ticket only, never
                    # the account, never an exit. It is never resent automatically.
                    "blocks": "new_risk_on_this_symbol_or_ticket",
                }
            )
    active = [item for item in restrictions if item["state"] == "active"]
    state, params = _headline(
        level=level,
        paused=bool(agent.paused),
        trading=trading,
        grants=grants,
        restrictions=active,
        operations=operations,
        unresolved_count=unresolved_count,
        money_limits=money_limits,
    )
    return {
        "presentation_only": True,
        "observed_at": now.isoformat(),
        "state": state,
        "params": params,
        "level": level,
        "grants": grants,
        "global_trading": trading,
        "restrictions": restrictions[:LIST_LIMIT],
        "money_limits": money_limits,
        "unresolved_operations": operations,
        "unresolved_count": unresolved_count,
        # Exits stay allowed under every brake except a "freeze everything" pause.
        "exits_allowed": not any(
            item["action_class"] == "all_mutations" and item["symbol"] is None for item in active
        ),
    }


def _headline(
    *,
    level: str,
    paused: bool,
    trading: dict[str, Any],
    grants: list[dict[str, Any]],
    restrictions: list[dict[str, Any]],
    operations: list[dict[str, Any]],
    unresolved_count: int,
    money_limits: list[dict[str, Any]],
) -> tuple[str, dict[str, Any]]:
    """The one line: the agent's ladder level, or the strongest thing stopping it."""
    granted = {grant["account_id"] for grant in grants}
    if level == "analysis":
        return "no_trading", {}
    if paused:
        return "agent_paused", {}
    if trading["state"] == "stopped":
        return "stopped", {"since": trading["since"]}
    if restrictions:
        first = restrictions[0]
        return "paused", {
            "action_class": first["action_class"],
            "valid_until": first["valid_until"],
            "symbol": first["symbol"],
            "count": len(restrictions),
        }
    if unresolved_count:
        return "uncertain", {
            "count": unresolved_count,
            "symbol": operations[0]["symbol"] if operations else None,
        }
    if level == "supervised":
        return "ask_me", {"money_limit_set": any(item["configured"] for item in money_limits)}
    first_grant = grants[0] if grants else None
    return "on_its_own", {
        "symbol_scope": first_grant["symbol_scope"] if first_grant else "selected",
        "symbols": first_grant["symbols"][:3] if first_grant else [],
        "valid_until": first_grant["valid_until"] if first_grant else None,
        "grant_count": len(grants),
        "money_limit_set": any(
            item["configured"] for item in money_limits if item["account_id"] in granted
        ),
    }
