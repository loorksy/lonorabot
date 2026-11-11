"""One model choice per Agent, and the owner's allowed models, stored without a schema change.

Like the per-Agent approval preference, the record lives in ``ln_settings`` under an
owner-scoped key. It only orders the model candidates the router tries; it never grants
authority or changes what the Agent may do, and changing it never repeats a tool call,
a trade or any other effect: the next model turn simply asks another model.

An Agent is *Automatic* (Lonora chooses: the owner's default model, and the Agent may
switch itself among the allowed models) or *Fixed* (the owner chose one model; only the
owner changes it). The allowed models are the owner's global text routes and backups
plus the models the owner added (``model_allowed``).
"""

from collections.abc import Iterable
from hashlib import sha256
from typing import Any, Literal, cast

from lonora_contracts.domain import utcnow
from lonora_contracts.model_catalog import ModelDescriptor
from lonora_contracts.model_routing import (
    MAXIMUM_ADDED_MODELS,
    AgentModelChange,
    AgentModelPreference,
    AgentModelRecord,
    AgentModelState,
    AllowedModels,
    ModelSelection,
    RoutingPolicy,
)
from lonora_core.model_routing import model_match_score, text_routes
from lonora_core.user_error import LonoraError
from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from .events import emit
from .schema import AgentRow, SettingRow
from .transactions import SettingsRepository, owned_agent

ALLOWED_KEY = "model_allowed"


def agent_model_key(owner_id: str, agent_id: str) -> str:
    return "agent-model:" + sha256((owner_id + ":" + agent_id).encode()).hexdigest()


async def stored_agent_model(
    session: AsyncSession, owner_id: str, agent_id: str
) -> AgentModelRecord:
    """The record for an Agent the caller already scoped; empty when unset."""
    row = await session.get(SettingRow, agent_model_key(owner_id, agent_id))
    if row is None:
        return AgentModelRecord(owner_id=owner_id, agent_id=agent_id)
    try:
        value = AgentModelRecord.model_validate(row.payload)
    except ValidationError:
        raise LonoraError("agent_model_state_invalid", 409) from None
    if value.owner_id != owner_id or value.agent_id != agent_id:
        raise LonoraError("agent_model_scope_mismatch", 409)
    return value


async def agent_model_record(
    session: AsyncSession, owner_id: str, agent_id: str
) -> AgentModelRecord:
    await owned_agent(session, owner_id, agent_id)
    return await stored_agent_model(session, owner_id, agent_id)


async def agent_model_preference(
    session: AsyncSession, owner_id: str, agent_id: str
) -> AgentModelRecord | None:
    """The router's read: an unreadable record degrades to the global routes."""
    try:
        return await stored_agent_model(session, owner_id, agent_id)
    except LonoraError:
        return None


async def added_models(session: AsyncSession) -> AllowedModels:
    try:
        return AllowedModels.model_validate(await SettingsRepository().get(session, ALLOWED_KEY))
    except ValidationError:
        return AllowedModels()


async def routed_models(session: AsyncSession) -> list[ModelSelection]:
    """The owner's global text routes, then the global backups."""
    settings = SettingsRepository()
    try:
        routing = RoutingPolicy.model_validate(await settings.get(session, "model_routing"))
    except ValidationError:
        routing = RoutingPolicy()
    chosen = text_routes(routing)
    for item in (await settings.get(session, "model_backups")).get("choices", []):
        try:
            selection = ModelSelection.model_validate(item)
        except ValidationError:
            continue
        if selection not in chosen:
            chosen.append(selection)
    return chosen


async def allowed_models(session: AsyncSession) -> list[ModelSelection]:
    """Every model an Agent may choose on its own: routes, backups, the owner's additions."""
    chosen = await routed_models(session)
    for selection in (await added_models(session)).added:
        if selection not in chosen:
            chosen.append(selection)
    return chosen


async def provider_in_use(session: AsyncSession, owner_id: str, provider: str) -> bool:
    """Whether anything would still ask this provider for a model: a global route (the voice
    routes too), a backup, an allowed model, or one Agent's own choice."""
    try:
        routing = RoutingPolicy.model_validate(
            await SettingsRepository().get(session, "model_routing")
        )
    except ValidationError:
        routing = RoutingPolicy()
    chosen: list[ModelSelection | None] = [
        routing.unified,
        *routing.routes.values(),
        *await allowed_models(session),
    ]
    for agent_id in await session.scalars(select(AgentRow.id).where(AgentRow.owner_id == owner_id)):
        record = await agent_model_preference(session, owner_id, agent_id)
        if record:
            chosen += [record.preference.primary, *record.preference.fallbacks]
    return any(selection is not None and selection.provider == provider for selection in chosen)


async def save_added_models(session: AsyncSession, value: AllowedModels) -> AllowedModels:
    await SettingsRepository().put(session, ALLOWED_KEY, value.model_dump(mode="json"))
    return value


async def allow_model(session: AsyncSession, selection: ModelSelection) -> bool:
    """Add one model to the owner's additions (an owner card's confirmation)."""
    if selection in await allowed_models(session):
        return False
    current = await added_models(session)
    if len(current.added) >= MAXIMUM_ADDED_MODELS:
        raise LonoraError("allowed_models_full", 409)
    await save_added_models(session, AllowedModels(added=[*current.added, selection]))
    return True


def same_choice(record: AgentModelRecord, state: AgentModelState) -> bool:
    return record.mode == state.mode and record.preference == state.preference


async def apply_agent_model(
    session: AsyncSession,
    owner_id: str,
    agent_id: str,
    state: AgentModelState,
    *,
    chosen_by: Literal["owner", "agent"] | None,
    by_agent_id: str | None = None,
    run_id: str | None = None,
    expected_revision: int | None = None,
    via: str = "owner_settings",
    source_message_id: str | None = None,
) -> tuple[AgentModelRecord, bool]:
    """Store one Agent's model choice; returns the record and whether it changed.

    The same choice again changes nothing (no revision, no event), so a replayed or
    repeated request is harmless. The choice it replaces is kept for Undo. ``chosen_by``
    is None only when Undo restores the default nobody chose.
    """
    await owned_agent(session, owner_id, agent_id, lock=True)
    key = agent_model_key(owner_id, agent_id)
    row = await session.get(SettingRow, key, with_for_update=True, populate_existing=True)
    current = await stored_agent_model(session, owner_id, agent_id)
    if expected_revision is not None and expected_revision != current.revision:
        raise LonoraError("version_conflict", 409)
    if same_choice(current, state):
        return current, False
    record = AgentModelRecord(
        owner_id=owner_id,
        agent_id=agent_id,
        revision=current.revision + 1,
        mode=state.mode,
        preference=state.preference,
        chosen_by=chosen_by,
        chosen_by_agent_id=by_agent_id,
        previous=current.state(),
        changed_at=utcnow(),
    )
    payload = record.model_dump(mode="json")
    if row is None:
        session.add(SettingRow(key=key, payload=payload))
    else:
        row.payload = payload
        row.updated_at = utcnow()
    await session.flush()
    primary = state.preference.primary
    emit(
        session,
        owner_id,
        "agent.model.updated",
        agent_id=agent_id,
        run_id=run_id,
        payload={
            "agent_id": agent_id,
            "revision": record.revision,
            "mode": record.mode,
            "chosen_by": chosen_by,
            "by_agent_id": by_agent_id,
            "via": via,
            # The owner's message an agent's switch answered, when it answered one.
            "source_message_id": source_message_id,
            "provider": primary.provider if primary else None,
            "model": primary.model if primary else None,
        },
    )
    return record, True


async def change_agent_model(
    session: AsyncSession, owner_id: str, agent_id: str, change: AgentModelChange
) -> AgentModelRecord:
    """The owner's choice from settings or the model card; it wins over any agent's."""
    from .model_cards import supersede_agent_model_cards
    from .owner_actions import lock_owner_actions

    # Cards before the agent: the order a card decision takes them in.
    await lock_owner_actions(session, owner_id)
    fallbacks = change.fallbacks
    if "fallbacks" not in change.model_fields_set:
        # A choice that names no fallbacks keeps the agent's own, behind its new primary.
        current = await stored_agent_model(session, owner_id, agent_id)
        fallbacks = [item for item in current.preference.fallbacks if item != change.primary]
    state = AgentModelState(
        mode=change.mode,
        preference=AgentModelPreference(primary=change.primary, fallbacks=fallbacks),
    )
    record, changed = await apply_agent_model(
        session,
        owner_id,
        agent_id,
        state,
        chosen_by="owner",
        expected_revision=change.expected_revision,
    )
    if changed:
        # Only a real change ends the pending requests and the Undo about this agent.
        await supersede_agent_model_cards(session, owner_id, agent_id, "owner_changed_model")
    return record


async def catalog_models(session: AsyncSession, providers: Iterable[str]) -> list[dict[str, str]]:
    """Text models the providers' discovered catalogs list, as provider, id and name."""
    settings = SettingsRepository()
    found: list[dict[str, str]] = []
    for provider in providers:
        payload = await settings.get(session, "catalog:" + provider)
        for item in cast(list[Any], payload.get("models", [])):
            try:
                descriptor = ModelDescriptor.model_validate(item)
            except ValidationError:
                continue
            # A model the catalog verifies without text is not an agent's model.
            if descriptor.verified and "text" not in descriptor.capabilities:
                continue
            found.append({"provider": provider, "model": descriptor.id, "name": descriptor.name})
    return found


def closest_models(
    query: str, entries: list[dict[str, str]], allowed: list[ModelSelection], limit: int = 6
) -> list[dict[str, Any]]:
    """Catalog entries that best match a model name or a guessed id ("Opus" finds the
    exact Opus ids), allowed models first among equals."""
    listed = {(item.provider, item.model) for item in allowed}
    scored = [
        (score, (entry["provider"], entry["model"]) in listed, index, entry)
        for index, entry in enumerate(entries)
        if (score := model_match_score(query, entry["provider"], entry["model"], entry["name"]))
    ]
    scored.sort(key=lambda item: (-item[0], not item[1], item[2]))
    return [{**entry, "allowed": allowed_now} for _, allowed_now, _, entry in scored[:limit]]


async def catalog_has(session: AsyncSession, selection: ModelSelection) -> bool:
    """Whether the provider's discovered catalog lists this model."""
    catalog = await SettingsRepository().get(session, "catalog:" + selection.provider)
    models = cast(list[Any], catalog.get("models", []))
    return any(
        isinstance(item, dict) and cast(dict[str, Any], item).get("id") == selection.model
        for item in models
    )
