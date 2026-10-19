"""Chart observations share the existing Agent host and cannot block broker cleanup."""

from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace
from typing import cast
from unittest.mock import AsyncMock

import pytest
from cryptography.fernet import Fernet
from lonora_adapters.brokers.base import BrokerManager
from lonora_api.env import Settings
from lonora_api.runtime import ApiRuntime
from lonora_charts.visual import ChartVisualRuntime
from lonora_contracts.runs import Lease
from lonora_db.schema import Base
from lonora_gateway.runtime import OwnerServices
from lonora_market.runtime import MarketRuntime
from lonora_worker.runtime import create_gateway
from pydantic import SecretStr


@pytest.mark.asyncio
async def test_configured_visual_runtime_reaches_the_same_agent_context(tmp_path: Path) -> None:
    settings = Settings(
        database_url="sqlite+aiosqlite:///:memory:",
        encryption_key=SecretStr(Fernet.generate_key().decode()),
        bootstrap_token=SecretStr("visual-host-only-bootstrap-2026"),
        chart_renderer_url="http://localhost:8000/charts/render",
        artifact_root=tmp_path,
    )
    db, gateway = create_gateway(settings)
    api = ApiRuntime.create(settings)
    try:
        for database in (db, api.db):
            async with database.engine.begin() as connection:
                await connection.run_sync(Base.metadata.create_all)
        assert gateway.chart_visual is not None
        services = OwnerServices.create(
            db,
            "test-owner",
            settings.encryption_key.get_secret_value(),
            chart_visual=gateway.chart_visual,
        )
        ctx = services.tool_context(
            "test-agent", "test-thread", Lease(run_id="test-run", owner="worker", fence=1), tmp_path
        )
        assert ctx.chart_visual is gateway.chart_visual
        assert ctx.for_call("call").chart_visual is ctx.chart_visual
        assert replace(ctx, depth=1).chart_visual is ctx.chart_visual
        assert api.services("test-owner").chart_visual is not None
        assert api.services("test-owner") is api.services("test-owner")
        await services.close()
        await gateway.chart_visual.close()  # Shared shutdown is idempotent.
    finally:
        await api.close()
        await db.close()


@pytest.mark.asyncio
async def test_visual_close_failure_does_not_leave_market_or_broker_running() -> None:
    visual = AsyncMock(side_effect=RuntimeError("scripted visual shutdown failure"))
    market = AsyncMock()
    brokers = AsyncMock()
    services = cast(
        OwnerServices,
        SimpleNamespace(
            chart_visual=cast(ChartVisualRuntime, SimpleNamespace(close=visual)),
            market=cast(MarketRuntime, SimpleNamespace(close=market)),
            brokers=cast(BrokerManager, SimpleNamespace(close=brokers)),
        ),
    )
    with pytest.raises(RuntimeError, match="scripted visual shutdown failure"):
        await OwnerServices.close(services)
    market.assert_awaited_once()
    brokers.assert_awaited_once()
