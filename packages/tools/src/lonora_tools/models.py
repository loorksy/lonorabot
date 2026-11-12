"""The owner assigns an Agent's model from chat (VISION 12.3).

``model_request`` changes the model an Agent's next turns use, and only on the owner's
own words: it applies at once when the owner's typed message this run answers names the
model (its id, its catalog name or a distinctive word of either); otherwise nothing
changes and the result says to ask the owner. No card is raised either way. Any text
model of a connected provider's catalog is assignable. Only Lonora changes another
agent's model. It never grants authority and never repeats anything: tool results,
memory, Tasks, grants and uncertain operations stay exactly as they are, and the next
model turn simply asks another model.

``model_list`` gives the Agent the facts it needs first: the model answering now, who
chose it, and catalog matches for a name ("Opus") with their exact ids. Every change
that applies is logged (``agent.model.updated``) with the owner's message it answered.
"""

from typing import Any, get_args

from lonora_contracts.domain import Contract
from lonora_contracts.model_routing import (
    AgentModelPreference,
    Capability,
    ModelSelection,
    ProviderId,
)
from lonora_core.model_routing import names_model
from lonora_core.user_error import LonoraError
from lonora_db.agent_models import (
    apply_agent_model,
    catalog_has,
    catalog_models,
    closest_models,
    model_label,
    same_choice,
    stored_agent_model,
)
from lonora_db.runs import require_lease
from lonora_db.schema import EffectReceiptRow, MessageRow, RunRow, SteeringRow
from lonora_db.transactions import owned_agent
from pydantic import Field
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from .base import Tool
from .context import ToolContext
from .restrictions import owner_message_id

NAME = "model_request"
LIST_NAME = "model_list"
# Catalog matches one answer carries: enough to tell versions apart.
MAXIMUM_MATCHES = 6
UNCHANGED = "memory, tasks, grants, open trades and uncertain operations stay as they are"


class ModelRequestInput(Contract):
    model: ModelSelection = Field(
        description="The model the owner named, by exact provider and id from model_list."
    )
    agent_id: str | None = Field(
        default=None,
        min_length=1,
        max_length=36,
        description="Another agent whose model the owner wants changed (Lonora only).",
    )


class ModelListInput(Contract):
    query: str | None = Field(
        default=None,
        min_length=1,
        max_length=80,
        description='A model name or part of one ("Opus", "gpt-5") to find its exact ids '
        "in the connected providers' catalogs.",
    )
    agent_id: str | None = Field(
        default=None,
        min_length=1,
        max_length=36,
        description="Another of the owner's agents whose model to read.",
    )


async def _connected(context: ToolContext) -> list[str]:
    credentials: Any = getattr(context.router, "credentials", None)
    if credentials is None:
        return []
    return [item for item in get_args(ProviderId) if await credentials.configured(item)]


async def model_available(context: ToolContext, selection: ModelSelection) -> bool:
    """Whether a connected provider's catalog lists this model: any such model is
    available to an agent, with no list of the owner's to be on (VISION 12.3)."""
    if selection.provider not in await _connected(context):
        return False
    async with context.db.sessions() as session:
        return await catalog_has(session, selection)


async def _named(session: AsyncSession, selection: ModelSelection) -> dict[str, Any]:
    """Provider, exact id and the name the owner knows (the id when the catalog has none)."""
    label = await model_label(session, selection)
    return {**label, "name": label["name"] or selection.model}


async def owner_named(
    session: AsyncSession, run: RunRow, message_id: str, selection: ModelSelection
) -> bool:
    """Whether the owner's words this Run answers name the model: the message it started
    on, or one the owner added while it worked."""
    added = select(SteeringRow.message_id).where(SteeringRow.run_id == run.id)
    said = await session.scalars(
        select(MessageRow.content).where(
            MessageRow.thread_id == run.thread_id,
            MessageRow.role == "user",
            # The owner's own words only: never a card's send or a follow-up tap.
            MessageRow.origin == "owner",
            or_(MessageRow.id == message_id, MessageRow.id.in_(added)),
        )
    )
    name = (await model_label(session, selection))["name"]
    return any(names_model(text, selection, name) for text in said)


async def _answering(context: ToolContext, agent_id: str) -> ModelSelection | None:
    try:
        route = await context.router.route(
            Capability.CONVERSATION,
            owner_id=context.owner_id,
            agent_id=agent_id,
            run_choice=context.run_model if agent_id == context.agent_id else None,
        )
    except LonoraError as error:
        if error.code != "model_not_configured":
            raise
        return None
    return route.choices[0]


async def list_models(context: ToolContext, args: dict[str, Any]) -> dict[str, Any]:
    params = ModelListInput.model_validate(args)
    target = params.agent_id or context.agent_id
    async with context.db.sessions() as session:
        await owned_agent(session, context.owner_id, target)
    answering = await _answering(context, target)
    connected = await _connected(context)
    async with context.db.sessions() as session:
        record = await stored_agent_model(session, context.owner_id, target)
        result: dict[str, Any] = {
            "chosen_by": record.chosen_by,
            "answering": await _named(session, answering) if answering else None,
            "connected_providers": connected,
            # Reading changes nothing; the change itself is model_request (G0 baseline D05).
            "next": "Only the owner assigns a model: when his message names one, call "
            "model_request with its exact id. query finds exact ids in the catalogs.",
        }
        if params.query:
            entries = await catalog_models(session, connected)
            result["matches"] = closest_models(params.query, entries, MAXIMUM_MATCHES)
    return result


async def _not_in_catalog(context: ToolContext, selection: ModelSelection) -> dict[str, Any] | None:
    """The refusal for a model no catalog lists, with the closest real ids to retry with."""
    async with context.db.sessions() as session:
        if await catalog_has(session, selection):
            return None
    connected = await _connected(context)
    async with context.db.sessions() as session:
        entries = await catalog_models(session, connected)
    return {
        "ok": False,
        "code": "model_not_in_catalog",
        "changed": False,
        "closest": closest_models(
            selection.provider + " " + selection.model, entries, MAXIMUM_MATCHES
        ),
        "recovery": "Nothing changed. Retry with the exact provider and model of one of "
        "these, or find others with model_list.",
    }


async def request_model(context: ToolContext, args: dict[str, Any]) -> dict[str, Any]:
    params = ModelRequestInput.model_validate(args)
    target = params.agent_id or context.agent_id
    credentials: Any = getattr(context.router, "credentials", None)
    if credentials is not None and not await credentials.configured(params.model.provider):
        return {
            "ok": False,
            "code": "model_provider_not_connected",
            "changed": False,
            "recovery": "Nothing changed. The owner adds this provider's key in Model "
            "settings; until then only a connected provider's models are available.",
        }
    receipt_key = "model-request:" + context.resource_id
    async with context.db.sessions() as session:
        replayed = await session.get(EffectReceiptRow, receipt_key)
    refusal = None if replayed else await _not_in_catalog(context, params.model)
    if refusal is not None:
        return refusal
    async with context.db.sessions() as session, session.begin():
        receipt = await session.get(EffectReceiptRow, receipt_key)
        if receipt is not None:
            return receipt.result  # A crash-replayed call answers as it did.
        run = await require_lease(session, context.lease)
        if run.agent_id != context.agent_id:
            raise LonoraError("agent_run_mismatch", 409)
        proposer = await owned_agent(session, context.owner_id, context.agent_id)
        if target != context.agent_id:
            if proposer.role != "personal":
                # Lonora routes the owner's choices; no other agent changes another's.
                raise LonoraError("model_request_agent_forbidden", 403)
            await owned_agent(session, context.owner_id, target)
        record = await stored_agent_model(session, context.owner_id, target)
        # The agent's own fallbacks stay behind the model the owner named.
        preference = AgentModelPreference(
            primary=params.model,
            fallbacks=[item for item in record.preference.fallbacks if item != params.model],
        )
        message_id = await owner_message_id(session, run)
        if message_id is None or not await owner_named(session, run, message_id, params.model):
            # Only the owner assigns a model: his typed message this run answers names it.
            result: dict[str, Any] = {
                "ok": False,
                "code": "model_assignment_requires_owner_message",
                "changed": False,
                "recovery": "Nothing changed. Only the owner assigns a model: ask him to "
                "name it in chat.",
            }
        elif same_choice(record, preference):
            result = {"ok": True, "changed": False, "model": params.model.model_dump(mode="json")}
        else:
            await apply_agent_model(
                session,
                context.owner_id,
                target,
                preference,
                # The owner's choice; the agent that applied it and his message are recorded.
                chosen_by="owner",
                by_agent_id=context.agent_id,
                run_id=run.id,
                via=NAME,
                source_message_id=message_id,
            )
            result = {
                "ok": True,
                "changed": True,
                "model": params.model.model_dump(mode="json"),
                "applies_from": "the next model turn",
                "unchanged": UNCHANGED,
            }
        session.add(EffectReceiptRow(key=receipt_key, result=result))
        # Fenced: a Run that lost its lease writes nothing.
        await require_lease(session, context.lease, lock=True)
        return result


def tools() -> list[Tool]:
    return [
        Tool(
            NAME,
            "Assign the model the owner names in his message to you (or, for Lonora, to an "
            "agent he names), by exact provider and model id from model_list. It applies "
            "at once only when his typed message this turn names the model; otherwise "
            "nothing changes. Nothing is repeated: memory, tasks, grants and open trades "
            "stay as they are.",
            ModelRequestInput,
            request_model,
            replay_safe=True,
            parallel_safe=False,
        ),
        Tool(
            LIST_NAME,
            "Your model: the model answering now and who chose it. With query, the closest "
            'models in the connected providers\' catalogs ("Opus" finds the exact Opus ids).',
            ModelListInput,
            list_models,
            read_only=True,
        ),
    ]
