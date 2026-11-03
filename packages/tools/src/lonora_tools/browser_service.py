"""Isolated research Chromium service; no database, owner secrets or saved profile.

Chromium has a deliberately unreachable proxy. Every allowed request is fetched
by the public-address-pinned reader and fulfilled locally, including redirects
and JavaScript subresources. Unhandled/background requests cannot use the network.
"""

import asyncio
import json
import os
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager, suppress
from datetime import UTC, datetime
from typing import Any, cast
from urllib.parse import urljoin

import httpx
import uvicorn
from fastapi import FastAPI, HTTPException
from lonora_core.user_error import LonoraError
from lonora_security.public_http import PublicResponse, public_address, public_get
from playwright.async_api import (
    Browser,
    BrowserContext,
    Page,
    Request,
    Route,
    WebSocketRoute,
    async_playwright,
)
from playwright.async_api import (
    Error as PlaywrightError,
)
from playwright.async_api import (
    TimeoutError as PlaywrightTimeout,
)

from .browser import BrowseInput

MAX_REQUESTS = 80
MAX_TOTAL_BYTES = 16 * 1024 * 1024
MAX_REDIRECTS = 6
ALLOWED_RESOURCES = frozenset({"document", "script", "stylesheet", "xhr", "fetch"})


def bounded_snapshot(snapshot: dict[str, Any]) -> dict[str, Any]:
    """Reserve output space by UTF-8 bytes, including non-Latin page content."""
    text = str(snapshot.get("untrusted_content", ""))
    low, high = 0, len(text)
    while low < high:
        middle = (low + high + 1) // 2
        if len(json.dumps(text[:middle], ensure_ascii=False).encode()) <= 48000:
            low = middle
        else:
            high = middle - 1
    snapshot["untrusted_content"] = text[:low]
    truncated = snapshot["untrusted_content"] != text
    for name, budget in (("links", 24000), ("controls", 12000)):
        items: list[Any] = snapshot.get(name, [])
        selected: list[Any] = []
        used = 0
        for item in items:
            size = len(json.dumps(item, ensure_ascii=False).encode()) + 1
            if used + size > budget:
                truncated = True
                break
            selected.append(item)
            used += size
        snapshot[name] = selected
    snapshot["truncated"] = truncated
    return snapshot


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None]:
    async with async_playwright() as playwright:
        browser = await playwright.chromium.launch(
            executable_path=os.getenv("BROWSER_EXECUTABLE", "/usr/bin/chromium"),
            chromium_sandbox=os.getenv("BROWSER_SANDBOX", "true").lower() == "true",
            headless=True,
            args=[
                "--proxy-server=http://127.0.0.1:9",
                "--proxy-bypass-list=<-loopback>",
                "--disable-background-networking",
                "--disable-component-update",
                "--disable-sync",
                "--disable-quic",
                "--no-first-run",
                "--disable-extensions",
                "--force-webrtc-ip-handling-policy=disable_non_proxied_udp",
            ],
        )
        app.state.browser = browser
        app.state.capacity = asyncio.Semaphore(2)
        try:
            yield
        finally:
            await browser.close()


app = FastAPI(lifespan=lifespan, docs_url=None, redoc_url=None, openapi_url=None)


@app.get("/health")
async def health() -> dict[str, str]:
    browser = cast(Browser, app.state.browser)
    if not browser.is_connected():
        raise HTTPException(503, "browser_unavailable")
    return {"status": "ok"}


async def close_websocket(route: WebSocketRoute) -> None:
    await route.close()


async def render(browser: Browser, body: BrowseInput) -> dict[str, Any]:
    await public_address(body.url)
    context: BrowserContext = await browser.new_context(
        accept_downloads=False,
        java_script_enabled=True,
        service_workers="block",
        permissions=[],
        viewport={"width": 1280, "height": 900},
    )
    blocked = 0
    requests = 0
    transferred = 0
    request_slots = asyncio.Semaphore(6)
    route_tasks: set[asyncio.Task[Any]] = set()
    document_failure: str | None = None
    page: Page | None = None
    next_navigation: str | None = None
    navigation_redirects = 0

    async def route_one(route: Route, request: Request) -> None:
        nonlocal blocked, requests, transferred, document_failure, next_navigation
        main_navigation = bool(
            request.is_navigation_request() and page and request.frame == page.main_frame
        )
        requests += 1
        if (
            requests > MAX_REQUESTS
            or transferred >= MAX_TOTAL_BYTES
            or request.method not in {"GET", "HEAD"}
            or request.resource_type not in ALLOWED_RESOURCES
        ):
            blocked += 1
            await route.abort("blockedbyclient")
            return
        try:
            async with request_slots:
                target = request.url
                result: PublicResponse | None = None
                for hop in range(MAX_REDIRECTS + 1):
                    if hop:
                        requests += 1
                    if requests > MAX_REQUESTS or transferred >= MAX_TOTAL_BYTES:
                        raise LonoraError("research_source_too_large", 413)
                    result = await public_get(target, request.method)
                    transferred += len(result.body)
                    if transferred > MAX_TOTAL_BYTES:
                        raise LonoraError("research_source_too_large", 413)
                    if result.status not in range(300, 400):
                        break
                    location = result.headers.get("location")
                    if not location or hop == MAX_REDIRECTS:
                        raise LonoraError("browser_source_unavailable", 502)
                    target = urljoin(target, location)
                    await public_address(target)
                    if main_navigation:
                        # Chromium's routing callback is skipped after HTTP redirects.
                        # Abort and navigate explicitly so final URL/origin stay real.
                        next_navigation = target
                        await route.abort("blockedbyclient")
                        return
            assert result is not None
            content_type = result.headers.get("content-type", "").lower()
            if "attachment" in result.headers.get("content-disposition", "").lower() or (
                request.resource_type == "document"
                and result.status not in range(300, 400)
                and not any(value in content_type for value in ["text/", "xhtml", "xml", "json"])
            ):
                raise LonoraError("browser_source_unavailable", 502)
            if main_navigation and result.status >= 400:
                raise LonoraError("browser_source_unavailable", 502)
            await route.fulfill(status=result.status, headers=result.headers, body=result.body)
        except (LonoraError, httpx.HTTPError) as error:
            blocked += 1
            if main_navigation:
                if isinstance(error, LonoraError):
                    document_failure = error.code
                else:
                    document_failure = (
                        "browser_timeout"
                        if isinstance(error, httpx.TimeoutException)
                        else "tool_connection_failure"
                    )
            with suppress(PlaywrightError):
                await route.abort("blockedbyclient")

    async def route_request(route: Route, request: Request) -> None:
        task = asyncio.current_task()
        if task:
            route_tasks.add(task)
        try:
            await route_one(route, request)
        except PlaywrightError:
            # Closing a context cancels pending page requests during cleanup.
            pass
        finally:
            if task:
                route_tasks.discard(task)

    try:
        await context.route("**/*", route_request)
        await context.route_web_socket("**/*", close_websocket)
        page = await context.new_page()
        page.set_default_timeout(4000)
        page.set_default_navigation_timeout(15000)

        async def close_popup(popup: Any) -> None:
            if popup != page:
                await popup.close()

        context.on("page", close_popup)

        async def navigate(target: str) -> None:
            nonlocal next_navigation, document_failure, navigation_redirects
            assert page is not None
            while True:
                next_navigation = None
                document_failure = None
                try:
                    await page.goto(target, wait_until="domcontentloaded")
                except PlaywrightError:
                    if next_navigation:
                        navigation_redirects += 1
                        if navigation_redirects > MAX_REDIRECTS:
                            raise LonoraError("browser_source_unavailable", 502) from None
                        target = next_navigation
                        continue
                    if document_failure:
                        raise LonoraError(document_failure, 502) from None
                    raise
                return

        await navigate(body.url)
        await page.wait_for_timeout(400)
        if next_navigation:
            await navigate(next_navigation)
        for action in body.actions:
            await page.evaluate(
                """() => [...document.querySelectorAll('a[href],button,input,textarea,select,[role="button"]')]
                .filter(el => !!el.getClientRects().length && getComputedStyle(el).visibility !== 'hidden')
                .forEach((el,index) => el.setAttribute('data-lonora-control', String(index)))"""
            )
            if action.action == "click":
                try:
                    await page.locator("css=" + (action.selector or "")).first.click()
                except PlaywrightError:
                    if not next_navigation:
                        raise
            elif action.action == "fill":
                target = page.locator("css=" + (action.selector or "")).first
                kind = await target.get_attribute("type")
                if kind and kind.lower() in {"password", "file", "hidden"}:
                    raise LonoraError("browser_action_failed", 403)
                await target.fill(action.text or "")
            elif action.action == "scroll":
                await page.mouse.wheel(0, action.pixels)
            else:
                await page.wait_for_timeout(action.milliseconds)
            await page.wait_for_timeout(150)
            if next_navigation:
                await navigate(next_navigation)
        if document_failure:
            raise LonoraError(document_failure, 502)
        # A navigation to a non-HTTP scheme is never an acceptable final source.
        await public_address(page.url)
        snapshot: dict[str, Any] = await page.evaluate(
            """() => {
              const visible = el => !!(el.getClientRects().length) && getComputedStyle(el).visibility !== 'hidden';
              const elements = [...document.querySelectorAll('a[href],button,input,textarea,select,[role="button"]')].filter(visible);
              elements.forEach((el,index) => el.setAttribute('data-lonora-control', String(index)));
              const label = el => (el.getAttribute('aria-label') || el.labels?.[0]?.innerText || el.innerText || el.getAttribute('placeholder') || el.getAttribute('name') || '').trim().slice(0,240);
              const selector = el => '[data-lonora-control="' + el.getAttribute('data-lonora-control') + '"]';
              return {
                title: document.title.slice(0,300),
                untrusted_content: (document.body?.innerText || '').slice(0,24000),
                links: elements.filter(el => el.tagName === 'A' && el.href.startsWith('https://')).slice(0,60).map(el => ({title: label(el), url: el.href.slice(0,2048), selector: selector(el)})),
                controls: elements.filter(el => el.tagName !== 'A' && el.getAttribute('type') !== 'password' && el.getAttribute('type') !== 'file').slice(0,40).map(el => ({label: label(el), role: el.getAttribute('role') || el.tagName.toLowerCase(), selector: selector(el)}))
              };
            }"""
        )
        return {
            "source": page.url,
            "observed_at": datetime.now(UTC).isoformat(),
            **bounded_snapshot(snapshot),
            "blocked_requests": blocked,
        }
    finally:
        pending = list(route_tasks)
        for task in pending:
            task.cancel()
        if pending:
            await asyncio.gather(*pending, return_exceptions=True)
        await context.close()


@app.post("/browse")
async def browse(body: BrowseInput) -> dict[str, Any]:
    capacity = cast(asyncio.Semaphore, app.state.capacity)
    try:
        await asyncio.wait_for(capacity.acquire(), timeout=2)
    except TimeoutError:
        raise HTTPException(503, "browser_busy") from None
    try:
        async with asyncio.timeout(40):
            return await render(cast(Browser, app.state.browser), body)
    except (TimeoutError, PlaywrightTimeout):
        raise HTTPException(504, "browser_timeout") from None
    except LonoraError as error:
        raise HTTPException(error.status, error.code) from None
    except PlaywrightError:
        raise HTTPException(502, "browser_action_failed") from None
    finally:
        capacity.release()


def main() -> None:
    uvicorn.run(app, host="0.0.0.0", port=8090, access_log=False)


if __name__ == "__main__":
    main()
