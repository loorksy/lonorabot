from typing import Any, cast

from lonora_core.user_error import LonoraError
from lonora_db.agent_binding import (
    agent_binding,
    assert_payload_binding,
    fixed_market,
    flexible_scope,
    require_financial_agent,
    same_binding,
)
from lonora_db.broker_sessions import BrokerSessionRepository, current_broker_identity
from lonora_db.runs import require_lease
from lonora_db.schema import (
    AccountAuthorityRow,
    AgentRow,
    BrokerSessionRow,
    CloudChartRow,
    TradingGoalRow,
)
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from .context import ToolContext
from .resolve import Option, resolve, several

MARKET_TOOLS = ("market_", "chart_", "watch_", "trade_", "goal_", "account_")
# Reading records and narrowing admission need no financial authority: any agent may
# record an owner's restriction, and none can lift one.
NONFINANCIAL_TRADE_TOOLS = frozenset(
    {
        "trade_record_read",
        "trade_record_history",
        "trade_restriction_create",
        "trade_restriction_list",
    }
)


# Reading is open: a fixed-market agent reads every owned account and symbol (quotes,
# candles, accounts, full history and activity, records), like every other Agent. Its
# bound account and symbol stay its focus for every mutation path except orders (charts,
# watches, goals, decisions); the door never binds an order (3.1.2, 6.9). Copying market data into the agent's own workspace is a read
# of the market.
OPEN_READ_EFFECTS = frozenset({"market_candles_to_workspace"})


def market_tool(name: str) -> bool:
    return name.startswith(MARKET_TOOLS) or name == "list_accounts"


def align_payload(agent: AgentRow, payload: Any) -> Any:
    """Rewrite case-only differences onto the bound account and symbol."""
    if isinstance(payload, list):
        return [align_payload(agent, item) for item in cast(list[Any], payload)]
    if not isinstance(payload, dict):
        return payload
    aligned: dict[str, Any] = {}
    for key, value in cast(dict[str, Any], payload).items():
        if isinstance(value, (dict, list)):
            aligned[key] = align_payload(agent, value)
            continue
        if key == "account_id" and same_binding(value, agent.trading_account_id):
            aligned[key] = agent.trading_account_id
        elif key == "symbol" and same_binding(value, agent.trading_symbol):
            aligned[key] = agent.trading_symbol
        else:
            aligned[key] = value
    return aligned


def fill_bound_fields(agent: AgentRow, args: dict[str, Any], fields: set[str]) -> dict[str, Any]:
    filled = dict(args)
    if agent.trading_account_id and "account_id" in fields and not filled.get("account_id"):
        filled["account_id"] = agent.trading_account_id
    if (
        agent.trading_symbol
        and "symbol" in fields
        and not filled.get("symbol")
        # An explicit every-symbol scope (trade_restriction_create) is not a missing symbol.
        and not filled.get("all_symbols")
        # The focus symbol belongs to the focus account: a call naming another owned
        # account reads (or is refused) for that account as a whole, fixed agents too.
        and ("account_id" not in fields or filled.get("account_id") == agent.trading_account_id)
    ):
        filled["symbol"] = agent.trading_symbol
    return filled


async def default_account(session: AsyncSession, owner_id: str, agent: AgentRow) -> str | None:
    """The account a call means when it names none: the agent's own account, else the
    one account it holds a signed authority for, else the owner's only account. Never a
    choice between several: then the call fails on its missing argument as before."""
    if agent.trading_account_id:
        return agent.trading_account_id
    for query in (
        select(AccountAuthorityRow.account_id)
        .where(
            AccountAuthorityRow.owner_id == owner_id,
            AccountAuthorityRow.agent_id == agent.id,
            AccountAuthorityRow.status == "active",
        )
        .distinct(),
        select(BrokerSessionRow.id).where(BrokerSessionRow.owner_id == owner_id),
    ):
        accounts = list(await session.scalars(query.limit(2)))
        if len(accounts) == 1:
            return accounts[0]
        if accounts:
            return None
    return None


def _login(value: object) -> str:
    """An account number as the broker identity keys it: no padding, no spaces."""
    text = str(value or "").strip()
    return str(int(text)) if text.isascii() and text.isdigit() else text


async def account_options(session: AsyncSession, owner_id: str) -> list[Option]:
    """The owner's accounts as he names them: the account number, its name, the broker."""
    options: list[Option] = []
    for row in await BrokerSessionRepository().list(session, owner_id):
        identity = current_broker_identity(row) or {}
        named = {key: str(identity.get(key) or "").strip() for key in ("name", "broker")}
        login = _login(identity.get("login"))
        options.append(
            Option(
                row.id,
                tuple(text for text in (login, named["name"], named["broker"]) if text),
                {
                    key: value
                    for key, value in {"broker": named["broker"], "login": login}.items()
                    if value
                },
            )
        )
    return options


async def named_account(
    session: AsyncSession, owner_id: str, args: dict[str, Any], *, read: bool
) -> tuple[dict[str, Any], dict[str, Any] | None]:
    """``args`` with an account the call named in the owner's words put as its id.

    Only a read takes the one account that fits; anything else is refused with it, so an
    order, a watch or a grant is never pointed at an account the call did not name.
    """
    requested = args.get("account_id")
    if not isinstance(requested, str) or not requested.strip():
        return args, None
    row = await session.get(BrokerSessionRow, requested)
    if row is not None and row.owner_id == owner_id:
        return args, None
    account_id, note = resolve(
        _login(requested),
        await account_options(session, owner_id),
        missing="broker_sessions_not_found",
        argument="account_id",
        use="any" if read else "refuse",
        listing="list_accounts",
    )
    return {**args, "account_id": account_id}, note


async def prepare_market_arguments(
    context: ToolContext,
    name: str,
    args: dict[str, Any],
    model: type[BaseModel],
    *,
    read: bool = False,
) -> tuple[dict[str, Any], dict[str, Any] | None]:
    """The call's arguments completed from the agent's market, and the note to state when
    an account was taken from the owner's words for it."""
    if not market_tool(name):
        return args, None
    async with context.db.sessions() as session:
        args, note = await named_account(session, context.owner_id, args, read=read)
        agent = await agent_binding(session, context.owner_id, context.agent_id)
        if not agent.trading_account_id or not agent.trading_symbol:
            field = model.model_fields.get("account_id")
            if field is None or not field.is_required() or args.get("account_id"):
                return args, note
            account_id = await default_account(session, context.owner_id, agent)
            if account_id is not None:
                return {**args, "account_id": account_id}, note
            accounts = await account_options(session, context.owner_id)
            if len(accounts) > 1:
                # Several accounts and the call named none: never a choice between them.
                raise several("broker_sessions_ambiguous", "", "account_id", accounts)
            return args, note
        aligned = args if flexible_scope(agent) else align_payload(agent, args)
        if not isinstance(aligned, dict):
            return args, note
        fields = set(model.model_fields)
        if name == "trade_close_positions":
            # A close-all is not narrowed to the focus symbol (3.1.2, 6.9). Its operation
            # ids are per ticket and its set frozen per call, so no replayed id changes.
            fields.discard("symbol")
        filled = fill_bound_fields(agent, cast(dict[str, Any], aligned), fields)
        return filled, note


async def guard_market_tool(
    context: ToolContext, name: str, args: dict[str, Any], *, read: bool = False
) -> dict[str, Any]:
    """The run's lease for financial tools; a fixed market for mutations other than
    orders (the door never binds an agent's orders, 3.1.2, 6.9).

    ``read`` is the registry's own effect metadata for the tool: reads are open.
    """
    if not market_tool(name):
        return args
    async with context.db.sessions() as session:
        agent = await agent_binding(session, context.owner_id, context.agent_id)
        trading = name.startswith("trade_") and name not in NONFINANCIAL_TRADE_TOOLS
        if trading:
            await require_lease(session, context.lease)
        elif name.startswith("goal_") and name not in {"goal_read", "goal_list", "goal_decisions"}:
            await require_lease(session, context.lease)
            await require_financial_agent(session, context.owner_id, context.agent_id)
        if not fixed_market(agent):
            return args
        aligned = align_payload(agent, args)
        if isinstance(aligned, dict):
            args = cast(dict[str, Any], aligned)
        if read or name in OPEN_READ_EFFECTS:
            return args
        if trading:
            # The door never binds an agent's orders to its focus pair (3.1.2, 6.9): a
            # close-all is not narrowed to it either (its ids are per ticket, its set frozen
            # per call, so no replayed id changes).
            return args
        if name == "watch_create" and not args.get("symbol"):
            args = {**args, "symbol": agent.trading_symbol}
        assert_payload_binding(agent, args)
        if args.get("chart_id"):
            chart = await session.get(CloudChartRow, args["chart_id"])
            if chart is None or chart.owner_id != context.owner_id:
                raise LonoraError("cloud_charts_not_found", 404)
            assert_payload_binding(agent, chart.payload)
        if args.get("goal_id"):
            goal = await session.get(TradingGoalRow, args["goal_id"])
            if goal is None or goal.owner_id != context.owner_id:
                raise LonoraError("goal_not_found", 404)
            assert_payload_binding(agent, goal.payload)
        if name == "watch_create" and args.get("position_id"):
            broker = await context.brokers.get(context.owner_id, str(agent.trading_account_id))
            position = next(
                (item for item in await broker.positions() if item.id == args["position_id"]), None
            )
            if position is None:
                raise LonoraError("position_not_found", 404)
            assert_payload_binding(agent, {"symbol": position.symbol})
        return args


FOCUS_PAIR_NOTE = (
    "Reading and trading are open across every owned account and symbol; charts, watches, "
    "goals and decisions stay on this bound account and symbol."
)


async def scope_market_result(
    context: ToolContext, name: str, result: dict[str, Any]
) -> dict[str, Any]:
    """Name a fixed-market agent's focus pair; never hide what it may read or trade."""
    if name not in {"market_symbols", "market_instruments", "account_read"}:
        return result
    async with context.db.sessions() as session:
        agent = await agent_binding(session, context.owner_id, context.agent_id)
        if not fixed_market(agent):
            return result
        return {
            **result,
            "focus_pair": {
                "account_id": agent.trading_account_id,
                "symbol": agent.trading_symbol,
                "note": FOCUS_PAIR_NOTE,
            },
        }
