"""An Agent chooses its own model within the owner's allowed list (W15-10).

``model_request`` switches the model an Agent's next turns use. It never grants
authority and never repeats anything: tool results, memory, Tasks, grants and uncertain
operations stay exactly as they are, and the next model turn simply asks another model.

- The owner asked in this conversation turn: the choice applies at once, and the owner's
  message is recorded with it (Lonora may set another agent's model this way).
- Otherwise an Agent switches only itself, only while it is Automatic, and only to a
  model the owner allowed. Anything else (a model outside the list, an Agent the owner
  fixed, another Agent) becomes a one-tap owner card; nothing changes until the tap.

Every switch that applies is logged (``agent.model.updated``) and raises an Undo card.
"""

from typing import Any

from lonora_contracts.domain import Contract
from lonora_contracts.model_routing import (
    AgentModelPreference,
    AgentModelState,
    ModelSelection,
)
from lonora_core.user_error import LonoraError
from lonora_db.agent_models import (
    allowed_models,
    apply_agent_model,
    catalog_has,
    same_choice,
    stored_agent_model,
)
from lonora_db.model_cards import (
    hold_model_cards,
    raise_model_card,
    request_payload,
    undo_payload,
)
from lonora_db.runs import require_lease
from lonora_db.schema import EffectReceiptRow, EventRow
from lonora_db.transactions import owned_agent, owned_thread
from lonora_session.idempotency import stable_id
from pydantic import Field, model_validator
from sqlalchemy import func, select

from .base import Tool
from .context import ToolContext
from .restrictions import owner_message_id

NAME = "model_request"
# Switches one Run may apply; a choice that keeps changing helps nobody.
MAXIMUM_SWITCHES_PER_RUN = 3
UNCHANGED = "memory, tasks, grants, open trades and uncertain operations stay as they are"


class ModelRequestInput(Contract):
    model: ModelSelection | None = Field(
        default=None,
        description="The model to use. Omit (with fixed false) to let Lonora choose again: "
        "the owner's default model.",
    )
    fixed: bool = Field(
        default=False,
        description="True only when the owner asked for this model to stay; then only the "
        "owner changes it.",
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


def _choices(models: list[ModelSelection]) -> list[dict[str, Any]]:
    return [item.model_dump(mode="json") for item in models]


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
        if params.model is not None and not listed and not await catalog_has(session, params.model):
            return {
                "ok": False,
                "code": "model_not_in_catalog",
                "changed": False,
                "allowed_models": _choices(allowed),
            }
        record = await stored_agent_model(session, context.owner_id, target)
        # The agent's own fallbacks stay behind whichever primary it uses.
        state = AgentModelState(
            mode="fixed" if params.fixed else "automatic",
            preference=AgentModelPreference(
                primary=params.model,
                fallbacks=[item for item in record.preference.fallbacks if item != params.model],
            ),
        )
        message_id = await owner_message_id(session, run)
        owner_asked = message_id is not None
        own_choice = (
            target == context.agent_id
            and not params.fixed
            and record.mode == "automatic"
            and listed
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
        elif not (owner_asked or own_choice):
            card, created = await raise_model_card(
                session,
                context.owner_id,
                "agent_model",
                request_payload(target, state, allow=not listed and not params.fixed),
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
            previous = record.state()
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
                undo_payload(target, stored.revision, previous, stored.state()),
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
            "Switch which model answers for you (or, for Lonora, for the agent the owner "
            "names). Your own switch to one of the owner's allowed models applies at once "
            "while you are Automatic; when the owner asked in this turn it applies at once "
            "too (fixed=true when the owner wants it kept). A model outside the allowed list, "
            "an agent the owner fixed or another agent raises a one-tap owner card instead. "
            "Nothing is repeated: memory, tasks, grants and open trades stay as they are; the "
            "owner can undo the switch.",
            ModelRequestInput,
            request_model,
            replay_safe=True,
            parallel_safe=False,
        ),
    ]
