"""Bounded, credential-free visual verification of an immutable cloud-chart scene.

This service accepts no browser instructions. The operator chooses the renderer;
callers supply an already-authorized backend scene, never a URL or JavaScript.
"""

from __future__ import annotations

import asyncio
import importlib
import json
import struct
import tempfile
from collections.abc import Coroutine, Mapping
from dataclasses import dataclass
from typing import TYPE_CHECKING, cast
from urllib.parse import unquote, urlsplit

from lonora_core.user_error import LonoraError

if TYPE_CHECKING:
    from playwright.async_api import Browser, BrowserContext, Playwright, Route

_CLEANUP_TIMEOUT = 3.0
_MAX_SCENE_BYTES = 4_000_000
_MAX_PNG_BYTES = 5_000_000
_BRIDGE = """(() => {
  window.__lonoraCaptureMessages = [];
  window.ReactNativeWebView = {postMessage: (raw) => {
    try { window.__lonoraCaptureMessages.push(JSON.parse(raw)); } catch (_) {}
  }};
})();"""


def _consume_cleanup(task: asyncio.Task[None]) -> None:
    if not task.cancelled():
        task.exception()


async def _bounded_cleanup(operation: Coroutine[object, object, None]) -> bool:
    """Never let a failed browser transport stall market/worker shutdown.

    A timed-out task is cancelled and its eventual exception consumed. We do not
    wait indefinitely for third-party code to acknowledge cancellation.
    """
    task = asyncio.create_task(operation)
    task.add_done_callback(_consume_cleanup)
    try:
        done, _ = await asyncio.wait({task}, timeout=_CLEANUP_TIMEOUT)
    except asyncio.CancelledError:
        task.cancel()
        raise
    if not done:
        task.cancel()
        return False
    return not task.cancelled() and task.exception() is None


@dataclass(frozen=True)
class ChartVisualCapture:
    png: bytes
    receipt: dict[str, object]


class ChartVisualRuntime:
    """One lazy browser process, with isolated, short-lived capture contexts."""

    def __init__(
        self,
        renderer_url: str | None,
        executable_path: str | None = None,
        *,
        maximum_concurrency: int = 2,
        queue_timeout: float = 5,
        total_timeout: float = 30,
        chromium_sandbox: bool = True,
    ) -> None:
        self._url = self._validate_url(renderer_url)
        self._executable = executable_path
        if not 1 <= maximum_concurrency <= 4 or not 0 < queue_timeout <= 30:
            raise ValueError("invalid chart visual concurrency limits")
        if not 0 < total_timeout <= 120:
            raise ValueError("invalid chart visual capture timeout")
        self._queue_timeout = queue_timeout
        self._total_timeout = total_timeout
        self._sandbox = chromium_sandbox
        self._slots = asyncio.Semaphore(maximum_concurrency)
        self._launch_lock = asyncio.Lock()
        self._browser: Browser | None = None
        self._playwright: Playwright | None = None
        self._closed = False
        self._data_directory: tempfile.TemporaryDirectory[str] | None = None

    @staticmethod
    def _validate_url(value: str | None) -> str | None:
        if not value:
            return None
        parsed = urlsplit(value)
        if (
            parsed.scheme not in {"http", "https"}
            or not parsed.hostname
            or parsed.username is not None
            or parsed.password is not None
            or parsed.path != "/charts/render"
            or parsed.query
            or parsed.fragment
        ):
            raise ValueError("chart renderer must be an operator-configured /charts/render URL")
        # Validate malformed ports at configuration time, without exposing the URL.
        _ = parsed.port
        return value

    @staticmethod
    def _payload(
        scene: Mapping[str, object], account_id: str, locale: str, width: int, height: int
    ) -> tuple[dict[str, object], dict[str, object]]:
        if (
            locale not in {"en", "ar"}
            or not 0 < len(account_id) <= 256
            or isinstance(width, bool)
            or isinstance(height, bool)
            or not 320 <= width <= 1920
            or not 240 <= height <= 1080
        ):
            raise LonoraError("chart_visual_invalid_scene")
        try:
            encoded = json.dumps(dict(scene), ensure_ascii=False, allow_nan=False)
            if len(encoded.encode("utf-8")) > _MAX_SCENE_BYTES:
                raise ValueError("scene too large")
            frozen = cast(dict[str, object], json.loads(encoded))
        except (ValueError, TypeError, RecursionError) as exc:
            raise LonoraError("chart_visual_invalid_scene") from exc
        for key in ("chart_id", "symbol", "timeframe", "data_revision"):
            value = frozen.get(key)
            if not isinstance(value, str) or not 0 < len(value) <= 256:
                raise LonoraError("chart_visual_invalid_scene")
        for key in ("revision", "scene_version"):
            value = frozen.get(key)
            if not isinstance(value, int) or isinstance(value, bool) or value < 0:
                raise LonoraError("chart_visual_invalid_scene")
        for key, maximum in (("candles", 10000), ("annotations", 500), ("indicators", 32)):
            values = frozen.get(key)
            if not isinstance(values, list) or len(cast(list[object], values)) > maximum:
                raise LonoraError("chart_visual_invalid_scene")
        if not frozen["candles"] or frozen.get("status") != "ready":
            raise LonoraError("chart_data_unavailable")
        receipt: dict[str, object] = {
            "renderer": "tradingview",
            "chart_id": frozen["chart_id"],
            "scene_version": frozen["scene_version"],
            "data_revision": frozen["data_revision"],
            "revision": frozen["revision"],
            "account_id": account_id,
            "symbol": frozen["symbol"],
            "timeframe": frozen["timeframe"],
            "locale": locale,
            "viewport_width": width,
            "viewport_height": height,
        }
        return {
            "type": "lonora.chart.scene",
            "scene": frozen,
            "account_id": account_id,
            "locale": locale,
        }, receipt

    async def _get_browser(self) -> Browser:
        async with self._launch_lock:
            if self._closed:
                raise LonoraError("chart_visual_runtime_closed", 503)
            if self._browser is not None and self._browser.is_connected():
                return self._browser
            self._browser = None
            if self._playwright is None:
                try:
                    module = importlib.import_module("playwright.async_api")
                    self._playwright = cast("Playwright", await module.async_playwright().start())
                except (ImportError, OSError) as exc:
                    raise LonoraError("chart_visual_unconfigured", 503) from exc
            if self._closed:
                driver, self._playwright = self._playwright, None
                await _bounded_cleanup(driver.stop())
                raise LonoraError("chart_visual_runtime_closed", 503)
            if self._data_directory is None:
                self._data_directory = tempfile.TemporaryDirectory(prefix="lonora-chart-visual-")
            directory = self._data_directory.name
            # The trusted Playwright Node driver inherits the host environment: its public
            # startup API has no environment argument. The browser/rendering process does
            # not inherit host credentials, proxies, the user's HOME or browser state.
            browser_env: dict[str, str | float | bool] = {
                "PATH": "/usr/local/bin:/usr/bin:/bin",
                "HOME": directory,
                "TMPDIR": directory,
                "XDG_CACHE_HOME": directory + "/cache",
                "LANG": "C.UTF-8",
                "TZ": "UTC",
            }
            driver = self._playwright
            try:
                browser = await driver.chromium.launch(
                    executable_path=self._executable,
                    headless=True,
                    chromium_sandbox=self._sandbox,
                    env=browser_env,
                    args=["--disable-background-networking", "--disable-component-update"],
                )
            except Exception as exc:
                # A dead driver is not a reusable cache entry either. The next bounded
                # request starts a fresh driver rather than failing forever on this one.
                if self._playwright is driver:
                    self._playwright = None
                if not await _bounded_cleanup(driver.stop()):
                    self._closed = True  # Never duplicate an unconfirmed old process.
                raise LonoraError("chart_visual_unconfigured", 503) from exc
            if self._closed:
                await _bounded_cleanup(browser.close())
                await _bounded_cleanup(driver.stop())
                raise LonoraError("chart_visual_runtime_closed", 503)
            self._browser = browser
            return browser

    def _allowed_request(self, url: str, method: str) -> bool:
        if self._url is None or method != "GET":
            return False
        requested, configured = urlsplit(url), urlsplit(self._url)
        if (
            requested.scheme != configured.scheme
            or requested.netloc != configured.netloc
            or requested.username is not None
            or requested.password is not None
        ):
            return False
        if any(part == ".." for part in unquote(requested.path).replace("\\", "/").split("/")):
            return False
        return (
            requested.path in {"/charts/render", "/theme-init.js"}
            or requested.path.startswith("/chart-runtime/")
            or requested.path.startswith("/charting_library/")
        )

    async def capture(
        self,
        scene: Mapping[str, object],
        *,
        account_id: str,
        locale: str = "en",
        width: int = 1280,
        height: int = 720,
    ) -> ChartVisualCapture:
        payload, receipt = self._payload(scene, account_id, locale, width, height)
        if self._url is None:
            raise LonoraError("chart_visual_unconfigured", 503)
        try:
            await asyncio.wait_for(self._slots.acquire(), self._queue_timeout)
        except TimeoutError as exc:
            raise LonoraError("chart_visual_busy", 503) from exc
        try:
            async with asyncio.timeout(self._total_timeout):
                return await self._capture(payload, receipt, width, height)
        except TimeoutError as exc:
            raise LonoraError("chart_visual_timeout", 504) from exc
        except LonoraError:
            raise
        except Exception as exc:
            # Browser exceptions may contain renderer URLs and scene details. Do not log them.
            raise LonoraError("chart_visual_capture_failed", 503) from exc
        finally:
            self._slots.release()

    async def _capture(
        self, payload: dict[str, object], receipt: dict[str, object], width: int, height: int
    ) -> ChartVisualCapture:
        context: BrowserContext | None = None
        try:
            browser = await self._get_browser()
            context = await browser.new_context(
                viewport={"width": width, "height": height},
                device_scale_factor=1,
                locale="en-US",
                service_workers="block",
                accept_downloads=False,
            )

            async def route(request: Route) -> None:
                if self._allowed_request(request.request.url, request.request.method):
                    await request.continue_()
                else:
                    await request.abort("blockedbyclient")

            await context.route("**/*", route)
            await context.route_web_socket("**/*", lambda socket: socket.close())
            await context.add_init_script(_BRIDGE)
            page = await context.new_page()
            page.set_default_timeout(self._total_timeout * 1000)
            page.on("popup", lambda popup: popup.close())
            assert self._url is not None
            await page.goto(self._url, wait_until="domcontentloaded")
            await page.wait_for_function(
                "() => window.__lonoraCaptureMessages?.some(m => m.type === 'lonora.chart.ready')"
            )
            await page.evaluate(
                "payload => window.postMessage(payload, window.location.origin)", payload
            )
            await page.wait_for_function(
                """expected => window.__lonoraCaptureMessages?.some(m =>
                  m.type === 'lonora.chart.applied' && m.chart_id === expected.chart_id &&
                  m.scene_version === expected.scene_version &&
                  m.data_revision === expected.data_revision)""",
                arg=receipt,
            )
            surface = page.locator(".chart-renderer")
            await surface.wait_for(state="visible")
            # APPLIED means studies and drawings were installed; paint the same immutable scene.
            await page.evaluate(
                "() => new Promise(resolve => requestAnimationFrame(() => requestAnimationFrame(resolve)))"
            )
            png = await surface.screenshot(type="png", animations="disabled", timeout=5000)
            if not png.startswith(b"\x89PNG\r\n\x1a\n") or len(png) > _MAX_PNG_BYTES:
                raise LonoraError("chart_visual_image_invalid", 503)
            actual_width, actual_height = struct.unpack("!II", png[16:24])
            if not 0 < actual_width <= width or not 0 < actual_height <= height:
                raise LonoraError("chart_visual_image_invalid", 503)
            return ChartVisualCapture(
                png=png,
                receipt={
                    **receipt,
                    "applied": True,
                    "width": actual_width,
                    "height": actual_height,
                },
            )
        finally:
            if context is not None:
                try:
                    cleaned = await _bounded_cleanup(context.close())
                except asyncio.CancelledError:
                    await self.close()
                    raise
                if not cleaned:
                    # Do not reuse a browser with an unknown, possibly credential-bearing
                    # context. If transport shutdown fails too, the service stays closed.
                    await self.close()

    async def close(self) -> None:
        """Bounded shutdown; failed cleanup cannot admit another browser process."""
        # Mark closed before awaiting anything. A launch already holding the lock
        # observes this flag when it returns and disposes its own late handles.
        self._closed = True
        browser, self._browser = self._browser, None
        driver, self._playwright = self._playwright, None
        directory, self._data_directory = self._data_directory, None
        try:
            if browser is not None:
                await _bounded_cleanup(browser.close())
        finally:
            try:
                if driver is not None:
                    await _bounded_cleanup(driver.stop())
            finally:
                if directory is not None:
                    # This private directory contains no owner credentials; temporary
                    # profile cleanup must not mask an original capture exception.
                    try:
                        directory.cleanup()
                    except OSError:
                        pass
