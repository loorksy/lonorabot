"""Strategy backtesting is excluded from Lonora (owner mandate section 5).

The SMA-cross research engine and its two Agent tools were removed. These checks keep
it from returning through the live catalog, the operating policy or the market
package, and prove that history written while it existed stays harmless: old tool
calls get the same outcomes as any unknown tool, and saved report attachments remain
ordinary, inert files.
"""

import asyncio
import importlib.util
import json
import os
import re
from dataclasses import replace
from datetime import timedelta
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any, cast
from unittest.mock import patch

import pytest
from lonora_adapter_kit.types import ModelMessage, ModelReply, ToolCall
from lonora_agent.skills.loader import resources_root
from lonora_agent.skills.system_policy import (
    DOMAIN_MARKER,
    apply_operating_policy,
    policy_bundle,
)
from lonora_contracts.domain import Contract
from lonora_core.user_error import LonoraError
from lonora_tools.base import Tool
from lonora_tools.context import ToolContext
from lonora_tools.loader import MODULES, load_tools
from lonora_tools.registry import BRIDGE_TOOLS, ToolRegistry

REMOVED_TOOLS = ("market_strategy_research", "market_research_history")
BACKTEST_TERMS = re.compile(
    r"backtest|walk.?forward|monte.?carlo|out.of.sample|strategy.research", re.I
)
# Exactly what the removed tool persisted on its report attachments.
LEGACY_RESEARCH_STATE: dict[str, Any] = {
    "research_result": True,
    "research_request_sha256": "0" * 64,
    "research_scope": {"account_id": "legacy-account", "symbol": "EURUSD"},
    "research_summary": {
        "mode": "historical_research",
        "execution_authorized": False,
        "artifact_id": "legacy",
        "symbol": "EURUSD",
        "timeframe": "1h",
        "observed_at": "2026-10-01T00:00:00+00:00",
        "dataset_sha256": "1" * 64,
        "result_sha256": "2" * 64,
        "engine_version": "sma-cross-v1",
        "confidence": "low",
    },
}


def test_backtesting_engine_and_tools_are_absent():
    assert importlib.util.find_spec("lonora_market.research") is None
    assert importlib.util.find_spec("lonora_tools.strategy_research") is None
    assert "strategy_research" not in MODULES
    registry = load_tools()
    for name in REMOVED_TOOLS:
        assert name not in registry.tools
    for tool in registry.tools.values():
        definition = tool.definition()
        assert not BACKTEST_TERMS.search(definition.name + " " + definition.description), tool.name
        assert not BACKTEST_TERMS.search(json.dumps(definition.parameters)), tool.name


def test_operating_policy_states_the_exclusion_and_routes_no_backtest_tool():
    manual = (resources_root() / "system/lonora.md").read_text()
    manifest = json.loads((resources_root() / "system/manifest.json").read_text())
    for name in REMOVED_TOOLS:
        assert name not in manual
        assert name not in manifest["tool_policies"]
        assert name not in policy_bundle().tool_policies
    sections = policy_bundle().sections
    intelligence = sections["intelligence"]
    assert "Strategy backtesting is excluded from Lonora" in intelligence
    assert "never require one before creating or changing a strategy" in intelligence
    # Legacy reports stay readable on request; only building, running or relying on one is out.
    assert "Do not build or run a historical strategy simulation" in intelligence
    assert "present an old one as validation or as a basis for authority" in intelligence
    assert "Reading an old saved report on request remains allowed" in intelligence
    assert "cite a historical strategy simulation" not in intelligence
    assert "must not become a strategy backtest" in sections["files"]
    # A backtest request usually starts with candles, which load only this chapter.
    assert "do not turn them into a strategy backtest" in sections["market"]
    assert manifest["tool_policies"]["market_candles"] == "market"
    # Every remaining mention in the shipped manual is the exclusion itself.
    for line in manual.splitlines():
        if BACKTEST_TERMS.search(line):
            assert "Lonora excludes" in line or "excluded from Lonora" in line, line
    # No other shipped resource (skills, playbooks, constitution, prompts, bootstrap,
    # references, schemas) may teach or mention backtesting at all.
    manual_path = (resources_root() / "system/lonora.md").resolve()
    scanned = 0
    for path in resources_root().rglob("*"):
        if not path.is_file() or path.resolve() == manual_path:
            continue
        scanned += 1
        assert not BACKTEST_TERMS.search(path.read_text(errors="replace")), path
    for folder in ("skills", "playbooks", "constitution", "prompts", "bootstrap"):
        assert any((resources_root() / folder).rglob("*.md")), folder
    assert scanned > 40


@pytest.mark.asyncio
async def test_the_registry_refuses_a_removed_tool_name_before_using_the_context():
    # Registry level only: no handler, broker or file access, so the context is never
    # used. The Run tool loop around it is covered by the PostgreSQL case below.
    registry = load_tools()
    context = cast(ToolContext, object())
    for name in REMOVED_TOOLS:
        with pytest.raises(LonoraError) as error:
            await registry.execute(ToolCall(id="legacy", name=name, arguments={}), context)
        assert error.value.code == "tool_call_target_unknown"


def test_old_history_with_a_removed_tool_call_loads_no_stale_guidance():
    request = ModelMessage(role="user", content="What did the old report say?")
    history = [
        request,
        ModelMessage(
            role="assistant",
            content="",
            tool_calls=[ToolCall(id="old", name="market_strategy_research", arguments={})],
        ),
        ModelMessage(role="tool", tool_call_id="old", content='{"mode":"historical_research"}'),
    ]
    result = apply_operating_policy(history, load_tools().definitions())
    assert not any(DOMAIN_MARKER in message.content for message in result)
    assert result[-3:] == history  # The recorded exchange itself is preserved unchanged.


@pytest.mark.asyncio
async def test_saved_research_report_attachments_stay_readable_and_inert():
    if not os.environ.get("LONORA_DATABASE_URL"):
        pytest.skip("Set an explicit disposable PostgreSQL *_test URL for integration checks.")
    from check_streaming import Fixture
    from lonora_db.schema import ArtifactRow
    from lonora_tools.artifacts import store_artifact

    fixture = await Fixture().open()
    original_root = fixture.settings.artifact_root
    try:
        with TemporaryDirectory(prefix="lonora-legacy-research-") as directory:
            fixture.settings.artifact_root = Path(directory)
            agent = await fixture.agent("Legacy research reader")
            thread = await fixture.conversation(agent)
            context = await fixture.lease(await fixture.run(agent, thread))
            content = json.dumps({"mode": "historical_research", "folds": []}).encode()
            # Written by the removed tool before its deletion; nothing reads these keys now.
            stored = await store_artifact(
                context.for_call("legacy-research"),
                "strategy-research.json",
                content,
                "application/json",
                receipt_state=LEGACY_RESEARCH_STATE,
            )
            artifact_id = stored["id"]
            async with fixture.runtime.db.sessions() as session:
                row = await session.get(ArtifactRow, artifact_id)
                assert row is not None and row.state["research_result"] is True

            listed = await fixture.client.get(
                "/api/artifacts", params={"agent_id": agent["id"], "thread_id": thread["id"]}
            )
            assert listed.status_code == 200
            assert artifact_id in {item["id"] for item in listed.json()}
            download = await fixture.client.get(f"/api/artifacts/{artifact_id}/file")
            assert download.status_code == 200 and download.content == content

            read = await load_tools().execute(
                ToolCall(
                    id="read-legacy", name="artifact_read", arguments={"artifact_id": artifact_id}
                ),
                context,
            )
            assert json.loads(read["content"]) == {"mode": "historical_research", "folds": []}
    finally:
        fixture.settings.artifact_root = original_root
        await fixture.close()


class _NoArguments(Contract):
    pass


@pytest.mark.asyncio
async def test_a_run_checkpointed_across_the_removal_gets_unknown_tool_outcomes():
    """A Run interrupted mid-tool-block by the upgrade, resumed on the new catalog.

    The call that was in flight is reported as tool_execution_uncertain, like any
    interrupted call to an unknown tool: the removed tools had no broker effect, but
    the loop cannot know that and conservatively refuses to replay it. The call
    that was still only pending reaches the registry and is refused as
    tool_call_target_unknown. Neither removed handler runs after the resume.
    """
    if not os.environ.get("LONORA_DATABASE_URL"):
        pytest.skip("Set an explicit disposable PostgreSQL *_test URL for integration checks.")
    from check_streaming import Fixture
    from lonora_agent.executor import execute_run
    from lonora_contracts.domain import utcnow
    from lonora_contracts.model_routing import ModelSelection
    from lonora_contracts.runs import Lease
    from lonora_db.runs import claim_next
    from lonora_db.schema import RunRow

    effects: list[str] = []

    async def interrupted(_: ToolContext, args: dict[str, Any]) -> dict[str, Any]:
        effects.append("market_strategy_research")
        raise asyncio.CancelledError()  # The old worker stops here during the upgrade.

    async def never_started(_: ToolContext, args: dict[str, Any]) -> dict[str, Any]:
        effects.append("market_research_history")
        return {}

    # The previous release's catalog, with read-only stand-ins for the removed tools.
    # ToolRegistry adds its own tool_environment and tool_call, so the loaded ones are
    # left out.
    previous_catalog = ToolRegistry(
        [
            *(tool for name, tool in load_tools().tools.items() if name not in BRIDGE_TOOLS),
            # The previous release executed every call serially (single inflight slot).
            Tool(
                "market_strategy_research",
                "Removed stand-in",
                _NoArguments,
                interrupted,
                True,
                parallel_safe=False,
            ),
            Tool(
                "market_research_history",
                "Removed stand-in",
                _NoArguments,
                never_started,
                True,
                parallel_safe=False,
            ),
        ]
    )
    calls = [
        ToolCall(id="legacy-inflight", name="market_strategy_research", arguments={}),
        ToolCall(id="legacy-pending", name="market_research_history", arguments={}),
    ]
    turns = 0
    observed: dict[str, dict[str, Any]] = {}

    async def model(_: Any, messages: list[ModelMessage], tools: Any, **kwargs: Any):
        nonlocal turns
        turns += 1
        selection = ModelSelection(provider="openai", model="scripted-removed-tools")
        if turns == 1:
            return ModelReply(tool_calls=calls, text=""), selection
        assert not {call.name for call in calls} & {tool.name for tool in tools}
        for message in messages:
            if message.role == "tool" and message.tool_call_id in {call.id for call in calls}:
                observed[message.tool_call_id] = json.loads(message.content)
        return ModelReply(tool_calls=[], text="Backtesting is excluded."), selection

    fixture = await Fixture().open()
    try:
        agent = await fixture.agent("Removed tool resume")
        thread = await fixture.conversation(agent)
        context = await fixture.lease(await fixture.run(agent, thread))
        with patch.object(context.router, "complete", model):
            with pytest.raises(asyncio.CancelledError):
                await execute_run(context, previous_catalog, 120, 5)
            async with fixture.runtime.db.sessions() as session, session.begin():
                row = await session.get(RunRow, context.lease.run_id, with_for_update=True)
                assert row is not None
                state = row.execution_state
                assert state["environment"]["inflight"]["call_id"] == "legacy-inflight"
                assert [call["id"] for call in state["pending"]] == [call.id for call in calls]
                row.lease_expires_at = utcnow() - timedelta(seconds=1)
            async with fixture.runtime.db.sessions() as session, session.begin():
                claimed = await claim_next(session, "upgraded-worker", 120)
                assert claimed is not None and claimed.id == context.lease.run_id
                lease = Lease(run_id=claimed.id, owner="upgraded-worker", fence=claimed.lease_fence)
            await execute_run(replace(context, lease=lease), load_tools(), 120, 5)
    finally:
        await fixture.close()

    assert turns == 2
    assert effects == ["market_strategy_research"]  # Only the old worker's attempt.
    inflight, pending = observed["legacy-inflight"], observed["legacy-pending"]
    assert inflight["ok"] is False and inflight["reason"] == "tool execution uncertain"
    assert inflight["recovery"]["safe_to_retry"] is False
    assert pending["ok"] is False and pending["reason"] == "tool call target unknown"
    assert pending["recovery"]["category"] == "not found"
