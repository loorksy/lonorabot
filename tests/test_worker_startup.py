"""Cold offline encoding setup precedes conversation readiness."""

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from lonora_worker import main


@pytest.mark.asyncio
async def test_tokenizer_setup_finishes_before_the_gateway_accepts_work(
    monkeypatch: pytest.MonkeyPatch,
):
    warmed: list[str] = []

    def warm(name: str):
        warmed.append(name)

    async def serve():
        # Starting foreground workers before either cold encoder is loaded
        # would move that work back onto the first owner's request.
        assert warmed == ["cl100k_base", "o200k_base"]

    db = SimpleNamespace(close=AsyncMock())
    gateway = SimpleNamespace(serve=serve, request_stop=lambda: None)

    def ignore(_value: object) -> None:
        return None

    def create(_settings: object) -> tuple[SimpleNamespace, SimpleNamespace]:
        return db, gateway

    monkeypatch.setattr(main, "get_settings", lambda: SimpleNamespace(log_level="WARNING"))
    monkeypatch.setattr(main, "configure_logging", ignore)
    monkeypatch.setattr(main, "install_signals", ignore)
    monkeypatch.setattr(main, "create_gateway", create)
    monkeypatch.setattr(main, "cached_encoding", warm)
    await main.serve()
    db.close.assert_awaited_once()
