"""Read preparation uses one current runtime lease, not repeat chart creation."""

from typing import Any, cast
from unittest.mock import AsyncMock

import pytest
from lonora_charts import state
from lonora_contracts.runs import Lease


@pytest.mark.asyncio
@pytest.mark.parametrize("code", [None, "symbol_not_found", "broker_connection_unavailable"])
async def test_ready_and_failed_evidence_do_not_silently_refetch(
    monkeypatch: pytest.MonkeyPatch, code: str | None
) -> None:
    saved: dict[str, Any] = {
        "chart": {"version": 1},
        "scene": {"status": "ready"} if code is None else None,
    }
    if code:
        saved["code"] = code
    loader, refresh = AsyncMock(return_value=saved), AsyncMock()
    monkeypatch.setattr(state, "inspect_chart", loader)
    monkeypatch.setattr(state, "refresh_chart", refresh)
    lease = Lease(run_id="run", owner="worker", fence=1)
    db, brokers = cast(Any, object()), cast(Any, object())
    result = await state.prepare_chart_scene(db, brokers, "owner", "chart", lease)
    assert result == saved
    refresh.assert_not_awaited()
    loader.assert_awaited_once()


@pytest.mark.asyncio
@pytest.mark.parametrize("busy", [False, True])
async def test_initializing_configuration_uses_one_runtime_attempt(
    monkeypatch: pytest.MonkeyPatch, busy: bool
) -> None:
    initial = {"scene": None, "code": "chart_initializing"}
    latest = initial if busy else {"scene": {"status": "ready", "revision": 2}}
    loader, refresh = AsyncMock(side_effect=[initial, latest]), AsyncMock(return_value=not busy)
    monkeypatch.setattr(state, "inspect_chart", loader)
    monkeypatch.setattr(state, "refresh_chart", refresh)
    lease = Lease(run_id="run", owner="worker", fence=2)
    db, brokers = cast(Any, object()), cast(Any, object())
    result = await state.prepare_chart_scene(db, brokers, "owner", "chart", lease)
    assert result == latest and loader.await_count == 2
    refresh.assert_awaited_once()
    assert refresh.await_args is not None
    assert refresh.await_args.args[:4] == (db, brokers, "owner", "chart")
    assert refresh.await_args.args[5] is lease and refresh.await_args.kwargs == {"force": True}
