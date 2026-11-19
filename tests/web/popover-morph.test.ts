import assert from "node:assert/strict";
import { test } from "node:test";
import { MORPH, morphGeom, morphOutline } from "../../apps/web/src/shell/lists/morph";
import { springCurve } from "../../apps/web/src/shell/spring";

const ys = (d: string) => [...d.matchAll(/(-?[\d.]+) (-?[\d.]+)/g)].map((m) => Number(m[2]));
const xs = (d: string) => [...d.matchAll(/(-?[\d.]+) (-?[\d.]+)/g)].map((m) => Number(m[1]));

test("the permission menu's spring overshoots about 6% and settles by 330 ms", () => {
  const x = springCurve(MORPH);
  let peak = 0;
  for (let t = 0; t <= 0.6; t += 0.001) peak = Math.max(peak, x(t));
  assert.ok(peak > 1.05 && peak < 1.07, `peak ${peak}`);
  assert.equal(x(0), 0);
  assert.ok(Math.abs(x(MORPH.open / 1000) - 1) < 0.03, `at 330 ms ${x(0.33)}`);
});

test("the panel spans the composer on a phone and stops under the chat header", () => {
  const card = { left: 10, top: 736, width: 370 };
  const chip = { left: 180, right: 320 };
  const g = morphGeom(card, chip, 56, false, 9999);
  assert.deepEqual([g.L, g.W, g.Yc], [36, 318, 736]);
  assert.equal(g.H, 736 - 56 - 8);
  assert.equal(morphGeom(card, chip, 56, false, 339).H, 339);
  assert.equal(morphGeom(card, chip, 700, false, 339).H, 120);
});

test("on a desktop the panel is at most 440 wide, on the chip's side of the composer", () => {
  const card = { left: 68, top: 669, width: 708 };
  const start = morphGeom(card, { left: 600, right: 740 }, 56, true, 321);
  assert.equal(start.W, 440);
  assert.equal(start.L, 68 + 708 - 26 - 440);
  assert.equal(morphGeom(card, { left: 80, right: 200 }, 56, true, 321).L, 68 + 26);
});

test("the outline grows from a drop at the composer's edge into the full panel", () => {
  const g = morphGeom(
    { left: 10, top: 736, width: 370 },
    { left: 180, right: 320 },
    56,
    false,
    339,
  );
  const top = MORPH.padY;
  const edge = g.Yc - (g.top - MORPH.padY);
  const closed = morphOutline(g, 0, 0);
  assert.equal(Math.min(...ys(closed.line)), edge);
  const open = morphOutline(g, 1, 0);
  assert.equal(Math.min(...ys(open.line)), top);
  assert.equal(Math.max(...ys(open.line)), edge);
  // the panel plus its two fillets where it meets the composer
  assert.equal(Math.max(...xs(open.line)) - Math.min(...xs(open.line)), g.W + 2 * MORPH.fillet);
  const over = morphOutline(g, 1.06, 0);
  assert.ok(Math.min(...ys(over.line)) < top, "the top passes its place a little");
  assert.ok(open.fill.startsWith(open.line) && open.fill.endsWith("Z"));
});
