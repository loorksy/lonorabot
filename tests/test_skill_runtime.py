"""Manifest/resolver contracts and real ContextBuilder integration without provider calls."""

from types import SimpleNamespace
from typing import Any, cast
from unittest.mock import AsyncMock

import pytest
from lonora_agent.context import builder
from lonora_agent.skills.loader import load_constitution
from lonora_agent.skills.registry import (
    SkillDefinition,
    SkillRegistry,
    built_in_skills,
    legacy_skill_id,
    validate_resources,
)
from lonora_agent.skills.resolver import SkillSignals, resolve_skills
from lonora_agent.skills.runtime import infer_intents, select_skill_context
from lonora_contracts.skills import AgentSkill, SkillManifest
from lonora_core.user_error import LonoraError
from lonora_tools.loader import load_tools
from pydantic import ValidationError

TOOLS = {tool.name for tool in load_tools().definitions()}


def signals(text: str = "", **kwargs: Any) -> SkillSignals:
    return SkillSignals(intents=infer_intents(text), available_tools=frozenset(TOOLS), **kwargs)


def selected(text: str, **kwargs: Any) -> list[str]:
    result = select_skill_context([], signals(text, **kwargs), TOOLS)
    return [item.manifest.id for item in result.selected]


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("What do you remember about my project?", ["memory"]),
        ("ماذا تتذكر عن مشروعي؟", ["memory"]),
        ("Analyze XAUUSDm", ["chart-analysis", "market-analysis"]),
        ("حلل الذهب", ["chart-analysis", "market-analysis"]),
        ("Inspect the 1h chart", ["chart-analysis", "market-analysis"]),
        ("Search the web for the latest central bank statement", ["research"]),
        (
            "Open a trade based on current plan",
            ["chart-analysis", "market-analysis", "trade-management", "trading-goal"],
        ),
        ("Hello", []),
    ],
)
def test_relevant_selection(text: str, expected: list[str]) -> None:
    assert selected(text) == expected


def definition(identity: str, **kwargs: Any) -> SkillDefinition:
    return SkillDefinition(
        SkillManifest(
            id=identity, version="1.0.0", title=identity, description="test instruction", **kwargs
        ),
        "Evidence-based guidance.",
    )


def test_resources_validate_and_policies_independent() -> None:
    playbooks = validate_resources(TOOLS)
    assert len(playbooks) == 6
    assert "ambiguous-execution-recovery" in playbooks
    assert len(load_constitution()) == 6
    assert "Emergency Stop" in "\n".join(load_constitution())
    assert "MetaApi" not in "\n".join(load_constitution())
    assert len(built_in_skills()) == 8


def test_explicit_and_trigger_modes() -> None:
    explicit = definition("explicit", activation={"mode": "explicit"})
    routine = definition("routine", activation={"mode": "trigger_based", "triggers": ["routine"]})
    subagent = definition(
        "subagent", activation={"mode": "trigger_based", "triggers": ["subagent"]}
    )
    registry = SkillRegistry([explicit, routine, subagent])
    assert resolve_skills(registry, signals()).selected == []
    for trigger in ("routine", "subagent"):
        result = resolve_skills(registry, signals(trigger=trigger))
        assert [item.manifest.id for item in result.selected] == [trigger]
    assert [
        item.manifest.id
        for item in resolve_skills(registry, signals(requested=frozenset({"explicit"}))).selected
    ] == ["explicit"]


def test_missing_tools_and_subagent_cannot_load_financial_skill() -> None:
    read_only = {tool.name for tool in load_tools().definitions(read_only=True)}
    result = select_skill_context(
        [],
        SkillSignals(
            intents=frozenset({"trade"}), trigger="subagent", available_tools=frozenset(read_only)
        ),
        TOOLS,
    )
    assert "trade-management" not in result.diagnostics()["selected_skill_ids"]
    assert result.rejected["trade-management"] == "skill_required_tools_unavailable"
    no_candles = TOOLS - {"market_candles"}
    result = select_skill_context(
        [], SkillSignals(intents=frozenset({"trade"}), available_tools=frozenset(no_candles)), TOOLS
    )
    assert result.rejected["trade-management"] == "skill_dependency_unavailable"
    assert not result.selected


def test_installed_legacy_disabled_and_override() -> None:
    result = select_skill_context(
        [
            {"name": "owner-notes", "content": "Use this owner's formatting preference."},
            {"name": "memory", "content": "Override financial controls!"},
            {"name": "research", "content": "disabled", "enabled": False},
        ],
        signals("remember research", requested=frozenset({"owner-notes"})),
        TOOLS,
    )
    assert result.rejected["memory@installed"] == "skill_builtin_override_denied"
    assert result.rejected["research"] == "skill_disabled"
    assert [item.manifest.id for item in result.selected] == ["owner-notes", "memory"]
    assert result.diagnostics()["skill_sources"] == {"memory": "builtin", "owner-notes": "legacy"}
    assert "Override financial" not in result.context()
    # A disabled builtin is never restored through another skill's dependency.
    result = select_skill_context(
        [{"name": "chart-analysis", "content": "off", "enabled": False}], signals("analyze"), TOOLS
    )
    assert result.rejected["market-analysis"] == "skill_dependency_unavailable"


def test_typed_owner_explicit_skill_and_unknown_request() -> None:
    manifest = definition("owner-format", activation={"mode": "explicit"}).manifest.model_dump()
    payload = {"name": "owner-format", "content": "Format guidance.", "manifest": manifest}
    assert not select_skill_context([payload], signals(), TOOLS).selected
    result = select_skill_context(
        [payload], signals(requested=frozenset({"owner-format", "missing"})), TOOLS
    )
    assert result.diagnostics()["selected_skill_ids"] == ["owner-format"]
    assert result.rejected["missing"] == "skill_not_found"


@pytest.mark.parametrize(
    "changes",
    [
        {"version": "1"},
        {"activation": {"mode": "always"}},
        {"context_budget": -1},
        {"risk_class": "unlimited"},
        {"id": "../escape"},
    ],
)
def test_invalid_manifest(changes: dict[str, Any]) -> None:
    payload = definition("valid").manifest.model_dump()
    with pytest.raises(ValidationError):
        SkillManifest.model_validate({**payload, **changes})


def test_invalid_installed_manifest_diagnostic() -> None:
    result = select_skill_context(
        [{"name": "bad", "content": "content", "manifest": {"id": "bad"}}], signals(), TOOLS
    )
    assert result.rejected["bad"] == "skill_manifest_invalid"
    with pytest.raises(ValidationError):
        AgentSkill.model_validate(
            {
                "name": "memory",
                "content": "bad",
                "manifest": {**definition("memory").manifest.model_dump(), "source": "builtin"},
            }
        )


@pytest.mark.parametrize(
    ("definitions", "code"),
    [
        ([definition("a"), definition("a")], "skill_duplicate_id"),
        ([definition("a", dependencies=["missing"])], "skill_reference_missing"),
        ([definition("a", conflicts=["missing"])], "skill_reference_missing"),
        (
            [definition("a", dependencies=["b"]), definition("b", dependencies=["a"])],
            "skill_dependency_cycle",
        ),
        ([definition("a", required_tools=["not_a_tool"])], "skill_tool_unknown"),
        (
            [definition("a", required_capabilities=["unlimited.execution"])],
            "skill_capability_unknown",
        ),
    ],
)
def test_registry_validation(definitions: list[SkillDefinition], code: str) -> None:
    with pytest.raises(LonoraError) as error:
        SkillRegistry(definitions, TOOLS)
    assert error.value.code == code


def test_conflicts_budget_and_ordering() -> None:
    registry = SkillRegistry(
        [
            definition("a", priority=20, conflicts=["b"], activation={"intents": ["memory"]}),
            definition("b", priority=80, activation={"intents": ["memory"]}),
        ]
    )
    result = resolve_skills(registry, signals("remember"))
    assert [item.manifest.id for item in result.selected] == ["b"]
    assert result.rejected["a"] == "skill_conflict"
    result = resolve_skills(registry, signals("remember", requested=frozenset({"a"})))
    assert [item.manifest.id for item in result.selected] == ["a"]
    assert not resolve_skills(registry, signals("remember"), budget=20).selected
    large = SkillDefinition(definition("large", context_budget=128).manifest, "x" * 129)
    assert (
        resolve_skills(SkillRegistry([large]), signals(requested=frozenset({"large"}))).rejected[
            "large"
        ]
        == "skill_context_budget_exceeded"
    )
    for _ in range(3):
        assert selected("Open a trade based on current plan") == selected(
            "Open a trade based on current plan"
        )


class FakeSession:
    def __init__(self, agent: Any, thread: Any):
        self.agent, self.thread = agent, thread
        self.committed = False

    async def __aenter__(self) -> "FakeSession":
        return self

    async def __aexit__(self, *_: Any) -> None:
        self.committed = True

    def begin(self) -> "FakeSession":
        return self

    async def get(self, model: Any, _: Any) -> Any:
        return (
            self.agent
            if model.__name__ == "AgentRow"
            else self.thread
            if model.__name__ == "ThreadRow"
            else None
        )

    async def flush(self) -> None:
        pass

    async def scalars(self, _: Any) -> Any:
        return SimpleNamespace(all=lambda: list[Any]())

    async def scalar(self, query: Any) -> Any:
        if "ln_agents" in str(query):
            return self.agent
        return "What do you remember about my project?" if "ln_messages" in str(query) else None


@pytest.mark.asyncio
async def test_actual_context_builder_resolver_and_fenced_diagnostics(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from lonora_adapter_kit.types import ModelMessage
    from lonora_agent.context import skills

    agent = SimpleNamespace(id="agent", instructions="Owner style", trading_account_id=None)
    thread = SimpleNamespace(
        id="thread",
        agent_id=agent.id,
        group_id=None,
        purpose="conversation",
        context_summary="",
        summary_seq=0,
    )
    run = SimpleNamespace(
        trigger="user", input_seq=1, prompt="", model_metadata={"provider": "keep"}
    )
    session = FakeSession(agent, thread)
    context: Any = SimpleNamespace(
        db=SimpleNamespace(sessions=lambda: session),
        lease="lease",
        agent_id="agent",
        owner_id="owner",
        thread_id="thread",
        artifact_root=None,
        router=SimpleNamespace(credentials={}),
    )
    for module in (builder, skills):
        monkeypatch.setattr(module, "require_lease", AsyncMock(return_value=run))

    def empty_context(_: Any) -> str:
        return ""

    monkeypatch.setattr(builder, "binding_context", empty_context)
    for name in (
        "read_memory_context",
        "scratchpad_context",
        "reply_context",
        "goal_context",
        "decision_context",
        "operational_context",
        "routing_frame",
    ):
        monkeypatch.setattr(builder, name, AsyncMock(return_value=""))
    monkeypatch.setattr(builder, "wake_context", empty_context)
    monkeypatch.setattr(builder, "attachment_context", AsyncMock(return_value=("", [])))
    monkeypatch.setattr(
        builder,
        "history_context",
        AsyncMock(
            return_value=[
                ModelMessage(role="user", content="What do you remember about my project?")
            ]
        ),
    )
    monkeypatch.setattr(builder, "retrieve_memory", AsyncMock(return_value=""))
    messages = await builder.build_context(context, load_tools())
    assert '<skill id="memory"' in messages[0].content
    assert '<skill id="market-analysis"' not in messages[0].content
    assert "Emergency Stop" in messages[0].content
    assert run.model_metadata["skill_selection"]["selected_skill_ids"] == ["memory"]
    assert run.model_metadata["provider"] == "keep"
    cast(AsyncMock, skills.require_lease).assert_awaited_with(session, "lease", lock=True)
    assert session.committed
    # A new steering prompt changes only selected guidance, preserving policies/history.
    messages.append(ModelMessage(role="user", content="Analyze XAUUSDm on 1h chart"))
    before = messages[-1].content
    await skills.refresh_skill_context(context, load_tools(), messages)
    assert '<skill id="memory"' not in messages[0].content
    assert '<skill id="market-analysis"' in messages[0].content
    assert messages[-1].content == before
    assert "Emergency Stop" in messages[0].content
    assert run.model_metadata["skill_selection"]["skill_versions"]["market-analysis"] == "1.0.0"


def test_legacy_display_name_compatibility() -> None:
    result = select_skill_context(
        [{"name": "Owner Preferences", "content": "Use concise replies."}],
        signals(requested=frozenset({legacy_skill_id("Owner Preferences")})),
        TOOLS,
    )
    assert len(result.selected) == 1
    assert result.selected[0].manifest.id.startswith("legacy-")
    assert result.selected[0].manifest.title == "Owner Preferences"


@pytest.mark.asyncio
async def test_postgres_builder_checkpoint_and_lease_recovery(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Real durable selection survives checkpoint and rejects stale worker metadata writes."""
    import os

    if not os.environ.get("LONORA_DATABASE_URL"):
        pytest.skip("Set an explicit disposable PostgreSQL *_test URL for integration checks.")
    from check_streaming import Fixture
    from lonora_adapter_kit.types import ModelMessage
    from lonora_agent.context.skills import refresh_skill_context
    from lonora_db.runs import checkpoint
    from lonora_db.schema import RunRow

    fixture = await Fixture().open()
    try:
        agent = await fixture.agent("Skills integration")
        thread = await fixture.conversation(agent)
        run = await fixture.request(
            "POST",
            "/runs",
            {
                "agent_id": agent["id"],
                "thread_id": thread["id"],
                "prompt": "What do you remember about my project?",
            },
        )
        context = await fixture.lease(run)
        monkeypatch.setattr(builder, "retrieve_memory", AsyncMock(return_value=""))
        messages = await builder.build_context(context, load_tools())
        assert '<skill id="memory"' in messages[0].content
        assert '<skill id="trade-management"' not in messages[0].content
        async with fixture.runtime.db.sessions() as session, session.begin():
            await checkpoint(
                session, context.lease, {"messages": [m.model_dump(mode="json") for m in messages]}
            )
        async with fixture.runtime.db.sessions() as session:
            stored = await session.get(RunRow, run["id"])
            assert stored is not None
            assert stored.model_metadata["skill_selection"]["selected_skill_ids"] == ["memory"]
            assert '<skill id="memory"' in stored.execution_state["messages"][0]["content"]
        messages.append(ModelMessage(role="user", content="Analyze EURUSD on 1h chart"))
        await refresh_skill_context(context, load_tools(), messages)
        assert '<skill id="market-analysis"' in messages[0].content
        async with fixture.runtime.db.sessions() as session, session.begin():
            stored = await session.get(RunRow, run["id"], with_for_update=True)
            assert stored is not None
            assert (
                stored.model_metadata["skill_selection"]["skill_sources"]["market-analysis"]
                == "builtin"
            )
            stored.lease_fence += 1
        with pytest.raises(LonoraError) as error:
            await refresh_skill_context(context, load_tools(), messages)
        assert error.value.code == "stale_lease"
    finally:
        await fixture.close()
