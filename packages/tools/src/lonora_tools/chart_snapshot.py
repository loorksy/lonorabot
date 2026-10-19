from hashlib import sha256
from typing import Any, Literal

from lonora_charts.scene_snapshot import scene_svg
from lonora_charts.snapshot import svg_snapshot
from lonora_charts.snapshot_render import png_snapshot
from lonora_charts.state import inspect_chart, prepare_chart_scene
from lonora_contracts.domain import Contract, utcnow
from lonora_core.user_error import LonoraError
from lonora_db.artifacts import ArtifactRepository
from lonora_market.broker import broker_market
from lonora_security.runtime_storage import confined_path
from pydantic import Field, model_validator

from .artifacts import store_artifact
from .base import Tool
from .context import ToolContext


class SnapshotInput(Contract):
    renderer: Literal["semantic", "tradingview"] = "semantic"
    locale: Literal["en", "ar"] = "en"
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
        if self.renderer == "tradingview" and (not self.chart_id or self.format == "svg"):
            raise ValueError("TradingView capture requires chart_id and PNG format")
        market = (self.account_id, self.symbol, self.timeframe)
        if self.chart_id and any(value is not None for value in market):
            raise ValueError("Use chart_id or explicit market fields, not both")
        if not self.chart_id and not all(market):
            raise ValueError("Provide chart_id or account_id, symbol and timeframe")
        return self


def snapshot_result(artifact: dict[str, Any], descriptor: dict[str, Any]) -> dict[str, Any]:
    return {
        **artifact,
        "chart_snapshot": descriptor,
        **{
            key: descriptor[key]
            for key in ("chart_id", "scene_revision", "scene_version")
            if key in descriptor
        },
    }


def source_request(args: dict[str, Any]) -> dict[str, Any]:
    if args.get("chart_id"):
        identity = {"chart_id": args["chart_id"]}
        if args.get("renderer") == "tradingview":
            identity.update(renderer="tradingview", locale=args.get("locale", "en"))
        return identity
    return {key: args[key] for key in ("account_id", "symbol", "timeframe")} | {
        "limit": args.get("limit", 300)
    }


async def snapshot(context: ToolContext, args: dict[str, Any]) -> dict[str, Any]:
    image_format = args.get("format") or "png"
    descriptor: dict[str, Any] | None = None
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
            descriptor = existing.state.get("chart_snapshot")
            if descriptor is None and args.get("renderer") == "tradingview":
                # A legacy semantic artifact cannot satisfy a browser-pixel request.
                raise LonoraError("artifact_nonce_conflict", 409)
            if descriptor is not None and descriptor.get("request") != source_request(args):
                raise LonoraError("artifact_nonce_conflict", 409)
        else:
            payload = None
    if payload is not None:
        path = confined_path(context.artifact_root, payload["key"])
        if not path.is_file():
            raise LonoraError("artifact_file_missing", 404)
        content = path.read_bytes()
        if len(content) != payload["size"] or sha256(content).hexdigest() != payload["sha256"]:
            raise LonoraError("artifact_integrity_failed", 409)
        artifact = await store_artifact(
            context,
            payload["name"],
            content,
            payload["media_type"],
            receipt_state={"chart_snapshot": descriptor} if descriptor is not None else None,
        )
        # Older receipts did not retain source evidence; do not reconstruct it from
        # today's chart, current arguments, file timestamps, or the image filename.
        return snapshot_result(
            artifact,
            descriptor
            if descriptor is not None
            else {
                "source": "unknown",
                "format": "png" if payload["media_type"] == "image/png" else "svg",
            },
        )
    media_type = "image/png" if image_format == "png" else "image/svg+xml"
    if args.get("chart_id"):
        result = await inspect_chart(context.db, context.owner_id, args["chart_id"])
        if result.get("code") == "chart_initializing":
            result = await prepare_chart_scene(
                context.db, context.brokers, context.owner_id, args["chart_id"], context.lease
            )
        scene = result.get("scene")
        if scene is None:
            raise LonoraError(str(result.get("code", "chart_data_unavailable")), 409)
        renderer_receipt: dict[str, object] | None = None
        if args.get("renderer") == "tradingview":
            if context.chart_visual is None:
                raise LonoraError("chart_visual_unconfigured", 503)
            capture = await context.chart_visual.capture(
                scene,
                account_id=result["chart"]["payload"]["account_id"],
                locale=args.get("locale", "en"),
            )
            content = capture.png
            renderer_receipt = capture.receipt
        else:
            image = scene_svg(scene)
            content = png_snapshot(image) if image_format == "png" else image.encode()
        descriptor = {
            "source": "tradingview_renderer"
            if renderer_receipt is not None
            else "saved_semantic_scene",
            "format": image_format,
            "request": source_request(args),
            "chart_id": result["chart"]["id"],
            "account_id": result["chart"]["payload"]["account_id"],
            "symbol": scene["symbol"],
            "timeframe": scene["timeframe"],
            "captured_at": utcnow().isoformat(),
        }
        if renderer_receipt is not None:
            descriptor["renderer_receipt"] = renderer_receipt
        quote: dict[str, Any] = scene.get("quote") or {}
        for key, value in {
            "scene_revision": result["chart"]["state"].get("scene_revision"),
            "scene_version": scene.get("scene_version"),
            "data_revision": scene.get("data_revision"),
            "scene_updated_at": result["chart"]["state"].get("scene_updated_at"),
            "last_candle_at": scene["candles"][-1]["time"] if scene.get("candles") else None,
            "source_observed_at": scene.get("candle_observed_at"),
            "quote_observed_at": quote.get("observed_at"),
        }.items():
            if value is not None:
                descriptor[key] = value
        artifact = await store_artifact(
            context,
            scene["symbol"] + "." + image_format,
            content,
            media_type,
            receipt_state={"chart_snapshot": descriptor},
        )
        return snapshot_result(artifact, descriptor)
    provider = await broker_market(context.brokers, context.owner_id, args["account_id"])
    candles = await provider.candles(args["symbol"], args["timeframe"], args["limit"])
    if any(candle.timeframe != args["timeframe"] for candle in candles):
        raise LonoraError("broker_candles_mismatch", 502)
    image = svg_snapshot(args["symbol"], candles)
    content = png_snapshot(image) if image_format == "png" else image.encode()
    descriptor = {
        "source": "broker_candles",
        "format": image_format,
        "request": source_request(args),
        "account_id": args["account_id"],
        "symbol": args["symbol"],
        "timeframe": args["timeframe"],
        "last_candle_at": candles[-1].time.isoformat(),
        "captured_at": utcnow().isoformat(),
    }
    # Candle.time identifies the bar; it is not a quote/source observation timestamp.
    artifact = await store_artifact(
        context,
        args["symbol"] + "." + image_format,
        content,
        media_type,
        receipt_state={"chart_snapshot": descriptor},
    )
    return snapshot_result(artifact, descriptor)


def tools() -> list[Tool]:
    return [
        Tool(
            "chart_snapshot",
            "Save a durable chart image with immutable source/revision provenance. Default renderer=semantic uses server SVG/Pillow drawing; renderer=tradingview with chart_id captures actual browser-rendered PNG pixels and applied-revision receipt, when configured. TradingView capture supports locale=en|ar and does not accept SVG or explicit market fields. Read the returned artifact with artifact_read(view_image=true) to inspect its actual pixels before claiming visual verification. Saved/delivered images do not prove the user rendered or saw them. Semantic mode also accepts account_id/symbol/timeframe for candle-only snapshots and format=svg for vector downloads. No execution or trading approval is implied.",
            SnapshotInput,
            snapshot,
            replay_safe=True,
        )
    ]
