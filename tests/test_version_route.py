from pathlib import Path

import httpx
import pytest
from lonora_api.app import create_app
from lonora_api.env import get_settings


@pytest.mark.asyncio
async def test_version_reports_the_served_web_build(tmp_path: Path):
    (tmp_path / "index.html").write_text("<!doctype html>")
    settings = get_settings().model_copy(update={"web_root": tmp_path, "chart_renderer_root": None})
    app = create_app(settings)
    try:
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app), base_url="https://lonora.test"
        ) as client:
            # No build.json: the deployment carries no build id, so the client shows no update bar.
            first = await client.get("/api/version")
            assert first.status_code == 200
            assert first.json() == {"version": "0.2.0", "build": None}
            (tmp_path / "build.json").write_text('{"build": "k9x2m4"}')
            current = await client.get("/api/version")
            assert current.json() == {"version": "0.2.0", "build": "k9x2m4"}
            (tmp_path / "build.json").write_text("not json")
            assert (await client.get("/api/version")).json()["build"] is None
    finally:
        await app.state.runtime.close()
