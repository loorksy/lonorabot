"""The agent directory and creating persistent agents from the conversation.

``agent_create`` creates an independent root agent from a template when the run answers
the owner's message (that message is recorded as its source). Otherwise it raises a
creation card and nothing is created until the owner taps it. A new agent never gets
money authority: the trading template starts at "Ask me" and the others at "No
trading". The trading template's focus pair is looked up in the broker catalog: the
only connected account is used without asking, and when two accounts or two symbols
match, the result lists them so the agent asks the owner one focused question.
"""

from hashlib import sha256
from typing import Any, cast

from lonora_adapters.brokers.base import BrokerManager
from lonora_contracts.agent_creation import TEMPLATE_LEVEL, AgentCreateInput
from lonora_contracts.broker import BrokerConnection
from lonora_contracts.domain import Contract, utcnow
from lonora_core.user_error import LonoraError
from lonora_db.agent_binding import agent_binding
from lonora_db.agent_creation import (
    MAXIMUM_CREATIONS_PER_RUN,
    agent_origin,
    existing_creation,
    report_targets,
    run_creations,
)
from lonora_db.agent_directory import agent_directory
from lonora_db.broker_sessions import BrokerSessionRepository
from lonora_db.client import Database
from lonora_db.lead import personal_agent_id
from lonora_db.owner_actions import (
    account_facts,
    live_status,
    lock_owner_actions,
    payload_hash,
    pending_effect,
    propose_creation,
    raise_created_card,
)
from lonora_db.runs import require_lease
from lonora_db.schema import AgentRow, BrokerSessionRow, EffectReceiptRow, OwnerActionRow
from lonora_db.supervision import supervised_ids
from lonora_session.idempotency import stable_id
from pydantic import Field
from sqlalchemy.ext.asyncio import AsyncSession

from .base import Tool
from .context import ToolContext
from .models import model_available, owner_named
from .restrictions import owner_message_id

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
    return {"resolved": True, "account_id": row.id, "symbol": name, "version": row.version}


def creation_receipt(owner_id: str, message_id: str, template: str, name: str) -> str:
    """One agent per owner message, template and requested name, across retries."""
    digest = sha256(
        "\n".join((owner_id, message_id, template, name.casefold())).encode()
    ).hexdigest()
    return "agent-create:" + digest


def created_card_id(owner_id: str, agent_id: str) -> str:
    return stable_id(owner_id, "owner-action:agent_created:agent:" + agent_id)


async def created_result(
    session: AsyncSession,
    context: ToolContext,
    row: AgentRow,
    *,
    deduplicated: bool,
) -> dict[str, Any]:
    origin = await agent_origin(session, context.owner_id, row.id)
    template = str(origin.get("template") or "general")
    card = await session.get(OwnerActionRow, created_card_id(context.owner_id, row.id))
    return {
        "created": True,
        "deduplicated": deduplicated,
        "agent": {
            "id": row.id,
            "name": row.name,
            "template": template,
            "focus": {"account_id": row.trading_account_id, "symbol": row.trading_symbol}
            if row.trading_symbol
            else None,
            "trading_level": "ask_me" if TEMPLATE_LEVEL[template] == "supervised" else "no_trading",
            "reports_to": report_targets(origin),
            "supervises": await supervised_ids(session, context.owner_id, row.id),
        },
        "undo_card_shown": card is not None,
        "money_authority": "none: every trade waits for the owner's tap until the owner signs "
        "a grant",
        "next": "It works when it has a task: send its first task with peer_send, then say in "
        "one line what was created and what is still missing.",
    }


def proposal_result(card: OwnerActionRow, *, created: bool) -> dict[str, Any]:
    return {
        "created": False,
        "owner_action": {
            "id": card.id,
            "kind": card.kind,
            "status": live_status(card),
            "expires_at": card.expires_at.isoformat(),
        },
        "already_shown": not created,
        # No owner message asked for this agent: it exists only after the owner's tap.
        "owner_must_tap": True,
        "money_authority": "none",
    }


async def check_limits(session: AsyncSession, owner_id: str, run_id: str) -> None:
    """A new creation (or creation card) fits the per-run guard against a runaway loop;
    the number of the owner's agents is never counted (mandate 3.3.2)."""
    if await run_creations(session, owner_id, run_id) >= MAXIMUM_CREATIONS_PER_RUN:
        raise LonoraError("agent_create_run_limit", 429)


async def create(context: ToolContext, args: dict[str, Any]) -> dict[str, Any]:
    from lonora_agent.collaboration.agent_create import check_responsibility, create_from_spec

    params = AgentCreateInput.model_validate(args)
    async with context.db.sessions() as session:
        run = await require_lease(session, context.lease)
        if run.agent_id != context.agent_id:
            raise LonoraError("agent_run_mismatch", 409)
        creator = await agent_binding(session, context.owner_id, context.agent_id)
        if creator.role == "delegated":
            raise LonoraError("delegated_agent_create_forbidden", 403)
        # A crash-replayed call returns what it already did, unchanged.
        replayed = await session.get(AgentRow, context.resource_id)
        if replayed is not None and replayed.owner_id == context.owner_id:
            return await created_result(session, context, replayed, deduplicated=True)
        card = await session.get(OwnerActionRow, context.resource_id)
        if card is not None and card.owner_id == context.owner_id:
            return proposal_result(card, created=False)
    check_responsibility(params.responsibility)
    spec: dict[str, Any] = {
        "template": params.template,
        "name": params.name,
        "responsibility": params.responsibility.strip(),
        "account_id": None,
        "symbol": None,
        "connection_version": None,
        "model": params.model.model_dump(mode="json") if params.model else None,
        "report_to": params.report_to,
        "supervises": params.supervises,
    }
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
            connection_version=market["version"],
        )
    if params.model is not None and not await model_available(context, params.model):
        return {
            "created": False,
            "code": "agent_model_not_available",
            "recovery": "Find the exact id with model_list, or omit model: the new agent "
            "starts on Lonora's current model.",
        }
    async with context.db.sessions() as session, session.begin():
        # The order the owner's card decision takes them in: cards, then creation.
        await lock_owner_actions(session, context.owner_id)
        run = await require_lease(session, context.lease)
        origin_thread = run.model_metadata.get("origin_thread_id") or context.thread_id
        message_id = await owner_message_id(session, run)
        if message_id is not None and await personal_agent_id(session, context.owner_id) in set(
            spec["supervises"]
        ):
            # Oversight over Lonora opens the owner's own chats: always the owner's tap.
            message_id = None
        if message_id is None:
            # Already created (the owner said yes in chat, or tapped another card): a
            # card would only create a second one.
            existing = await existing_creation(
                session, context.owner_id, params.template, params.name
            )
            if existing is not None:
                return {
                    "created": False,
                    "code": "agent_already_exists",
                    "agent": {"id": existing.id, "name": existing.name, "paused": existing.paused},
                    "recovery": "Use this agent (peer_send) instead of creating another one.",
                }
            # No owner message asked for it: the owner's tap creates it. A repeat returns
            # the card already shown, whatever the limits are now.
            shown = await pending_effect(
                session,
                context.agent_id,
                "create_agent",
                payload_hash("create_agent", {"spec": spec}),
            )
            if shown is None or shown.thread_id is None or shown.expires_at <= utcnow():
                await check_limits(session, context.owner_id, run.id)
            card, created = await propose_creation(
                session,
                context.owner_id,
                spec,
                card_id=context.resource_id,
                agent_id=context.agent_id,
                thread_id=origin_thread,
                run_id=run.id,
            )
            # Fenced after the conversation lock: the thread-before-run order of admission.
            await require_lease(session, context.lease, lock=True)
            return proposal_result(card, created=created)
        dropped = params.model is not None and not await owner_named(
            session, run, message_id, params.model
        )
        if dropped:
            # Only the owner assigns a model (VISION 12.3): one his words do not name is
            # dropped, and the new agent starts on Lonora's (3.1.2).
            spec["model"] = None
        key = creation_receipt(context.owner_id, message_id, params.template, params.name)
        receipt = await session.get(EffectReceiptRow, key)
        agent_id = str(receipt.result["agent_id"]) if receipt else context.resource_id
        if receipt is None:
            await check_limits(session, context.owner_id, run.id)
        elif await session.get(AgentRow, agent_id) is None:
            # The owner undid it: the same message never creates it again.
            raise LonoraError("agent_create_undone", 409)
        row, created = await create_from_spec(
            session,
            context.owner_id,
            spec,
            agent_id=agent_id,
            created_via="owner_message",
            created_by_agent_id=context.agent_id,
            source_message_id=message_id,
            run_id=run.id,
        )
        if receipt is None:
            session.add(EffectReceiptRow(key=key, result={"agent_id": row.id}))
        await raise_created_card(
            session,
            context.owner_id,
            row,
            agent_id=context.agent_id,
            thread_id=origin_thread,
            run_id=run.id,
        )
        await require_lease(session, context.lease, lock=True)
        result = await created_result(session, context, row, deduplicated=not created)
        if dropped:
            result["model_dropped"] = "not named by the owner: it starts on Lonora's model"
        return result


def tools() -> list[Tool]:
    return [
        Tool(
            "list_agents",
            "List all of the owner's agents/colleagues with exact routing IDs, names, "
            "paused status, template, whom each reports to and your own identity. Omit name "
            "for the full directory. Use this instead of search_internal to discover colleagues.",
            ListAgentsInput,
            list_agents,
            True,
        ),
        Tool(
            "agent_create",
            "Create a persistent agent from a template when the owner asks for one: trading "
            "(needs market, its focus pair), general, research or supervisor. Put what the "
            "owner asked it to do in responsibility. Without the owner's message in this run "
            "it becomes a card the owner taps. It never gets money authority: trading starts "
            "at Ask me, the others at No trading. If two accounts or symbols match, ask the "
            "owner once and call again with account_id. report_to: agents it reports to; "
            "supervises: agents it supervises. The owner gets an Undo card; a taken name gets "
            "a number.",
            AgentCreateInput,
            create,
            replay_safe=True,
        ),
    ]
