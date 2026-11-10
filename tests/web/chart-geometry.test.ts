import assert from "node:assert/strict";
import test from "node:test";
import { type Bar, layout } from "../../apps/web/src/shell/agent/chart-geometry";

const start = Date.parse("2026-11-10T00:00:00Z");
const bars: Bar[] = Array.from({ length: 40 }, (_, i) => ({
  t: start + i * 15 * 60_000,
  o: 100 + i,
  h: 104 + i,
  l: 99 + i,
  c: 102 + i,
}));
const at = (i: number) => new Date(bars[i].t).toISOString();
const base = {
  width: 600,
  height: 310,
  bars,
  frame: "15m",
  indicators: [],
  indicatorTimes: [],
  labels: { entry: "Entry", stop: "Stop", target: "Target" },
};

test("each annotation kind keeps its own form (Q37)", () => {
  const g = layout({
    ...base,
    annotations: [
      {
        type: "price_zone",
        start: { time: at(30), price: 120 },
        end: { time: at(35), price: 125 },
      },
      { type: "fibonacci", start: { time: at(30), price: 110 }, end: { time: at(35), price: 130 } },
      {
        type: "scenario",
        start: { time: at(30), price: 120 },
        end: { time: at(36), price: 130 },
        stop: 115,
      },
      { type: "note", time: at(32), price: 128, text: "Breakout" },
      {
        type: "channel",
        start: { time: at(28), price: 110 },
        end: { time: at(36), price: 120 },
        parallel: { time: at(30), price: 125 },
      },
    ],
  });
  const kinds = g.shapes.map((shape) => shape.kind);
  assert.equal(kinds.filter((k) => k === "box").length, 1);
  // Six default Fibonacci levels plus the scenario's entry, target and stop.
  const lines = g.shapes.filter((shape) => shape.kind === "hline");
  assert.equal(lines.length, 9);
  assert.deepEqual(
    lines.slice(6).map((line) => (line.kind === "hline" ? [line.label, line.tone] : null)),
    [
      ["Entry", "agent"],
      ["Target", "up"],
      ["Stop", "down"],
    ],
  );
  const note = g.shapes.find((shape) => shape.kind === "note");
  assert.equal(note?.kind === "note" && note.text, "Breakout");
  assert.equal(kinds.filter((k) => k === "segment").length, 2);
});

test("an annotation scoped to other timeframes is not drawn", () => {
  const g = layout({
    ...base,
    annotations: [{ type: "horizontal_line", price: 120, timeframes: ["1h"] }],
  });
  assert.equal(g.shapes.length, 0);
});

test("Fibonacci level L sits at start + (end − start) × L, labelled by its percentage", () => {
  const g = layout({
    ...base,
    annotations: [
      { type: "fibonacci", start: { time: at(30), price: 110 }, end: { time: at(35), price: 130 } },
    ],
  });
  const lines = g.shapes.filter((shape) => shape.kind === "hline");
  assert.deepEqual(
    lines.map((line) => (line.kind === "hline" ? [line.label, +line.price.toFixed(3)] : null)),
    [
      ["0.0%", 110],
      ["23.6%", 114.72],
      ["38.2%", 117.64],
      ["50.0%", 120],
      ["61.8%", 122.36],
      ["100.0%", 130],
    ],
  );
  for (const line of lines)
    if (line.kind === "hline") assert.ok(Math.abs(line.y - g.Y(line.price)) < 1e-9);
});

test("a ray and a trend line anchored before the window keep their true slope", () => {
  // Anchors 60 and 50 bars before the first bar: far left of the window.
  const before = (k: number) => new Date(bars[0].t - k * 15 * 60_000).toISOString();
  const g = layout({
    ...base,
    annotations: [
      {
        type: "trend_line",
        start: { time: before(60), price: 40 },
        end: { time: at(30), price: 132 },
      },
      { type: "ray", start: { time: before(50), price: 50 }, end: { time: before(40), price: 60 } },
    ],
  });
  const [trend, ray] = g.shapes;
  assert.ok(trend.kind === "segment" && ray.kind === "segment");
  // The first anchor lies left of the plot, never pulled onto its edge.
  assert.ok(trend.x1 < g.plot.x && ray.x1 < g.plot.x);
  const pxPerBar = 17;
  const trendSlope = (trend.y2 - trend.y1) / (trend.x2 - trend.x1);
  const expected = (g.Y(132) - g.Y(40)) / ((60 + 30) * pxPerBar);
  assert.ok(Math.abs(trendSlope - expected) < 1e-9, "the trend line's slope is exact");
  const raySlope = (ray.y2 - ray.y1) / (ray.x2 - ray.x1);
  assert.ok(Math.abs(raySlope - (g.Y(60) - g.Y(50)) / (10 * pxPerBar)) < 1e-9);
  assert.equal(ray.x2, g.right, "the ray runs on to the right edge");
});

test("a scenario at the latest bar keeps a readable width with its labels in the plot", () => {
  const g = layout({
    ...base,
    annotations: [
      {
        type: "scenario",
        start: { time: at(39), price: 140 },
        end: { time: new Date(bars[39].t + 60_000).toISOString(), price: 145 },
        stop: 138,
      },
    ],
  });
  for (const shape of g.shapes) {
    assert.ok(shape.kind === "hline");
    assert.ok(shape.x2 - shape.x1 >= 72);
    assert.ok(shape.x1 >= g.plot.x && shape.x2 <= g.right);
  }
});

test("each oscillator has its own lower pane; RSI is never drawn on the price scale", () => {
  const rsi = bars.map((_, i) => (i < 14 ? null : 30 + i));
  const atr = bars.map((_, i) => (i < 14 ? null : 1 + i / 10));
  const g = layout({
    ...base,
    annotations: [],
    indicators: [
      { name: "rsi", period: 14, series: { value: rsi } },
      { name: "atr", period: 14, series: { value: atr } },
      { name: "sma", period: 5, series: { value: bars.map((b) => b.c) } },
    ],
    indicatorTimes: bars.map((b) => b.t),
  });
  assert.deepEqual(
    g.panes.map((pane) => pane.label),
    ["RSI 14", "ATR 14"],
  );
  assert.ok(g.panes[0].top > g.bottom && g.panes[1].top > g.panes[0].bottom);
  for (const pane of g.panes) {
    const ys = pane.lines[0].points.split(" ").map((p) => Number(p.split(",")[1]));
    // Points are written to 0.1 units.
    for (const y of ys)
      assert.ok(y >= pane.top - 0.05 && y <= pane.bottom + 0.05, `y ${y} in ${pane.label}`);
  }
  assert.deepEqual(
    g.priceLines.map((line) => line.name),
    ["sma:value"],
  );
  assert.equal(g.plot.y + g.plot.h, g.bottom, "the price clip ends above the panes");
});

test("a scenario at the latest bar ending 8 bars ahead stays 72 wide inside the plot", () => {
  const ahead = new Date(bars[39].t + 8 * 15 * 60_000).toISOString();
  const g = layout({
    ...base,
    annotations: [
      {
        type: "scenario",
        start: { time: at(39), price: 140 },
        end: { time: ahead, price: 145 },
        stop: 138,
      },
    ],
  });
  assert.equal(g.shapes.length, 3);
  for (const shape of g.shapes) {
    assert.ok(shape.kind === "hline");
    assert.ok(shape.x2 <= g.right, "the visible end");
    assert.ok(shape.x2 - shape.x1 >= 72, `width ${shape.x2 - shape.x1}`);
    assert.ok(shape.x1 >= g.plot.x, "the label starts inside the plot");
  }
});

test("labels of drawings older than the window stay inside the plot", () => {
  const before = (k: number) => new Date(bars[0].t - k * 15 * 60_000).toISOString();
  const g = layout({
    ...base,
    annotations: [
      {
        type: "price_zone",
        start: { time: before(20), price: 120 },
        end: { time: at(10), price: 125 },
        label: "Supply",
      },
      { type: "note", time: before(30), price: 128, text: "An early note that is long" },
      { type: "note", text: "No price" },
    ],
  });
  const box = g.shapes.find((shape) => shape.kind === "box");
  assert.ok(box?.kind === "box" && box.x < g.plot.x && box.lx >= g.plot.x);
  const [early, unpriced] = g.shapes.filter((shape) => shape.kind === "note");
  assert.ok(early.kind === "note" && early.anchor === "start" && early.x >= g.plot.x);
  // The text's baseline sits 0.6 fs above the dot; its glyphs rise about 0.8 fs above that.
  assert.ok(unpriced.kind === "note");
  assert.ok(unpriced.ty - g.fs * 0.8 >= g.plot.y, "glyph tops in the clip");
});

/** Where a note's text starts, on the same width estimate as the layout. */
const textStart = (
  g: ReturnType<typeof layout>,
  note: { anchor: string; tx: number; text: string },
) => (note.anchor === "start" ? note.tx : note.tx - (note.text.length * g.fs * 0.6 + 8));

test("a long note at the right edge on a phone starts inside the plot", () => {
  const text = "A long note the agent wrote at the latest bar";
  assert.ok(text.length >= 43);
  const g = layout({
    ...base,
    width: 330,
    height: 170,
    annotations: [
      { type: "note", time: at(39), price: 130, text },
      { type: "note", text },
    ],
  });
  const notes = g.shapes.filter((shape) => shape.kind === "note");
  assert.equal(notes.length, 2);
  for (const note of notes) {
    assert.ok(note.kind === "note");
    const start = textStart(g, note);
    assert.ok(start >= g.plot.x && start <= g.right - g.fs, `text start ${start}`);
  }
});

test("a zone wholly older than the window shows no label; a note above the range is not pinned", () => {
  const before = (k: number) => new Date(bars[0].t - k * 15 * 60_000).toISOString();
  const g = layout({
    ...base,
    annotations: [
      {
        type: "price_zone",
        start: { time: before(20), price: 120 },
        end: { time: before(10), price: 125 },
        label: "Old supply",
      },
      { type: "note", time: at(20), price: 900, text: "Far above" },
    ],
  });
  const box = g.shapes.find((shape) => shape.kind === "box");
  assert.ok(box?.kind === "box" && box.label === undefined);
  const note = g.shapes.find((shape) => shape.kind === "note");
  assert.ok(note?.kind === "note" && note.y < g.plot.y, "cut by the clip like other drawings");
});

test("four oscillators on a phone: each pane keeps its height, never inverted, the rest counted", () => {
  const series = (k: number) => ({ value: bars.map((_, i) => (i < 5 ? null : k + i)) });
  const g = layout({
    ...base,
    width: 330,
    height: 170,
    annotations: [],
    indicators: [
      { name: "rsi", period: 14, series: series(30) },
      { name: "atr", period: 14, series: series(1) },
      { name: "macd", period: 12, series: { macd: series(0).value, signal: series(1).value } },
      { name: "rsi", period: 7, series: series(40) },
    ],
    indicatorTimes: bars.map((b) => b.t),
  });
  assert.ok(g.panes.length >= 1);
  for (const pane of g.panes) assert.ok(pane.bottom - pane.top >= g.fs * 2, `${pane.label} height`);
  assert.equal(
    g.panes.length + g.panes.reduce((sum, pane) => sum + pane.more, 0),
    4,
    "every oscillator is drawn or counted",
  );
  assert.ok(g.bottom - g.top >= (g.VH - g.top) * 0.35, "the candles keep their share");
});

test("an in-range note at the top of a phone plot keeps its text inside the plot", () => {
  const g = layout({
    ...base,
    width: 330,
    height: 170,
    annotations: [{ type: "note", time: at(20), price: 143, text: "Top" }],
    indicators: [{ name: "rsi", period: 14, series: { value: bars.map((_, i) => 40 + i) } }],
    indicatorTimes: bars.map((b) => b.t),
  });
  const note = g.shapes.find((shape) => shape.kind === "note");
  assert.ok(note?.kind === "note");
  assert.ok(note.y >= g.plot.y && note.y - g.fs * 1.4 < g.plot.y, "in range, near the top");
  // Glyphs rise about 0.8 fs above the baseline and descend about 0.2 fs below it.
  assert.ok(note.ty - g.fs * 0.8 >= g.plot.y, `text top ${note.ty - g.fs * 0.8}`);
  assert.ok(note.ty + g.fs * 0.2 <= g.plot.y + g.plot.h, "text bottom");
});
