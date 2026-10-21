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

export interface MountOptions {
  state?: AvatarStateId;
  /** 0.25 … 4 (1 = normal) */
  speed?: number;
  paused?: boolean;
  /** Any CSS colour. Semantic states (success / error / warning / angry) keep their own colour. */
  accent?: string;
  /** Where the face looks: follow the pointer (default, wanders when idle), idle wandering only, or stay centred. */
  look?: "pointer" | "idle" | "off";
  /** Tapping the avatar pushes the face in with a spring (default true). */
  interactive?: boolean;
}

export interface AvatarController {
  setState(id: AvatarStateId): void;
  setSpeed(speed: number): void;
  setPaused(paused: boolean): void;
  setAccent(color?: string): void;
  setLook(mode?: "pointer" | "idle" | "off"): void;
  /** Trigger the tap reaction programmatically. */
  poke(): void;
  /** Jump to an exact loop phase (0…1) without animating. */
  seek(u: number, gazeX?: number, gazeY?: number): void;
  /** Test/demo helper: start a morph to `id` and freeze it `seconds` in. */
  scrubMorph(id: AvatarStateId, seconds: number): void;
  getState(): AvatarStateId;
  destroy(): void;
}

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

/** Attach the engine to an element that already contains the avatar SVG. */
export function mount(root: Element, options?: MountOptions): AvatarController;
/** Avatar SVG markup for plain-HTML usage. quality: "full" (liquid + glow + glossy highlight) | "lite" | "flat". */
export function markup(uid?: string | null, quality?: "full" | "lite" | "flat"): string;
/** Pure sampler: the 4 bar poses of a state at loop phase u (0…1). */
export function poseAt(stateId: AvatarStateId, u: number, accent?: string): BarPose[];
/** Loop length in seconds. */
export function loopSeconds(stateId: AvatarStateId, speed?: number): number;

/** The 3D transform of the face for a gaze (−1…1) and tap push (0…1). */
export function faceTransform(
  gx?: number,
  gy?: number,
  poke?: number,
): { tx: number; ty: number; rot: number; skew: number; sx: number; sy: number };

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
