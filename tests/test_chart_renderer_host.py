"""Shared renderer hosting never substitutes the Mobile application shell."""

from pathlib import Path

import httpx
import pytest
from fastapi import FastAPI
from lonora_api.chart_renderer import install_chart_renderer
from lonora_api.errors import install_errors


@pytest.mark.asyncio
async def test_separate_renderer_root_and_strict_assets(tmp_path: Path):
    web = tmp_path / "web"
    (web / "chart-runtime" / "assets").mkdir(parents=True)
    (web / "charting_library").mkdir()
    (web / "chart-runtime" / "index.html").write_text("<html>Shared chart</html>")
    (web / "chart-runtime" / "assets" / "chart.js").write_text("/* chart */")
    (web / "charting_library" / "chart.js").write_text("/* vendor */")
    (web / "charting_library" / "charting_library.standalone.js").write_text("/* entry */")
    (tmp_path / "private.txt").write_text("private")
    (web / "chart-runtime" / "escape").symlink_to(tmp_path / "private.txt")
    app = FastAPI()
    install_errors(app)
    install_chart_renderer(app, web)

    @app.get("/{path:path}")
    async def mobile_shell(path: str):
        return {"shell": "expo"}

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app), base_url="https://lonora.test"
    ) as client:
        frame = await client.get("/charts/render?locale=ar")
        assert frame.status_code == 200 and "Shared chart" in frame.text
        assert frame.headers["cache-control"] == "no-cache"
        assert frame.headers["x-content-type-options"] == "nosniff"
        assert (await client.get("/chart-runtime/assets/chart.js")).text == "/* chart */"
        assert (await client.get("/charting_library/chart.js")).text == "/* vendor */"
        entry = await client.get("/charting_library/charting_library.standalone.js")
        assert entry.status_code == 200 and entry.headers["cache-control"] == "no-cache"
        for path in ("/chart-runtime/missing.js", "/charting_library/missing.js"):
            missing = await client.get(path)
            assert missing.status_code == 404 and missing.json()["code"] == "asset_not_found"
        escaped = await client.get("/chart-runtime/escape")
        assert escaped.status_code == 403
        assert "private" not in escaped.text
        assert (await client.get("/app")).json() == {"shell": "expo"}


@pytest.mark.asyncio
async def test_missing_renderer_is_explicit_without_shell_fallback(tmp_path: Path):
    app = FastAPI()
    install_errors(app)
    install_chart_renderer(app, tmp_path / "not-built")
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app), base_url="https://lonora.test"
    ) as client:
        response = await client.get("/charts/render")
        assert response.status_code == 404
        assert response.json()["code"] == "chart_renderer_unavailable"
