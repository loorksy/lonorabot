"""Calendar sources fail one by one: a broken source never hides a healthy one's events."""

import json
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from typing import Any, cast

import httpx
import pytest
from lonora_adapters.market import economic_calendar as adapter_module
from lonora_contracts.market import CalendarEvent
from lonora_core.user_error import LonoraError
from lonora_db.client import Database
from lonora_market.economic_calendar import CalendarSource, read_calendar

NOW = datetime.now(UTC)


def event_payload(identifier: str = "cpi") -> dict[str, Any]:
    return {
        "id": identifier,
        "name": "US CPI",
        "currency": "USD",
        "observed_at": NOW.isoformat(),
        "scheduled_at": (NOW + timedelta(hours=1)).isoformat(),
        "impact": "High",
        "source": "fixture",
    }


class Rows:
    def __init__(self, rows: list[SimpleNamespace]):
        self.rows = rows

    def all(self) -> list[SimpleNamespace]:
        return self.rows


class Session:
    def __init__(self, names: list[str]):
        self.names = names

    async def scalars(self, query: object) -> Rows:
        return Rows(
            [
                SimpleNamespace(
                    id="cal-" + name,
                    payload={
                        "type": "economic_calendar",
                        "enabled": True,
                        "name": name,
                        "url": "https://" + name + ".calendar.example/secret-token/events.json",
                    },
                )
                for name in self.names
            ]
        )


class FakeDatabase:
    def __init__(self, names: list[str]):
        self.names = names

    @asynccontextmanager
    async def sessions(self) -> AsyncGenerator[Session]:
        yield Session(self.names)


def database(*names: str) -> Database:
    return cast(Database, FakeDatabase(list(names)))


class Source:
    """An injected source: `down` raises the raw transport error, `ok` answers."""

    def __init__(self, url: str):
        self.url = url

    async def events(self) -> list[CalendarEvent]:
        if "//down." in self.url:
            raise httpx.ConnectError("[Errno 111] Connection refused: " + self.url)
        if "//garbled." in self.url:
            raise ValueError("Expecting value: line 1 column 1 (char 0)")
        if "//broken." in self.url:
            raise RuntimeError("unexpected " + self.url)
        return [CalendarEvent.model_validate(event_payload())]


def source(url: str) -> CalendarSource:
    return Source(url)


def by_name(sources: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    return {str(item["name"]): item for item in sources}


@pytest.mark.asyncio
async def test_any_source_exception_stays_with_that_source() -> None:
    sources, events = await read_calendar(
        database("down", "garbled", "broken", "ok"), "owner", source=source
    )
    status = by_name(sources)
    assert status["ok"]["status"] == "ok" and status["ok"]["events"] == 1
    assert [(integration, event.id) for integration, event in events] == [("cal-ok", "cpi")]
    assert status["down"] == {
        "integration_id": "cal-down",
        "name": "down",
        "status": "unavailable",
        "reason": "calendar_source_failed",
    }
    assert status["garbled"]["reason"] == "calendar_response_invalid"
    assert status["broken"]["reason"] == "calendar_source_failed"
    assert "secret-token" not in str(sources)


@pytest.mark.asyncio
async def test_real_adapter_turns_transport_and_payload_failures_into_codes(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        host = request.url.host.split(".")[0]
        if host == "down":
            raise httpx.ConnectError("[Errno 111] Connection refused", request=request)
        if host == "slow":
            raise httpx.ReadTimeout("timed out", request=request)
        if host == "html":
            return httpx.Response(200, text="<html>Maintenance</html>")
        if host == "malformed":
            return httpx.Response(200, json=[event_payload(), {"id": "no-fields"}])
        if host == "object":
            return httpx.Response(200, json={"events": []})
        if host == "error":
            return httpx.Response(503, text="unavailable")
        return httpx.Response(200, content=json.dumps([event_payload()]).encode())

    real_client = httpx.AsyncClient

    def client(**options: Any) -> httpx.AsyncClient:
        return real_client(transport=httpx.MockTransport(handler), **options)

    async def public(url: str) -> str:
        return url

    monkeypatch.setattr(adapter_module, "validate_public_url", public)
    monkeypatch.setattr(adapter_module.httpx, "AsyncClient", client)
    names = ("down", "slow", "html", "malformed", "object", "error", "ok")
    sources, events = await read_calendar(database(*names), "owner")
    status = by_name(sources)
    assert {name: status[name].get("reason") for name in names} == {
        "down": "calendar_source_unavailable",
        "slow": "calendar_source_timeout",
        "html": "calendar_response_invalid",
        "malformed": "calendar_response_invalid",
        "object": "calendar_response_invalid",
        "error": "calendar_source_unavailable",
        "ok": None,
    }
    assert status["ok"]["status"] == "ok"
    assert [event.id for _, event in events] == ["cpi"]
    with pytest.raises(LonoraError) as error:
        await adapter_module.EconomicCalendarAdapter("https://down.calendar.example/x").events()
    assert error.value.code == "calendar_source_unavailable"
    assert error.value.__cause__ is None and error.value.__suppress_context__
