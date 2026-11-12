"""The agent directory and creating persistent agents from the conversation.

Only Lonora creates agents (mandate 3.1.2, 3.2.2), on its own judgment, without asking
first: flat, with no template, hierarchy, card or cap. A team agent's call is refused
with the way to ask Lonora. An assigned market is looked up in the broker catalog (the
only connected account is used without asking; when two accounts or two symbols match,
the result lists them so Lonora asks the owner one focused question) and written into
the new agent's method. The mode follows 4.3.2 and 4.3.3: an agent created in a turn the
owner typed starts in Ask, and a request for full authority shows its Mandate card; one
created on a wake or routine copies Lonora's mode unless Lonora creates it in Ask.
"""

from hashlib import sha256
from typing import Any, cast

from lonora_adapters.brokers.base import BrokerManager
from lonora_contracts.agent_creation import AgentCreateInput
from lonora_contracts.broker import BrokerConnection
from lonora_contracts.domain import Contract
from lonora_contracts.owner_actions import OwnerActionProposal
from lonora_core.user_error import LonoraError, ToolRefusal
from lonora_db.agent_creation import (
    MAXIMUM_CREATIONS_PER_RUN,
    run_creations,
)
from lonora_db.agent_directory import agent_directory
from lonora_db.broker_sessions import BrokerSessionRepository
from lonora_db.client import Database
from lonora_db.lead import is_lead
from lonora_db.owner_actions import (
    account_facts,
    lock_owner_actions,
    raise_system_card,
)
from lonora_db.owner_words import owner_typed_message
from lonora_db.runs import require_lease
from lonora_db.schema import AgentRow, BrokerSessionRow, EffectReceiptRow, OwnerActionRow
from pydantic import Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from .base import Tool
from .context import ToolContext
from .restrictions import OWNER_TRIGGERS

# A broker's spelling of a symbol may add a suffix ("XAUUSD.r", "XAUUSDm").
SUFFIX_SEPARATORS = frozenset(".-_#!+")
MAXIMUM_LOWERCASE_SUFFIX = 4
MAXIMUM_CANDIDATES = 8


class ListAgentsInput(Contract):
    name: str | None = Field(default=None, min_length=1, max_length=80)


async def list_agents(context: ToolContext, args: dict[str, Any]) -> dict[str, Any]:
    async with context.db.sessions() as session:
        agents = await agent_directory(
            session, context.owner_id, context.agent_id, args.get("name")
        )
    return {"agents": agents}


def symbol_candidates(names: list[object], symbol: str) -> list[str]:
    """The catalog's names for ``symbol``: the exact name, else the case-only matches,
    else every name that only adds a broker suffix to it."""
    catalog = [name for name in names if isinstance(name, str)]
    if symbol in catalog:
        return [symbol]
    folded = symbol.casefold()
    exact = [name for name in catalog if name.casefold() == folded]
    if exact:
        return exact
    candidates: list[str] = []
    for name in catalog:
        rest = name[len(symbol) :]
        if not rest or not name.casefold().startswith(folded):
            continue
        if rest[0] in SUFFIX_SEPARATORS or (
            rest.isalpha() and rest.islower() and len(rest) <= MAXIMUM_LOWERCASE_SUFFIX
        ):
            candidates.append(name)
    return candidates


async def resolve_market(
    db: Database, brokers: BrokerManager, owner_id: str, symbol: str, account_id: str | None
) -> dict[str, Any]:
    """The focus pair as the broker names it, or the candidates to ask the owner about."""
    async with db.sessions() as session:
        rows = await BrokerSessionRepository().all_connections(session, owner_id)
    enabled = [
        row
        for row in sorted(rows, key=lambda item: (item.created_at, item.id))
        if BrokerConnection.model_validate(row.payload).enabled
    ]
    if account_id is not None:
        enabled = [row for row in enabled if row.id == account_id]
        if not enabled:
            raise LonoraError("broker_connection_not_found", 404)
    if not enabled:
        raise LonoraError("agent_market_account_required", 409)
    found: list[tuple[BrokerSessionRow, str]] = []
    failure: LonoraError | None = None
    for row in enabled:
        try:
            broker = await brokers.get(owner_id, row.id)
            names = cast(list[object], await broker.symbols())
        except LonoraError as error:
            failure = failure or error
            continue
        found.extend((row, name) for name in symbol_candidates(names, symbol))
    if not found:
        if failure is not None and len(enabled) == 1:
            raise failure
        raise LonoraError("symbol_not_found", 404)
    if len(found) > 1:
        return {
            "resolved": False,
            "candidates": [
                {
                    "account_id": row.id,
                    "account": account_facts(row, row.id)["label"],
                    "market": name,
                }
                for row, name in found[:MAXIMUM_CANDIDATES]
            ],
        }
    row, name = found[0]
    broker = await brokers.get(owner_id, row.id)
    if (await broker.instrument(name)).symbol != name:
        raise LonoraError("broker_symbol_mismatch", 409)
    return {
        "resolved": True,
        "account_id": row.id,
        # The broker's verified label, else the connection id the agent's tools take.
        "account": account_facts(row, row.id)["label"] or row.id,
        "symbol": name,
        "version": row.version,
    }


def creation_receipt(owner_id: str, message_id: str, name: str) -> str:
    """One agent per owner message and requested name, across retries."""
    digest = sha256("\n".join((owner_id, message_id, name.casefold())).encode()).hexdigest()
    return "agent-create:" + digest


LEAD_ONLY_HINT = (
    "Only Lonora creates agents. Ask Lonora with peer_send for the agent you need, saying "
    "what it is for; when the owner asked you for it, hand the owner's request to Lonora "
    "that way and tell the owner in one line that Lonora will create it."
)


async def created_result(
    session: AsyncSession, context: ToolContext, row: AgentRow, *, deduplicated: bool
) -> dict[str, Any]:
    from lonora_db.trading_mode import trading_mode

    mandate = await session.scalar(
        select(OwnerActionRow.id).where(
            OwnerActionRow.owner_id == context.owner_id,
            OwnerActionRow.subject == "trading_mode:" + row.id,
        )
    )
    return {
        "created": True,
        "deduplicated": deduplicated,
        "agent": {
            "id": row.id,
            "name": row.name,
            "trading_mode": await trading_mode(session, context.owner_id, row.id),
        },
        "mandate_card_shown": mandate is not None,
        # A new agent is reported to the owner in one line (3.1.2; the conversation gate).
        **({} if deduplicated else {"owner_line": "required"}),
        "next": "It works when it has a task: send its first task with peer_send, then tell "
        "the owner in one line what you created and why.",
    }


async def check_limits(session: AsyncSession, owner_id: str, run_id: str) -> None:
    """A new creation fits the per-run guard against a runaway loop; the number of the
    owner's agents is never counted (mandate 3.3.2)."""
    if await run_creations(session, owner_id, run_id) >= MAXIMUM_CREATIONS_PER_RUN:
        raise LonoraError("agent_create_run_limit", 429)


async def assigned_market(
    context: ToolContext, params: AgentCreateInput, spec: dict[str, Any]
) -> dict[str, Any] | None:
    """Fill the spec's assigned market and account, or the question to ask the owner."""
    if params.market is not None:
        market = await resolve_market(
            context.db, context.brokers, context.owner_id, params.market, params.account_id
        )
        if not market["resolved"]:
            return {
                "created": False,
                "code": "agent_market_ambiguous",
                "candidates": market["candidates"],
                "recovery": "Ask the owner one focused question (wait_for_input) naming these "
                "choices, then call agent_create again with the chosen account_id and market.",
            }
        spec.update(
            account_id=market["account_id"],
            symbol=market["symbol"],
            account_label=market["account"],
            connection_version=market["version"],
        )
    elif params.account_id is not None:
        async with context.db.sessions() as session:
            found = await BrokerSessionRepository().get(
                session, context.owner_id, params.account_id
            )
            row = cast(BrokerSessionRow, found)
            spec.update(
                account_id=row.id,
                account_label=account_facts(row, row.id)["label"] or row.id,
                connection_version=row.version,
            )
    return None


async def create(context: ToolContext, args: dict[str, Any]) -> dict[str, Any]:
    from lonora_agent.collaboration.agent_create import check_responsibility, create_from_spec
    from lonora_db.trading_mode import trading_mode

    params = AgentCreateInput.model_validate(args)
    async with context.db.sessions() as session:
        run = await require_lease(session, context.lease)
        if run.agent_id != context.agent_id:
            raise LonoraError("agent_run_mismatch", 409)
        if not await is_lead(session, context.owner_id, context.agent_id):
            # No leading (3.2.2): a team agent asks Lonora, whatever its run says.
            raise ToolRefusal(
                "agent_create_lead_only",
                403,
                details={"class": "permission_denied", "hint": LEAD_ONLY_HINT},
            )
        # A crash-replayed call returns what it already did, unchanged.
        replayed = await session.get(AgentRow, context.resource_id)
        if replayed is not None and replayed.owner_id == context.owner_id:
            return await created_result(session, context, replayed, deduplicated=True)
    check_responsibility(params.responsibility)
    spec: dict[str, Any] = {
        "name": params.name,
        "responsibility": params.responsibility.strip(),
        "account_id": None,
        "symbol": None,
        "account_label": None,
        "connection_version": None,
    }
    question = await assigned_market(context, params, spec)
    if question is not None:
        return question
    async with context.db.sessions() as session, session.begin():
        # The order the owner's card decision takes them in: cards, then creation.
        await lock_owner_actions(session, context.owner_id)
        run = await require_lease(session, context.lease)
        origin_thread = run.model_metadata.get("origin_thread_id") or context.thread_id
        # The owner's typed request, also after the run read outside text: an agent the
        # owner asked for never takes Lonora's mode, so injected text can only make it Ask.
        typed = await owner_typed_message(session, run) if run.trigger in OWNER_TRIGGERS else None
        message_id = str(typed.id) if typed is not None else None
        if message_id is not None:
            # The owner asked for it (4.3.2): it starts in Ask, and a request for full
            # authority shows its Mandate card; only the owner's tap sets Full.
            spec["mode"] = "ask"
            mandate = params.mode == "full"
            key = creation_receipt(context.owner_id, message_id, params.name)
            receipt = await session.get(EffectReceiptRow, key)
        else:
            # On Lonora's own judgment (4.3.3): Lonora's mode now, unless created in Ask.
            spec["mode"] = (
                "ask"
                if params.mode == "ask"
                else await trading_mode(session, context.owner_id, context.agent_id)
            )
            mandate, key, receipt = False, None, None
        agent_id = str(receipt.result["agent_id"]) if receipt else context.resource_id
        if receipt is None:
            await check_limits(session, context.owner_id, run.id)
        elif await session.get(AgentRow, agent_id) is None:
            # The owner deleted it: the same message never creates it again.
            raise LonoraError("agent_create_undone", 409)
        row, created = await create_from_spec(
            session,
            context.owner_id,
            spec,
            agent_id=agent_id,
            created_via="owner_message" if message_id else "lead",
            created_by_agent_id=context.agent_id,
            source_message_id=message_id,
            run_id=run.id,
        )
        if key is not None and receipt is None:
            session.add(EffectReceiptRow(key=key, result={"agent_id": row.id}))
        if mandate:
            # Raised once per agent (the card's id is its subject), also when a repeated
            # call for the same request names full authority only now.
            await raise_system_card(
                session,
                context.owner_id,
                OwnerActionProposal(kind="trading_mode", agent_id=row.id),
                agent_id=context.agent_id,
                thread_id=origin_thread,
                run_id=run.id,
            )
        # Fenced after the conversation lock: the thread-before-run order of admission.
        await require_lease(session, context.lease, lock=True)
        return await created_result(session, context, row, deduplicated=not created)


def tools() -> list[Tool]:
    return [
        Tool(
            "list_agents",
            "List all of the owner's agents/colleagues with exact routing IDs, names, "
            "paused status, template and your own identity. Omit name "
            "for the full directory. Use this instead of search_internal to discover colleagues.",
            ListAgentsInput,
            list_agents,
            True,
        ),
        Tool(
            "agent_create",
            "Lonora only: create a team agent on your own judgment, without asking first. "
            "responsibility: its responsibilities and instructions. market and account_id: "
            "an instrument and account to assign, written into its method; if two match, "
            "ask the owner once and call again with account_id. mode: the mode the owner "
            "named (full shows the owner its Mandate card), or ask to create it in Ask; "
            "omitted, an agent created in a turn the owner typed starts in Ask, and one "
            "created on a wake or routine copies your mode. It uses your current model. A taken name gets a "
            "number.",
            AgentCreateInput,
            create,
            replay_safe=True,
        ),
    ]
