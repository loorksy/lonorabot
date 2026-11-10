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

test("oscillators get their own lower pane; RSI is never drawn on the price scale", () => {
  const rsi = bars.map((_, i) => (i < 14 ? null : 30 + i));
  const g = layout({
    ...base,
    annotations: [],
    indicators: [
      { name: "rsi", period: 14, series: { value: rsi } },
      { name: "sma", period: 5, series: { value: bars.map((b) => b.c) } },
    ],
    indicatorTimes: bars.map((b) => b.t),
  });
  assert.ok(g.pane);
  assert.equal(g.pane.label, "RSI 14");
  assert.ok(g.pane.top > g.bottom, "the pane sits under the candles");
  const ys = g.pane.lines[0].points.split(" ").map((p) => Number(p.split(",")[1]));
  for (const y of ys) assert.ok(y >= g.pane.top && y <= g.pane.bottom, `RSI y ${y} in its pane`);
  assert.deepEqual(
    g.priceLines.map((line) => line.name),
    ["sma:value"],
  );
});
