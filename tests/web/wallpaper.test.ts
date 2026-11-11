import assert from "node:assert/strict";
import { test } from "node:test";
import {
  WALL_IDS,
  WALL_LEVEL_IDS,
  wallAlpha,
  wallPreviewAlpha,
  wallState,
} from "../../apps/web/src/conversation/wallpaper.ts";

test("the patterns and the levels keep the reference's order", () => {
  assert.deepEqual(WALL_IDS, ["lonora", "agents", "market", "calm", "none"]);
  assert.deepEqual(WALL_LEVEL_IDS, ["light", "mid", "strong"]);
});

test("a stored choice falls back field by field, never as a whole", () => {
  assert.deepEqual(wallState({}), { id: "lonora", level: "light" });
  assert.deepEqual(wallState({ id: "market", level: "y" }), { id: "market", level: "light" });
  assert.deepEqual(wallState({ id: "x", level: "strong" }), { id: "lonora", level: "strong" });
  assert.deepEqual(wallState({ id: 3, level: null }), { id: "lonora", level: "light" });
});

test("the layer's opacity is the reference's, per level and theme", () => {
  assert.equal(wallAlpha("light", "dark"), 0.1);
  assert.equal(wallAlpha("light", "light"), 0.085);
  assert.equal(wallAlpha("mid", "dark"), 0.15);
  assert.equal(wallAlpha("strong", "light"), 0.17);
});

test("a preview card shows the pattern stronger, up to one half", () => {
  assert.equal(Math.round(wallPreviewAlpha("light", "dark") * 1000), 230);
  assert.equal(Math.round(wallPreviewAlpha("strong", "dark") * 1000), 483);
  assert.ok(wallPreviewAlpha("strong", "dark") <= 0.5);
});
