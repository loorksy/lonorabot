from pathlib import Path

import httpx
import pytest
from lonora_api.app import create_app
from lonora_api.env import get_settings


@pytest.mark.asyncio
async def test_spa_entry_and_deep_links_never_keep_an_old_asset_selection(tmp_path: Path):
    (tmp_path / "index.html").write_text('<script src="/chart-runtime/assets/app-old.js"></script>')
    (tmp_path / "theme-init.js").write_text("/* current theme bootstrap */")
    (tmp_path / "chart-runtime/assets").mkdir(parents=True)
    (tmp_path / "chart-runtime/assets/app-new.js").write_text("/* current application */")
    settings = get_settings().model_copy(update={"web_root": tmp_path, "chart_renderer_root": None})
    app = create_app(settings)
    try:
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app), base_url="https://lonora.test"
        ) as client:
            for path in ("/", "/app", "/app/", "/app/old-agent?thread=old-thread", "/index.html"):
                old = await client.get(path)
                assert old.status_code == 200
                assert old.headers["cache-control"] == "no-store"
                assert old.headers["x-content-type-options"] == "nosniff"
                assert "app-old.js" in old.text
                (tmp_path / "index.html").write_text(
                    '<script src="/chart-runtime/assets/app-new.js"></script>'
                )
                current = await client.get(path, headers={"If-None-Match": old.headers["etag"]})
                assert current.status_code == 200
                assert current.headers["cache-control"] == "no-store"
                assert "app-new.js" in current.text and "app-old.js" not in current.text
                (tmp_path / "index.html").write_text(
                    '<script src="/chart-runtime/assets/app-old.js"></script>'
                )
            bootstrap = await client.get("/theme-init.js")
            assert bootstrap.headers["cache-control"] == "no-cache"
            asset = await client.get("/chart-runtime/assets/app-new.js")
            assert asset.status_code == 200
            assert asset.headers["cache-control"] == "public, max-age=3600"
            assert (await client.get("/api/nonexistent-route")).status_code == 404
    finally:
        await app.state.runtime.close()
