import assert from "node:assert/strict";
import { test } from "node:test";
import { AvatarMotion, avatarBarPath } from "../../packages/core/src/avatar-motion";
import { avatarState } from "../../packages/core/src/avatar-state";
import {
  AVATAR_FACES,
  avatarPersonality,
  avatarTurn,
  FACE_TOKENS,
  FACIAL_GEOMETRY,
  GEOMETRY,
  GLYPH_SCALE,
  idleAvatarPose,
  PARTICLES,
  poseAt,
  resolveAvatarFace,
  STATE_IDS,
  segmentPoints,
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
  const profile = avatarPersonality();
  const samples = Array.from({ length: 1001 }, (_, index) =>
    idleAvatarPose((index * profile.cycleSeconds) / 1000),
  );
  assert.ok(samples.some((pose) => pose.gazeX < -0.35));
  assert.ok(samples.some((pose) => pose.gazeX > 0.35));
  assert.equal(idleAvatarPose(profile.cycleSeconds - profile.spinSeconds).yaw, 0);
  assert.ok(idleAvatarPose(profile.cycleSeconds - 0.001).yaw > Math.PI * 1.99);
  assert.equal(idleAvatarPose(profile.cycleSeconds).yaw, 0);
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

test("face catalog preserves legacy values and every selectable expression fits the persisted field", () => {
  assert.equal(AVATAR_FACES.length, 16);
  assert.equal(new Set(AVATAR_FACES.map((face) => face.id)).size, AVATAR_FACES.length);
  for (const face of AVATAR_FACES) {
    assert.ok(face.id.length <= 24);
    assert.equal(resolveAvatarFace(face.id), face.id);
  }
  for (const legacy of [undefined, null, "organic", "diamond", "circle", "not-a-face"])
    assert.equal(resolveAvatarFace(legacy), "orb");
});

test("selected faces are distinct white and teal geometry inside the visor, never activity replacements", () => {
  const signatures = new Set();
  for (const face of AVATAR_FACES) {
    signatures.add(JSON.stringify(poseAt("waiting", 0.25, undefined, "face-owner", face.id)));
    for (const phase of [0, 0.25, 0.53, 0.82, 0.99]) {
      const bars = poseAt("waiting", phase, "#ff0000", "face-owner", face.id);
      assert.equal(bars.length, PARTICLES);
      const visible = bars.filter((bar) => bar.w > 1);
      assert.ok(visible.length >= 3 && visible.length <= 8);
      for (const bar of visible) {
        assert.ok(Object.values(bar).every(Number.isFinite));
        assert.ok(
          [
            [248, 248, 251],
            [31, 212, 179],
          ].some((color) =>
            color.every((channel, index) => channel === [bar.r, bar.g, bar.b][index]),
          ),
        );
        for (const [x, y] of segmentPoints(bar)) {
          const px = 200 + (x - 200) * 1.1,
            py = 200.5 + (y - 200.5) * 1.1;
          const half = (bar.w * 1.1) / 2;
          assert.ok(
            px - half >= GEOMETRY.face.x && px + half <= GEOMETRY.face.x + GEOMETRY.face.width,
            face.id,
          );
          assert.ok(
            py - half >= GEOMETRY.face.y && py + half <= GEOMETRY.face.y + GEOMETRY.face.height,
            face.id,
          );
        }
      }
    }
    for (const state of STATE_IDS.filter((state) => state !== "waiting"))
      assert.deepEqual(
        poseAt(state, 0.37, undefined, "face-owner", face.id),
        poseAt(state, 0.37, undefined, "face-owner"),
      );
  }
  assert.equal(signatures.size, AVATAR_FACES.length);
  assert.ok(poseAt("waiting", 0, undefined, "", "face-smile").some((bar) => bar.k !== 0));
});

test("native face changes morph from the displayed expression and reduced motion stays static", () => {
  const sampler = new AvatarMotion("waiting", "owner", "face-smile");
  const before = sampler.frame(0);
  sampler.setFace("face-wink");
  assert.deepEqual(sampler.frame(0), before);
  for (let i = 0; i < 40; i++) sampler.frame(1 / 30);
  assert.notDeepEqual(sampler.frame(0), before);
  assert.deepEqual(sampler.frame(0, true), sampler.frame(0.1, true));
  sampler.setState("writing");
  for (let i = 0; i < 40; i++) sampler.frame(1 / 30);
  const writing = sampler.frame(0);
  sampler.setFace("face-happy");
  assert.deepEqual(sampler.frame(0), writing);
});

test("idle personality is calm with rare slower full turns and bounded gentle gaze", () => {
  for (const identity of ["", ...Array.from({ length: 40 }, (_, i) => `calm-${i}`)]) {
    const profile = avatarPersonality(identity);
    assert.ok(profile.cycleSeconds >= 18 && profile.cycleSeconds <= 30);
    assert.ok(profile.spinSeconds >= 2.4 && profile.spinSeconds <= 3);
    assert.ok(profile.tempo <= 0.65);
    assert.ok(profile.gazeXFrequency <= 0.25 && profile.gazeYFrequency <= 0.18);
    assert.ok(profile.gazeXAmplitude <= 0.5 && profile.gazeYAmplitude <= 0.17);
  }
});

test("canonical facial geometry preserves the original shell, display and stroke hierarchy", () => {
  assert.deepEqual(GEOMETRY.shell, { cx: 200, cy: 200, r: 177 });
  assert.deepEqual(GEOMETRY.face, { x: 78, y: 123, width: 244, height: 155, rx: 77.5 });
  assert.equal(FACIAL_GEOMETRY.outerShell, GEOMETRY.shell);
  assert.equal(FACIAL_GEOMETRY.faceDisplay, GEOMETRY.face);
  assert.equal(FACIAL_GEOMETRY.viewBox, GEOMETRY.viewBox);
  const checkFrozen = (value: object) => {
    assert.ok(Object.isFrozen(value));
    for (const part of Object.values(value))
      if (part && typeof part === "object") checkFrozen(part);
  };
  checkFrozen(FACE_TOKENS);
  checkFrozen(FACIAL_GEOMETRY);
  const { primary, curvedEye, secondary, eyebrow, accent } = FACE_TOKENS.stroke;
  assert.ok(
    primary > curvedEye && curvedEye > secondary && secondary > eyebrow && eyebrow >= accent,
  );
  assert.ok(
    (accent * GLYPH_SCALE * 40) / 356 > 0.9,
    "tertiary strokes remain near one physical CSS pixel at40px",
  );
  assert.ok(FACE_TOKENS.shape.laughingMouthScale <= 1.15);
  assert.ok(
    FACE_TOKENS.spacing.mouthLine - FACE_TOKENS.spacing.eyeLine > FACE_TOKENS.shape.eyeHeight * 0.9,
  );
});

test("every facial preset stays inside its safe region and the curved visor at idle gaze extremes", () => {
  const safe = FACIAL_GEOMETRY.facialSafeArea;
  const { width, height, rx } = GEOMETRY.face;
  const faces = AVATAR_FACES.filter((face) => face.id !== "orb");
  const center = FACIAL_GEOMETRY;
  for (const { id } of faces)
    for (const identity of ["", "face-owner", "same-name-another-id"]) {
      for (let tick = 0; tick <= 40; tick++) {
        const bars = poseAt("waiting", tick / 40, undefined, identity, id);
        for (const bar of bars.filter((bar) => bar.w > 1 && bar.o > 0.01)) {
          for (const gx of [-0.5, 0, 0.5])
            for (const gy of [-0.17, 0, 0.17]) {
              const depth =
                (1 - gx * Math.max(-1, Math.min(1, (bar.cx - 200) / 60)) * 0.14) * GLYPH_SCALE;
              const shifted = {
                ...bar,
                cx:
                  center.horizontalCenter +
                  (bar.cx - center.horizontalCenter) * GLYPH_SCALE +
                  gx * 6,
                cy: center.verticalCenter + (bar.cy - center.verticalCenter) * GLYPH_SCALE + gy * 4,
                L: bar.L * depth,
                k: bar.k / depth,
              };
              const half = (bar.w * depth) / 2;
              for (const [x, y] of segmentPoints(shifted, 40)) {
                assert.ok(
                  x - half >= safe.x && x + half <= safe.x + safe.width,
                  `${id} horizontal safe area`,
                );
                assert.ok(
                  y - half >= safe.y && y + half <= safe.y + safe.height,
                  `${id} vertical safe area`,
                );
                const endDistance = Math.max(
                  0,
                  Math.abs(x - center.horizontalCenter) - (width - height) / 2,
                );
                assert.ok(
                  Math.hypot(endDistance, y - center.verticalCenter) + half <= rx,
                  `${id} curved visor containment`,
                );
              }
            }
        }
      }
    }
});

test("brows, eye centers and mouths stay optically aligned and separate", () => {
  const T = FACE_TOKENS;
  const at = (face: string) => poseAt("waiting", 0, undefined, "", face);
  const vertical = at("face-smile");
  assert.equal(vertical[0].cx, FACIAL_GEOMETRY.eyeAnchors.left.x);
  assert.equal(vertical[1].cy, FACIAL_GEOMETRY.eyeAnchors.right.y);
  for (const face of ["face-smile", "face-wink", "face-angry", "face-worried", "face-surprised"]) {
    const bars = at(face);
    assert.equal(bars[0].cy, FACIAL_GEOMETRY.eyeAnchors.left.y);
    assert.equal(bars[0].w, T.stroke.primary);
  }
  const distance = (a: (typeof vertical)[number], b: (typeof vertical)[number]) =>
    Math.min(
      ...segmentPoints(a, 40).flatMap(([ax, ay]) =>
        segmentPoints(b, 40).map(([bx, by]) => Math.hypot(ax - bx, ay - by)),
      ),
    ) -
    (a.w + b.w) / 2;
  for (const face of ["face-angry", "face-worried"]) {
    const bars = at(face);
    assert.ok(distance(bars[0], bars[2]) >= T.spacing.minimumSeparation - 0.1, face);
    assert.ok(distance(bars[1], bars[3]) >= T.spacing.minimumSeparation - 0.1, face);
  }
  const surprised = at("face-surprised");
  assert.ok(distance(surprised[0], surprised[2]) >= T.spacing.minimumSeparation);
  const laugh = at("face-laugh"),
    smile = at("face-smile"),
    excited = at("face-excited");
  assert.equal(laugh[2].w, smile[2].w);
  assert.equal(excited[3].w, smile[2].w);
  assert.ok(distance(laugh[0], laugh[2]) >= T.spacing.minimumSeparation);
});

test("every face-to-face transition remains inside the actual curved display before clipping", () => {
  const { face } = GEOMETRY;
  for (const from of AVATAR_FACES)
    for (const to of AVATAR_FACES) {
      const sampler = new AvatarMotion("waiting", "", from.id);
      sampler.setFace(to.id);
      for (let frame = 0; frame < 40; frame++) {
        for (const bar of sampler.frame(1 / 30).filter((bar) => bar.w > 1 && bar.o > 0.01)) {
          for (const [x, y] of segmentPoints(bar, 24)) {
            const px = 200 + (x - 200) * GLYPH_SCALE,
              py = 200.5 + (y - 200.5) * GLYPH_SCALE;
            const half = (bar.w * GLYPH_SCALE) / 2;
            const endDistance = Math.max(0, Math.abs(px - 200) - (face.width - face.height) / 2);
            assert.ok(
              Math.hypot(endDistance, py - 200.5) + half <= face.rx,
              `${from.id}->${to.id} frame${frame} escaped the display`,
            );
          }
        }
      }
    }
});
