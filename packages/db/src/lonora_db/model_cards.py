"""Model cards (W15-10): choosing an Agent's model from the conversation.

``agent_model`` asks the owner to use a model for an Agent: one the owner has not allowed
yet, a change to an Agent the owner fixed, or a change for another Agent. Confirming it
applies the choice in the owner's name (and adds the model to the allowed list when the
Agent would choose it on its own). ``agent_model_changed`` follows a switch that already
applied and offers Undo. Neither touches money, so both are one tap and no passkey. The
card shows only server facts: the Agent, the models (their catalog names) and the mode.
"""

from typing import Any, Literal, cast

from lonora_contracts.domain import utcnow
from lonora_contracts.model_routing import (
    AgentModelPreference,
    AgentModelRecord,
    AgentModelState,
    ModelSelection,
)
from lonora_core.user_error import LonoraError
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from .agent_models import allow_model, allowed_models, apply_agent_model, stored_agent_model
from .schema import AgentRow, OwnerActionRow
from .transactions import SettingsRepository, owned_agent

MODEL_SUBJECT = "agent-model:"


def model_subject(agent_id: str) -> str:
    return MODEL_SUBJECT + agent_id


def request_payload(agent_id: str, state: AgentModelState, *, allow: bool) -> dict[str, Any]:
    """An ``agent_model`` card's exact effect: the Agent, the mode and its model, and
    whether the model joins the allowed list."""
    primary = state.preference.primary
    return {
        "agent_id": agent_id,
        "mode": state.mode,
        "primary": primary.model_dump(mode="json") if primary else None,
        "allow": allow,
    }


def requested_state(payload: dict[str, Any]) -> AgentModelState:
    primary = payload.get("primary")
    return AgentModelState(
        mode=cast(Literal["automatic", "fixed"], payload["mode"]),
        preference=AgentModelPreference(
            primary=ModelSelection.model_validate(primary) if primary else None
        ),
    )


def undo_payload(
    agent_id: str, revision: int, previous: AgentModelRecord, current: AgentModelState
) -> dict[str, Any]:
    """An ``agent_model_changed`` card: the switch that applied and what Undo restores,
    including who had made that earlier choice."""
    return {
        "agent_id": agent_id,
        "revision": revision,
        "previous": previous.state().model_dump(mode="json"),
        "previous_chosen_by": previous.chosen_by,
        "previous_chosen_by_agent_id": previous.chosen_by_agent_id,
        "current": current.model_dump(mode="json"),
    }


async def model_label(session: AsyncSession, selection: ModelSelection | None) -> dict[str, Any]:
    """The model as the owner recognizes it: its catalog name when known."""
    if selection is None:
        return {"provider": None, "model": None, "name": None}
    catalog = await SettingsRepository().get(session, "catalog:" + selection.provider)
    entries = [
        cast(dict[str, Any], item)
        for item in cast(list[Any], catalog.get("models", []))
        if isinstance(item, dict)
    ]
    name = next((item.get("name") for item in entries if item.get("id") == selection.model), None)
    return {
        "provider": selection.provider,
        "model": selection.model,
        "name": name if isinstance(name, str) and name != selection.model else None,
    }


async def state_facts(session: AsyncSession, state: AgentModelState) -> dict[str, Any]:
    return {
        "mode": state.mode,
        "model": await model_label(session, state.preference.primary),
    }


async def default_model(session: AsyncSession) -> ModelSelection | None:
    """The owner's default model for conversations (what an Automatic Agent starts on)."""
    from .agent_models import routed_models

    routed = await routed_models(session)
    return routed[0] if routed else None


async def model_stale_reason(
    session: AsyncSession, owner_id: str, kind: str, payload: dict[str, Any]
) -> str | None:
    """Raises when the Agent is not the owner's: such a card is never created."""
    agent_id = cast(str, payload["agent_id"])
    await owned_agent(session, owner_id, agent_id)
    record = await stored_agent_model(session, owner_id, agent_id)
    if kind == "agent_model_changed":
        return None if record.revision == payload["revision"] else "model_changed_again"
    wanted = requested_state(payload)
    if record.mode == wanted.mode and record.preference.primary == wanted.preference.primary:
        if not payload.get("allow") or wanted.preference.primary in await allowed_models(session):
            return "model_already_set"
    return None


async def model_card_facts(session: AsyncSession, row: OwnerActionRow) -> dict[str, Any]:
    payload = row.payload
    agent = await session.get(AgentRow, payload["agent_id"])
    proposer = await session.get(AgentRow, row.agent_id) if row.agent_id else None
    facts: dict[str, Any] = {
        "agent_name": agent.name if agent and agent.owner_id == row.owner_id else None,
        "default_model": await model_label(session, await default_model(session)),
    }
    if row.kind == "agent_model":
        facts["requested"] = await state_facts(session, requested_state(payload))
        facts["allow"] = bool(payload.get("allow"))
        if proposer is not None and proposer.id != payload["agent_id"]:
            facts["asked_by_agent_name"] = proposer.name
        if agent is not None:
            record = await stored_agent_model(session, row.owner_id, agent.id)
            facts["current"] = await state_facts(session, record.state())
        return facts
    facts["current"] = await state_facts(
        session, AgentModelState.model_validate(payload["current"])
    )
    facts["previous"] = await state_facts(
        session, AgentModelState.model_validate(payload["previous"])
    )
    return facts


async def raise_model_card(
    session: AsyncSession,
    owner_id: str,
    kind: Literal["agent_model", "agent_model_changed"],
    payload: dict[str, Any],
    *,
    card_id: str,
    agent_id: str,
    thread_id: str | None,
    run_id: str | None,
) -> tuple[OwnerActionRow, bool]:
    """A model card in the conversation; returns it and whether it is new.

    The same effect asked again by the same Agent returns the card already shown, and a
    request card counts toward the Agent's cap of waiting cards. An Undo card is the
    server's record of a switch that applied; a newer one replaces it.
    """
    from .owner_actions import (
        MAXIMUM_PENDING_PER_AGENT,
        card_thread,
        create_card,
        lock_owner_actions,
        payload_hash,
        pending_effect,
        settle,
        supersede_subject,
    )

    await lock_owner_actions(session, owner_id)
    existing = await session.get(OwnerActionRow, card_id)
    if existing is not None:
        if existing.owner_id != owner_id or existing.agent_id != agent_id:
            raise LonoraError("owner_action_not_found", 404)
        return existing, False
    subject = model_subject(cast(str, payload["agent_id"]))
    if kind == "agent_model_changed":
        # Only the latest switch can be undone, and an earlier request about this
        # agent's model no longer applies: a later tap must not undo this choice.
        for ended in ("agent_model", "agent_model_changed"):
            await supersede_subject(session, owner_id, ended, subject, "model_changed_again")
    else:
        current = await pending_effect(session, agent_id, kind, payload_hash(kind, payload))
        if current is not None:
            if current.thread_id is not None and current.expires_at > utcnow():
                return current, False
            await settle(
                session,
                current,
                "expired" if current.expires_at <= utcnow() else "superseded",
                "expired" if current.expires_at <= utcnow() else "conversation_deleted",
            )
        pending = await session.scalar(
            select(func.count())
            .select_from(OwnerActionRow)
            .where(
                OwnerActionRow.owner_id == owner_id,
                OwnerActionRow.agent_id == agent_id,
                OwnerActionRow.source == "agent",
                OwnerActionRow.status == "pending",
                OwnerActionRow.expires_at > utcnow(),
            )
        )
        if (pending or 0) >= MAXIMUM_PENDING_PER_AGENT:
            raise LonoraError("owner_action_limit", 429)
    thread = await card_thread(session, owner_id, agent_id, thread_id)
    row = await create_card(
        session,
        owner_id,
        card_id=card_id,
        agent_id=agent_id,
        thread=thread,
        run_id=run_id,
        source="agent" if kind == "agent_model" else "system",
        kind=kind,
        subject=subject,
        payload=payload,
    )
    return row, True


async def confirm_model_card(session: AsyncSession, row: OwnerActionRow) -> dict[str, Any]:
    """The owner's tap: use the model the card names, or undo the switch it reports."""
    agent_id = cast(str, row.payload["agent_id"])
    if row.kind == "agent_model":
        wanted = requested_state(row.payload)
        current = await stored_agent_model(session, row.owner_id, agent_id)
        # The agent's own fallbacks stay behind the model the owner chose.
        state = wanted.model_copy(
            update={
                "preference": AgentModelPreference(
                    primary=wanted.preference.primary,
                    fallbacks=[
                        item
                        for item in current.preference.fallbacks
                        if item != wanted.preference.primary
                    ],
                )
            }
        )
        added = False
        if row.payload.get("allow") and state.preference.primary is not None:
            added = await allow_model(session, state.preference.primary)
        record, _ = await apply_agent_model(
            session,
            row.owner_id,
            agent_id,
            state,
            chosen_by="owner",
            via="owner_card",
        )
        return {"revision": record.revision, "allowed_added": added}
    previous = AgentModelState.model_validate(row.payload["previous"])
    # Undo restores the earlier choice as it was, including who had made it.
    chosen_by = row.payload.get("previous_chosen_by", "owner")
    record, _ = await apply_agent_model(
        session,
        row.owner_id,
        agent_id,
        previous,
        chosen_by=cast(Literal["owner", "agent"] | None, chosen_by),
        by_agent_id=cast(str | None, row.payload.get("previous_chosen_by_agent_id")),
        via="owner_undo",
        expected_revision=cast(int, row.payload["revision"]),
    )
    return {"revision": record.revision, "undone": True}


async def supersede_agent_model_cards(
    session: AsyncSession,
    owner_id: str,
    agent_id: str,
    reason: str,
    *,
    keep: str | None = None,
) -> None:
    """The owner chose this Agent's model: the pending requests and Undo about it end."""
    from .owner_actions import lock_owner_actions, supersede_subject

    await lock_owner_actions(session, owner_id)
    for kind in ("agent_model", "agent_model_changed"):
        await supersede_subject(session, owner_id, kind, model_subject(agent_id), reason, keep=keep)


async def hold_model_cards(session: AsyncSession, owner_id: str) -> None:
    """The owner's card lock, taken before the agent and the conversation: the order a
    card decision takes them in."""
    from .owner_actions import lock_owner_actions

    await lock_owner_actions(session, owner_id)
