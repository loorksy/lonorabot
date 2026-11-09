"""Bounded discovery contracts and the existing instruction resolver."""

from typing import Any

import pytest
from lonora_agent.skills.access import acknowledgment, admission_snapshot, select_bundle
from lonora_agent.skills.registry import installed_registry
from lonora_agent.skills.resolver import SkillSignals
from lonora_contracts.skills import SkillActivation, SkillManifest
from lonora_core.user_error import LonoraError
from lonora_tools.loader import load_tools
from lonora_tools.skills import SkillsListInput, SkillViewInput, catalog, view
from pydantic import ValidationError

TOOLS = {tool.name for tool in load_tools().definitions()}


def procedure(identity: str, **changes: Any) -> dict[str, Any]:
    manifest = SkillManifest(
        id=identity,
        version="1.0.0",
        title=identity,
        description="A bounded procedure",
        activation=SkillActivation(mode="explicit"),
        **changes,
    )
    return {"name": identity, "content": "Verified procedure", "manifest": manifest.model_dump()}


def bundle(payloads: list[dict[str, Any]], identity: str, active: tuple[str, ...] = ()) -> Any:
    registry, rejected = installed_registry(payloads, TOOLS)
    return select_bundle(
        registry,
        rejected,
        SkillSignals(trigger="", available_tools=frozenset(TOOLS)),
        active,
        identity,
    )


def test_static_registration_and_no_authority_grant() -> None:
    registry = load_tools()
    for name in ("skills_list", "skill_view"):
        assert registry.tools[name].read_only
        assert not registry.tools[name].financial
    combined, selected = bundle(
        [procedure("dependency"), procedure("requested", dependencies=["dependency"])],
        "requested",
    )
    result = acknowledgment("requested", selected)
    assert [item["id"] for item in result["skills"]] == ["dependency", "requested"]
    assert result["authority_granted"] is False
    assert len(combined.context()) < 16000


@pytest.mark.parametrize(
    ("payloads", "identity", "active", "code"),
    [
        ([{**procedure("disabled"), "enabled": False}], "disabled", (), "skill_disabled"),
        ([procedure("tools", required_tools=["absent"])], "tools", (), "skill_tool_unknown"),
        ([procedure("missing", dependencies=["absent"])], "missing", (), "skill_reference_missing"),
        (
            [procedure("one"), procedure("two", conflicts=["one"])],
            "two",
            ("one",),
            "skill_conflict",
        ),
        ([], "unknown", (), "skill_not_found"),
    ],
)
def test_ineligible_views_never_replace_active_instructions(
    payloads: list[dict[str, Any]], identity: str, active: tuple[str, ...], code: str
) -> None:
    with pytest.raises(LonoraError, match=code):
        bundle(payloads, identity, active)


def test_combined_instruction_budget_is_not_silently_evicted() -> None:
    payloads = [
        {**procedure(identity, context_budget=10000), "content": identity[0] * 9000}
        for identity in ("alpha", "beta")
    ]
    with pytest.raises(LonoraError, match="skill_total_budget_exceeded"):
        bundle(payloads, "beta", ("alpha",))


@pytest.mark.parametrize("arguments", [{"limit": 21}, {"offset": -1}, {"offset": 100001}])
def test_catalog_input_bounds(arguments: dict[str, Any]) -> None:
    with pytest.raises(ValidationError):
        SkillsListInput.model_validate(arguments)


@pytest.mark.parametrize("identity", ["../escape", "https://host/skill", "", "x" * 81])
def test_view_accepts_an_identity_not_a_path(identity: str) -> None:
    with pytest.raises(ValidationError):
        SkillViewInput(skill_id=identity)


@pytest.mark.asyncio
async def test_unbound_tools_fail_explicitly_without_agent_imports() -> None:
    from types import SimpleNamespace
    from typing import cast

    from lonora_tools.context import ToolContext

    context = cast(ToolContext, SimpleNamespace(skill_access=None))
    with pytest.raises(LonoraError, match="skill_runtime_unavailable"):
        await catalog(context, {"offset": 0, "limit": 8})
    with pytest.raises(LonoraError, match="skill_runtime_unavailable"):
        await view(context, {"skill_id": "market-analysis"})


def test_observe_only_access_filters_financial_procedures() -> None:
    registry, rejected = installed_registry(
        [procedure("financial", risk_class="financial", required_tools=["trade_execute"])],
        TOOLS,
    )
    with pytest.raises(LonoraError, match="skill_scope_unavailable"):
        select_bundle(
            registry,
            rejected,
            SkillSignals(
                trigger="",
                scope="observe_only",
                available_tools=frozenset(load_tools().names("observe_only")),
            ),
            (),
            "financial",
        )


def test_filtered_tool_availability_remains_authoritative() -> None:
    registry, rejected = installed_registry(
        [procedure("account-procedure", required_tools=["account_read"])], TOOLS
    )
    with pytest.raises(LonoraError, match="skill_required_tools_unavailable"):
        select_bundle(
            registry,
            rejected,
            SkillSignals(trigger="", available_tools=frozenset()),
            (),
            "account-procedure",
        )


def test_snapshot_capacity_rejects_new_admissions_without_eviction() -> None:
    from lonora_agent.skills.resolver import SkillSelection
    from lonora_agent.skills.snapshot import write_snapshot

    payloads = [procedure(f"retained-{index}") for index in range(32)]
    registry, _ = installed_registry(payloads, TOOLS)
    retained = SkillSelection(selected=[registry.definitions[item["name"]] for item in payloads])
    metadata = {"skill_snapshot": write_snapshot({}, retained)}
    incoming = SkillSelection(selected=[registry.definitions["memory"]])
    with pytest.raises(LonoraError, match="skill_snapshot_budget_exceeded"):
        admission_snapshot(metadata, incoming)
    assert len(metadata["skill_snapshot"]["skills"]) == 32
    assert "memory" not in metadata["skill_snapshot"]["skills"]


@pytest.mark.parametrize(
    ("source", "provenance", "trust"),
    [
        ("builtin", "bundled", "bundled_first_party"),
        ("owner", "owner", "owner_supplied"),
        ("legacy", "owner", "legacy_owner_skill"),
        ("installed", "agent_authored", "agent_authored"),
        ("external", "external", "external_import"),
    ],
)
def test_every_skill_surface_labels_provenance_truthfully(
    source: str, provenance: str, trust: str
) -> None:
    from lonora_agent.context.skills import catalog_label
    from lonora_agent.skills.provenance import skill_provenance, skill_trust

    assert skill_provenance(source) == provenance and skill_trust(source) == trust
    assert catalog_label(source) == ("" if source == "builtin" else f" ({provenance})")
    if source in {"builtin", "legacy"}:
        return
    _, selected = bundle([procedure("labelled", source=source)], "labelled")
    view = acknowledgment("labelled", selected)
    assert [item["provenance"] for item in view["skills"]] == [provenance]
    assert selected.diagnostics()["skill_provenance"] == {"labelled": provenance}
    # External or agent-written instructions are never presented as the owner's.
    assert (provenance == "owner") == (source == "owner")


def test_pre_upgrade_view_receipts_with_the_old_label_still_verify() -> None:
    from lonora_agent.skills.access import same_acknowledgment

    _, selected = bundle([procedure("labelled", source="installed")], "labelled")
    expected = acknowledgment("labelled", selected)
    legacy = {
        **expected,
        "skills": [{**item, "provenance": "owner_supplied"} for item in expected["skills"]],
    }
    assert same_acknowledgment(legacy, expected)
    tampered = {
        **legacy,
        "skills": [{**item, "content": "changed"} for item in legacy["skills"]],
    }
    assert not same_acknowledgment(tampered, expected)
    assert not same_acknowledgment({**expected, "skills": []}, expected)
