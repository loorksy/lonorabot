import hashlib
import re
from dataclasses import dataclass
from typing import Any

from lonora_contracts.skills import AgentSkill, SkillActivation, SkillManifest
from lonora_core.user_error import LonoraError
from pydantic import ValidationError

from .loader import load_skill, resources_root

CAPABILITY_TOOLS = {
    "memory.read": {"memory_read"},
    "memory.write": {"memory_write"},
    "research.read": {"search_internal", "web_fetch"},
    "market.read": {"market_quote", "market_candles", "market_instrument"},
    "chart.read": {"chart_inspect"},
    "chart.write": {"chart_open", "chart_annotate"},
    "account.read": {"account_read", "list_accounts"},
    "trade.propose": {"trade_execute"},
    "goal.manage": {"goal_read", "goal_plan", "goal_control"},
    "watch.manage": {"watch_create", "watch_list"},
    "collaboration.read": {"list_agents"},
}


@dataclass(frozen=True)
class SkillDefinition:
    manifest: SkillManifest
    content: str


class SkillRegistry:
    def __init__(self, definitions: list[SkillDefinition], known_tools: set[str] | None = None):
        self.definitions: dict[str, SkillDefinition] = {}
        for definition in definitions:
            manifest = definition.manifest
            if manifest.id in self.definitions:
                raise LonoraError("skill_duplicate_id", 409)
            if not definition.content.strip():
                raise LonoraError("skill_content_empty", 500)
            if set(manifest.required_capabilities) - CAPABILITY_TOOLS.keys():
                raise LonoraError("skill_capability_unknown", 500)
            if known_tools is not None and set(manifest.required_tools) - known_tools:
                raise LonoraError("skill_tool_unknown", 500)
            self.definitions[manifest.id] = definition
        self.validate_graph()

    def validate_graph(self) -> None:
        visited: set[str] = set()
        visiting: set[str] = set()

        def visit(identity: str) -> None:
            if identity in visiting:
                raise LonoraError("skill_dependency_cycle", 500)
            if identity in visited:
                return
            visiting.add(identity)
            manifest = self.definitions[identity].manifest
            if set(manifest.dependencies + manifest.conflicts) - self.definitions.keys():
                raise LonoraError("skill_reference_missing", 500)
            if identity in manifest.conflicts:
                raise LonoraError("skill_self_conflict", 500)
            for dependency in manifest.dependencies:
                visit(dependency)
            visiting.remove(identity)
            visited.add(identity)

        for identity in sorted(self.definitions):
            visit(identity)


def built_in_skills() -> dict[str, SkillDefinition]:
    root = resources_root() / "skills"
    result: dict[str, SkillDefinition] = {}
    for path in sorted(root.glob("*/SKILL.md")):
        try:
            manifest = SkillManifest.model_validate_json(path.with_name("skill.json").read_text())
        except (OSError, ValueError, ValidationError) as error:
            raise LonoraError("skill_manifest_invalid", 500) from error
        if manifest.id != path.parent.name or manifest.source != "builtin":
            raise LonoraError("skill_manifest_identity_invalid", 500)
        result[manifest.id] = SkillDefinition(manifest, load_skill(manifest.id))
    return result


def legacy_skill_id(name: str) -> str:
    return (
        name
        if re.fullmatch(r"[a-z0-9][a-z0-9_-]{0,79}", name)
        else "legacy-" + hashlib.sha256(name.encode()).hexdigest()[:24]
    )


def installed_registry(
    installed: list[dict[str, Any]], known_tools: set[str]
) -> tuple[SkillRegistry, dict[str, str]]:
    definitions = built_in_skills()
    builtin_ids = set(definitions)
    rejected: dict[str, str] = {}
    seen: set[str] = set()
    for payload in installed:
        try:
            skill = AgentSkill.model_validate(payload)
        except ValidationError:
            identity = str(payload.get("name", "invalid"))
            key = identity + "@installed" if identity in builtin_ids else identity
            rejected[key] = "skill_manifest_invalid"
            continue
        if skill.name in seen:
            raise LonoraError("skill_duplicate_id", 409)
        seen.add(skill.name)
        if not skill.enabled and skill.name in builtin_ids:
            rejected[skill.name] = "skill_disabled"
            continue
        if skill.name in builtin_ids:
            rejected[skill.name + "@installed"] = "skill_builtin_override_denied"
            continue
        manifest = skill.manifest or SkillManifest(
            id=legacy_skill_id(skill.name),
            version="0.0.0",
            title=skill.name,
            description="Legacy owner-installed instructions; untyped compatibility metadata.",
            source="legacy",
            stability="legacy",
            context_budget=4000,
            activation=SkillActivation(mode="explicit"),
        )
        if manifest.id in definitions:
            raise LonoraError("skill_duplicate_id", 409)
        if not skill.enabled:
            rejected[manifest.id] = "skill_disabled"
        if not skill.content.strip():
            rejected[manifest.id] = "skill_content_empty"
            continue
        if set(manifest.required_tools) - known_tools:
            rejected[manifest.id] = "skill_tool_unknown"
            continue
        if set(manifest.required_capabilities) - CAPABILITY_TOOLS.keys():
            rejected[manifest.id] = "skill_capability_unknown"
            continue
        definitions[manifest.id] = SkillDefinition(manifest, skill.content)

    # Quarantine owner data without letting one malformed graph disable shipped Skills.
    # Validate each installed root against the whole candidate graph before removing any,
    # so cycles and transitive failures have order-independent diagnostics.
    def graph_failure(identity: str, path: frozenset[str] = frozenset()) -> str | None:
        if identity in path:
            return "skill_dependency_cycle"
        manifest = definitions[identity].manifest
        if set(manifest.dependencies + manifest.conflicts) - definitions.keys():
            return "skill_reference_missing"
        if identity in manifest.conflicts:
            return "skill_self_conflict"
        for dependency in sorted(set(manifest.dependencies)):
            if failure := graph_failure(dependency, path | {identity}):
                return failure
        return None

    while True:
        invalid = {
            identity: failure
            for identity in sorted(definitions.keys() - builtin_ids)
            if (failure := graph_failure(identity))
        }
        if not invalid:
            break
        for identity, failure in invalid.items():
            rejected[identity] = failure
            definitions.pop(identity)
    return SkillRegistry(list(definitions.values()), known_tools), rejected


def validate_resources(known_tools: set[str]) -> dict[str, Any]:
    """Fail early in builds/startup when shipped instructions cannot be resolved."""
    from lonora_contracts.skills import PlaybookManifest

    from .loader import load_constitution

    registry = SkillRegistry(list(built_in_skills().values()), known_tools)
    load_constitution()
    playbooks: dict[str, Any] = {}
    for path in sorted((resources_root() / "playbooks").glob("*/playbook.json")):
        manifest = PlaybookManifest.model_validate_json(path.read_text())
        if manifest.id != path.parent.name:
            raise LonoraError("playbook_identity_invalid", 500)
        if set(manifest.required_skills) - registry.definitions.keys():
            raise LonoraError("playbook_skill_unknown", 500)
        if set(manifest.required_tools) - known_tools:
            raise LonoraError("playbook_tool_unknown", 500)
        instruction = path.with_name("PLAYBOOK.md")
        if not instruction.is_file() or not instruction.read_text().strip():
            raise LonoraError("playbook_content_empty", 500)
        playbooks[manifest.id] = manifest.model_dump()
    return playbooks
