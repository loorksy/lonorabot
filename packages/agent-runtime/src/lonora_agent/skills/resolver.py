import hashlib
from dataclasses import dataclass, field
from html import escape
from typing import Any

from .registry import CAPABILITY_TOOLS, SkillDefinition, SkillRegistry


@dataclass(frozen=True)
class SkillSignals:
    intents: frozenset[str] = frozenset()
    trigger: str = "user"
    requested: frozenset[str] = frozenset()
    available_tools: frozenset[str] = frozenset()
    read_only: bool = False
    has_market: bool = False
    has_goal: bool = False
    has_chart: bool = False


@dataclass
class SkillSelection:
    selected: list[SkillDefinition] = field(default_factory=list[SkillDefinition])
    reasons: dict[str, str] = field(default_factory=dict[str, str])
    rejected: dict[str, str] = field(default_factory=dict[str, str])
    budget: int = 16000

    def context(self) -> str:
        return "\n\n".join(
            f'<skill id="{escape(item.manifest.id, quote=True)}" '
            f'version="{item.manifest.version}" source="{item.manifest.source}">\n'
            + item.content
            + "\n</skill>"
            for item in self.selected
        )

    def diagnostics(self) -> dict[str, Any]:
        return {
            "resolver_version": "1.1.0",
            "selected_skill_ids": [item.manifest.id for item in self.selected],
            "skill_versions": {item.manifest.id: item.manifest.version for item in self.selected},
            "skill_sources": {item.manifest.id: item.manifest.source for item in self.selected},
            # Installed source labels describe claimed origin, not publisher verification
            # or authority. Only shipped definitions can claim bundled provenance.
            "skill_provenance": {
                item.manifest.id: "bundled"
                if item.manifest.source == "builtin"
                else "owner_supplied"
                for item in self.selected
            },
            "skill_content_sha256": {
                item.manifest.id: hashlib.sha256(item.content.encode()).hexdigest()
                for item in self.selected
            },
            "selection_reason": self.reasons,
            "rejected_skills": self.rejected,
            "context_char_budget": self.budget,
            "context_chars": len(self.context()),
        }


def eligibility_reason(
    definition: SkillDefinition, signals: SkillSignals, rejected: dict[str, str]
) -> str | None:
    """One eligibility boundary for initial selection and retained instruction use."""
    manifest = definition.manifest
    if manifest.id in rejected:
        return rejected[manifest.id]
    if signals.read_only and manifest.risk_class != "read_only":
        return "skill_scope_unavailable"
    if set(manifest.required_tools) - signals.available_tools:
        return "skill_required_tools_unavailable"
    if set(manifest.required_capabilities) - CAPABILITY_TOOLS.keys():
        return "skill_capability_unknown"
    for capability in manifest.required_capabilities:
        if CAPABILITY_TOOLS[capability] - signals.available_tools:
            return "skill_required_capability_unavailable"
    if len(definition.content) > manifest.context_budget:
        return "skill_context_budget_exceeded"
    return None


def resolve_skills(
    registry: SkillRegistry,
    signals: SkillSignals,
    budget: int = 16000,
    rejected: dict[str, str] | None = None,
) -> SkillSelection:
    selection = SkillSelection(rejected=dict(rejected or {}), budget=budget)
    candidates: dict[str, str] = {}
    for identity, definition in registry.definitions.items():
        activation = definition.manifest.activation
        if identity in signals.requested:
            candidates[identity] = "explicit_request"
        elif activation.mode == "explicit":
            continue
        elif activation.mode == "trigger_based":
            if signals.trigger in activation.triggers:
                candidates[identity] = "run_trigger:" + signals.trigger
        elif set(activation.intents) & signals.intents:
            candidates[identity] = "intent:" + sorted(set(activation.intents) & signals.intents)[0]
        elif activation.triggers and signals.trigger in activation.triggers:
            candidates[identity] = "run_trigger:" + signals.trigger
    for unknown in signals.requested - registry.definitions.keys():
        selection.rejected.setdefault(unknown, "skill_not_found")

    def closure(identity: str) -> list[str]:
        result: list[str] = []
        for dependency in sorted(set(registry.definitions[identity].manifest.dependencies)):
            result.extend(item for item in closure(dependency) if item not in result)
        if identity not in result:
            result.append(identity)
        return result

    def eligible(identity: str) -> str | None:
        return eligibility_reason(registry.definitions[identity], signals, selection.rejected)

    ordering = sorted(
        candidates,
        key=lambda identity: (
            identity not in signals.requested,
            -registry.definitions[identity].manifest.priority,
            identity,
        ),
    )
    selected: set[str] = set()
    for identity in ordering:
        bundle = closure(identity)
        failure = next(((item, eligible(item)) for item in bundle if eligible(item)), None)
        if failure:
            failed, reason = failure
            selection.rejected[failed] = str(reason)
            selection.rejected[identity] = (
                str(reason) if failed == identity else "skill_dependency_unavailable"
            )
            continue
        combined = selected | set(bundle)
        conflict = any(
            set(registry.definitions[item].manifest.conflicts) & combined for item in combined
        )
        if conflict:
            selection.rejected[identity] = "skill_conflict"
            continue
        additions = [registry.definitions[item] for item in bundle if item not in selected]
        previous = selection.selected
        selection.selected = [*previous, *additions]
        if len(selection.context()) > budget:
            selection.selected = previous
            selection.rejected[identity] = "skill_total_budget_exceeded"
            continue
        for item in bundle:
            selected.add(item)
            selection.reasons[item] = candidates.get(item, "dependency:" + identity)
    for identity in registry.definitions.keys() - selected - selection.rejected.keys():
        selection.rejected[identity] = "skill_not_relevant"
    return selection
