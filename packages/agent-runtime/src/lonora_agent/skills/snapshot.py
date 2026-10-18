"""Bounded current-Run instruction snapshots, stored by the existing context owner."""

from typing import Any, cast

from lonora_contracts.skills import SkillManifest
from lonora_core.user_error import LonoraError
from pydantic import ValidationError

from .registry import SkillDefinition, SkillRegistry
from .resolver import SkillSelection

MAX_SNAPSHOT_SKILLS = 32
MAX_SNAPSHOT_CHARS = 128000


def read_snapshot(payload: Any) -> dict[str, SkillDefinition]:
    if payload is None:
        return {}
    if not isinstance(payload, dict):
        raise LonoraError("skill_snapshot_invalid", 409)
    record = cast(dict[str, Any], payload)
    if record.get("version") != 1:
        raise LonoraError("skill_snapshot_invalid", 409)
    entries: Any = record.get("skills")
    if not isinstance(entries, dict):
        raise LonoraError("skill_snapshot_invalid", 409)
    entries = cast(dict[str, Any], entries)
    if len(entries) > MAX_SNAPSHOT_SKILLS:
        raise LonoraError("skill_snapshot_invalid", 409)
    result: dict[str, SkillDefinition] = {}
    total = 0
    for identity, entry in entries.items():
        if not isinstance(identity, str) or not isinstance(entry, dict):
            raise LonoraError("skill_snapshot_invalid", 409)
        entry = cast(dict[str, Any], entry)
        try:
            manifest = SkillManifest.model_validate(entry.get("manifest"))
        except ValidationError as error:
            raise LonoraError("skill_snapshot_invalid", 409) from error
        content = entry.get("content")
        if manifest.id != identity or not isinstance(content, str) or not content.strip():
            raise LonoraError("skill_snapshot_invalid", 409)
        if len(content) > manifest.context_budget:
            raise LonoraError("skill_snapshot_invalid", 409)
        total += len(content) + len(manifest.model_dump_json())
        if total > MAX_SNAPSHOT_CHARS:
            raise LonoraError("skill_snapshot_invalid", 409)
        result[identity] = SkillDefinition(manifest, content)
    return result


def apply_snapshot(
    registry: SkillRegistry,
    rejected: dict[str, str],
    snapshot: dict[str, SkillDefinition],
    known_tools: set[str],
) -> SkillRegistry:
    definitions = dict(registry.definitions)
    for identity, pinned in snapshot.items():
        current = definitions.get(identity)
        # Current catalog membership/source/disable state remain authoritative. Tool/scope
        # requirements are checked again by the resolver against the pinned manifest.
        if current is None:
            rejected.setdefault(identity, "skill_snapshot_unavailable")
            continue
        if identity in rejected:
            continue
        if current.manifest.source != pinned.manifest.source:
            rejected[identity] = "skill_snapshot_source_changed"
            continue
        if set(pinned.manifest.required_tools) - known_tools:
            rejected[identity] = "skill_required_tools_unavailable"
            continue
        definitions[identity] = pinned
    # A removed pinned dependency blocks the run explicitly rather than substituting
    # current instructions or accepting a broken graph.
    return SkillRegistry(list(definitions.values()), known_tools)


def write_snapshot(
    previous: dict[str, SkillDefinition], selection: SkillSelection
) -> dict[str, Any]:
    definitions = {**previous, **{item.manifest.id: item for item in selection.selected}}
    payload = {
        "version": 1,
        "skills": {
            identity: {"manifest": item.manifest.model_dump(), "content": item.content}
            for identity, item in sorted(definitions.items())
        },
    }
    # Apply the same bounds on reads and writes; never silently evict active versions.
    read_snapshot(payload)
    return payload
