/* The chart sheet's drawing, as data (Q37): the reference's geometry (chartGeom/drawChart)
   over the broker's candles, and the agent's annotations and indicators read-only in the same
   visual language. Pure, so it is unit-tested without a browser. */

export type Bar = { t: number; o: number; h: number; l: number; c: number };
export type Annotation = Record<string, unknown>;
export type Indicator = { name: string; period: number; series: Record<string, (number | null)[]> };

/** Oscillators get their own pane under the candles; the others share the price scale. */
export const OSCILLATORS: ReadonlySet<string> = new Set(["rsi", "atr", "macd"]);

export type Shape =
  | { kind: "hline"; y: number; x1: number; x2: number; label?: string; tone: Tone; dash?: boolean }
  | { kind: "segment"; x1: number; y1: number; x2: number; y2: number; tone: Tone; arrow?: boolean }
  | { kind: "box"; x: number; y: number; w: number; h: number; tone: Tone; label?: string }
  | { kind: "note"; x: number; y: number; text: string; tone: Tone };
export type Tone = "agent" | "up" | "down";
export type Pane = {
  label: string;
  top: number;
  bottom: number;
  lines: { name: string; points: string }[];
  /** Fixed guides (RSI 30/70) or the zero line. */
  guides: { y: number; label: string }[];
};

export type Layout = {
  VW: number;
  VH: number;
  fs: number;
  right: number;
  top: number;
  bottom: number;
  bars: Bar[];
  X: (i: number) => number;
  Y: (price: number) => number;
  grid: { y: number; label: string }[];
  times: { x: number; label: string }[];
  shapes: Shape[];
  /** Moving averages and bands on the price scale. */
  priceLines: { name: string; points: string }[];
  pane: Pane | null;
};

const f = (v: number) => v.toFixed(1);
const num = (value: unknown) => Number(value);
const hm = (ms: number) => {
  const d = new Date(ms);
  return `${d.getHours()}:${String(d.getMinutes()).padStart(2, "0")}`;
};

/** A round step that puts grid lines ~48px apart (reference chartStep). */
export function priceStep(range: number, px: number) {
  const want = Math.max(2, Math.floor(px / 48));
  const raw = range / want;
  const magnitude = 10 ** Math.floor(Math.log10(raw || 1));
  return [1, 2, 2.5, 5, 10].map((m) => m * magnitude).find((step) => step >= raw) ?? 10 * magnitude;
}

/** An annotation scoped to timeframes shows on those only (the agent's chart tools). */
export const shownOn = (item: Annotation, frame: string) =>
  !Array.isArray(item.timeframes) || item.timeframes.includes(frame);

export function layout(input: {
  width: number;
  height: number;
  bars: Bar[];
  frame: string;
  annotations: Annotation[];
  /** The scene's indicators with the candle times they align to (same timeframe only). */
  indicators: Indicator[];
  indicatorTimes: number[];
  labels: { entry: string; stop: string; target: string };
}): Layout {
  const s = Math.min(1, Math.max(0.55, input.width / 600));
  const VW = Math.round(input.width / s);
  const VH = Math.max(160, Math.round(input.height / s));
  const fs = +(10.5 / s).toFixed(1);
  const gut = Math.round(fs * 3.7 + 14);
  const right = VW - gut;
  const xLast = right - 12;
  const top = Math.round(fs * 0.9);
  const axis = VH - Math.round(fs * 1.9 + 8);
  const n = Math.max(8, Math.floor((xLast - 20) / 17) + 1);
  const bars = input.bars.slice(-n);
  const X = (i: number) => xLast - (bars.length - 1 - i) * 17;
  const oscillators = input.indicators.filter((item) => OSCILLATORS.has(item.name));
  const overlays = input.indicators.filter((item) => !OSCILLATORS.has(item.name));
  // The oscillator pane takes the lower quarter of the plot, under its own label.
  const paneHeight = oscillators.length ? Math.round((axis - top) * 0.26) : 0;
  const bottom = axis - paneHeight;
  let lo = Math.min(...bars.map((b) => b.l));
  let hi = Math.max(...bars.map((b) => b.h));
  if (!Number.isFinite(lo) || !Number.isFinite(hi)) {
    lo = 0;
    hi = 1;
  }
  if (hi === lo) hi = lo + 1;
  const pad = (hi - lo) * 0.12;
  const p0 = lo - pad;
  const p1 = hi + pad;
  const Y = (price: number) => top + ((p1 - price) / (p1 - p0)) * (bottom - top);
  const step = priceStep(p1 - p0, (bottom - top) * s);
  const digits = step < 0.01 ? 5 : step < 0.5 ? 2 : 1;
  const grid: Layout["grid"] = [];
  for (let p = Math.ceil(p0 / step) * step; p <= p1 + 1e-9; p += step)
    grid.push({ y: Y(p), label: p.toFixed(digits) });
  const times: Layout["times"] = [];
  bars.forEach((bar, i) => {
    if ((bars.length - 1 - i) % 7 === 1 && X(i) >= 15) times.push({ x: X(i), label: hm(bar.t) });
  });
  // Time → x on the bars' own spacing; outside the window clamps to its edges.
  const spacing =
    bars.length > 1 ? (bars[bars.length - 1].t - bars[0].t) / (bars.length - 1) : 60_000;
  const timeX = (value: unknown) => {
    const ms = Date.parse(String(value));
    if (!bars.length || !Number.isFinite(ms)) return null;
    const x = X(0) + 5 + ((ms - bars[0].t) / (spacing || 1)) * 17;
    return Math.min(right, Math.max(15, x));
  };
  const point = (value: unknown) => {
    const p = value as { time?: unknown; price?: unknown } | undefined;
    const x = timeX(p?.time);
    return x == null || p?.price == null ? null : { x, y: Y(num(p.price)), price: num(p.price) };
  };
  const shapes: Shape[] = [];
  for (const item of input.annotations) {
    if (!shownOn(item, input.frame)) continue;
    const label = typeof item.label === "string" ? item.label : undefined;
    switch (item.type) {
      case "price":
      case "horizontal_line":
        shapes.push({
          kind: "hline",
          y: Y(num(item.price)),
          x1: 15,
          x2: right,
          label,
          tone: "agent",
          dash: true,
        });
        break;
      case "note": {
        const text = (typeof item.text === "string" && item.text) || label || "";
        const x = item.time != null ? (timeX(item.time) ?? right) : right - 4;
        const y = item.price != null ? Y(num(item.price)) : top + fs;
        shapes.push({ kind: "note", x, y, text, tone: "agent" });
        break;
      }
      case "price_zone": {
        const a = point(item.start);
        const b = point(item.end);
        if (!a || !b) break;
        shapes.push({
          kind: "box",
          x: Math.min(a.x, b.x),
          y: Math.min(a.y, b.y),
          w: Math.max(2, Math.abs(b.x - a.x)),
          h: Math.max(2, Math.abs(b.y - a.y)),
          tone: "agent",
          label,
        });
        break;
      }
      case "fibonacci": {
        const a = point(item.start);
        const b = point(item.end);
        if (!a || !b) break;
        const levels = Array.isArray(item.levels)
          ? (item.levels as unknown[]).map(Number)
          : [0, 0.236, 0.382, 0.5, 0.618, 1];
        for (const level of levels)
          shapes.push({
            kind: "hline",
            y: Y(b.price + (a.price - b.price) * level),
            x1: Math.min(a.x, b.x),
            x2: right,
            label: `${(level * 100).toFixed(1)}%`,
            tone: "agent",
          });
        break;
      }
      case "scenario": {
        const a = point(item.start);
        const b = point(item.end);
        if (!a || !b || item.stop == null) break;
        const x1 = Math.min(a.x, b.x);
        const x2 = Math.max(a.x, b.x);
        shapes.push({ kind: "hline", y: a.y, x1, x2, label: input.labels.entry, tone: "agent" });
        shapes.push({ kind: "hline", y: b.y, x1, x2, label: input.labels.target, tone: "up" });
        shapes.push({
          kind: "hline",
          y: Y(num(item.stop)),
          x1,
          x2,
          label: input.labels.stop,
          tone: "down",
        });
        break;
      }
      case "channel": {
        const a = point(item.start);
        const b = point(item.end);
        const c = point(item.parallel);
        if (!a || !b || !c) break;
        shapes.push({ kind: "segment", x1: a.x, y1: a.y, x2: b.x, y2: b.y, tone: "agent" });
        // The parallel line keeps the slope and passes through the third point.
        const slope = (b.y - a.y) / (b.x - a.x || 1);
        const dy = c.y - (a.y + slope * (c.x - a.x));
        shapes.push({
          kind: "segment",
          x1: a.x,
          y1: a.y + dy,
          x2: b.x,
          y2: b.y + dy,
          tone: "agent",
        });
        break;
      }
      case "ray": {
        const a = point(item.start);
        const b = point(item.end);
        if (!a || !b) break;
        const slope = (b.y - a.y) / (b.x - a.x || 1);
        const x2 = b.x >= a.x ? right : 15;
        shapes.push({
          kind: "segment",
          x1: a.x,
          y1: a.y,
          x2,
          y2: a.y + slope * (x2 - a.x),
          tone: "agent",
        });
        break;
      }
      case "arrow":
      case "trend_line": {
        const a = point(item.start);
        const b = point(item.end);
        if (!a || !b) break;
        shapes.push({
          kind: "segment",
          x1: a.x,
          y1: a.y,
          x2: b.x,
          y2: b.y,
          tone: "agent",
          arrow: item.type === "arrow",
        });
        break;
      }
    }
  }
  // Indicator values align to the scene's candles by time.
  const at = (values: (number | null)[], bar: Bar) => {
    const index = input.indicatorTimes.indexOf(bar.t);
    return index < 0 ? null : values[index];
  };
  const polyline = (values: (number | null)[], y: (v: number) => number) => {
    const points = bars
      .map((bar, i) => {
        const value = at(values, bar);
        return value == null ? null : `${f(X(i) + 5)},${f(y(value))}`;
      })
      .filter(Boolean);
    return points.length > 1 ? points.join(" ") : null;
  };
  const priceLines: Layout["priceLines"] = [];
  for (const indicator of overlays)
    for (const [key, values] of Object.entries(indicator.series)) {
      const points = polyline(values, Y);
      if (points) priceLines.push({ name: `${indicator.name}:${key}`, points });
    }
  let pane: Pane | null = null;
  if (oscillators.length) {
    const indicator = oscillators[0];
    const paneTop = bottom + fs * 1.6;
    const paneBottom = axis - fs * 0.4;
    const visible = Object.values(indicator.series)
      .flatMap((values) => bars.map((bar) => at(values, bar)))
      .filter((v): v is number => v != null);
    const fixed = indicator.name === "rsi";
    let v0 = fixed ? 0 : Math.min(...visible, 0);
    let v1 = fixed ? 100 : Math.max(...visible, 0);
    if (!Number.isFinite(v0) || !Number.isFinite(v1) || v0 === v1) {
      v0 = 0;
      v1 = 1;
    }
    const py = (v: number) => paneTop + ((v1 - v) / (v1 - v0)) * (paneBottom - paneTop);
    const lines: Pane["lines"] = [];
    for (const [key, values] of Object.entries(indicator.series)) {
      const points = polyline(values, py);
      if (points) lines.push({ name: `${indicator.name}:${key}`, points });
    }
    pane = {
      label: `${indicator.name.toUpperCase()} ${indicator.period}`,
      top: paneTop,
      bottom: paneBottom,
      lines,
      guides: fixed
        ? [
            { y: py(70), label: "70" },
            { y: py(30), label: "30" },
          ]
        : v0 < 0 && v1 > 0
          ? [{ y: py(0), label: "0" }]
          : [],
    };
  }
  return { VW, VH, fs, right, top, bottom, bars, X, Y, grid, times, shapes, priceLines, pane };
}
