"""Strategy backtesting is excluded from Lonora (owner mandate section 5).

The SMA-cross research engine and its two Agent tools were removed. These checks keep
it from returning through the live catalog, the operating policy or the market
package, and prove that history written while it existed stays harmless: old tool
calls are refused like any unknown tool, and saved report attachments remain
ordinary, inert files.
"""

import importlib.util
import json
import os
import re
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any, cast

import pytest
from lonora_adapter_kit.types import ModelMessage, ToolCall
from lonora_agent.skills.loader import resources_root
from lonora_agent.skills.system_policy import (
    DOMAIN_MARKER,
    apply_operating_policy,
    policy_bundle,
)
from lonora_core.user_error import LonoraError
from lonora_tools.context import ToolContext
from lonora_tools.loader import MODULES, load_tools

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
    intelligence = policy_bundle().sections["intelligence"]
    assert "Strategy backtesting is excluded from Lonora" in intelligence
    assert "never require one before creating or changing a strategy" in intelligence
    assert "must not become a strategy backtest" in policy_bundle().sections["files"]
    skills = resources_root() / "skills"
    for path in skills.rglob("*"):
        if path.is_file() and path.suffix in {".md", ".json"}:
            assert not re.search(r"backtest|strategy_research", path.read_text(), re.I), path


@pytest.mark.asyncio
async def test_a_checkpointed_call_to_a_removed_tool_is_refused_without_side_effects():
    registry = load_tools()
    # Refused before any database, broker or file access: the context is never used.
    context = cast(ToolContext, object())
    for name in REMOVED_TOOLS:
        with pytest.raises(LonoraError) as error:
            await registry.execute(ToolCall(id="legacy", name=name, arguments={}), context)
        assert error.value.code == "tool_not_allowed"


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
