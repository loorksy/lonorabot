"""The deployed web build, so an open shell can learn that a newer one is served."""

import json
from pathlib import Path
from typing import cast

from fastapi import APIRouter, Request

from ..middleware.auth import runtime

router = APIRouter(prefix="/version")

APP_VERSION = "0.2.0"


def web_build_id(web_root: Path) -> str | None:
    """The id Vite wrote next to the SPA (build.json); None when no build is served."""
    try:
        data: object = json.loads((web_root / "build.json").read_text("utf-8"))
    except (OSError, ValueError):
        return None
    if not isinstance(data, dict):
        return None
    build = cast(dict[str, object], data).get("build")
    return build if isinstance(build, str) and 0 < len(build) <= 64 else None


@router.get("")
async def version(request: Request) -> dict[str, str | None]:
    return {"version": APP_VERSION, "build": web_build_id(runtime(request).settings.web_root)}
