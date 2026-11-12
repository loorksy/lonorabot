"""One model choice per Agent, stored without a schema change.

Like the per-Agent approval preference, the record lives in ``ln_settings`` under an
owner-scoped key. It only orders the model candidates the router tries; it never grants
authority or changes what the Agent may do, and changing it never repeats a tool call,
a trade or any other effect: the next model turn simply asks another model.

Only the owner assigns a model (VISION 12.3): from an agent's settings, or in chat, where
an agent applies it when the owner's own message names the model. Any text model of a
connected provider's catalog is assignable. A new agent starts on Lonora's current model
(``inherit_lead_model``, VISION 3.1.2) until the owner assigns another.
"""

from collections.abc import Iterable
from hashlib import sha256
from typing import Any, Literal, cast

from lonora_contracts.domain import utcnow
from lonora_contracts.model_catalog import ModelDescriptor
from lonora_contracts.model_routing import (
    AgentModelChange,
    AgentModelPreference,
    AgentModelRecord,
    ModelSelection,
)
from lonora_core.model_routing import model_match_score
from lonora_core.user_error import LonoraError
from pydantic import ValidationError
from sqlalchemy.ext.asyncio import AsyncSession

from .events import emit
from .lead import personal_agent_id
from .schema import SettingRow
from .transactions import SettingsRepository, owned_agent


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


def same_choice(record: AgentModelRecord, preference: AgentModelPreference) -> bool:
    return record.preference == preference


async def apply_agent_model(
    session: AsyncSession,
    owner_id: str,
    agent_id: str,
    preference: AgentModelPreference,
    *,
    chosen_by: Literal["owner", "inherited"],
    by_agent_id: str | None = None,
    run_id: str | None = None,
    expected_revision: int | None = None,
    via: str = "owner_settings",
    source_message_id: str | None = None,
) -> tuple[AgentModelRecord, bool]:
    """Store one Agent's model choice; returns the record and whether it changed.

    The same choice again changes nothing (no revision, no event), so a replayed or
    repeated request is harmless. The choice it replaces is kept as ``previous``.
    """
    await owned_agent(session, owner_id, agent_id, lock=True)
    key = agent_model_key(owner_id, agent_id)
    row = await session.get(SettingRow, key, with_for_update=True, populate_existing=True)
    current = await stored_agent_model(session, owner_id, agent_id)
    if expected_revision is not None and expected_revision != current.revision:
        raise LonoraError("version_conflict", 409)
    if same_choice(current, preference):
        return current, False
    record = AgentModelRecord(
        owner_id=owner_id,
        agent_id=agent_id,
        revision=current.revision + 1,
        preference=preference,
        chosen_by=chosen_by,
        chosen_by_agent_id=by_agent_id,
        previous=current.preference,
        changed_at=utcnow(),
    )
    payload = record.model_dump(mode="json")
    if row is None:
        session.add(SettingRow(key=key, payload=payload))
    else:
        row.payload = payload
        row.updated_at = utcnow()
    await session.flush()
    primary = preference.primary
    emit(
        session,
        owner_id,
        "agent.model.updated",
        agent_id=agent_id,
        run_id=run_id,
        payload={
            "agent_id": agent_id,
            "revision": record.revision,
            "chosen_by": chosen_by,
            "by_agent_id": by_agent_id,
            "via": via,
            # The owner's message an agent applied, when an agent applied one.
            "source_message_id": source_message_id,
            "provider": primary.provider if primary else None,
            "model": primary.model if primary else None,
        },
    )
    return record, True


async def change_agent_model(
    session: AsyncSession, owner_id: str, agent_id: str, change: AgentModelChange
) -> AgentModelRecord:
    """The owner's choice from an agent's settings."""
    fallbacks = change.fallbacks
    if "fallbacks" not in change.model_fields_set:
        # A choice that names no fallbacks keeps the agent's own, behind its new primary.
        current = await stored_agent_model(session, owner_id, agent_id)
        fallbacks = [item for item in current.preference.fallbacks if item != change.primary]
    record, _ = await apply_agent_model(
        session,
        owner_id,
        agent_id,
        AgentModelPreference(primary=change.primary, fallbacks=fallbacks),
        chosen_by="owner",
        expected_revision=change.expected_revision,
    )
    return record


async def inherit_lead_model(session: AsyncSession, owner_id: str, agent_id: str) -> None:
    """A new agent starts on Lonora's current model (VISION 3.1.2): a snapshot of the
    Personal Agent's stored choice, kept until the owner assigns another. Without one,
    nothing is stored and the agent follows the owner's default, as Lonora does."""
    lead = await personal_agent_id(session, owner_id)
    if lead is None or lead == agent_id:
        return
    preference = (await stored_agent_model(session, owner_id, lead)).preference
    if preference.primary is None:
        return
    await apply_agent_model(
        session,
        owner_id,
        agent_id,
        preference,
        chosen_by="inherited",
        by_agent_id=lead,
        via="inherited_from_lonora",
    )


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
    query: str, entries: list[dict[str, str]], limit: int = 6
) -> list[dict[str, str]]:
    """Catalog entries that best match a model name or a guessed id ("Opus" finds the
    exact Opus ids), in catalog order among equals."""
    scored = [
        (score, index, entry)
        for index, entry in enumerate(entries)
        if (score := model_match_score(query, entry["provider"], entry["model"], entry["name"]))
    ]
    scored.sort(key=lambda item: (-item[0], item[1]))
    return [entry for _, _, entry in scored[:limit]]


async def catalog_has(session: AsyncSession, selection: ModelSelection) -> bool:
    """Whether the provider's discovered catalog lists this model."""
    catalog = await SettingsRepository().get(session, "catalog:" + selection.provider)
    models = cast(list[Any], catalog.get("models", []))
    return any(
        isinstance(item, dict) and cast(dict[str, Any], item).get("id") == selection.model
        for item in models
    )


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
