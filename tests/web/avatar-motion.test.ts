import assert from "node:assert/strict";
import { test } from "node:test";
import { AvatarMotion, avatarBarPath } from "../../packages/core/src/avatar-motion";
import { avatarState } from "../../packages/core/src/avatar-state";
import {
  avatarTurn,
  GEOMETRY,
  idleAvatarPose,
  PARTICLES,
  poseAt,
  STATE_IDS,
} from "../../packages/core/src/trading-avatar-motion.js";

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

test("waiting uses four bottom-aligned capsules with one teal highlight and no wicks", () => {
  for (const phase of [0, 0.2, 0.5, 0.8]) {
    const visible = poseAt("waiting", phase, "#ff0000").filter((bar) => bar.w > 1 && bar.o > 0);
    assert.equal(visible.length, 4);
    for (const [index, bar] of visible.entries()) {
      assert.equal(bar.k, 0);
      assert.equal(bar.th, 90);
      assert.equal(bar.w, GEOMETRY.barWidth);
      assert.ok(Math.abs(bar.cy + (bar.L + bar.w) / 2 - GEOMETRY.floorY) < 0.00001);
      assert.equal(bar.cx, GEOMETRY.barX[index]);
      assert.deepEqual([bar.r, bar.g, bar.b], index === 2 ? [31, 212, 179] : [248, 248, 251]);
      if (phase === 0) assert.equal(bar.L + bar.w, GEOMETRY.restHeights[index]);
    }
  }
  assert.notDeepEqual(poseAt("waiting", 0), poseAt("waiting", 0.2));
});

test("idle look scans both sides and makes a full turn without mirrored back-facing eyes", () => {
  const samples = Array.from({ length: 701 }, (_, index) => idleAvatarPose(index / 100));
  assert.ok(samples.some((pose) => pose.gazeX < -0.7));
  assert.ok(samples.some((pose) => pose.gazeX > 0.7));
  assert.equal(idleAvatarPose(5.8).yaw, 0);
  assert.ok(idleAvatarPose(6.99).yaw > Math.PI * 1.99);
  assert.equal(idleAvatarPose(7).yaw, 0);
  assert.deepEqual(avatarTurn(0), { tx: 0, scaleX: 1, opacity: 1 });
  assert.equal(avatarTurn(Math.PI).opacity, 0);
  assert.equal(avatarTurn(Math.PI / 2).opacity, 0);
  assert.equal(avatarTurn((Math.PI * 3) / 2).opacity, 0);
  assert.equal(avatarTurn(Math.PI * 2).opacity, 1);
  for (const pose of samples) {
    const projected = avatarTurn(pose.yaw);
    assert.ok(Object.values(pose).every(Number.isFinite));
    assert.ok(Object.values(projected).every(Number.isFinite));
    assert.ok(projected.scaleX > 0, "back faces must never mirror the glyph");
    assert.ok(projected.opacity >= 0 && projected.opacity <= 1);
  }
  assert.deepEqual(idleAvatarPose(Infinity), idleAvatarPose(0));
});
