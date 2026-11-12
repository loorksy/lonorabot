"""An Agent chooses its own model within the owner's allowed list (W15-10).

``model_request`` switches the model an Agent's next turns use. It never grants
authority and never repeats anything: tool results, memory, Tasks, grants and uncertain
operations stay exactly as they are, and the next model turn simply asks another model.

- An Automatic Agent switches itself among the models the owner allowed at once.
- A change the owner asked for applies at once only when the owner's message this run
  answers names the model (its id, its catalog name or a distinctive word of either);
  that is how Lonora sets another agent's model, or an Agent the owner fixed changes.
- Everything else (a model outside the allowed list, always; an Agent the owner fixed;
  another Agent; a mode change the owner's words do not name) becomes a one-tap owner
  card; nothing changes until the tap.

``model_list`` gives the Agent the facts it needs first: its mode, the model answering
now, the allowed models with their exact ids, and catalog matches for a name ("Opus").
Every switch that applies is logged (``agent.model.updated``) and raises an Undo card.
"""

from typing import Any, get_args

from lonora_contracts.domain import Contract
from lonora_contracts.model_routing import (
    AgentModelMode,
    AgentModelPreference,
    AgentModelState,
    Capability,
    ModelSelection,
    ProviderId,
)
from lonora_core.model_routing import names_model
from lonora_core.user_error import LonoraError
from lonora_db.agent_models import (
    allowed_models,
    apply_agent_model,
    catalog_has,
    catalog_models,
    closest_models,
    same_choice,
    stored_agent_model,
)
from lonora_db.model_cards import (
    hold_model_cards,
    model_label,
    raise_model_card,
    request_payload,
    undo_payload,
)
from lonora_db.runs import require_lease
from lonora_db.schema import EffectReceiptRow, EventRow, MessageRow, RunRow, SteeringRow
from lonora_db.transactions import owned_agent, owned_thread
from lonora_session.idempotency import stable_id
from pydantic import Field, model_validator
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from .base import Tool
from .context import ToolContext
from .provenance import owner_message_id

NAME = "model_request"
LIST_NAME = "model_list"
# Switches one Run may apply; a choice that keeps changing helps nobody.
MAXIMUM_SWITCHES_PER_RUN = 3
# Catalog matches one answer carries: enough to tell versions apart.
MAXIMUM_MATCHES = 6
UNCHANGED = "memory, tasks, grants, open trades and uncertain operations stay as they are"


class ModelRequestInput(Contract):
    model: ModelSelection | None = Field(
        default=None,
        description="The model to use, by exact provider and id. Omit to let Lonora choose "
        "again: the owner's default model.",
    )
    fixed: bool | None = Field(
        default=None,
        description="true when the owner wants this model kept (then only the owner changes "
        "it); false when the owner wants Lonora to choose again later; omit to keep the "
        "current mode.",
    )
    agent_id: str | None = Field(
        default=None,
        min_length=1,
        max_length=36,
        description="Another agent whose model the owner wants changed (Lonora only).",
    )

    @model_validator(mode="after")
    def fixed_has_model(self) -> "ModelRequestInput":
        if self.fixed and self.model is None:
            raise ValueError("agent_model_fixed_requires_model")
        return self


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


def _choices(models: list[ModelSelection]) -> list[dict[str, Any]]:
    return [item.model_dump(mode="json") for item in models]


async def _connected(context: ToolContext) -> list[str]:
    credentials: Any = getattr(context.router, "credentials", None)
    if credentials is None:
        return []
    return [item for item in get_args(ProviderId) if await credentials.configured(item)]


async def _named(session: AsyncSession, selection: ModelSelection) -> dict[str, Any]:
    """Provider, exact id and the name the owner knows (the id when the catalog has none)."""
    label = await model_label(session, selection)
    return {**label, "name": label["name"] or selection.model}


async def _owner_named(
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
        allowed = await allowed_models(session)
        result: dict[str, Any] = {
            "mode": record.mode,
            "chosen_by": record.chosen_by,
            "answering": await _named(session, answering) if answering else None,
            "allowed": [await _named(session, item) for item in allowed],
            "connected_providers": connected,
            # Reading changes nothing; the choice itself is model_request (G0 baseline D05).
            "next": "To choose or change this agent's model, call model_request with an exact "
            "id: it applies when the rules allow, otherwise the owner gets a one-tap card. "
            "query finds catalog models beyond the allowed list.",
        }
        if params.query:
            entries = await catalog_models(session, connected)
            result["matches"] = closest_models(params.query, entries, allowed, MAXIMUM_MATCHES)
    return result


async def _not_in_catalog(context: ToolContext, selection: ModelSelection) -> dict[str, Any] | None:
    """The refusal for a model no catalog lists, with the closest real ids to retry with."""
    async with context.db.sessions() as session:
        allowed = await allowed_models(session)
        if selection in allowed or await catalog_has(session, selection):
            return None
    connected = await _connected(context)
    async with context.db.sessions() as session:
        entries = await catalog_models(session, connected)
    return {
        "ok": False,
        "code": "model_not_in_catalog",
        "changed": False,
        "closest": closest_models(
            selection.provider + " " + selection.model, entries, allowed, MAXIMUM_MATCHES
        ),
        "allowed_models": _choices(allowed),
        "recovery": "Nothing changed. Retry with the exact provider and model of one of "
        "these, or find others with model_list.",
    }


async def request_model(context: ToolContext, args: dict[str, Any]) -> dict[str, Any]:
    params = ModelRequestInput.model_validate(args)
    target = params.agent_id or context.agent_id
    credentials: Any = getattr(context.router, "credentials", None)
    if params.model is not None and credentials is not None:
        if not await credentials.configured(params.model.provider):
            return {
                "ok": False,
                "code": "model_provider_not_connected",
                "changed": False,
                "recovery": "Nothing changed. The owner adds this provider's key in Model "
                "settings; until then choose one of the allowed models.",
            }
    receipt_key = "model-request:" + context.resource_id
    if params.model is not None:
        async with context.db.sessions() as session:
            replayed = await session.get(EffectReceiptRow, receipt_key)
        refusal = None if replayed else await _not_in_catalog(context, params.model)
        if refusal is not None:
            return refusal
    async with context.db.sessions() as session, session.begin():
        # Cards before the agent and the conversation: the order a card decision takes.
        await hold_model_cards(session, context.owner_id)
        receipt = await session.get(EffectReceiptRow, receipt_key)
        if receipt is not None:
            return receipt.result  # A crash-replayed call answers as it did.
        run = await require_lease(session, context.lease)
        if run.agent_id != context.agent_id:
            raise LonoraError("agent_run_mismatch", 409)
        proposer = await owned_agent(session, context.owner_id, context.agent_id)
        if target != context.agent_id:
            if proposer.role != "personal":
                # Lonora routes the owner's choices; every other agent changes only its own.
                raise LonoraError("model_request_agent_forbidden", 403)
            await owned_agent(session, context.owner_id, target)
        allowed = await allowed_models(session)
        listed = params.model is None or params.model in allowed
        record = await stored_agent_model(session, context.owner_id, target)
        # Unless asked otherwise, a Fixed choice stays Fixed; no model means Lonora chooses.
        mode: AgentModelMode = (
            "fixed"
            if params.fixed
            else "automatic"
            if params.fixed is False or params.model is None
            else record.mode
        )
        # The agent's own fallbacks stay behind whichever primary it uses.
        state = AgentModelState(
            mode=mode,
            preference=AgentModelPreference(
                primary=params.model,
                fallbacks=[item for item in record.preference.fallbacks if item != params.model],
            ),
        )
        message_id = await owner_message_id(session, run)
        own_choice = (
            target == context.agent_id
            and record.mode == "automatic"
            and mode == "automatic"
            and listed
        )
        # Anything beyond the agent's own choice applies at once only on the owner's
        # words: the message this run answers names the model. A model outside the
        # allowed list is always the owner's tap.
        owner_named = (
            not own_choice
            and listed
            and params.model is not None
            and message_id is not None
            and await _owner_named(session, run, message_id, params.model)
        )
        origin = run.model_metadata.get("origin_thread_id") or context.thread_id
        thread = await owned_thread(session, context.owner_id, origin)
        if thread.agent_id not in {context.agent_id, None}:
            raise LonoraError("agent_thread_mismatch", 409)
        if same_choice(record, state):
            result: dict[str, Any] = {
                "ok": True,
                "changed": False,
                "mode": record.mode,
                "model": params.model.model_dump(mode="json") if params.model else None,
            }
        elif not (own_choice or owner_named):
            card, created = await raise_model_card(
                session,
                context.owner_id,
                "agent_model",
                # Confirming adds the model to the allowed list: one tap, once.
                request_payload(target, state, allow=not listed),
                card_id=context.resource_id,
                agent_id=context.agent_id,
                thread_id=thread.id,
                run_id=run.id,
            )
            result = {
                "ok": True,
                "changed": False,
                "owner_must_tap": True,
                "owner_action": {"id": card.id, "kind": card.kind, "status": card.status},
                "already_shown": not created,
                "why": "outside_allowed_list"
                if not listed
                else "owner_fixed_model"
                if record.mode == "fixed"
                else "owner_choice",
                "allowed_models": _choices(allowed),
            }
        else:
            switches = await session.scalar(
                select(func.count())
                .select_from(EventRow)
                .where(
                    EventRow.run_id == run.id,
                    EventRow.kind == "agent.model.updated",
                    EventRow.payload["via"].as_string() == NAME,
                )
            )
            if (switches or 0) >= MAXIMUM_SWITCHES_PER_RUN:
                return {
                    "ok": False,
                    "code": "model_switch_limit",
                    "changed": False,
                    "limit": MAXIMUM_SWITCHES_PER_RUN,
                }
            stored, _ = await apply_agent_model(
                session,
                context.owner_id,
                target,
                state,
                # The agent made the switch; the owner's message it answered is recorded.
                chosen_by="agent",
                by_agent_id=context.agent_id,
                run_id=run.id,
                via=NAME,
                source_message_id=message_id,
            )
            undo, _ = await raise_model_card(
                session,
                context.owner_id,
                "agent_model_changed",
                undo_payload(target, stored.revision, record, stored.state()),
                card_id=stable_id(context.resource_id, "model-undo"),
                agent_id=context.agent_id,
                thread_id=thread.id,
                run_id=run.id,
            )
            result = {
                "ok": True,
                "changed": True,
                "mode": stored.mode,
                "model": params.model.model_dump(mode="json") if params.model else None,
                "applies_from": "your next model turn",
                "unchanged": UNCHANGED,
                "undo_card": undo.id,
            }
        session.add(EffectReceiptRow(key=receipt_key, result=result))
        # Fenced after the conversation lock: the thread-before-run order of admission.
        await require_lease(session, context.lease, lock=True)
        return result


def tools() -> list[Tool]:
    return [
        Tool(
            NAME,
            "Switch which model answers for you (or, for Lonora, for an agent the owner "
            "names), by exact provider and model id from model_list. While you are "
            "Automatic, your own switch to one of the owner's allowed models applies at once. "
            "A change the owner asks for this turn applies at once when their message names "
            "the model (fixed=true when they want it kept). A model outside the allowed list, "
            "and any other change, raises a one-tap owner card instead. Nothing is repeated: "
            "memory, tasks, grants and open trades stay as they are; the owner can undo it.",
            ModelRequestInput,
            request_model,
            replay_safe=True,
            parallel_safe=False,
        ),
        Tool(
            LIST_NAME,
            "Your model: Automatic or Fixed, the model answering now and the owner's allowed "
            "models with exact ids. With query, the closest models in the connected "
            'providers\' catalogs ("Opus" finds the exact Opus ids) and whether each is allowed.',
            ModelListInput,
            list_models,
            read_only=True,
        ),
    ]
