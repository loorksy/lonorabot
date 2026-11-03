"""Real Chromium executes controlled pages through the guarded request boundary.

These tests replace public HTTP responses, not the browser or JavaScript engine.
They establish routing/isolation behavior; live source availability is checked
separately against the deployed research service.
"""

import asyncio
import json
import socket
from collections.abc import AsyncGenerator, Callable
from types import SimpleNamespace
from typing import Any, cast
from unittest.mock import AsyncMock, patch

import httpx
import pytest
import pytest_asyncio
from lonora_core.user_error import LonoraError
from lonora_security.public_http import PublicResponse, public_address
from lonora_tools import browser_service
from lonora_tools.browser import BrowseInput, browse
from lonora_tools.context import ToolContext
from playwright.async_api import Browser, async_playwright
from pydantic import ValidationError


@pytest_asyncio.fixture
async def chromium() -> AsyncGenerator[Browser]:
    async with async_playwright() as playwright:
        browser = await playwright.chromium.launch(
            executable_path="/usr/bin/chromium",
            chromium_sandbox=False,
            args=[
                "--proxy-server=http://127.0.0.1:9",
                "--proxy-bypass-list=<-loopback>",
                "--disable-background-networking",
            ],
        )
        try:
            yield browser
        finally:
            await browser.close()


def dns(host: str, *_: Any, **__: Any) -> list[Any]:
    return [
        (
            socket.AF_INET,
            socket.SOCK_STREAM,
            6,
            "",
            ("127.0.0.1" if host == "127.0.0.1" else "93.184.216.34", 443),
        )
    ]


def document(text: str, **headers: str) -> PublicResponse:
    return PublicResponse(200, {"content-type": "text/html", **headers}, text.encode())


@pytest.mark.asyncio
async def test_chromium_renders_javascript_fills_clicks_and_keeps_actual_redirect_source(
    chromium: Browser,
) -> None:
    requests: list[str] = []
    pages = {
        "/": document(
            '<title>Research</title><script src="/entry.js"></script>'
            '<input id="name" aria-label="Name"><button id="show">Show</button>'
            '<a id="next" href="/redirect">Read next</a><p id="result">Waiting</p>'
        ),
        "/entry.js": PublicResponse(302, {"location": "/actual.js"}, b""),
        "/actual.js": PublicResponse(
            200,
            {"content-type": "application/javascript"},
            b'window.addEventListener("DOMContentLoaded",()=>{document.querySelector("#result").textContent="Rendered JS";document.querySelector("#show").onclick=()=>document.querySelector("#result").textContent="Hello "+document.querySelector("#name").value;});',
        ),
        "/redirect": PublicResponse(302, {"location": "/final"}, b""),
        "/final": document("<title>Final page</title><p>Actual final source</p>"),
    }

    async def read(url: str, _: str = "GET") -> PublicResponse:
        await public_address(url)
        requests.append(url)
        return pages[httpx.URL(url).path]

    with (
        patch("lonora_security.public_http.socket.getaddrinfo", side_effect=dns),
        patch.object(browser_service, "public_get", side_effect=read),
    ):
        first = await browser_service.render(chromium, BrowseInput(url="https://example.test/"))
        assert "Rendered JS" in first["untrusted_content"]
        assert first["controls"][0]["label"] == "Name"
        changed = await browser_service.render(
            chromium,
            BrowseInput.model_validate(
                {
                    "url": "https://example.test/",
                    "actions": [
                        {"action": "fill", "selector": "#name", "text": "Lonora"},
                        {"action": "click", "selector": "#show"},
                    ],
                }
            ),
        )
        assert "Hello Lonora" in changed["untrusted_content"]
        final = await browser_service.render(
            chromium,
            BrowseInput.model_validate(
                {
                    "url": "https://example.test/",
                    "actions": [{"action": "click", "selector": "#next"}],
                }
            ),
        )
        assert final["source"] == "https://example.test/final"
        assert final["title"] == "Final page"
        assert "Actual final source" in final["untrusted_content"]
        assert "https://example.test/actual.js" in requests
    assert not chromium.contexts


@pytest.mark.asyncio
async def test_private_frame_and_subresource_post_websocket_do_not_escape_or_poison_main_page(
    chromium: Browser,
) -> None:
    received: list[str] = []
    html = """<title>Public</title><h1>Readable public page</h1>
    <iframe src="https://127.0.0.1/private"></iframe>
    <script>
      fetch('https://127.0.0.1/private-api').catch(()=>{});
      fetch('/submit',{method:'POST',body:'must-not-send'}).catch(()=>{});
      new WebSocket('wss://example.test/socket');
    </script>"""

    async def read(url: str, method: str = "GET") -> PublicResponse:
        await public_address(url)
        received.append(url)
        assert method in {"GET", "HEAD"}
        return document(html)

    with (
        patch("lonora_security.public_http.socket.getaddrinfo", side_effect=dns),
        patch.object(browser_service, "public_get", side_effect=read),
    ):
        result = await browser_service.render(chromium, BrowseInput(url="https://example.test/"))
    assert "Readable public page" in result["untrusted_content"]
    assert result["blocked_requests"] >= 3
    assert received == ["https://example.test/"]
    assert not chromium.contexts


@pytest.mark.asyncio
async def test_browser_rejects_private_redirect_and_closes_context(chromium: Browser) -> None:
    with (
        patch("lonora_security.public_http.socket.getaddrinfo", side_effect=dns),
        patch.object(
            browser_service,
            "public_get",
            AsyncMock(return_value=PublicResponse(302, {"location": "https://127.0.0.1/"}, b"")),
        ) as read,
    ):
        with pytest.raises(LonoraError, match="private_remote_address_forbidden"):
            await browser_service.render(chromium, BrowseInput(url="https://example.test/"))
        assert read.await_count == 1
    assert not chromium.contexts


@pytest.mark.asyncio
async def test_redirect_loops_and_failed_actions_terminate_and_close_context(
    chromium: Browser,
) -> None:
    async def redirect(url: str, _: str = "GET") -> PublicResponse:
        return PublicResponse(302, {"location": "/loop"}, b"")

    with (
        patch("lonora_security.public_http.socket.getaddrinfo", side_effect=dns),
        patch.object(browser_service, "public_get", side_effect=redirect) as read,
    ):
        with pytest.raises(LonoraError, match="browser_source_unavailable"):
            await browser_service.render(chromium, BrowseInput(url="https://example.test/"))
        assert read.call_count <= browser_service.MAX_REDIRECTS + 1
    assert not chromium.contexts


@pytest.mark.asyncio
async def test_cancellation_stops_pending_resource_and_closes_context(chromium: Browser) -> None:
    entered, stopped = asyncio.Event(), asyncio.Event()

    async def pending(_: str, __: str = "GET") -> PublicResponse:
        entered.set()
        try:
            await asyncio.Future()
        finally:
            stopped.set()
        raise AssertionError("unreachable")

    with (
        patch("lonora_security.public_http.socket.getaddrinfo", side_effect=dns),
        patch.object(browser_service, "public_get", side_effect=pending),
    ):
        task = asyncio.create_task(
            browser_service.render(chromium, BrowseInput(url="https://example.test/"))
        )
        await asyncio.wait_for(entered.wait(), timeout=5)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await asyncio.wait_for(task, timeout=5)
        assert stopped.is_set()
    assert not chromium.contexts


@pytest.mark.asyncio
async def test_browser_context_does_not_reuse_local_storage(chromium: Browser) -> None:
    page = document(
        '<p id="previous"></p><script>document.querySelector("#previous").textContent=localStorage.getItem("test")||"fresh";localStorage.setItem("test","stored");</script>'
    )
    with (
        patch("lonora_security.public_http.socket.getaddrinfo", side_effect=dns),
        patch.object(browser_service, "public_get", AsyncMock(return_value=page)),
    ):
        for _ in range(2):
            result = await browser_service.render(
                chromium, BrowseInput(url="https://example.test/")
            )
            assert result["untrusted_content"] == "fresh"
    assert not chromium.contexts


def factory(respond: Callable[[httpx.Request], httpx.Response]) -> Callable[..., httpx.AsyncClient]:
    original = httpx.AsyncClient

    def create(**kwargs: Any) -> httpx.AsyncClient:
        assert kwargs["trust_env"] is False
        return original(transport=httpx.MockTransport(respond), **kwargs)

    return create


@pytest.mark.parametrize(
    "status,payload,code",
    [
        (200, b"[]", "browser_response_invalid"),
        (200, b"{}", "browser_response_invalid"),
        (200, b"x" * (128 * 1024 + 1), "browser_response_invalid"),
        (500, b"[]", "browser_unavailable"),
        (503, b'{"detail":"browser_busy"}', "tool_read_timeout"),
        (504, b'{"detail":"browser_timeout"}', "tool_read_timeout"),
        (302, b"", "browser_response_invalid"),
    ],
)
@pytest.mark.asyncio
async def test_client_rejects_invalid_bounded_rpc_outputs(
    status: int, payload: bytes, code: str
) -> None:
    context = cast(ToolContext, SimpleNamespace(browser_url="http://browser:8090"))
    with (
        patch(
            "lonora_tools.browser.validate_public_url",
            AsyncMock(return_value="https://example.test/"),
        ),
        patch(
            "lonora_tools.browser.httpx.AsyncClient",
            side_effect=factory(lambda _: httpx.Response(status, content=payload)),
        ),
    ):
        with pytest.raises(LonoraError, match=code):
            await browse(context, {"url": "https://example.test/"})


def test_actions_and_output_remain_bounded_with_multibyte_content() -> None:
    with pytest.raises(ValidationError):
        BrowseInput.model_validate(
            {"url": "https://example.test/", "actions": [{"action": "wait"}] * 9}
        )
    for action in [{"action": "click"}, {"action": "fill", "selector": "input"}]:
        with pytest.raises(ValidationError):
            BrowseInput.model_validate({"url": "https://example.test/", "actions": [action]})
    value = browser_service.bounded_snapshot(
        {
            "untrusted_content": "😀" * 24000,
            "links": [{"title": "😀" * 240, "url": "x" * 2048, "selector": "x" * 80}] * 60,
            "controls": [{"label": "😀" * 240, "selector": "x" * 80}] * 40,
        }
    )
    assert value["truncated"] is True
    assert len(json.dumps(value, ensure_ascii=False).encode()) < 96000
