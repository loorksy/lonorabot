"""Owner-visible current catalog built with the existing resolver and controls.

Catalog reads do not create Runs, select active instructions or grant authority.
Only the separate detail endpoint exposes procedural text on demand.
"""

from collections.abc import Sequence
from dataclasses import replace

from lonora_contracts.skills import AgentSkill, SkillCatalogDetail, SkillVersionControls
from lonora_db.schema import SkillRow
from pydantic import ValidationError

from .registry import installed_registry, legacy_skill_id
from .resolver import SkillSignals, resolve_skills


def owner_skill_catalog(
    rows: Sequence[SkillRow], controls: SkillVersionControls, known_tools: set[str]
) -> dict[str, SkillCatalogDetail]:
    registry, rejected = installed_registry([row.payload for row in rows], known_tools)
    resources: dict[str, SkillRow] = {}
    for row in rows:
        name = str(row.payload.get("name", "invalid"))
        if name + "@installed" in rejected:
            identity = name + "@installed"
        elif name in rejected:
            identity = name
        else:
            identity = legacy_skill_id(name)
        resources[identity] = row

    revoked = {(item.skill_id, item.version) for item in controls.revoked}
    for identity, definition in registry.definitions.items():
        if (identity, definition.manifest.version) in revoked:
            rejected[identity] = "skill_version_revoked"
    signals = SkillSignals(trigger="", available_tools=frozenset(known_tools))
    result: dict[str, SkillCatalogDetail] = {}
    for identity in sorted(registry.definitions.keys() | rejected.keys()):
        definition = registry.definitions.get(identity)
        resource = resources.get(identity)
        manifest = definition.manifest if definition else None
        content = definition.content if definition else ""
        if definition is None and resource is not None:
            # Quarantined owner data stays inspectable without admitting it as a Skill.
            raw_content = resource.payload.get("content")
            content = raw_content[:16000] if isinstance(raw_content, str) else ""
            try:
                manifest = AgentSkill.model_validate(resource.payload).manifest
            except ValidationError:
                pass
        reason = rejected.get(identity)
        if reason is None and definition is not None:
            selection = resolve_skills(
                registry, replace(signals, requested=frozenset({identity})), 16000, rejected
            )
            if identity not in {item.manifest.id for item in selection.selected}:
                reason = selection.rejected.get(identity, "skill_unavailable")
        result[identity] = SkillCatalogDetail(
            id=identity,
            version=manifest.version if manifest else None,
            title=manifest.title if manifest else identity[:160],
            description=manifest.description if manifest else "",
            source=manifest.source if manifest else None,
            available=reason is None,
            code=reason,
            manifest=manifest,
            resource_id=resource.id if resource else None,
            resource_version=resource.version if resource else None,
            content=content,
        )
    return result
