"""Serve the credential-free chart renderer from the single Web distribution.

Mobile Web may serve a separate Expo shell. Its chart frame must still use the
same renderer and licensed assets as Web, never fall back to that Expo shell.
"""

from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import FileResponse
from lonora_core.user_error import LonoraError
from lonora_security.runtime_storage import confined_path


def install_chart_renderer(app: FastAPI, root: Path) -> None:
    build = root.resolve()

    def response(path: Path, *, document: bool = False) -> FileResponse:
        if not path.is_file():
            raise LonoraError("chart_renderer_unavailable" if document else "asset_not_found", 404)
        # No scene, account or credentials are embedded into this public shell.
        # Scene data comes from its validated parent bridge after loading.
        entry = (
            document
            or path.suffix == ".html"
            or path.name
            in {
                "charting_library.js",
                "charting_library.standalone.js",
                "asset-manifest.json",
            }
        )
        return FileResponse(
            path,
            headers={
                "Cache-Control": "no-cache" if entry else "public, max-age=3600",
                "X-Content-Type-Options": "nosniff",
                "Referrer-Policy": "no-referrer",
            },
        )

    @app.get("/charts/render", include_in_schema=False)
    async def chart_renderer() -> FileResponse:
        return response(confined_path(build, "chart-runtime/index.html"), document=True)

    @app.get("/chart-runtime/{path:path}", include_in_schema=False)
    async def chart_runtime_asset(path: str) -> FileResponse:
        return response(confined_path(build / "chart-runtime", path))

    @app.get("/charting_library/{path:path}", include_in_schema=False)
    async def chart_vendor_asset(path: str) -> FileResponse:
        return response(confined_path(build / "charting_library", path))
