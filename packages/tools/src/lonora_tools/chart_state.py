from typing import Any, cast

from lonora_charts.state import inspect_chart, update_chart
from lonora_contracts.chart import ChartState, IndicatorSpec
from lonora_contracts.domain import Contract
from lonora_core.chart_annotations import protect_agent_annotations, validate_annotations
from lonora_core.chart_indicator import validate_indicator
from lonora_core.user_error import LonoraError
from lonora_db.cloud_charts import CloudChartRepository
from lonora_session.idempotency import stable_id
from pydantic import Field, model_validator

from .base import Tool
from .context import ToolContext


class ChartRefInput(Contract):
    chart_id: str = Field(min_length=1, max_length=36)


class ChartInspectInput(ChartRefInput):
    include_scene: bool = Field(
        default=True,
        description="Include a bounded scene; false returns chart configuration and scene status only.",
    )
    tail: int = Field(
        default=60,
        ge=1,
        le=200,
        description="Latest candles to return, with indicator series aligned to those same candle timestamps.",
    )


class ChartListInput(Contract):
    thread_id: str | None = Field(default=None, min_length=1, max_length=36)


class ChartEditInput(ChartRefInput):
    version: int = Field(ge=1)


class SetSymbolInput(ChartEditInput):
    symbol: str = Field(min_length=1, max_length=80)


class SetTimeframeInput(ChartEditInput):
    timeframe: str = Field(min_length=1, max_length=10)


class IndicatorEditInput(ChartEditInput):
    name: str = Field(min_length=1, max_length=30)
    period: int = Field(default=14, ge=2, le=500)


class ReadIndicatorInput(ChartRefInput):
    name: str = Field(min_length=1, max_length=30)
    period: int = Field(default=14, ge=2, le=500)
    tail: int = Field(default=20, ge=1, le=200)


class DrawingOperation(Contract):
    op: str = Field(pattern="^(add|update|delete)$")
    id: str | None = Field(default=None, min_length=1, max_length=100)
    annotation: dict[str, Any] | None = None


class AnnotateInput(ChartEditInput):
    annotation: dict[str, Any] | None = Field(
        default=None, description="Legacy single drawing append. Use annotation OR operations."
    )
    operations: list[DrawingOperation] | None = Field(
        default=None,
        min_length=1,
        max_length=100,
        description="Atomic drawing batch: add/update/delete by stable id. Update supplies full replacement geometry. Agent can edit only its own layer.",
    )

    @model_validator(mode="after")
    def check_command(self) -> "AnnotateInput":
        if (self.annotation is None) == (self.operations is None):
            raise ValueError("provide_annotation_or_operations")
        return self


def bounded_inspection(
    current: dict[str, Any], *, include_scene: bool = True, tail: int = 60
) -> dict[str, Any]:
    """Project a tool result without changing the durable scene or the API contract."""
    chart = current["chart"]
    state = chart["state"]
    scene: dict[str, Any] | None = current.get("scene")
    # resource_data also includes the original scene in state. Returning it here
    # would defeat a bounded top-level scene and duplicate the entire history.
    result: dict[str, Any] = {
        **current,
        "chart": {**chart, "state": {key: value for key, value in state.items() if key != "scene"}},
    }
    candles: list[dict[str, Any]] = scene.get("candles", []) if scene else []
    indicators: list[dict[str, Any]] = scene.get("indicators", []) if scene else []
    start = max(0, len(candles) - tail) if include_scene else len(candles)
    selected = candles[start:] if include_scene else []
    indicator_values = sum(
        len(values) for item in indicators for values in item.get("series", {}).values()
    )
    selected_indicators: list[dict[str, Any]] = []
    returned_values = 0
    if scene and include_scene:
        for item in indicators:
            series: dict[str, Any] = {}
            for key, values in item.get("series", {}).items():
                # Use candle indices, never an independent series[-tail:]. This
                # preserves timestamps even for an incomplete historical series.
                series[key] = [
                    values[index] if index < len(values) else None
                    for index in range(start, len(candles))
                ]
                returned_values += len(values[start : len(candles)])
            selected_indicators.append({**item, "series": series})
        result["scene"] = {
            **scene,
            "candles": selected,
            "indicators": selected_indicators,
        }
    else:
        result["scene"] = None
    result["scene_summary"] = {
        "available": scene is not None,
        "included": scene is not None and include_scene,
        "total_candles": len(candles),
        "returned_candles": len(selected),
        "candles_truncated": len(selected) < len(candles),
        "total_indicator_values": indicator_values,
        "returned_indicator_values": returned_values,
        "indicator_values_truncated": returned_values < indicator_values,
        "first_candle_at": candles[0]["time"] if candles else None,
        "last_candle_at": candles[-1]["time"] if candles else None,
    }
    return result


async def inspect(context: ToolContext, args: dict[str, Any]) -> dict[str, Any]:
    current = await inspect_chart(context.db, context.owner_id, args["chart_id"])
    return bounded_inspection(
        current, include_scene=args.get("include_scene", True), tail=args.get("tail", 60)
    )


async def list_charts(context: ToolContext, args: dict[str, Any]) -> dict[str, Any]:
    async with context.db.sessions() as session:
        rows = await CloudChartRepository().list(
            session, context.owner_id, thread_id=args.get("thread_id")
        )
        return {
            "charts": [
                {
                    "chart_id": row.id,
                    "version": row.version,
                    "account_id": row.payload["account_id"],
                    "symbol": row.payload["symbol"],
                    "timeframe": row.payload["timeframe"],
                    "status": row.state.get("scene_status", "pending"),
                    "scene_revision": row.state.get("scene_revision"),
                    "scene_version": row.state.get("scene_version"),
                }
                for row in rows
            ]
        }


async def editable(context: ToolContext, args: dict[str, Any]) -> ChartState:
    current = await inspect_chart(context.db, context.owner_id, args["chart_id"])
    if current["chart"]["version"] != args["version"]:
        raise LonoraError("version_conflict", 409)
    return ChartState.model_validate(current["chart"]["payload"])


async def save(context: ToolContext, args: dict[str, Any], state: ChartState) -> dict[str, Any]:
    current = await update_chart(
        context.db,
        context.brokers,
        context.owner_id,
        args["chart_id"],
        args["version"],
        state,
        lease=context.lease,
        actor_agent_id=context.agent_id,
    )
    return bounded_inspection(current)


async def set_symbol(context: ToolContext, args: dict[str, Any]) -> dict[str, Any]:
    state = await editable(context, args)
    state.symbol = args["symbol"]
    return await save(context, args, state)


async def set_timeframe(context: ToolContext, args: dict[str, Any]) -> dict[str, Any]:
    state = await editable(context, args)
    state.timeframe = args["timeframe"]
    return await save(context, args, state)


async def add_indicator(context: ToolContext, args: dict[str, Any]) -> dict[str, Any]:
    state = await editable(context, args)
    name, period = args["name"].casefold(), args["period"]
    validate_indicator(name, period)
    if any(item.name.casefold() == name and item.period == period for item in state.indicators):
        raise LonoraError("chart_indicator_already_exists", 409)
    state.indicators.append(IndicatorSpec(name=name, period=period))
    return await save(context, args, state)


async def remove_indicator(context: ToolContext, args: dict[str, Any]) -> dict[str, Any]:
    state = await editable(context, args)
    name, period = args["name"].casefold(), args["period"]
    remaining = [
        item
        for item in state.indicators
        if not (item.name.casefold() == name and item.period == period)
    ]
    if len(remaining) == len(state.indicators):
        raise LonoraError("chart_indicator_not_found", 404)
    state.indicators = remaining
    return await save(context, args, state)


async def read_indicator(context: ToolContext, args: dict[str, Any]) -> dict[str, Any]:
    current = await inspect_chart(context.db, context.owner_id, args["chart_id"])
    chart, scene = current["chart"], current.get("scene")
    if not scene or chart["state"].get("scene_revision") != chart["version"]:
        raise LonoraError("chart_scene_unavailable", 409)
    name, period = args["name"].casefold(), args["period"]
    indicator = next(
        (
            item
            for item in scene.get("indicators", [])
            if item["name"].casefold() == name and item["period"] == period
        ),
        None,
    )
    if indicator is None:
        raise LonoraError("chart_indicator_not_found", 404)
    tail = args["tail"]
    candles = scene.get("candles", [])
    return {
        "chart_id": chart["id"],
        "version": chart["version"],
        "scene_version": chart["state"]["scene_version"],
        "scene_revision": chart["state"]["scene_revision"],
        "account_id": chart["payload"]["account_id"],
        "status": chart["state"].get("scene_status", "pending"),
        "symbol": scene["symbol"],
        "timeframe": scene["timeframe"],
        "name": name,
        "period": period,
        "times": [candle["time"] for candle in candles[-tail:]],
        "series": {key: values[-tail:] for key, values in indicator["series"].items()},
        "observed_at": chart["state"].get("scene_updated_at"),
        "last_candle_at": candles[-1]["time"] if candles else None,
    }


def apply_drawing_operations(
    state: ChartState, args: dict[str, Any], *, agent_id: str, chart_id: str, mutation_id: str
) -> list[dict[str, Any]]:
    previous = state.annotations
    following: list[dict[str, Any]] = list(previous)
    operations = args.get("operations")
    if operations is None:
        operations = [{"op": "add", "annotation": args["annotation"]}]
    if not 1 <= len(operations) <= 100:
        raise LonoraError("invalid_chart_annotation")
    for index, operation in enumerate(operations):
        op, identity = operation["op"], operation.get("id")
        annotation = operation.get("annotation")
        if op not in {"add", "update", "delete"} or (op != "add" and not identity):
            raise LonoraError("invalid_chart_annotation")
        existing = (
            next((item for item in following if item.get("id") == identity), None)
            if identity
            else None
        )
        if op in {"update", "delete"} and existing is None:
            raise LonoraError("chart_annotation_not_found", 404)
        scope = {"account_id": state.account_id, "symbol": state.symbol, "chart_id": chart_id}
        if existing is not None and existing.get("scope", scope) != scope:
            raise LonoraError("chart_annotation_scope_mismatch", 409)
        if op == "delete":
            if annotation is not None:
                raise LonoraError("invalid_chart_annotation")
            following = [item for item in following if item is not existing]
            continue
        if not isinstance(annotation, dict):
            raise LonoraError("invalid_chart_annotation")
        annotation = cast(dict[str, Any], annotation)
        identity = identity or annotation.get("id") or stable_id(mutation_id, str(index))
        if annotation.get("id", identity) != identity:
            raise LonoraError("invalid_chart_annotation")
        if op == "add" and any(item.get("id") == identity for item in following):
            raise LonoraError("chart_annotation_already_exists", 409)
        normalized: dict[str, Any] = {
            **annotation,
            "id": identity,
            "source": "agent",
            "author_id": agent_id,
            "scope": scope,
        }
        if op == "update":
            following = [normalized if item is existing else item for item in following]
        else:
            following.append(normalized)
    validate_annotations(following)
    protect_agent_annotations(previous, following, agent_id)
    return following


async def annotate(context: ToolContext, args: dict[str, Any]) -> dict[str, Any]:
    state = await editable(context, args)
    state.annotations = apply_drawing_operations(
        state,
        args,
        agent_id=context.agent_id,
        chart_id=args["chart_id"],
        mutation_id=context.resource_id,
    )
    return await save(context, args, state)


def tools() -> list[Tool]:
    return [
        Tool(
            "chart_list",
            "Discover up to 200 of the owner's persisted chart IDs and versions without loading candle scenes. Optionally filter by an owned thread_id; use chart_inspect before editing.",
            ChartListInput,
            list_charts,
            True,
        ),
        Tool(
            "chart_inspect",
            "Inspect the owner's persisted chart configuration, current version and latest server-rendered candles/indicators (default tail=60, maximum 200). Set include_scene=false for configuration/status only or reduce tail for a smaller result. Candle and indicator values share timestamps; scene_summary reports omitted history. Read before editing; never guess a version.",
            ChartInspectInput,
            inspect,
            True,
        ),
        Tool(
            "chart_set_symbol",
            "Change an existing chart's broker symbol. Requires its inspected version; preserves annotations and indicators.",
            SetSymbolInput,
            set_symbol,
        ),
        Tool(
            "chart_set_timeframe",
            "Change an existing chart's supported timeframe using its inspected version.",
            SetTimeframeInput,
            set_timeframe,
        ),
        Tool(
            "chart_add_indicator",
            "Add a supported indicator to an existing persistent chart. Use name+period and current version.",
            IndicatorEditInput,
            add_indicator,
        ),
        Tool(
            "chart_remove_indicator",
            "Remove one named indicator/period from an existing chart using its current version.",
            IndicatorEditInput,
            remove_indicator,
        ),
        Tool(
            "chart_read_indicator",
            "Read bounded numerical indicator values from the current server-rendered chart scene. Values including null warmup entries reflect that chart, not a separately fetched market series.",
            ReadIndicatorInput,
            read_indicator,
            True,
        ),
        Tool(
            "chart_annotate",
            "Append one drawing or atomically add/update/delete a batch of typed drawings using the inspected chart version. Types: price, horizontal_line, trend_line, note, price_zone, ray, channel, fibonacci, arrow, scenario. Geometry uses time/price anchors. Only this Agent’s attributed layer can be changed. An annotation is visual evidence, not an order or trading approval.",
            AnnotateInput,
            annotate,
        ),
    ]
