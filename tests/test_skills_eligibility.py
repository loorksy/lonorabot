"""Installed catalog isolation and the real fenced context snapshot path."""

from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock

import pytest
from lonora_agent.context import skills
from lonora_agent.skills.registry import SkillDefinition, SkillRegistry, legacy_skill_id
from lonora_agent.skills.resolver import SkillSignals, resolve_skills
from lonora_agent.skills.runtime import select_skill_context
from lonora_agent.skills.snapshot import read_snapshot
from lonora_contracts.skills import SkillActivation, SkillManifest
from lonora_core.user_error import LonoraError
from lonora_tools.loader import load_tools

TOOLS = {tool.name for tool in load_tools().definitions()}


def payload(name: str, **changes: Any) -> dict[str, Any]:
    manifest = SkillManifest(
        id=name,
        version="1.0.0",
        title=name,
        description="Owner procedure",
        activation=SkillActivation(mode="explicit"),
        **changes,
    )
    return {
        "name": name,
        "content": "Original approved procedure.",
        "manifest": manifest.model_dump(),
    }


def choose(installed: list[dict[str, Any]], *requested: str) -> Any:
    return select_skill_context(
        installed,
        SkillSignals(requested=frozenset(requested), available_tools=frozenset(TOOLS)),
        TOOLS,
    )


def test_invalid_owner_graph_and_empty_content_do_not_disable_builtin() -> None:
    result = choose(
        [
            payload("missing", dependencies=["nonexistent"]),
            payload("cycle-a", dependencies=["cycle-b"]),
            payload("cycle-b", dependencies=["cycle-a"]),
            {**payload("blank"), "content": "   "},
            payload("conflict-with-cycle", conflicts=["cycle-a"]),
            payload("valid"),
        ],
        "missing",
        "cycle-a",
        "blank",
        "valid",
        "memory",
    )
    assert [item.manifest.id for item in result.selected] == ["memory", "valid"]
    assert result.rejected["missing"] == "skill_reference_missing"
    assert result.rejected["cycle-a"] == "skill_dependency_cycle"
    assert result.rejected["blank"] == "skill_content_empty"
    assert result.rejected["conflict-with-cycle"] == "skill_reference_missing"


def test_disabled_legacy_uses_canonical_identity() -> None:
    identity = legacy_skill_id("Owner Format")
    result = choose(
        [{"name": "Owner Format", "content": "Owner preference", "enabled": False}], identity
    )
    assert not result.selected
    assert result.rejected[identity] == "skill_disabled"


def test_invalid_builtin_override_does_not_suppress_builtin() -> None:
    result = choose([{"name": "memory", "content": "bad", "manifest": {"id": "memory"}}], "memory")
    assert [item.manifest.id for item in result.selected] == ["memory"]
    assert result.rejected["memory@installed"] == "skill_manifest_invalid"


def test_risk_scope_and_dependency_order_are_deterministic() -> None:
    definitions = [
        SkillDefinition(SkillManifest.model_validate(payload(name)["manifest"]), name)
        for name in ("a", "b")
    ]
    parent = payload("parent", dependencies=["b", "a", "a"])
    definitions.append(SkillDefinition(SkillManifest.model_validate(parent["manifest"]), "parent"))
    result = resolve_skills(
        SkillRegistry(definitions), SkillSignals(requested=frozenset({"parent"}))
    )
    assert [item.manifest.id for item in result.selected] == ["a", "b", "parent"]
    financial = payload("financial", risk_class="financial")
    result = select_skill_context(
        [financial],
        SkillSignals(
            requested=frozenset({"financial"}), read_only=True, available_tools=frozenset(TOOLS)
        ),
        TOOLS,
    )
    assert result.rejected["financial"] == "skill_scope_unavailable"


class ContextSession:
    def __init__(self, rows: list[Any], agent: Any):
        self.rows, self.agent = rows, agent

    async def __aenter__(self) -> "ContextSession":
        return self

    async def __aexit__(self, *_: Any) -> None:
        return None

    def begin(self) -> "ContextSession":
        return self

    async def scalars(self, _: Any) -> Any:
        return SimpleNamespace(all=lambda: self.rows)

    async def scalar(self, query: Any) -> Any:
        return self.agent if "ln_agents" in str(query) else None

    async def get(self, model: Any, *_: Any) -> Any:
        return self.agent if model.__name__ == "AgentRow" else None


@pytest.mark.asyncio
async def test_context_refresh_pins_content_after_catalog_update_and_honors_disable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from lonora_adapter_kit.types import ModelMessage

    owner = payload("owner-guide")
    row = SimpleNamespace(payload=owner)
    agent = SimpleNamespace(id="agent", trading_account_id=None)
    run: Any = SimpleNamespace(
        trigger="user",
        prompt="[skill:owner-guide]",
        input_seq=1,
        model_metadata={"provider": "preserved"},
    )
    session = ContextSession([row], agent)
    context: Any = SimpleNamespace(
        thread_id="thread",
        agent_id="agent",
        owner_id="owner",
        lease="lease",
        db=SimpleNamespace(sessions=lambda: session),
    )
    monkeypatch.setattr(skills, "require_lease", AsyncMock(return_value=run))
    first = await skills.read_skill_context(session, context, agent, load_tools())  # type: ignore[arg-type]
    assert "Original approved procedure." in first
    original_hash = run.model_metadata["skill_selection"]["skill_content_sha256"]["owner-guide"]
    # Simulate a restarted worker reading serialized metadata, with the catalog now updated.
    import json

    run.model_metadata = json.loads(json.dumps(run.model_metadata))
    row.payload = {
        **owner,
        "content": "Updated procedure must wait for a new Run.",
        "manifest": {**owner["manifest"], "version": "2.0.0"},
    }
    messages = [
        ModelMessage(role="system", content=first),
        ModelMessage(role="user", content="[skill:owner-guide]"),
    ]
    await skills.refresh_skill_context(context, load_tools(), messages)
    assert "Original approved procedure." in messages[0].content
    assert "Updated procedure" not in messages[0].content
    assert run.model_metadata["skill_selection"]["skill_versions"]["owner-guide"] == "1.0.0"
    assert (
        run.model_metadata["skill_selection"]["skill_content_sha256"]["owner-guide"]
        == original_hash
    )
    row.payload = {**row.payload, "enabled": False}
    await skills.refresh_skill_context(context, load_tools(), messages)
    assert 'id="owner-guide"' not in messages[0].content
    assert (
        run.model_metadata["skill_selection"]["rejected_skills"]["owner-guide"] == "skill_disabled"
    )
    assert "owner-guide" in run.model_metadata["skill_snapshot"]["skills"]
    assert run.model_metadata["provider"] == "preserved"
    row.payload = {**owner, "manifest": {**owner["manifest"], "source": "external"}}
    await skills.refresh_skill_context(context, load_tools(), messages)
    assert (
        run.model_metadata["skill_selection"]["rejected_skills"]["owner-guide"]
        == "skill_snapshot_source_changed"
    )
    assert 'id="owner-guide"' not in messages[0].content
    # Removed owner data stays removed, even while historical instructions are retained.
    session.rows = []
    await skills.refresh_skill_context(context, load_tools(), messages)
    assert 'id="owner-guide"' not in messages[0].content
    assert (
        run.model_metadata["skill_selection"]["rejected_skills"]["owner-guide"]
        == "skill_snapshot_unavailable"
    )
    # A fresh observe-only Run cannot load even a tool-free financial procedure.
    run.model_metadata = dict[str, Any](authority="observe_only")
    session.rows = [SimpleNamespace(payload=payload("owner-guide", risk_class="financial"))]
    await skills.refresh_skill_context(context, load_tools(), messages)
    assert (
        run.model_metadata["skill_selection"]["rejected_skills"]["owner-guide"]
        == "skill_scope_unavailable"
    )


@pytest.mark.parametrize("snapshot", [{"version": 99}, {"version": 1, "skills": {"bad": {}}}])
def test_unknown_or_corrupt_snapshot_blocks_instead_of_silent_upgrade(snapshot: Any) -> None:
    with pytest.raises(LonoraError, match="skill_snapshot_invalid"):
        read_snapshot(snapshot)


def test_snapshot_size_bound_does_not_silently_evict_versions() -> None:
    entries = {
        f"guide-{index}": {"manifest": payload(f"guide-{index}")["manifest"], "content": "guidance"}
        for index in range(33)
    }
    with pytest.raises(LonoraError, match="skill_snapshot_invalid"):
        read_snapshot({"version": 1, "skills": entries})
