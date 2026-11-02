export type AvatarStateId =
  | "thinking"
  | "executing"
  | "inspecting"
  | "writing"
  | "searching"
  | "working"
  | "listening"
  | "reviewing"
  | "waiting"
  | "angry"
  | "sending"
  | "speaking"
  | "success"
  | "error"
  | "warning"
  | "analyzing"
  | "learning"
  | "sleeping"
  | "celebrating"
  | "connecting";

export const STATE_IDS: readonly AvatarStateId[];

export const GEOMETRY: {
  readonly viewBox: string;
  readonly shell: { readonly cx: number; readonly cy: number; readonly r: number };
  readonly face: {
    readonly x: number;
    readonly y: number;
    readonly width: number;
    readonly height: number;
    readonly rx: number;
  };
  readonly barWidth: number;
  readonly barX: readonly number[];
  readonly centerY: number;
  readonly floorY: number;
  readonly restHeights: readonly number[];
};

export interface BarPose {
  /** centre */ cx: number;
  cy: number;
  /** centre-line length */ L: number;
  /** heading at the middle, degrees (0 = right, 90 = down) */ th: number;
  /** curvature (1 / radius, 0 = straight) */ k: number;
  /** stroke width */ w: number;
  /** opacity */ o: number;
  /** final colour channels 0…255 */ r: number;
  g: number;
  b: number;
}

export interface MorphPlan {
  perm: number[];
  flip: boolean[];
  rank: number[];
  bow: number[];
}
export function planMorph(from: BarPose[], to: BarPose[]): MorphPlan;
export function morphSegment(
  from: BarPose | null,
  target: BarPose[],
  plan: MorphPlan,
  index: number,
  seconds: number,
  out: BarPose,
): number;

/** Pure sampler: the 4 bar poses of a state at loop phase u (0…1). */
export function poseAt(stateId: AvatarStateId, u: number, accent?: string): BarPose[];
/** Loop length in seconds. */
export function loopSeconds(stateId: AvatarStateId, speed?: number): number;

/** SVG path data of the four resting bars (first paint / SSR). */
export const REST_PATHS: readonly string[];
export const REST_WIDTHS: readonly number[];
export const REST_STROKES: readonly string[];
/** Morph timing (seconds): total travel time and the stagger between signals. */
/** Number of particles that form the one liquid mass. */
export const PARTICLES: number;
/** How large the glyph is drawn inside the visor. */
export const GLYPH_SCALE: number;
export const MORPH: { readonly seconds: number; readonly delay: number };
/** Points along a signal's centre-line. */
export function segmentPoints(
  pose: Pick<BarPose, "cx" | "cy" | "L" | "th" | "k">,
  n?: number,
): [number, number][];
