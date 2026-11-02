import {
  type AvatarStateId,
  avatarPersonality,
  type BarPose,
  GLYPH_SCALE,
  loopSeconds,
  MORPH,
  morphSegment,
  planMorph,
  poseAt,
  resolveAvatarFace,
  segmentPoints,
} from "./trading-avatar-motion";

/** DOM-free adapter of the supplied engine for native SVG. Retargets the mass on screen. */
export class AvatarMotion {
  private state: AvatarStateId;
  private identity: string;
  private face: string;
  private reactionTime: number | null = null;
  private phase = 0;
  private elapsed = MORPH.seconds;
  private shown: BarPose[];
  private from: BarPose[] | null = null;
  private plan;

  constructor(state: AvatarStateId = "waiting", identity = "", face = "orb") {
    this.state = state;
    this.identity = identity;
    this.face = resolveAvatarFace(face);
    this.shown = poseAt(state, 0, undefined, identity, this.face);
    this.plan = planMorph(this.shown, this.shown);
  }

  react() {
    if (this.state === "waiting") this.reactionTime = 0;
  }

  setIdentity(identity: string) {
    if (identity === this.identity) return;
    this.identity = identity;
    if (this.state !== "waiting") return;
    this.from = this.shown.map((bar) => ({ ...bar }));
    this.elapsed = 0;
    this.plan = planMorph(
      this.from,
      poseAt(this.state, this.phase, undefined, identity, this.face),
    );
  }

  setFace(face: string) {
    const next = resolveAvatarFace(face);
    if (next === this.face) return;
    this.face = next;
    if (this.state !== "waiting") return;
    this.from = this.shown.map((bar) => ({ ...bar }));
    this.elapsed = 0;
    this.plan = planMorph(
      this.from,
      poseAt(this.state, this.phase, undefined, this.identity, next),
    );
  }

  setState(state: AvatarStateId) {
    if (state === this.state) return;
    this.from = this.shown.map((bar) => ({ ...bar }));
    this.state = state;
    this.phase = 0;
    this.elapsed = 0;
    this.plan = planMorph(this.from, poseAt(state, 0, undefined, this.identity, this.face));
  }

  frame(seconds: number, reduced = false): BarPose[] {
    const dt = Math.max(0, Math.min(seconds, 0.1));
    const tempo = this.state === "waiting" ? avatarPersonality(this.identity).tempo : 1;
    this.phase = reduced ? 0.3 : (this.phase + (dt * tempo) / loopSeconds(this.state)) % 1;
    this.elapsed = reduced ? MORPH.seconds : this.elapsed + dt;
    if (reduced || this.state !== "waiting") this.reactionTime = null;
    if (this.reactionTime !== null) {
      this.reactionTime += dt;
      if (this.reactionTime >= avatarPersonality(this.identity).spinSeconds)
        this.reactionTime = null;
    }
    const reaction =
      this.reactionTime === null
        ? 1
        : this.reactionTime / avatarPersonality(this.identity).spinSeconds;
    const target = poseAt(this.state, this.phase, undefined, this.identity, this.face, reaction);
    for (let i = 0; i < this.shown.length; i++) {
      const bar = this.shown[i];
      const source = this.from?.[i] ?? null;
      const t = morphSegment(
        this.elapsed < MORPH.seconds ? source : null,
        target,
        this.plan,
        i,
        this.elapsed,
        bar,
      );
      const end = target[this.plan.perm[i]];
      for (const key of ["r", "g", "b"] as const)
        bar[key] = source ? source[key] + (end[key] - source[key]) * t : end[key];
    }
    return this.shown.map((bar) => ({ ...bar }));
  }
}

export function avatarBarPath(bar: BarPose): string {
  const points = segmentPoints(
    {
      ...bar,
      cx: 200 + (bar.cx - 200) * GLYPH_SCALE,
      cy: 200.5 + (bar.cy - 200.5) * GLYPH_SCALE,
      L: bar.L * GLYPH_SCALE,
      k: bar.k / GLYPH_SCALE,
    },
    Math.min(32, Math.ceil(Math.abs(bar.k * bar.L) * 9) + 1),
  );
  return points
    .map(([x, y], i) => `${i ? "L" : "M"}${Math.round(x * 10) / 10} ${Math.round(y * 10) / 10}`)
    .join("");
}
