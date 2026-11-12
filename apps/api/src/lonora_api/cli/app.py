"""The `lonora` CLI endpoint (7.1.4, 7.3).

A separate ASGI app served only on a Unix socket (``LONORA_CLI_SOCKET``). Caddy publishes
port 8000, never this socket. Its directory is the ``cli-socket`` volume, which only the
API service mounts at this commit; the workspace will reach Lonora through it alone
(7.1.4). Every request carries an agent's token; the endpoint maps it to
exactly one agent and runs the command with that agent's identity, through the same
functions the agent tools call (7.3.1).

Every response is ``{"exit": <code>, "output": {...}}``: the client prints ``output`` as
its one JSON object and exits with ``exit`` (7.3.6).
"""

import json
import logging
from collections.abc import Awaitable, Callable
from typing import Any, cast

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from lonora_contracts.domain import Contract
from lonora_core.user_error import LonoraError, ToolRefusal
from lonora_db.broker_sessions import BrokerSessionRepository
from lonora_db.cli_tokens import agent_for_cli_token
from lonora_db.schema import AgentRow
from lonora_tools.account import read_account
from lonora_tools.market import CandlesInput, read_candles, read_quote
from lonora_tools.market_binding import named_account
from pydantic import Field, ValidationError
from sqlalchemy.ext.asyncio import AsyncSession

from ..runtime import ApiRuntime

logger = logging.getLogger(__name__)

EXECUTED, CARD_RAISED, REFUSED, UNKNOWN, IDENTITY_REFUSED = 0, 10, 20, 30, 77
MAXIMUM_BODY_BYTES = 64 * 1024


class AccountArgs(Contract):
    account: str | None = Field(default=None, min_length=1, max_length=80)


class PriceArgs(AccountArgs):
    symbol: str = Field(min_length=1, max_length=80)


class CandlesArgs(PriceArgs):
    timeframe: str = Field(min_length=1, max_length=8)
    count: int


def answer(code: int, output: dict[str, Any]) -> JSONResponse:
    return JSONResponse({"exit": code, "output": output})


def refused(code: str, **details: Any) -> JSONResponse:
    return answer(REFUSED, {"error": code, **details})


async def account_for(session: AsyncSession, owner_id: str, requested: str | None) -> str:
    """The account a command means (7.3.2): the one it names, else the only one connected.
    With several connected and none named it is refused, never chosen."""
    if requested is not None:
        named, _ = await named_account(session, owner_id, {"account_id": requested}, read=True)
        return str(named["account_id"])
    rows = await BrokerSessionRepository().list(session, owner_id)
    if len(rows) == 1:
        return rows[0].id
    if not rows:
        raise LonoraError("broker_sessions_not_found", 404)
    raise LonoraError("account_required", 409)


Command = Callable[[ApiRuntime, AgentRow, dict[str, Any]], Awaitable[JSONResponse]]


async def resolved_account(rt: ApiRuntime, agent: AgentRow, account: str | None) -> str:
    async with rt.db.sessions() as session:
        return await account_for(session, agent.owner_id, account)


async def price(rt: ApiRuntime, agent: AgentRow, body: dict[str, Any]) -> JSONResponse:
    args = PriceArgs.model_validate(body)
    account_id = await resolved_account(rt, agent, args.account)
    brokers = rt.services(agent.owner_id).brokers
    quote = await read_quote(brokers, agent.owner_id, account_id, args.symbol)
    return answer(EXECUTED, {"account": account_id, **quote})


async def candles(rt: ApiRuntime, agent: AgentRow, body: dict[str, Any]) -> JSONResponse:
    args = CandlesArgs.model_validate(body)
    account_id = await resolved_account(rt, agent, args.account)
    # The tool's own input contract bounds the request the same way for both callers.
    checked = CandlesInput.model_validate(
        {
            "account_id": account_id,
            "symbol": args.symbol,
            "timeframe": args.timeframe,
            "limit": args.count,
        }
    )
    brokers = rt.services(agent.owner_id).brokers
    series = await read_candles(
        brokers, agent.owner_id, account_id, checked.symbol, checked.timeframe, checked.limit
    )
    return answer(
        EXECUTED,
        {"account": account_id, "symbol": checked.symbol, "timeframe": checked.timeframe} | series,
    )


def snapshot_part(part: str) -> Command:
    async def command(rt: ApiRuntime, agent: AgentRow, body: dict[str, Any]) -> JSONResponse:
        args = AccountArgs.model_validate(body)
        account_id = await resolved_account(rt, agent, args.account)
        brokers = rt.services(agent.owner_id).brokers
        snapshot = await read_account(brokers, agent.owner_id, account_id)
        return answer(EXECUTED, {"account": account_id, part: snapshot[part]})

    return command


COMMANDS: dict[str, Command] = {
    "price": price,
    "candles": candles,
    "account": snapshot_part("account"),
    "positions": snapshot_part("positions"),
    "orders": snapshot_part("orders"),
}


def bearer(request: Request) -> str | None:
    header = request.headers.get("authorization", "")
    scheme, _, token = header.partition(" ")
    return token.strip() if scheme.lower() == "bearer" and token.strip() else None


def create_cli_app(rt: ApiRuntime) -> FastAPI:
    app = FastAPI(title="Lonora CLI", docs_url=None, redoc_url=None, openapi_url=None)
    app.state.runtime = rt

    @app.post("/v1/{command}")
    async def run(command: str, request: Request) -> JSONResponse:
        token = bearer(request)
        agent: AgentRow | None = None
        if token is not None:
            async with rt.db.sessions() as session:
                agent = await agent_for_cli_token(session, token)
        if agent is None:
            # Nothing is read or sent for a call that names no agent (7.3.3).
            return answer(IDENTITY_REFUSED, {"error": "identity_refused"})
        handler = COMMANDS.get(command)
        if handler is None:
            return refused("unknown_command")
        raw = b""
        # Bounded while it is read, chunked bodies too.
        async for chunk in request.stream():
            raw += chunk
            if len(raw) > MAXIMUM_BODY_BYTES:
                return refused("request_too_large")
        try:
            body: object = json.loads(raw) if raw else {}
        except ValueError:
            return refused("invalid_arguments")
        if not isinstance(body, dict):
            return refused("invalid_arguments")
        try:
            return await handler(rt, agent, cast(dict[str, Any], body))
        except ValidationError:
            return refused("invalid_arguments")
        except ToolRefusal as error:
            # Authored text and the account's own data (candidates), never exception text.
            return refused(error.code, details=error.details)
        except LonoraError as error:
            return refused(error.code)
        except Exception:
            logger.exception("lonora CLI command %s failed", command)
            return refused("command_failed")

    return app
