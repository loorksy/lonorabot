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
export type AvatarFaceId =
  | "orb"
  | "face-smile"
  | "face-thoughtful"
  | "face-happy"
  | "face-wink"
  | "face-sleepy"
  | "face-surprised"
  | "face-angry"
  | "face-playful"
  | "face-excited"
  | "face-skeptical"
  | "face-dreamy"
  | "face-focused"
  | "face-worried"
  | "face-laugh"
  | "face-determined";
export const AVATAR_FACES: readonly { readonly id: AvatarFaceId; readonly label: string }[];
export function resolveAvatarFace(value?: string | null): AvatarFaceId;

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

/** Canonical facial design tokens derived from the original signal bar and visor dimensions. */
export const FACE_TOKENS: {
  readonly stroke: Readonly<
    Record<"primary" | "curvedEye" | "secondary" | "eyebrow" | "accent" | "indicator", number>
  >;
  readonly shape: Readonly<
    Record<
      | "eyeWidth"
      | "eyeHeight"
      | "eyeArcRadius"
      | "eyeArcSpan"
      | "eyebrowLength"
      | "eyebrowRise"
      | "mouthWidth"
      | "mouthRadius"
      | "mouthArcSpan"
      | "laughingMouthScale"
      | "roundMouthRadius"
      | "tongueWidth"
      | "tongueLength"
      | "winkHalfWidth"
      | "winkHalfHeight"
      | "closedEyeLength"
      | "accentLength"
      | "accentRadius"
      | "questionRadius"
      | "cornerRadius",
      number
    >
  >;
  readonly spacing: Readonly<
    Record<
      | "eyeHalfSpacing"
      | "eyeLine"
      | "browLine"
      | "mouthLine"
      | "minimumSeparation"
      | "accentPitch"
      | "accentLine"
      | "sideAccentX"
      | "tongueLine"
      | "sideAccentLine",
      number
    >
  >;
  readonly optical: Readonly<
    Record<
      | "eyeArcCorrection"
      | "mouthCorrection"
      | "openMouthOffset"
      | "thoughtfulEyeOffset"
      | "focusedMouthOffset",
      number
    >
  >;
  readonly motion: Readonly<
    Record<"breathAmplitude" | "blinkPhase" | "blinkHalfDuration" | "blinkStrokeRatio", number>
  >;
  readonly render: {
    readonly gooBlur: number;
    readonly glowBlur: number;
    readonly glowOpacity: number;
  };
};
/** Anchors are pre-GLYPH_SCALE world coordinates; the safe area is in rendered SVG coordinates. */
export const FACIAL_GEOMETRY: {
  readonly viewBox: string;
  readonly outerShell: typeof GEOMETRY.shell;
  readonly faceDisplay: typeof GEOMETRY.face;
  readonly horizontalCenter: number;
  readonly verticalCenter: number;
  readonly eyeAnchors: {
    readonly left: Readonly<{ x: number; y: number }>;
    readonly right: Readonly<{ x: number; y: number }>;
  };
  readonly eyebrowAnchors: {
    readonly left: Readonly<{ x: number; y: number }>;
    readonly right: Readonly<{ x: number; y: number }>;
  };
  readonly mouthAnchor: Readonly<{ x: number; y: number }>;
  readonly expressionBounds: Readonly<{ left: number; right: number; top: number; bottom: number }>;
  readonly facialSafeArea: Readonly<{ x: number; y: number; width: number; height: number }>;
};

export interface MountOptions {
  face?: string;
  /** Stable bot ID; absent identities receive an independent per-instance fallback. */
  identity?: string;
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
  setFace(face: string): void;
  setIdentity(identity?: string): void;
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
export function poseAt(
  stateId: AvatarStateId,
  u: number,
  accent?: string,
  identity?: string,
  face?: string,
): BarPose[];
/** Loop length in seconds. */
export function loopSeconds(stateId: AvatarStateId, speed?: number): number;

export interface AvatarPersonality {
  readonly phase: number;
  readonly direction: 1 | -1;
  readonly tempo: number;
  readonly cycleSeconds: number;
  readonly spinSeconds: number;
  readonly pattern: number;
  readonly gazeXFrequency: number;
  readonly gazeYFrequency: number;
  readonly gazeXAmplitude: number;
  readonly gazeYAmplitude: number;
}
/** Deterministic idle-only visual behavior from a bot ID. */
export function avatarPersonality(identity?: string): AvatarPersonality;

/** Lively waiting gaze plus an occasional complete turn. seconds counts visible active time. */
export function idleAvatarPose(
  seconds: number,
  identity?: string,
): { gazeX: number; gazeY: number; yaw: number };
/** Project a visor around the sphere; back-facing content is invisible and never mirrored. */
export function avatarTurn(yaw: number): { tx: number; scaleX: number; opacity: number };

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
