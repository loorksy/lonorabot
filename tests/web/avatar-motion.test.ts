import assert from "node:assert/strict";
import { test } from "node:test";
import { AvatarMotion, avatarBarPath } from "../../packages/core/src/avatar-motion";
import { avatarState } from "../../packages/core/src/avatar-state";
import { PARTICLES, poseAt, STATE_IDS } from "../../packages/core/src/trading-avatar-motion.js";

test("all supplied states yield finite native and web geometry", () => {
  for (const state of STATE_IDS) {
    for (const phase of [0, 0.17, 0.3, 0.53, 0.89, 1]) {
      const bars = poseAt(state, phase);
      assert.equal(bars.length, PARTICLES);
      for (const bar of bars) {
        assert.ok(Object.values(bar).every(Number.isFinite), `${state} ${phase}`);
        assert.ok(!/NaN|Infinity/.test(avatarBarPath(bar)));
      }
    }
  }
});

test("native state changes start from the mass already displayed, including mid-morph", () => {
  const sampler = new AvatarMotion();
  const before = sampler.frame(0);
  sampler.setState("searching");
  assert.deepEqual(sampler.frame(0), before);
  for (let i = 0; i < 4; i++) sampler.frame(1 / 30);
  const halfway = sampler.frame(0);
  assert.notDeepEqual(halfway, before);
  sampler.setState("speaking");
  assert.deepEqual(sampler.frame(0), halfway);
  for (let i = 0; i < 40; i++) sampler.frame(1 / 30);
  assert.notDeepEqual(sampler.frame(0), halfway);
});

test("reduced motion remains still, and failures retain semantic colours", () => {
  const sampler = new AvatarMotion("error");
  assert.deepEqual(sampler.frame(0, true), sampler.frame(0.1, true));
  assert.deepEqual(poseAt("error", 0.4, "#111111"), poseAt("error", 0.4, "#00ff00"));
  assert.throws(() => poseAt("unsupported" as never, 0));
});

test("activity projections reflect actual call, mute and work states", () => {
  const voice = { connected: false, phase: "listening" as const, muted: false };
  assert.equal(avatarState(), "waiting");
  assert.equal(avatarState({ working: true }), "working");
  assert.equal(avatarState({ waiting: true }), "reviewing");
  assert.equal(avatarState({ voice }), "connecting");
  assert.equal(avatarState({ voice: { ...voice, connected: true } }), "listening");
  assert.equal(avatarState({ voice: { ...voice, connected: true, muted: true } }), "waiting");
  assert.equal(
    avatarState({ voice: { ...voice, connected: true, phase: "speaking" } }),
    "speaking",
  );
  assert.equal(avatarState({ voice, error: true }), "error");
  assert.equal(avatarState({ voice: { ...voice, ending: true } }), "waiting");
});
