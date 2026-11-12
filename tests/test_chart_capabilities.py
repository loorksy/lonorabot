"""Mandate 13.1: the supported chart timeframes and indicators reach the model.

``chart_capabilities`` was built but never called, so an agent learned the supported
indicators only from an ``unsupported_indicator`` refusal. ``capabilities_list`` now
carries them.
"""

from types import SimpleNamespace
from typing import Any, cast

import pytest
from lonora_core.chart_controller import TIMEFRAMES
from lonora_core.chart_indicator import SUPPORTED
from lonora_tools import capabilities


@pytest.mark.asyncio
async def test_capabilities_list_names_every_chart_timeframe_and_indicator(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def report(*_: Any, **__: Any) -> dict[str, Any]:
        return {"built_in": []}

    monkeypatch.setattr(capabilities, "capability_report", report)
    context = SimpleNamespace(
        db=None,
        owner_id="owner",
        workspace_access=None,
        searxng_url=None,
        browser_url=None,
        chart_visual=None,
        mcp_declarations=(),
        mcp_owner_trust=True,
    )
    listed = await capabilities.listing(cast(Any, context), {})
    assert listed["charts"] == {
        "timeframes": sorted(TIMEFRAMES),
        "indicators": sorted(SUPPORTED),
    }
    assert "1mn" in listed["charts"]["timeframes"] and "bollinger" in listed["charts"]["indicators"]
