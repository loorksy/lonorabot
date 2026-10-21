from typing import Any

from lonora_agent.skills.catalog import owner_skill_catalog
from lonora_contracts.domain import utcnow
from lonora_contracts.skills import SkillVersionControls, SkillVersionRevocation
from lonora_db.schema import SkillRow
from lonora_tools.loader import load_tools


def row(name: str, **changes: Any) -> SkillRow:
    payload: dict[str, Any] = {
        "name": name,
        "content": "Owner-authored procedure.",
        "enabled": True,
        "manifest": {
            "id": name,
            "version": "1.0.0",
            "title": name,
            "description": "Owner-authored current catalog entry.",
            "source": "owner",
            "activation": {"mode": "explicit"},
        },
    }
    payload.update(changes)
    return SkillRow(
        id=name + "-resource", owner_id="owner", agent_id="agent", payload=payload, version=1
    )


def catalog(rows: list[SkillRow], revoked: list[tuple[str, str]] | None = None):
    controls = SkillVersionControls(
        owner_id="owner",
        agent_id="agent",
        revision=len(revoked or []),
        revoked=[
            SkillVersionRevocation(skill_id=name, version=version, revoked_at=utcnow())
            for name, version in revoked or []
        ],
    )
    return owner_skill_catalog(rows, controls, {item.name for item in load_tools().definitions()})


def test_catalog_retains_manifest_resource_identity_without_selecting_instructions():
    item = row("owner-playbook")
    result = catalog([item])
    assert list(result) == sorted(result)
    entry = result["owner-playbook"]
    assert entry.available and entry.code is None
    assert entry.version == "1.0.0" and entry.source == "owner"
    assert entry.resource_id == item.id and entry.resource_version == 1
    assert entry.content == item.payload["content"]
    assert entry.manifest and entry.manifest.activation.mode == "explicit"
    builtin = result["chart-analysis"]
    assert builtin.source == "builtin" and builtin.resource_id is None
    assert "authority_granted" not in entry.model_dump()


def test_catalog_uses_exact_version_and_existing_dependency_eligibility():
    base = row("base")
    child = row("child")
    child.payload["manifest"]["dependencies"] = ["base"]
    result = catalog([base, child], [("base", "1.0.0")])
    assert result["base"].code == "skill_version_revoked"
    assert result["child"].code == "skill_dependency_unavailable"
    assert not result["base"].available and not result["child"].available
    assert result["base"].content == base.payload["content"]
    base.payload["manifest"]["version"] = "2.0.0"
    assert catalog([base, child], [("base", "1.0.0")])["child"].available


def test_quarantined_override_does_not_replace_bundled_instructions():
    override = row("chart-analysis", content="A disallowed override")
    result = catalog([override])
    assert result["chart-analysis"].source == "builtin"
    assert result["chart-analysis"].resource_id is None
    invalid = result["chart-analysis@installed"]
    assert invalid.code == "skill_builtin_override_denied" and not invalid.available
    assert invalid.resource_id == override.id and invalid.content == "A disallowed override"
    assert result["chart-analysis"].content != invalid.content


def test_disabled_and_legacy_entries_keep_actual_resource_and_diagnostics():
    item = row("A legacy owner title", manifest=None, enabled=False)
    result = catalog([item])
    legacy = next(entry for entry in result.values() if entry.resource_id == item.id)
    assert legacy.id.startswith("legacy-") and legacy.version == "0.0.0"
    assert legacy.code == "skill_disabled" and not legacy.available
    assert legacy.source == "legacy" and legacy.content == item.payload["content"]


def test_missing_tool_and_invalid_manifest_are_visible_without_admission():
    missing = row("missing-tool")
    missing.payload["manifest"]["required_tools"] = ["unavailable_in_production"]
    malformed = row("bad-manifest", manifest={"id": "different", "version": "broken"})
    result = catalog([missing, malformed])
    assert result["missing-tool"].code == "skill_tool_unknown"
    assert result["bad-manifest"].code == "skill_manifest_invalid"
    assert result["bad-manifest"].manifest is None and result["bad-manifest"].version is None
    assert result["bad-manifest"].content == malformed.payload["content"]
