// Regenerates test/avatar/fixtures/js_vectors.json from the production JavaScript/TypeScript
// avatar sources, so the Dart port can be checked number-for-number.
//
//   node --experimental-strip-types apps/android/test/avatar/tool/generate_js_vectors.mjs
//
// Sources: packages/core/src/{trading-avatar-motion.js,avatar-motion.ts,avatar-state.ts,
// avatar-geometry.ts}. avatar-motion.ts imports "./trading-avatar-motion" without an extension,
// which Node's ESM loader cannot resolve, so a temporary copy with the extension is imported.
import { mkdtempSync, readFileSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { dirname, join, resolve } from "node:path";
import { fileURLToPath, pathToFileURL } from "node:url";

const here = dirname(fileURLToPath(import.meta.url));
const core = resolve(here, "../../../../../packages/core/src");
const motionUrl = pathToFileURL(join(core, "trading-avatar-motion.js")).href;
const engine = await import(motionUrl);
const geometry = await import(pathToFileURL(join(core, "avatar-geometry.ts")).href);
const stateModule = await import(pathToFileURL(join(core, "avatar-state.ts")).href);
const temp = mkdtempSync(join(tmpdir(), "avatar-motion-"));
const adapter = readFileSync(join(core, "avatar-motion.ts"), "utf8").replace(
  '"./trading-avatar-motion"',
  JSON.stringify(motionUrl),
);
writeFileSync(join(temp, "avatar-motion.ts"), adapter);
const { AvatarMotion } = await import(pathToFileURL(join(temp, "avatar-motion.ts")).href);

const identities = [
  "",
  "a",
  "agent-1",
  "geometry-review",
  "0193f3f6-1c7a-7d38-9c2b-4d3e5f6a7b8c",
  "مرحبا",
  "bot_42",
  "x".repeat(40),
];
const faces = engine.AVATAR_FACES.map((face) => face.id);
const bar = (b) => ({ cx: b.cx, cy: b.cy, L: b.L, th: b.th, k: b.k, w: b.w, o: b.o, r: b.r, g: b.g, b: b.b });

const personality = Object.fromEntries(identities.map((id) => [id, { ...engine.avatarPersonality(id) }]));
const colors = identities.map((id) => ({ identity: id, explicit: null, ...geometry.resolveAvatarColor(id) }));
for (const explicit of ["violet", "Executive Violet", "#8B5CF6", "#ec4899", "#abc", "#123456", "#FAFAFA", "purple", ""])
  colors.push({ identity: "agent-1", explicit, ...geometry.resolveAvatarColor("agent-1", explicit) });

const poses = [];
// Identity only shapes the resting state, so other states are sampled once.
for (const state of engine.STATE_IDS)
  for (const u of [0, 0.3, 0.77])
    for (const identity of state === "waiting" ? ["", "geometry-review"] : [""])
      poses.push({ state, u, identity, face: "orb", reaction: 1, bars: engine.poseAt(state, u, undefined, identity, "orb").map(bar) });
for (const face of [...faces, "unknown-face"])
  for (const u of [0.3, 0.52])
    for (const reaction of [1, 0.4])
      poses.push({
        state: "waiting",
        u,
        identity: "agent-1",
        face,
        reaction,
        bars: engine.poseAt("waiting", u, undefined, "agent-1", face, reaction).map(bar),
      });
for (const identity of identities.slice(1, 5))
  for (const u of [0.1, 0.6])
    poses.push({ state: "waiting", u, identity, face: "orb", reaction: 1, bars: engine.poseAt("waiting", u, undefined, identity, "orb").map(bar) });

const plans = [];
for (const [a, b] of [
  ["waiting", "searching"],
  ["searching", "error"],
  ["working", "celebrating"],
  ["success", "waiting"],
]) {
  const from = engine.poseAt(a, 0.2, undefined, "agent-1", "orb");
  const to = engine.poseAt(b, 0, undefined, "agent-1", "orb");
  const plan = engine.planMorph(from, to);
  const steps = [0, 0.1, 0.35, 0.6, 0.94].map((t) =>
    Array.from({ length: engine.PARTICLES }, (_, i) => {
      const out = { cx: 0, cy: 0, L: 0, th: 0, k: 0, w: 0, o: 0 };
      const e = engine.morphSegment(from[i], to, plan, i, t, out);
      return { e, ...out };
    }),
  );
  plans.push({ from: a, to: b, plan: { perm: plan.perm, flip: plan.flip, rank: plan.rank, bow: plan.bow }, steps });
}

const motions = [];
const script = [
  { identity: "agent-1", face: "orb", state: "waiting", ops: [["frame", 0.033, 20], ["state", "searching"], ["frame", 0.033, 12], ["state", "success"], ["frame", 0.05, 25], ["frame", 0.2, 1, true]] },
  { identity: "geometry-review", face: "face-smile", state: "waiting", ops: [["frame", 0.033, 5], ["face", "face-wink"], ["frame", 0.033, 12], ["react"], ["frame", 0.033, 40], ["state", "thinking"], ["frame", 0.033, 10]] },
  { identity: "bot_42", face: "face-laugh", state: "working", ops: [["frame", 0.033, 8], ["state", "waiting"], ["frame", 0.04, 30], ["identity", "agent-1"], ["frame", 0.033, 10]] },
];
for (const run of script) {
  const motion = new AvatarMotion(run.state, run.identity, run.face);
  // Every frame is computed; every third one is recorded (the Dart test does the same).
  const frames = [];
  let count = 0;
  for (const [op, a, n, reduced] of run.ops) {
    if (op === "frame")
      for (let i = 0; i < n; i++) {
        const shown = motion.frame(a, !!reduced).map(bar);
        if (count++ % 3 === 0) frames.push(shown);
      }
    if (op === "state") motion.setState(a);
    if (op === "face") motion.setFace(a);
    if (op === "identity") motion.setIdentity(a);
    if (op === "react") motion.react();
  }
  motions.push({ ...run, frames });
}

const reactions = [];
for (const face of ["orb", "face-smile", "face-sleepy", "face-determined", "nope"])
  for (const p of [0, 0.25, 0.5, 0.8, 1])
    for (const identity of ["", "agent-1", "bot_42"])
      reactions.push({ face, p, identity, value: engine.faceReaction(p, face, identity) });
const idle = [];
for (const face of ["orb", "face-happy", "face-focused"])
  for (const t of [0, 1.7, 9.3, 21.5, 25, 26.2, 40])
    for (const identity of ["", "agent-1", "geometry-review"])
      idle.push({ face, t, identity, value: engine.idleAvatarPose(t, identity, face) });
const turns = [0, 0.4, 1.5, 3, Math.PI, 5].map((yaw) => ({ yaw, value: engine.avatarTurn(yaw) }));
const transforms = [[0, 0, 0], [0.5, -0.3, 0], [-1, 1, 0.8]].map(([gx, gy, poke]) => ({ gx, gy, poke, value: engine.faceTransform(gx, gy, poke) }));
const loops = Object.fromEntries(engine.STATE_IDS.map((id) => [id, engine.loopSeconds(id)]));
const segmentPoints = engine.segmentPoints({ cx: 210, cy: 190, L: 80, th: 30, k: 0.02 }, 8);
const states = [
  [{}, "waiting"],
  [{ working: true }, "working"],
  [{ waiting: true, working: true }, "reviewing"],
  [{ error: true, waiting: true }, "error"],
  [{ voice: { connected: false, phase: "listening", muted: false } }, "connecting"],
  [{ voice: { connected: true, phase: "speaking", muted: true } }, "speaking"],
  [{ voice: { connected: true, phase: "listening", muted: true } }, "waiting"],
  [{ voice: { connected: true, phase: "listening", muted: false } }, "listening"],
  [{ voice: { connected: false, phase: "listening", muted: false, ending: true } }, "waiting"],
].map(([input]) => ({ input, value: stateModule.avatarState(input) }));

// 12 significant digits keep the fixture small; the Dart test allows 1e-7 relative error.
const compact = (_, value) =>
  typeof value === "number" && !Number.isInteger(value) ? Number(value.toPrecision(12)) : value;
writeFileSync(
  resolve(here, "../fixtures/js_vectors.json"),
  JSON.stringify({
    faceTokens: engine.FACE_TOKENS,
    facialGeometry: engine.FACIAL_GEOMETRY,
    personality,
    colors,
    poses,
    plans,
    motions,
    reactions,
    idle,
    turns,
    transforms,
    loops,
    segmentPoints,
    states,
  }, compact),
);
console.log("wrote js_vectors.json");
