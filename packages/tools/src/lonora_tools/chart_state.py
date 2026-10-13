from typing import Any

from lonora_charts.state import inspect_chart, update_chart
from lonora_contracts.chart import ChartState, IndicatorSpec
from lonora_contracts.domain import Contract
from lonora_core.chart_indicator import validate_indicator
from lonora_core.user_error import LonoraError
from lonora_db.cloud_charts import CloudChartRepository
from pydantic import Field

from .base import Tool
from .context import ToolContext


class ChartRefInput(Contract):
    chart_id: str = Field(min_length=1, max_length=36)


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


class AnnotateInput(ChartEditInput):
    annotation: dict[str, Any] = Field(
        description="Semantic annotation, for example {type: 'price', price: 4000, label: 'Support'}. Supported formats are validated by the server."
    )


async def inspect(context: ToolContext, args: dict[str, Any]) -> dict[str, Any]:
    return await inspect_chart(context.db, context.owner_id, args["chart_id"])


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
    current = await inspect(context, args)
    if current["chart"]["version"] != args["version"]:
        raise LonoraError("version_conflict", 409)
    return ChartState.model_validate(current["chart"]["payload"])


async def save(context: ToolContext, args: dict[str, Any], state: ChartState) -> dict[str, Any]:
    return await update_chart(
        context.db,
        context.brokers,
        context.owner_id,
        args["chart_id"],
        args["version"],
        state,
        lease=context.lease,
    )


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
    current = await inspect(context, args)
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


async def annotate(context: ToolContext, args: dict[str, Any]) -> dict[str, Any]:
    state = await editable(context, args)
    state.annotations = [*state.annotations, args["annotation"]]
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
            "Inspect the owner's persisted chart state, version and server-rendered scene. Read before editing; never guess a version.",
            ChartRefInput,
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
            "Append a validated semantic price/time annotation to an existing chart using its current version. An annotation is visual evidence, not an order or trading approval.",
            AnnotateInput,
            annotate,
        ),
    ]
