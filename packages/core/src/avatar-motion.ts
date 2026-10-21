import {
  type AvatarStateId,
  type BarPose,
  GLYPH_SCALE,
  loopSeconds,
  MORPH,
  morphSegment,
  planMorph,
  poseAt,
  segmentPoints,
} from "./trading-avatar-motion";

/** DOM-free adapter of the supplied engine for native SVG. Retargets the mass on screen. */
export class AvatarMotion {
  private state: AvatarStateId;
  private phase = 0;
  private elapsed = MORPH.seconds;
  private shown: BarPose[];
  private from: BarPose[] | null = null;
  private plan;

  constructor(state: AvatarStateId = "waiting") {
    this.state = state;
    this.shown = poseAt(state, 0);
    this.plan = planMorph(this.shown, this.shown);
  }

  setState(state: AvatarStateId) {
    if (state === this.state) return;
    this.from = this.shown.map((bar) => ({ ...bar }));
    this.state = state;
    this.phase = 0;
    this.elapsed = 0;
    this.plan = planMorph(this.from, poseAt(state, 0));
  }

  frame(seconds: number, reduced = false): BarPose[] {
    const dt = Math.max(0, Math.min(seconds, 0.1));
    this.phase = reduced ? 0.3 : (this.phase + dt / loopSeconds(this.state)) % 1;
    this.elapsed = reduced ? MORPH.seconds : this.elapsed + dt;
    const target = poseAt(this.state, this.phase);
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
