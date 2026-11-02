import assert from "node:assert/strict";
import { test } from "node:test";
import { AvatarMotion, avatarBarPath } from "../../packages/core/src/avatar-motion";
import { avatarState } from "../../packages/core/src/avatar-state";
import {
  avatarPersonality,
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

test("bot IDs produce stable independent idle personalities, directions and inner expressions", () => {
  const ids = Array.from({ length: 40 }, (_, index) => `owned-bot-${index}`);
  const profiles = ids.map((id) => avatarPersonality(id));
  assert.deepEqual(avatarPersonality("fixed-id"), avatarPersonality("fixed-id"));
  assert.equal(new Set(profiles.map((profile) => profile.direction)).size, 2);
  assert.equal(new Set(profiles.map((profile) => profile.pattern)).size, 4);
  assert.equal(new Set(profiles.map((profile) => profile.cycleSeconds)).size, ids.length);
  assert.equal(new Set(ids.map((id) => JSON.stringify(idleAvatarPose(0.6, id)))).size, ids.length);
  assert.equal(
    new Set(ids.map((id) => JSON.stringify(poseAt("waiting", 0.4, undefined, id)))).size,
    ids.length,
  );
  for (const id of ids) {
    const profile = avatarPersonality(id);
    assert.equal(idleAvatarPose(0, id).yaw, 0, "every bot starts facing forward");
    const nearlyDone = idleAvatarPose(profile.cycleSeconds - 0.001, id).yaw;
    assert.equal(Math.sign(nearlyDone), profile.direction);
    assert.ok(Math.abs(nearlyDone) > Math.PI * 1.99);
    assert.equal(idleAvatarPose(profile.cycleSeconds, id).yaw, 0);
    for (const phase of [0, 0.17, 0.4, 0.65, 0.9]) {
      const visible = poseAt("waiting", phase, undefined, id).filter((bar) => bar.w > 1);
      assert.equal(visible.length, 4);
      for (const [index, bar] of visible.entries()) {
        assert.ok(Object.values(bar).every(Number.isFinite));
        assert.equal(bar.k, 0);
        assert.equal(bar.th, 90);
        assert.deepEqual([bar.r, bar.g, bar.b], index === 2 ? [31, 212, 179] : [248, 248, 251]);
        const top = 200.5 + (bar.cy - (bar.L + bar.w) / 2 - 200.5) * 1.1;
        const bottom = 200.5 + (bar.cy + (bar.L + bar.w) / 2 - 200.5) * 1.1;
        assert.ok(top > GEOMETRY.face.y && bottom < GEOMETRY.face.y + GEOMETRY.face.height);
      }
    }
    for (const state of STATE_IDS.filter((state) => state !== "waiting"))
      assert.deepEqual(poseAt(state, 0.37, undefined, id), poseAt(state, 0.37));
  }
});

test("native adapter retains the same bot's expression and retargets identity without resetting work", () => {
  const first = new AvatarMotion("waiting", "bot-a"),
    same = new AvatarMotion("waiting", "bot-a");
  const other = new AvatarMotion("waiting", "bot-b");
  assert.deepEqual(first.frame(0), same.frame(0));
  assert.notDeepEqual(first.frame(0), other.frame(0));
  for (let index = 0; index < 10; index++) {
    assert.deepEqual(first.frame(1 / 30), same.frame(1 / 30));
  }
  const before = first.frame(0);
  first.setIdentity("bot-a");
  assert.deepEqual(first.frame(0), before);
  first.setIdentity("bot-b");
  assert.deepEqual(first.frame(0), before, "an identity change morphs from what is displayed");
  for (let index = 0; index < 40; index++) first.frame(1 / 30);
  assert.notDeepEqual(first.frame(0), before);
  assert.deepEqual(first.frame(0, true), first.frame(0.1, true));
  first.setState("writing");
  for (let index = 0; index < 40; index++) first.frame(1 / 30);
  const work = first.frame(0);
  first.setIdentity("bot-c");
  assert.deepEqual(first.frame(0), work, "idle personality must not replace a work glyph");
});

test("every personalized inner expression stays continuous across its loop boundary", () => {
  for (let index = 0; index < 80; index++) {
    const id = `continuity-bot-${index}`;
    const before = poseAt("waiting", 1 - 1e-7, undefined, id);
    const after = poseAt("waiting", 1e-7, undefined, id);
    for (let slot = 0; slot < before.length; slot++) {
      for (const key of Object.keys(before[slot]) as (keyof (typeof before)[number])[]) {
        assert.ok(Math.abs(before[slot][key] - after[slot][key]) < 1e-4, `${id} ${slot} ${key}`);
      }
    }
  }
});
