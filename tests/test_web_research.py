"""Search readiness, bounded evidence and trusted endpoint propagation."""

from collections.abc import Callable
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace
from typing import Any, cast
from unittest.mock import AsyncMock, patch

import httpx
import pytest
from cryptography.fernet import Fernet
from lonora_api.env import Settings
from lonora_api.runtime import ApiRuntime
from lonora_contracts.runs import Lease
from lonora_core.user_error import LonoraError
from lonora_db.client import Database
from lonora_db.schema import Base, IntegrationRow, OwnerRow
from lonora_gateway.runtime import OwnerServices
from lonora_tools.context import ToolContext
from lonora_tools.search import SearchInput, search_payload, source_url, web_search
from lonora_worker.runtime import create_gateway
from pydantic import SecretStr, ValidationError


def client_factory(
    handler: Callable[[httpx.Request], httpx.Response],
) -> Callable[..., httpx.AsyncClient]:
    original = httpx.AsyncClient

    def create(**kwargs: Any) -> httpx.AsyncClient:
        return original(transport=httpx.MockTransport(handler), **kwargs)

    return create


def context(endpoint: str | None = "http://searxng:8080") -> ToolContext:
    # The SearXNG path must not require any owner integration, secret or DB query.
    return cast(ToolContext, SimpleNamespace(searxng_url=endpoint))


def configuration(**changes: object) -> Settings:
    return Settings.model_validate(
        {
            "database_url": "sqlite+aiosqlite:///:memory:",
            "encryption_key": SecretStr(Fernet.generate_key().decode()),
            "bootstrap_token": SecretStr("fixture-search-configuration-not-a-production-key"),
            "searxng_url": None,
            "browser_url": None,
            **changes,
        }
    )


def test_endpoint_is_deployment_configuration_not_a_model_argument() -> None:
    assert configuration().searxng_url is None
    assert configuration(searxng_url="http://searxng:8080/").searxng_url == "http://searxng:8080"
    for value in [
        "file:///etc/passwd",
        "https://key@service",
        "http://service/?q=x",
        "http://service/#x",
        "http://service:wrong",
    ]:
        with pytest.raises(ValidationError):
            configuration(searxng_url=value)
        with pytest.raises(ValidationError):
            configuration(browser_url=value)
    with pytest.raises(ValidationError):
        SearchInput.model_validate({"query": "example", "endpoint": "http://other-service"})


@pytest.mark.asyncio
async def test_searxng_search_is_keyless_bounded_deduplicated_and_attributed() -> None:
    requests: list[httpx.Request] = []
    items: list[Any] = [
        {
            "title": "Primary",
            "url": "https://docs.python.org/3/#section",
            "content": "Actual excerpt",
        },
        {"url": "https://docs.python.org/3/", "content": "duplicate"},
        {"url": "http://example.com/not-supported"},
        {"url": "https://127.0.0.1/private"},
        {"url": "https://user:password@example.com/"},
        {"url": "javascript:alert(1)"},
        "malformed result",
        *[
            {"title": "x" * 1000, "url": f"https://example.com/{index}", "content": "y" * 3000}
            for index in range(20)
        ],
    ]

    def respond(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        assert request.url.path == "/search"
        assert request.url.params["q"] == "Python توثيق"
        assert request.url.params["format"] == "json"
        assert "X-Subscription-Token" not in request.headers
        return httpx.Response(
            200, json={"results": items, "unresponsive_engines": [["one-engine", "timeout"]]}
        )

    with patch(
        "lonora_tools.search.httpx.AsyncClient",
        side_effect=client_factory(respond),
    ):
        result = await web_search(context(), {"query": "Python توثيق"})
    assert len(requests) == 1
    assert result["provider"] == "searxng" and result["observed_at"]
    assert result["partial"] is True
    assert len(result["sources"]) == 8
    assert result["sources"][0] == {
        "title": "Primary",
        "url": "https://docs.python.org/3/",
        "excerpt": "Actual excerpt",
    }
    assert all(
        len(item["title"]) <= 300 and len(item["excerpt"]) <= 1600 for item in result["sources"]
    )


@pytest.mark.asyncio
async def test_empty_search_is_distinct_from_failed_upstream_engines() -> None:
    with patch("lonora_tools.search.search_payload", AsyncMock(return_value={"results": []})):
        assert (await web_search(context(), {"query": "no matching result"}))["sources"] == []
    with patch(
        "lonora_tools.search.search_payload",
        AsyncMock(return_value={"results": [], "unresponsive_engines": [["engine", "CAPTCHA"]]}),
    ):
        with pytest.raises(LonoraError, match="research_provider_unavailable"):
            await web_search(context(), {"query": "upstream unavailable"})


@pytest.mark.parametrize(
    "failure, code",
    [
        (httpx.ReadTimeout("fixture"), "tool_read_timeout"),
        (httpx.ConnectError("fixture"), "tool_connection_failure"),
    ],
)
@pytest.mark.asyncio
async def test_search_network_errors_are_safe_recoverable_observations(
    failure: httpx.HTTPError, code: str
) -> None:
    def respond(_: httpx.Request) -> httpx.Response:
        raise failure

    with patch(
        "lonora_tools.search.httpx.AsyncClient",
        side_effect=client_factory(respond),
    ):
        with pytest.raises(LonoraError, match=code):
            await web_search(context(), {"query": "safe probe"})


@pytest.mark.parametrize(
    "status, body",
    [
        (302, b""),
        (403, b"forbidden"),
        (200, b"not JSON"),
        (200, b"[]"),
        (200, b"x" * (2 * 1024 * 1024 + 1)),
    ],
)
@pytest.mark.asyncio
async def test_provider_redirects_invalid_or_oversized_payloads_are_not_success(
    status: int, body: bytes
) -> None:
    with patch(
        "lonora_tools.search.httpx.AsyncClient",
        side_effect=client_factory(
            lambda _: httpx.Response(
                status, content=body, headers={"location": "http://other-service/"}
            )
        ),
    ):
        with pytest.raises(LonoraError, match="research_provider_unavailable"):
            await search_payload("http://searxng:8080/search", {"q": "test"})


@pytest.mark.parametrize("status", [429, 503])
@pytest.mark.asyncio
async def test_provider_outage_and_rate_limit_are_temporary(status: int) -> None:
    with patch(
        "lonora_tools.search.httpx.AsyncClient",
        side_effect=client_factory(lambda _: httpx.Response(status)),
    ):
        with pytest.raises(LonoraError, match="provider_temporarily_unavailable"):
            await search_payload("http://searxng:8080/search", {"q": "test"})


@pytest.mark.asyncio
async def test_unconfigured_search_stays_explicit_and_existing_brave_route_still_works() -> None:
    db = Database.connect("sqlite+aiosqlite:///:memory:")
    secret_read = AsyncMock(return_value="fixture-provider-key")
    tool_context = cast(
        ToolContext,
        SimpleNamespace(
            db=db,
            owner_id="fixture-owner",
            searxng_url=None,
            secrets=SimpleNamespace(read=secret_read),
        ),
    )
    try:
        async with db.engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)
        async with db.sessions() as session, session.begin():
            session.add(
                OwnerRow(
                    id="fixture-owner", email="fixture@example.test", password_hash="fixture-only"
                )
            )
        with pytest.raises(LonoraError, match="research_provider_not_configured"):
            await web_search(tool_context, {"query": "Python"})
        assert not secret_read.called
        async with db.sessions() as session, session.begin():
            session.add(
                IntegrationRow(
                    owner_id="fixture-owner",
                    payload={
                        "type": "brave_search",
                        "enabled": True,
                        "secret_id": "fixture-secret",
                    },
                )
            )

        def respond(request: httpx.Request) -> httpx.Response:
            assert str(request.url).startswith("https://api.search.brave.com/res/v1/web/search?")
            assert request.headers["X-Subscription-Token"] == "fixture-provider-key"
            return httpx.Response(
                200,
                json={
                    "web": {
                        "results": [
                            {
                                "title": "Python",
                                "url": "https://www.python.org/",
                                "description": "Official source",
                            }
                        ]
                    }
                },
            )

        with patch("lonora_tools.search.httpx.AsyncClient", side_effect=client_factory(respond)):
            result = await web_search(tool_context, {"query": "Python"})
        secret_read.assert_awaited_once_with("fixture-secret")
        assert result["provider"] == "brave"
        assert result["sources"][0]["excerpt"] == "Official source"
    finally:
        await db.close()


def test_search_evidence_rejects_unsafe_schemes_hosts_credentials_and_ports() -> None:
    for value in [
        None,
        "https://localhost/x",
        "https://sub.localhost/x",
        "https://[::1]/",
        "https://192.168.1.1/x",
        "https://example.com:8443/x",
        "https://example.com:bad/x",
        "https://key@example.com/x",
        " https://example.com/x",
        "https://example.com/\nx",
    ]:
        assert source_url(value) is None
    assert source_url("https://example.com/path#anchor") == "https://example.com/path"


@pytest.mark.asyncio
async def test_search_and_browser_config_reach_api_gateway_and_child_context(
    tmp_path: Path,
) -> None:
    settings = configuration(
        searxng_url="http://searxng:8080", browser_url="http://browser:8000", artifact_root=tmp_path
    )
    db, gateway = create_gateway(settings)
    api = ApiRuntime.create(settings)
    services = OwnerServices.create(
        db,
        "fixture-owner",
        settings.encryption_key.get_secret_value(),
        searxng_url=gateway.searxng_url,
        browser_url=gateway.browser_url,
    )
    try:
        for database in (db, api.db):
            async with database.engine.begin() as connection:
                await connection.run_sync(Base.metadata.create_all)
        assert gateway.searxng_url == settings.searxng_url
        assert gateway.browser_url == settings.browser_url
        owner = api.services("fixture-owner")
        assert owner.searxng_url == settings.searxng_url
        assert owner.browser_url == settings.browser_url
        tool_context = services.tool_context(
            "fixture-agent",
            "fixture-thread",
            Lease(run_id="fixture-run", owner="fixture-worker", fence=1),
            tmp_path,
        )
        for derived in (
            tool_context,
            tool_context.for_call("fixture-call"),
            replace(tool_context, depth=1),
        ):
            assert derived.searxng_url == settings.searxng_url
            assert derived.browser_url == settings.browser_url
    finally:
        await services.close()
        await api.close()
        await db.close()
