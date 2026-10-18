from typing import Any, Literal

from lonora_charts.scene_snapshot import scene_svg
from lonora_charts.snapshot import svg_snapshot
from lonora_charts.snapshot_render import png_snapshot
from lonora_charts.state import inspect_chart
from lonora_contracts.domain import Contract
from lonora_core.user_error import LonoraError
from lonora_db.artifacts import ArtifactRepository
from lonora_market.broker import broker_market
from lonora_security.runtime_storage import confined_path
from pydantic import Field, model_validator

from .artifacts import store_artifact
from .base import Tool
from .context import ToolContext


class SnapshotInput(Contract):
    format: Literal["png", "svg"] | None = Field(
        default=None,
        description="Defaults to PNG for new images; an interrupted older SVG operation preserves its original format on replay.",
    )
    chart_id: str | None = Field(default=None, min_length=1, max_length=36)
    account_id: str | None = None
    symbol: str | None = None
    timeframe: str | None = None
    limit: int = Field(default=300, ge=2, le=1000)

    @model_validator(mode="after")
    def source(self) -> "SnapshotInput":
        market = (self.account_id, self.symbol, self.timeframe)
        if self.chart_id and any(value is not None for value in market):
            raise ValueError("Use chart_id or explicit market fields, not both")
        if not self.chart_id and not all(market):
            raise ValueError("Provide chart_id or account_id, symbol and timeframe")
        return self


async def snapshot(context: ToolContext, args: dict[str, Any]) -> dict[str, Any]:
    image_format = args.get("format") or "png"
    async with context.db.sessions() as session:
        existing = await session.get(ArtifactRepository.row_type, context.resource_id)
        if existing:
            if (
                existing.owner_id != context.owner_id
                or existing.thread_id != context.thread_id
                or existing.agent_id != context.agent_id
            ):
                raise LonoraError("artifacts_not_found", 404)
            saved_type = existing.payload["media_type"]
            if args.get("format") and saved_type != (
                "image/png" if image_format == "png" else "image/svg+xml"
            ):
                raise LonoraError("artifact_nonce_conflict", 409)
            payload = dict(existing.payload)
        else:
            payload = None
    if payload is not None:
        path = confined_path(context.artifact_root, payload["key"])
        if not path.is_file():
            raise LonoraError("artifact_file_missing", 404)
        return await store_artifact(
            context, payload["name"], path.read_bytes(), payload["media_type"]
        )
    media_type = "image/png" if image_format == "png" else "image/svg+xml"
    if args.get("chart_id"):
        result = await inspect_chart(context.db, context.owner_id, args["chart_id"])
        scene = result.get("scene")
        if scene is None:
            raise LonoraError(str(result.get("code", "chart_data_unavailable")), 409)
        image = scene_svg(scene)
        content = png_snapshot(image) if image_format == "png" else image.encode()
        artifact = await store_artifact(
            context, scene["symbol"] + "." + image_format, content, media_type
        )
        return {
            **artifact,
            "chart_id": result["chart"]["id"],
            "scene_revision": result["chart"]["state"]["scene_revision"],
            "scene_version": scene["scene_version"],
        }
    provider = await broker_market(context.brokers, context.owner_id, args["account_id"])
    candles = await provider.candles(args["symbol"], args["timeframe"], args["limit"])
    image = svg_snapshot(args["symbol"], candles)
    content = png_snapshot(image) if image_format == "png" else image.encode()
    return await store_artifact(context, args["symbol"] + "." + image_format, content, media_type)


def tools() -> list[Tool]:
    return [
        Tool(
            "chart_snapshot",
            "Save a durable chart image attached to your assistant reply. PNG is the default for web/mobile; request format=svg for a vector download. Pass chart_id to capture its persisted candles, indicators and annotations; alternatively pass account_id/symbol/timeframe for a candle-only market snapshot. No execution or trading approval is implied.",
            SnapshotInput,
            snapshot,
        )
    ]
