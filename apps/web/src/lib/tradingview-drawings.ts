import type {
  CreateMultipointShapeOptions,
  IChartWidgetApi,
  PricedPoint,
} from "../../public/charting_library/charting_library";
import type { ChartScene } from "./charts";

type Annotation = Record<string, unknown>;
type Shape = NonNullable<CreateMultipointShapeOptions<object>["shape"]>;
function point(value: unknown): PricedPoint {
  const p = value as { time: string; price: number };
  return { time: Date.parse(p.time) / 1000, price: Number(p.price) };
}
export function drawingVisible(a: Annotation, scene: ChartScene, accountId?: string) {
  const scope = a.scope as { chart_id?: string; symbol?: string; account_id?: string } | undefined;
  return (
    (!scope?.chart_id || scope.chart_id === scene.chart_id) &&
    (!scope?.symbol || scope.symbol === scene.symbol) &&
    (!scope?.account_id || scope.account_id === accountId) &&
    (!Array.isArray(a.timeframes) || a.timeframes.includes(scene.timeframe))
  );
}
/** Saved domain geometry is projected into locked vendor shapes; vendor state is never persisted. */
export async function renderDrawing(chart: IChartWidgetApi, a: Annotation, scene: ChartScene) {
  const style = (a.style ?? {}) as { color?: string; line_width?: number; line_style?: string };
  const color = style.color ?? (a.source === "agent" ? "#6289e8" : "#d4a73c");
  const overrides: Record<string, unknown> = {
    linecolor: color,
    color,
    linewidth: style.line_width ?? 1,
    linestyle: ["solid", "dotted", "dashed"].indexOf(style.line_style ?? "solid"),
    backgroundColor: color,
    transparency: 88,
  };
  const opts = {
    lock: true,
    disableSelection: true,
    disableSave: true,
    disableUndo: true,
    text: String(a.label ?? a.text ?? ""),
    overrides,
  };
  const last = scene.candles.at(-1);
  const fallback = {
    time: last ? Date.parse(last.time) / 1000 : Date.now() / 1000,
    price: Number(a.price ?? last?.close ?? 0),
  };
  if (["price", "horizontal_line", "note"].includes(String(a.type))) {
    const p = a.time
      ? { time: Date.parse(String(a.time)) / 1000, price: fallback.price }
      : fallback;
    return [
      await chart.createShape(p, {
        ...opts,
        shape: a.type === "note" ? "text" : "horizontal_line",
      }),
    ];
  }
  const start = point(a.start),
    end = point(a.end);
  if (a.type === "scenario") {
    return Promise.all([
      chart.createMultipointShape([start, end], {
        ...opts,
        shape: "arrow",
        text: String(a.label ?? ""),
      }),
      chart.createMultipointShape(
        [
          { ...start, price: Number(a.stop) },
          { ...end, price: Number(a.stop) },
        ],
        { ...opts, shape: "trend_line", overrides: { ...overrides, linecolor: "#d95a64" } },
      ),
    ]);
  }
  if (a.type === "fibonacci") {
    // Explicit server levels, rather than vendor defaults or derived vendor state.
    const levels = (a.levels ?? [0, 0.236, 0.382, 0.5, 0.618, 1]) as number[];
    return Promise.all(
      levels.map((level) => {
        const price = start.price + (end.price - start.price) * level;
        return chart.createMultipointShape(
          [
            { ...start, price },
            { ...end, price },
          ],
          { ...opts, shape: "trend_line", text: String(level) },
        );
      }),
    );
  }
  const shapes: Record<string, Shape> = {
    trend_line: "trend_line",
    price_zone: "rectangle",
    ray: "ray",
    channel: "parallel_channel",
    arrow: "arrow",
  };
  const shape = shapes[String(a.type)];
  if (!shape) throw new Error("chart_drawing_unsupported");
  return [
    await chart.createMultipointShape(
      a.type === "channel" ? [start, end, point(a.parallel)] : [start, end],
      { ...opts, shape },
    ),
  ];
}
