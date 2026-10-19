"""Real licensed renderer captures; no broker credentials or trading mutations."""

from __future__ import annotations

# pyright: reportPrivateUsage=false
import asyncio
import functools
import importlib.util
import os
import shutil
import threading
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from io import BytesIO
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest
from lonora_charts.visual import ChartVisualRuntime
from lonora_core.user_error import LonoraError
from PIL import Image


@pytest.fixture(scope="module")
def renderer_url() -> Iterator[str]:
    root = Path(__file__).resolve().parents[1] / "apps/web/dist"
    if not (root / "chart-runtime/index.html").is_file():
        pytest.skip("Build the dedicated shared Web chart renderer before browser capture tests")

    class Handler(SimpleHTTPRequestHandler):
        def do_GET(self) -> None:
            if self.path == "/charts/render":
                self.path = "/chart-runtime/index.html"
            super().do_GET()

        def log_message(self, format: str, *args: object) -> None:
            pass

    server = ThreadingHTTPServer(("127.0.0.1", 0), functools.partial(Handler, directory=str(root)))
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield f"http://127.0.0.1:{server.server_port}/charts/render"
    server.shutdown()
    server.server_close()
    thread.join(timeout=2)


@pytest.fixture(scope="module")
def chromium_path() -> str:
    if importlib.util.find_spec("playwright") is None:
        pytest.skip("Install the Python Playwright dependency for real browser capture tests")
    executable = os.environ.get("LONORA_UI_TEST_BROWSER_PATH") or shutil.which("chromium")
    if not executable:
        from playwright.sync_api import sync_playwright

        with sync_playwright() as playwright:
            executable = playwright.chromium.executable_path
    if not Path(executable).is_file():
        pytest.skip("A Chromium executable is required for real renderer capture tests")
    return executable


def scene(*, price: float = 100, revision: int = 1) -> dict[str, object]:
    start = datetime(2026, 10, 19, tzinfo=UTC)
    candles: list[dict[str, object]] = []
    for index in range(120):
        close = price + (index % 8 - 4) + index / 15
        candles.append(
            {
                "symbol": "XAUUSDm",
                "timeframe": "15m",
                "time": (start + timedelta(minutes=15 * index)).isoformat(),
                "open": str(close - 1),
                "high": str(close + 2),
                "low": str(close - 2),
                "close": str(close),
                "volume": "10",
            }
        )
    return {
        "chart_id": "visual-owned-chart",
        "revision": revision,
        "scene_version": revision,
        "data_revision": f"immutable-{revision}",
        "status": "ready",
        "updated_at": start.isoformat(),
        "symbol": "XAUUSDm",
        "timeframe": "15m",
        "candles": candles,
        "annotations": [],
        "indicators": [],
    }


@pytest.mark.parametrize(
    "url",
    [
        "file:///charts/render",
        "https://user:pass@example.invalid/charts/render",
        "https://example.invalid/other",
        "https://example.invalid/charts/render?token=secret",
        "https://example.invalid/charts/render#fragment",
    ],
)
def test_renderer_configuration_rejects_user_controlled_url_forms(url: str) -> None:
    with pytest.raises(ValueError):
        ChartVisualRuntime(url)


@pytest.mark.asyncio
async def test_unconfigured_is_explicit_and_does_not_launch_browser() -> None:
    runtime = ChartVisualRuntime(None)
    with pytest.raises(LonoraError, match="chart_visual_unconfigured"):
        await runtime.capture(scene(), account_id="account")
    await runtime.close()


@pytest.mark.parametrize("key,value", [("data_revision", ""), ("candles", []), ("revision", True)])
@pytest.mark.asyncio
async def test_invalid_or_empty_scene_is_not_synthesized(key: str, value: object) -> None:
    value_scene = {**scene(), key: value}
    with pytest.raises(LonoraError):
        await ChartVisualRuntime(None).capture(value_scene, account_id="account")


def test_network_allowlist_blocks_other_origins_api_and_mutations() -> None:
    runtime = ChartVisualRuntime("http://127.0.0.1:9000/charts/render")
    assert runtime._allowed_request("http://127.0.0.1:9000/chart-runtime/assets/app.js", "GET")
    assert runtime._allowed_request("http://127.0.0.1:9000/charting_library/chart.html?x=1", "GET")
    for url, method in (
        ("http://127.0.0.1:9000/api/accounts", "GET"),
        ("http://127.0.0.1:9000/charts/render", "POST"),
        ("https://other.invalid/charting_library/a.js", "GET"),
        ("http://user:secret@127.0.0.1:9000/charts/render", "GET"),
    ):
        assert not runtime._allowed_request(url, method)


@pytest.mark.asyncio
async def test_real_renderer_exact_revision_png_and_process_reuse(
    renderer_url: str, chromium_path: str
) -> None:
    runtime = ChartVisualRuntime(renderer_url, chromium_path, chromium_sandbox=False)
    try:
        before = await runtime.capture(scene(), account_id="owned-account", width=960, height=600)
        browser = runtime._browser
        after = await runtime.capture(
            scene(price=200, revision=2),
            account_id="owned-account",
            locale="ar",
            width=960,
            height=600,
        )
        assert runtime._browser is browser
        assert before.receipt["data_revision"] == "immutable-1"
        assert after.receipt["data_revision"] == "immutable-2"
        assert after.receipt["locale"] == "ar"
        assert before.png != after.png
        assert before.receipt["applied"] is True
        for capture in (before, after):
            with Image.open(BytesIO(capture.png)) as image:
                assert image.width == 960 and 0 < image.height <= 600
                assert len(image.getcolors(image.width * image.height) or []) > 100
        assert browser is not None and browser.contexts == []
    finally:
        await runtime.close()
    with pytest.raises(LonoraError, match="chart_visual_runtime_closed"):
        await runtime.capture(scene(), account_id="owned-account")


@pytest.mark.asyncio
async def test_queue_bound_cancel_releases_slot() -> None:
    runtime = ChartVisualRuntime(
        "http://127.0.0.1:9000/charts/render", maximum_concurrency=1, queue_timeout=0.03
    )
    entered = asyncio.Event()

    async def blocked(*args: object) -> None:
        entered.set()
        await asyncio.Event().wait()

    with patch.object(runtime, "_capture", side_effect=blocked):
        task = asyncio.create_task(runtime.capture(scene(), account_id="account"))
        await entered.wait()
        with pytest.raises(LonoraError, match="chart_visual_busy"):
            await runtime.capture(scene(), account_id="account")
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
        assert runtime._slots._value == 1
    await runtime.close()


@pytest.mark.asyncio
async def test_capture_timeout_is_bounded_and_preserves_lifecycle() -> None:
    runtime = ChartVisualRuntime("http://127.0.0.1:9000/charts/render", total_timeout=0.03)
    with patch.object(runtime, "_capture", new=AsyncMock(side_effect=asyncio.TimeoutError)):
        with pytest.raises(LonoraError, match="chart_visual_timeout"):
            await runtime.capture(scene(), account_id="account")
    assert runtime._slots._value == 2
    await runtime.close()


@pytest.mark.asyncio
async def test_real_renderer_all_geometry_and_server_indicator_panes(
    renderer_url: str, chromium_path: str
) -> None:
    value = scene()
    start = {"time": "2026-10-19T12:00:00+00:00", "price": 102}
    end = {"time": "2026-10-19T23:00:00+00:00", "price": 108}
    annotations: list[dict[str, object]] = [
        {"type": "price", "price": 105},
        {"type": "horizontal_line", "price": 106},
        {"type": "note", "text": "Server analysis", "time": start["time"], "price": 108},
        *(
            {"type": kind, "start": start, "end": end}
            for kind in ("trend_line", "price_zone", "ray", "arrow")
        ),
        {"type": "channel", "start": start, "end": end, "parallel": {**start, "price": 106}},
        {"type": "fibonacci", "start": start, "end": end, "levels": [0, 0.5, 1]},
        {"type": "scenario", "start": start, "end": end, "stop": 99},
    ]
    value["annotations"] = [
        {**annotation, "id": f"shape-{index}", "source": "agent"}
        for index, annotation in enumerate(annotations)
    ]
    value["indicators"] = [
        {"name": "SMA", "period": 10, "series": {"value": [104.0] * 120}},
        {"name": "RSI", "period": 14, "series": {"value": [55.0] * 120}},
    ]
    runtime = ChartVisualRuntime(renderer_url, chromium_path, chromium_sandbox=False)
    try:
        result = await runtime.capture(value, account_id="account")
        assert result.receipt["applied"] is True
        with Image.open(BytesIO(result.png)) as image:
            assert result.receipt["width"] == image.width
            assert result.receipt["height"] == image.height
            assert len(result.png) > 10000
    finally:
        await runtime.close()


@pytest.mark.asyncio
async def test_real_browser_disconnect_recreates_one_shared_process(
    renderer_url: str, chromium_path: str
) -> None:
    runtime = ChartVisualRuntime(renderer_url, chromium_path, chromium_sandbox=False)
    try:
        await runtime.capture(scene(), account_id="account")
        first = runtime._browser
        assert first is not None
        await first.close()
        captures = await asyncio.gather(
            runtime.capture(scene(revision=2), account_id="account"),
            runtime.capture(scene(revision=3), account_id="account"),
        )
        assert all(capture.receipt["applied"] for capture in captures)
        assert runtime._browser is not first
        assert runtime._browser is not None and runtime._browser.contexts == []
    finally:
        await runtime.close()


@pytest.mark.asyncio
async def test_real_browser_cancel_during_scene_ack_closes_context(
    renderer_url: str, chromium_path: str
) -> None:
    # The bridge rejects malformed candles. A capture must cancel cleanly while waiting for APPLIED.
    value = scene()
    value["candles"] = [{"time": "invalid", "open": "0", "high": "1", "low": "0", "close": "1"}]
    runtime = ChartVisualRuntime(renderer_url, chromium_path, chromium_sandbox=False)
    try:
        task = asyncio.create_task(runtime.capture(value, account_id="account"))
        for _ in range(100):
            browser = runtime._browser
            if browser and browser.contexts and browser.contexts[0].pages:
                page = browser.contexts[0].pages[0]
                if page.url == renderer_url:
                    await page.wait_for_function(
                        "() => window.__lonoraCaptureMessages?.some(m => m.type === 'lonora.chart.ready')"
                    )
                    break
            await asyncio.sleep(0.02)
        else:
            pytest.fail("Renderer did not reach its scene acknowledgment wait")
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
        assert runtime._browser is not None and runtime._browser.contexts == []
        assert (await runtime.capture(scene(), account_id="account")).receipt["applied"]
    finally:
        await runtime.close()


@pytest.mark.asyncio
async def test_real_context_denies_network_and_has_no_credentials(
    renderer_url: str, chromium_path: str
) -> None:
    from typing import Any

    from playwright.async_api import BrowserContext

    runtime = ChartVisualRuntime(renderer_url, chromium_path, chromium_sandbox=False)
    failed: list[str] = []
    observed_cookies: list[object] = []
    try:
        browser = await runtime._get_browser()
        create = browser.new_context

        async def isolated(**kwargs: Any) -> BrowserContext:
            context = await create(**kwargs)
            observed_cookies.extend(await context.cookies())
            context.on("requestfailed", lambda request: failed.append(request.url))
            # Deliberately fault the trusted renderer, not an Agent-facing browser command.
            await context.add_init_script(
                """window.addEventListener('DOMContentLoaded', () => {
                fetch('/api/capture-network-probe').catch(() => {});
                fetch('https://outside.invalid/capture-network-probe').catch(() => {});
                fetch('/chart-runtime/capture-post-probe', {method:'POST'}).catch(() => {});
                });"""
            )
            return context

        with patch.object(browser, "new_context", side_effect=isolated):
            assert (await runtime.capture(scene(), account_id="account")).receipt["applied"]
        assert observed_cookies == []
        assert any(url.endswith("/api/capture-network-probe") for url in failed)
        assert any(url.startswith("https://outside.invalid/") for url in failed)
        assert any(url.endswith("/chart-runtime/capture-post-probe") for url in failed)
        assert browser.contexts == []
    finally:
        await runtime.close()


@pytest.mark.asyncio
async def test_missing_executable_is_unconfigured() -> None:
    runtime = ChartVisualRuntime(
        "http://127.0.0.1:9000/charts/render", "/not-installed/lonora-chromium"
    )
    try:
        with pytest.raises(LonoraError, match="chart_visual_unconfigured"):
            await runtime.capture(scene(), account_id="account")
    finally:
        await runtime.close()


@pytest.mark.asyncio
async def test_real_missing_applied_ack_times_out_and_cleans_up(
    renderer_url: str, chromium_path: str
) -> None:
    value = scene()
    value["candles"] = [{"time": "invalid", "open": "0", "high": "1", "low": "0", "close": "1"}]
    runtime = ChartVisualRuntime(
        renderer_url, chromium_path, chromium_sandbox=False, total_timeout=1.5
    )
    try:
        with pytest.raises(LonoraError, match="chart_visual_timeout"):
            await runtime.capture(value, account_id="account")
        assert runtime._browser is not None and runtime._browser.contexts == []
    finally:
        await runtime.close()


@pytest.mark.asyncio
async def test_hung_context_browser_and_driver_cleanup_are_bounded_without_masking_failure() -> (
    None
):
    from typing import cast
    from unittest.mock import MagicMock

    from playwright.async_api import Browser, BrowserContext, Playwright

    async def never() -> None:
        await asyncio.Event().wait()

    context = MagicMock(spec=BrowserContext)
    context.route = AsyncMock(side_effect=LonoraError("original_capture_failure"))
    context.close = AsyncMock(side_effect=never)
    browser = MagicMock(spec=Browser)
    browser.new_context = AsyncMock(return_value=context)
    browser.close = AsyncMock(side_effect=never)
    driver = MagicMock(spec=Playwright)
    driver.stop = AsyncMock(side_effect=never)
    runtime = ChartVisualRuntime("http://127.0.0.1:9000/charts/render")
    runtime._browser = cast(Browser, browser)
    runtime._playwright = cast(Playwright, driver)
    with patch("lonora_charts.visual._CLEANUP_TIMEOUT", 0.02):
        with patch.object(runtime, "_get_browser", new=AsyncMock(return_value=browser)):
            async with asyncio.timeout(0.5):
                with pytest.raises(LonoraError, match="original_capture_failure"):
                    await runtime.capture(scene(), account_id="account")
        assert runtime._browser is None and runtime._playwright is None
        assert runtime._closed
        context.close.assert_awaited_once()
        browser.close.assert_awaited_once()
        driver.stop.assert_awaited_once()
        with pytest.raises(LonoraError, match="chart_visual_runtime_closed"):
            await runtime.capture(scene(), account_id="account")


@pytest.mark.asyncio
async def test_cleanup_exception_does_not_replace_original_capture_failure() -> None:
    from typing import cast
    from unittest.mock import MagicMock

    from playwright.async_api import Browser, BrowserContext

    context = MagicMock(spec=BrowserContext)
    context.route = AsyncMock(side_effect=LonoraError("original_capture_failure"))
    context.close = AsyncMock(side_effect=RuntimeError("broken cleanup"))
    browser = MagicMock(spec=Browser)
    browser.new_context = AsyncMock(return_value=context)
    browser.close = AsyncMock(side_effect=RuntimeError("broken browser cleanup"))
    runtime = ChartVisualRuntime("http://127.0.0.1:9000/charts/render")
    runtime._browser = cast(Browser, browser)
    with patch.object(runtime, "_get_browser", new=AsyncMock(return_value=browser)):
        with pytest.raises(LonoraError, match="original_capture_failure"):
            await runtime.capture(scene(), account_id="account")
    assert runtime._closed and runtime._browser is None


@pytest.mark.asyncio
async def test_close_does_not_wait_for_launch_lock_and_late_browser_is_disposed() -> None:
    from typing import cast
    from unittest.mock import MagicMock

    from playwright.async_api import Browser, Playwright

    entered = asyncio.Event()
    release = asyncio.Event()
    browser = MagicMock(spec=Browser)
    browser.close = AsyncMock()

    async def launch(**kwargs: object) -> Browser:
        entered.set()
        await release.wait()
        return cast(Browser, browser)

    driver = MagicMock(spec=Playwright)
    driver.chromium.launch = AsyncMock(side_effect=launch)
    driver.stop = AsyncMock()
    runtime = ChartVisualRuntime("http://127.0.0.1:9000/charts/render")
    runtime._playwright = cast(Playwright, driver)
    pending = asyncio.create_task(runtime._get_browser())
    await entered.wait()
    async with asyncio.timeout(0.5):
        await runtime.close()
    release.set()
    with pytest.raises(LonoraError, match="chart_visual_runtime_closed"):
        await pending
    browser.close.assert_awaited_once()
    driver.chromium.launch.assert_awaited_once()
    assert runtime._browser is None and runtime._playwright is None
