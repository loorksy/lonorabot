/*!
 * Trading Avatar — Interactive Signal Engine (v7)
 * ------------------------------------------------------------------
 * A glossy 3D sphere with a dark visor. Inside the visor live FOUR
 * "signals". Each signal is a stroked segment (position, length, angle,
 * curvature, thickness) — so the same four signals can be a bar chart,
 * dots, a magnifier (search), text lines (writing), a spinner (work),
 * a bolt (execute), an arrow (send), sound waves (speak), Wi‑Fi bars
 * (connect), a check (success), a cross (error), a warning triangle,
 * or a burst (celebrate).
 *
 *  • Switching state does not cut: every signal travels from its current
 *    shape to the new one (best-match assignment, curved paths, staggered
 *    spring-like timing) — it reads as one continuous shot.
 *  • The face looks left/right (pointer / idle gaze) and reacts to taps.
 *  • Nothing is ever drawn outside the sphere. Zero dependencies.
 */

const TAU = Math.PI * 2;
const DEG = Math.PI / 180;

/* ───────────────────────── geometry (400-unit space) ───────────────────────── */
export const GEOMETRY = Object.freeze({
  viewBox: "22 22 356 356",
  shell: Object.freeze({ cx: 200, cy: 200, r: 177 }),
  face: Object.freeze({ x: 78, y: 123, width: 244, height: 155, rx: 77.5 }),
  barWidth: 26,
  barX: Object.freeze([140, 180, 220, 260]),
  centerY: 200.5,
  floorY: 241,
  restHeights: Object.freeze([39, 60, 81, 49]),
});
const W = GEOMETRY.barWidth,
  XS = GEOMETRY.barX,
  CY = GEOMETRY.centerY,
  FLOOR = GEOMETRY.floorY,
  REST = GEOMETRY.restHeights;

export const STATE_IDS = Object.freeze([
  "thinking",
  "executing",
  "inspecting",
  "writing",
  "searching",
  "working",
  "listening",
  "reviewing",
  "waiting",
  "angry",
  "sending",
  "speaking",
  "success",
  "error",
  "warning",
  "analyzing",
  "learning",
  "sleeping",
  "celebrating",
  "connecting",
]);

export const AVATAR_FACES = Object.freeze(
  [
    ["orb", "Signals"],
    ["face-smile", "Smile"],
    ["face-thoughtful", "Thoughtful"],
    ["face-happy", "Happy"],
    ["face-wink", "Wink"],
    ["face-sleepy", "Sleepy"],
    ["face-surprised", "Surprised"],
    ["face-angry", "Angry"],
    ["face-playful", "Playful"],
    ["face-excited", "Excited"],
    ["face-skeptical", "Skeptical"],
    ["face-dreamy", "Dreamy"],
    ["face-focused", "Focused"],
    ["face-worried", "Worried"],
    ["face-laugh", "Laugh"],
    ["face-determined", "Determined"],
  ].map(([id, label]) => Object.freeze({ id, label })),
);
const FACE_IDS = new Set(AVATAR_FACES.map((face) => face.id));
/** Existing shell identifiers retain the legacy signal face. */
export function resolveAvatarFace(value) {
  return FACE_IDS.has(value) ? value : "orb";
}

const BASE_SECONDS = 2.8;
const MORPH_SECONDS = 0.95; // shape → shape travel time
const MORPH_DELAY = 0.07; // stagger between signals

/* ───────────────────────────── math helpers ───────────────────────────── */
const clamp = (x, a = 0, b = 1) => (x < a ? a : x > b ? b : x);
const lerp = (a, b, t) => a + (b - a) * t;
const wrap = (x) => x - Math.floor(x);
const wrapSigned = (x) => {
  x = wrap(x);
  return x > 0.5 ? x - 1 : x;
};
const smooth = (x) => {
  x = clamp(x);
  return x * x * (3 - 2 * x);
};
const inOut = (x) => {
  x = clamp(x);
  return x < 0.5 ? 4 * x * x * x : 1 - Math.pow(-2 * x + 2, 3) / 2;
};
const outCubic = (x) => 1 - Math.pow(1 - clamp(x), 3);
const inCubic = (x) => {
  x = clamp(x);
  return x * x * x;
};
const spring = (x, z = 0.7, w = 7.3) => {
  x = clamp(x);
  const wd = w * Math.sqrt(1 - z * z),
    k = (z * w) / wd;
  const raw = (t) => 1 - Math.exp(-z * w * t) * (Math.cos(wd * t) + k * Math.sin(wd * t));
  return raw(x) + (1 - raw(1)) * x * x * x;
};
const bump = (d, r) => {
  d = Math.abs(d);
  return d >= r ? 0 : 0.5 * (1 + Math.cos((Math.PI * d) / r));
};
const seg = (u, a, b) => clamp((u - a) / (b - a));
const lerpAng = (a, b, t) => a + (((((b - a + 540) % 360) + 360) % 360) - 180) * t;

export const GLYPH_SCALE = 1.1; // how large the glyph is drawn inside the visor
const N = 8; // particles that make up the one liquid mass

/** One facial coordinate system, derived from the original visor and shortest idle capsule. */
const facialUnit = GEOMETRY.barWidth;
const facialCenter = { x: GEOMETRY.shell.cx, y: GEOMETRY.centerY };
const eyeHalfSpacing = (GEOMETRY.barX[3] - GEOMETRY.barX[0]) * 0.35;
const eyeLine = -GEOMETRY.face.height * 0.055;
const primaryStroke = facialUnit * 0.68,
  secondaryStroke = facialUnit * 0.44;
const browStroke = facialUnit * 0.32,
  accentStroke = facialUnit * 0.29;
const eyeHeight = GEOMETRY.restHeights[0],
  eyeArcRadius = primaryStroke * 0.72;
const eyeArcSpan = 140,
  mouthArcSpan = 110;
const mouthWidth = facialUnit * 1.6;
const eyeArcCorrection = (eyeArcRadius * (1 + Math.cos((eyeArcSpan * DEG) / 2))) / 2;
const mouthRadius = (mouthWidth - secondaryStroke) / (2 * Math.sin((mouthArcSpan * DEG) / 2));
const mouthCorrection = (mouthRadius * (1 + Math.cos((mouthArcSpan * DEG) / 2))) / 2;
const minimumSeparation = facialUnit * 0.2;
const browLine = eyeLine - eyeHeight / 2 - minimumSeparation - browStroke;
const mouthLine = GEOMETRY.face.height * 0.185;
const expressionHalfWidth = (GEOMETRY.face.width * 0.35) / GLYPH_SCALE;
const expressionHalfHeight = (GEOMETRY.face.height * 0.41) / GLYPH_SCALE;
const frozenPoint = (x, y) => Object.freeze({ x, y });
export const FACE_TOKENS = Object.freeze({
  stroke: Object.freeze({
    primary: primaryStroke,
    curvedEye: primaryStroke * 0.8,
    secondary: secondaryStroke,
    eyebrow: browStroke,
    accent: accentStroke,
    indicator: accentStroke * 1.08,
  }),
  shape: Object.freeze({
    eyeWidth: primaryStroke,
    eyeHeight,
    eyeArcRadius,
    eyeArcSpan,
    eyebrowLength: facialUnit * 1.08,
    eyebrowRise: browStroke,
    mouthWidth,
    mouthRadius,
    mouthArcSpan,
    laughingMouthScale: 1.12,
    roundMouthRadius: secondaryStroke * 0.88,
    tongueWidth: primaryStroke * 0.75,
    tongueLength: secondaryStroke * 0.25,
    winkHalfWidth: primaryStroke * 0.4,
    winkHalfHeight: eyeHeight * 0.3,
    closedEyeLength: eyeHeight - primaryStroke,
    accentLength: facialUnit * 0.42,
    accentRadius: facialUnit * 0.36,
    questionRadius: facialUnit * 0.34,
    cornerRadius: secondaryStroke / 2,
  }),
  spacing: Object.freeze({
    eyeHalfSpacing,
    eyeLine,
    browLine,
    mouthLine,
    minimumSeparation,
    accentPitch: facialUnit * 0.72,
    accentLine: -facialUnit * 1.52,
    sideAccentX: eyeHalfSpacing + facialUnit * 0.7,
    tongueLine: mouthLine + secondaryStroke * 0.9,
    sideAccentLine: -facialUnit * 1.05,
  }),
  optical: Object.freeze({
    eyeArcCorrection,
    mouthCorrection,
    openMouthOffset: secondaryStroke * 0.34,
    thoughtfulEyeOffset: facialUnit * 0.035,
    focusedMouthOffset: facialUnit * 0.16,
  }),
  motion: Object.freeze({
    breathAmplitude: facialUnit * 0.025,
    blinkPhase: 0.82,
    blinkHalfDuration: 0.035,
    blinkStrokeRatio: 0.65,
  }),
  render: Object.freeze({ gooBlur: 0.5, glowBlur: 2, glowOpacity: 0.16 }),
});
export const FACIAL_GEOMETRY = Object.freeze({
  viewBox: GEOMETRY.viewBox,
  outerShell: GEOMETRY.shell,
  faceDisplay: GEOMETRY.face,
  horizontalCenter: facialCenter.x,
  verticalCenter: facialCenter.y,
  eyeAnchors: Object.freeze({
    left: frozenPoint(facialCenter.x - eyeHalfSpacing, facialCenter.y + eyeLine),
    right: frozenPoint(facialCenter.x + eyeHalfSpacing, facialCenter.y + eyeLine),
  }),
  eyebrowAnchors: Object.freeze({
    left: frozenPoint(facialCenter.x - eyeHalfSpacing, facialCenter.y + browLine),
    right: frozenPoint(facialCenter.x + eyeHalfSpacing, facialCenter.y + browLine),
  }),
  mouthAnchor: frozenPoint(facialCenter.x, facialCenter.y + mouthLine),
  expressionBounds: Object.freeze({
    left: -expressionHalfWidth,
    right: expressionHalfWidth,
    top: -expressionHalfHeight,
    bottom: expressionHalfHeight,
  }),
  facialSafeArea: Object.freeze({
    x: facialCenter.x - expressionHalfWidth * GLYPH_SCALE,
    y: facialCenter.y - expressionHalfHeight * GLYPH_SCALE,
    width: expressionHalfWidth * GLYPH_SCALE * 2,
    height: expressionHalfHeight * GLYPH_SCALE * 2,
  }),
});
/* ───────────────────────────── segment model ─────────────────────────────
 * One signal = a stroked arc: centre (cx,cy) · length L (centre-line) · heading th°
 * at the middle (0 = right, 90 = down) · curvature k (1/radius, 0 = straight) ·
 * stroke width w · opacity o · accent tint c.  Round caps → L≈0 is a dot.      */
const H = (b, x = 0, y = 0) => G(b, x, y, 0.01, 0, 0, 0.01, 1, 0); // hidden particle (zero width)
const G = (b, x, y, L, th, k = 0, w = 16, o = 1, c = 0) => {
  b.cx = 200 + x;
  b.cy = CY + y;
  b.L = Math.max(L, 0.01);
  b.th = th;
  b.k = k;
  b.w = w;
  b.o = o;
  b.c = c;
  b.ar = null;
};
/* legacy "vertical capsule" pose: h = outer height, y = centre offset, dx, rot° */
const sit = (h) => FLOOR - CY - h / 2;
const P = (b, h, y, o = 1, c = 0, dx = 0, rot = 0, w = W) =>
  G(b, XS[b.i] - 200 + dx, y, Math.max(h - w, 0.01), 90 + rot, 0, w, o, c);
/* shape builders → [x, y, L, th, k] */
const arc = (ccx, ccy, R, alpha, span) => [
  ccx + R * Math.cos(alpha * DEG),
  ccy + R * Math.sin(alpha * DEG),
  R * span * DEG,
  alpha + 90,
  1 / R,
];
const line = (x0, y0, x1, y1) => [
  (x0 + x1) / 2,
  (y0 + y1) / 2,
  Math.hypot(x1 - x0, y1 - y0),
  Math.atan2(y1 - y0, x1 - x0) / DEG,
  0,
];
/* glyph-level transform: offset, rotation, scale */
const X = (ox = 0, oy = 0, psi = 0, s = 1) => {
  const c = Math.cos(psi * DEG),
    n = Math.sin(psi * DEG);
  return (b, x, y, L, th, k, w, o, col) =>
    G(b, (x * c - y * n) * s + ox, (x * n + y * c) * s + oy, L * s, th + psi, k / s, w * s, o, col);
};

/* 🕯 a Japanese candle = body + wick (two particles that fuse into one shape).
 * Heights are y-offsets from the visor centre (down = +). close < open ⇒ price went up ⇒ green. */
const GREEN = [52, 225, 150],
  RED = [251, 113, 133],
  OY = 12;
function candle(B, i, o, c, hi, lo, op = 1, tintAmt = 1, rot = 0, dx = 0, w = 22) {
  const x = XS[i] - 200 + dx,
    top = Math.min(o, c) + OY,
    bot = Math.max(o, c) + OY,
    my = (top + bot) / 2,
    wk = (hi + lo) / 2 + OY;
  const up = smooth((o - c) / 8 + 0.5),
    col = [lerp(RED[0], GREEN[0], up), lerp(RED[1], GREEN[1], up), lerp(RED[2], GREEN[2], up)];
  const r = rot * DEG,
    put = (b, d, L, ww) => {
      G(b, x - d * Math.sin(r), d * Math.cos(r), L, 90 + rot, 0, ww, op, tintAmt);
      b.ar = col;
    };
  put(B[2 * i], my, Math.max(bot - top - w, 0.01), w);
  const ww = Math.max(8, Math.round(w * 0.45));
  put(B[2 * i + 1], wk, Math.max(lo - hi - ww, 0.01), ww);
}
const CO = [-20, 28, 12, -4],
  CC = [24, -12, -32, -54]; // the resting four candles: open / close
const CHI = [-29, -21, -41, -63],
  CLO = [33, 37, 21, 5];

const CELEBRATE = [
  [255, 209, 102],
  [102, 244, 178],
  [125, 211, 252],
  [255, 158, 192],
];

/* ───────────────────────────── the 20 states ───────────────────────────── */
const sendX = (u) =>
  u < 0.34
    ? 56 * inCubic(u / 0.34)
    : u < 0.5
      ? 56 + 120 * seg(u, 0.34, 0.5)
      : u < 0.56
        ? -130
        : -130 + 130 * outCubic(seg(u, 0.56, 0.88));
const STATES = {
  /* Four smooth, bottom-aligned capsules are the idle identity; no price wicks. */
  waiting: {
    k: 0.72,
    fluid: 0.15,
    poster: 0,
    fn(u, B) {
      for (let i = 0; i < 4; i++) {
        const h = REST[i] + (i === 2 ? 4 : 2) * Math.sin(TAU * u);
        P(B[i], h, sit(h), 1, i === 2 ? 1 : 0);
        if (i === 2) B[i].ar = [31, 212, 179];
      }
    },
  },
  sleeping: {
    k: 2.6,
    fluid: 0.15,
    poster: 0.3,
    gaze: () => [0, 0.4],
    fn(u, B) {
      for (let i = 0; i < 4; i++) {
        const s = 0.5 + 0.5 * Math.sin(TAU * (u - i * 0.1)),
          e = 10 + 6 * s;
        candle(B, i, -2, 2, -e, e, 1, 0.12, 0, 0, 16);
        for (const b of [B[2 * i], B[2 * i + 1]]) b.o = 0.35 + 0.25 * s;
      }
    },
  },
  thinking: {
    k: 0.62,
    poster: 0.12,
    gaze: () => [0.5, -0.5],
    fn(u, B) {
      for (let i = 0; i < 4; i++) {
        const p = wrap(u - i * 0.13),
          a = p < 0.55 ? Math.sin((Math.PI * p) / 0.55) : 0;
        G(B[i], XS[i] - 200, 12 - 40 * a, 0.01 + 14 * a, 90, 0, 28 - 4 * a, 1, 0.3 + 0.5 * a);
      }
    },
  },
  analyzing: {
    k: 1.3,
    fluid: 0.15,
    poster: 0.32,
    fn(u, B) {
      const M = [10, 4, -2, -8],
        A = [10, 12, 10, 14],
        Bm = [26, 28, 30, 34],
        a = [0, 0.31, 0.62, 0.17],
        b = [0.45, 0.1, 0.75, 0.33];
      for (let i = 0; i < 4; i++) {
        const o = M[i] + A[i] * Math.sin(TAU * (u + a[i])),
          c = M[i] + Bm[i] * Math.sin(TAU * (2 * u + b[i])) - 6 * Math.sin(TAU * (u + a[i] + 0.2));
        const hi = Math.min(o, c) - 7 - 5 * (0.5 + 0.5 * Math.sin(TAU * (3 * u + a[i]))),
          lo = Math.max(o, c) + 7 + 5 * (0.5 + 0.5 * Math.sin(TAU * (3 * u + b[i])));
        candle(B, i, o, c, hi, lo, 1, 1);
      }
    },
  },
  inspecting: {
    k: 1.5,
    fluid: 0.15,
    poster: 0.5,
    gaze: (u) => [(((0.5 - 0.5 * Math.cos(TAU * u)) * 3 - 1.5) / 1.5) * 0.85, 0],
    fn(u, B) {
      const pos = (0.5 - 0.5 * Math.cos(TAU * u)) * 3;
      for (let i = 0; i < 4; i++) {
        const g = bump(i - pos, 1.3),
          cc = lerp(CO[i], CC[i], 1 + 0.35 * g);
        candle(B, i, CO[i], cc, CHI[i] - 8 * g, CLO[i] + 8 * g, 1, 0.3 + 0.7 * g);
      }
    },
  },
  reviewing: {
    k: 1.8,
    fluid: 0.15,
    poster: 0.72,
    fn(u, B) {
      const fade = smooth(seg(u, 0.88, 0.99)),
        all = bump(u - 0.8, 0.07);
      for (let i = 0; i < 4; i++) {
        const a = spring(seg(u, 0.06 + 0.17 * i, 0.06 + 0.17 * i + 0.1)) * (1 - fade),
          cc = lerp(CO[i], CC[i], 1 + 0.2 * a + 0.15 * all);
        candle(B, i, CO[i], cc, CHI[i] - 6 * a, CLO[i] + 6 * a, 1, 0.3 + 0.7 * clamp(a));
      }
    },
  },
  listening: {
    k: 1.0,
    fluid: 0.15,
    poster: 0.3,
    fn(u, B) {
      const ph1 = [0, 0.27, 0.55, 0.8],
        ph2 = [0.1, 0.5, 0.2, 0.7];
      for (let i = 0; i < 4; i++) {
        const s1 = 0.5 + 0.5 * Math.sin(TAU * (u + ph1[i])),
          s2 = 0.5 + 0.5 * Math.sin(TAU * (2 * u + ph2[i])),
          e = s1 * (0.35 + 0.65 * s2),
          r = 12 + 34 * e;
        candle(B, i, -4 * (1 - e), 4 * (1 - e), -r, r, 1, 0.4 + 0.5 * e, 0, 0, 18);
        B[2 * i].ar = null;
        B[2 * i + 1].ar = null;
      }
    },
  },
  learning: {
    k: 2.2,
    fluid: 0.15,
    poster: 0.7,
    fn(u, B) {
      const INC = [12, 17, 22, 28],
        reset = inOut(seg(u, 0.88, 1)),
        level = [0, 0, 0, 0],
        flash = [0, 0, 0, 0];
      for (let k = 0; k < 12; k++) {
        const t = 0.04 + 0.065 * k,
          i = k % 4;
        level[i] += spring(seg(u, t, t + 0.05), 0.62, 7);
        if (u >= t) flash[i] = Math.max(flash[i], 1 - smooth(seg(u, t, t + 0.12)));
      }
      for (let i = 0; i < 4; i++) {
        const lv = level[i] * (1 - reset),
          o = 22,
          c = o - (22 + (INC[i] * lv) / 2.4);
        candle(B, i, o, c, c - 8 - 3 * lv, o + 8, 1, 0.55 + 0.45 * Math.max(flash[i], lv / 3));
      }
    },
  },
  angry: {
    k: 0.5,
    fluid: 0.15,
    poster: 0.2,
    accent: "#fb7185",
    gaze: () => [0, 0],
    fn(u, B) {
      const R = [-15, -9, 9, 15],
        pulse = 0.5 + 0.5 * Math.sin(TAU * 3 * u);
      for (let i = 0; i < 4; i++) {
        const o = -22 - 3 * pulse,
          c = 22 + 3 * pulse;
        candle(B, i, o, c, o - 12, c + 12, 1, 1, R[i], 1.6 * Math.sin(TAU * 11 * u + i * 1.7), 22);
        B[2 * i].ar = RED;
        B[2 * i + 1].ar = RED;
      }
    },
  },

  /* ── glyph family: ONE liquid mass takes the shape of the job's icon ── */
  /* 🔍 a ring and a handle; the lens looks around */
  searching: {
    k: 2.0,
    poster: 0.15,
    gaze: (u) => [0.6 * Math.sin(TAU * u), 0.25 * Math.sin(TAU * 2 * u + 0.6)],
    fn(u, B) {
      const f = X(
        12 * Math.sin(TAU * u),
        7 * Math.sin(TAU * 2 * u + 0.6),
        6 * Math.sin(TAU * u + 0.8),
        1.0 + 0.04 * Math.sin(TAU * 2 * u),
      );
      const R = 30,
        cx = -8,
        cy = -8,
        d = 0.7071;
      for (let j = 0; j < 4; j++) f(B[j], ...arc(cx, cy, R, 45 + 90 * j, 90), 17, 1, 0.55);
      f(
        B[4],
        ...line(cx + (R + 6) * d, cy + (R + 6) * d, cx + (R + 32) * d, cy + (R + 32) * d),
        23,
        1,
        0.1,
      );
    },
  },
  /* ✏ a pencil that draws a line and erases it */
  writing: {
    k: 1.0,
    poster: 0.62,
    gaze: () => [-0.2, 0.3],
    fn(u, B) {
      const g = inOut(seg(u, 0.05, 0.78)) * (1 - inOut(seg(u, 0.88, 1))),
        tx = -40 + 74 * g;
      const wig = 3 * Math.sin(TAU * 12 * u) * smooth(g * 12) * smooth((1 - g) * 12),
        ty = 30 + wig,
        ux = 0.7071,
        uy = -0.7071;
      G(B[0], (-44 + tx) / 2, 40, tx + 44, 0, 0, 10, 1, 0.55);
      G(B[1], tx, ty, 0.01, 0, 0, 8, 1, 0.9);
      G(B[2], tx + ux * 13, ty + uy * 13, 10, -45, 0, 16, 1, 0.9);
      G(B[3], tx + ux * 47, ty + uy * 47, 38, -45, 0, 27, 1, 0);
    },
  },
  /* ⟳ a spinning ring around a pulsing core */
  working: {
    k: 0.8,
    poster: 0.2,
    gaze: () => [0, 0],
    fn(u, B) {
      const rot = 360 * u + 24 * Math.sin(TAU * 2 * u);
      for (let j = 0; j < 4; j++)
        G(
          B[j],
          ...arc(0, 0, 38, rot + 90 * j, 54 + 24 * Math.sin(TAU * (2 * u - j * 0.25))),
          16,
          1,
          0.3 + 0.6 * bump(wrapSigned(u - j / 4), 0.28),
        );
      G(B[4], 0, 0, 0.01, 0, 0, 14 + 5 * Math.sin(TAU * 2 * u), 1, 0.5);
    },
  },
  /* ⚡ a bolt that charges and fires in two beats */
  executing: {
    k: 0.78,
    poster: 0.27,
    gaze: () => [0, 0],
    fn(u, B) {
      const f1 = bump(u - 0.25, 0.09),
        f2 = bump(u - 0.55, 0.07),
        hit = Math.max(f1, f2);
      const f = X(2 * (f1 + f2) * Math.sin(TAU * 14 * u), 0, 0, 1.0 + 0.08 * f1 + 0.1 * f2),
        c = 0.6 + 0.4 * hit;
      f(B[0], ...line(14, -42, -12, 2), 22, 1, c);
      f(B[1], ...line(-12, 2, 12, 2), 22, 1, c);
      f(B[2], ...line(12, 2, -14, 44), 22, 1, c);
      f(B[3], 42, -30, 0.01, 0, 0, 7 + 8 * hit, 1, 1);
      f(B[4], -40, 32, 0.01, 0, 0, 6 + 7 * Math.max(f2, 0.3 * f1), 1, 1);
    },
  },
  /* ➜ an arrow that thrusts out through the visor edge and returns */
  sending: {
    k: 1.1,
    poster: 0.08,
    gaze: (u) => [clamp(sendX(u) / 80, -1, 1) * 0.7, 0],
    fn(u, B) {
      const st = u < 0.5 ? smooth(seg(u, 0.1, 0.34)) : 1 - smooth(seg(u, 0.56, 0.8));
      const f = X(14 + sendX(u), 0, 0, 1.12),
        x0 = -34 - 30 * st,
        tl = 10 + 18 * st;
      f(B[0], (x0 + 24) / 2, 0, 24 - x0, 0, 0, 20, 1, 0.35);
      f(B[1], ...line(24, 0, 2, -22), 20, 1, 0.9);
      f(B[2], ...line(24, 0, 2, 22), 20, 1, 0.9);
      f(B[3], x0 - 14 - tl / 2, 0, tl, 0, 0, 12, 1, 0.3);
    },
  },
  /* •))) a speaker: a dot and three waves pulsing with the syllables */
  speaking: {
    k: 0.85,
    poster: 0.2,
    gaze: () => [0.2, 0],
    fn(u, B) {
      const env = 0.3 + 0.7 * Math.pow(0.5 + 0.5 * Math.sin(TAU * 4 * u - 1), 1.4),
        f = X(16, 0, 0, 1.12),
        R = [28, 48, 68];
      f(B[0], -46, 0, 0.01, 0, 0, 22 + 10 * env, 1, 0.3 + 0.3 * env);
      for (let j = 0; j < 3; j++) {
        const wv = bump(wrapSigned(u * 4 - j * 0.2), 0.3);
        f(
          B[j + 1],
          ...arc(-46, 0, R[j] * (1 + 0.05 * wv), 0, 80),
          14,
          1,
          0.2 + 0.6 * Math.max(wv, env * 0.4),
        );
      }
    },
  },
  /* Wi‑Fi: a dot and three arcs light up one by one */
  connecting: {
    k: 1.3,
    poster: 0.7,
    gaze: () => [0, -0.2],
    fn(u, B) {
      const f = X(0, 0, 0, 1.12),
        fade = inOut(seg(u, 0.8, 0.95)),
        lit = (a) => spring(seg(u, a, a + 0.12), 0.6, 6.6) * (1 - fade),
        R = [24, 44, 64],
        l0 = lit(0.06);
      f(B[0], 0, 28, 0.01, 0, 0, 14 + 10 * clamp(l0), 1, 0.2 + 0.75 * clamp(l0));
      for (let j = 0; j < 3; j++) {
        const l = lit(0.18 + 0.14 * j);
        f(
          B[j + 1],
          ...arc(0, 28, R[j] * (0.92 + 0.08 * l), -90, 90),
          6 + 8 * clamp(l),
          1,
          0.2 + 0.75 * clamp(l),
        );
      }
    },
  },
  /* ✓ a bold check mark with two sparkles */
  success: {
    k: 1.6,
    poster: 0.4,
    accent: "#66f4b2",
    gaze: () => [0, -0.1],
    fn(u, B) {
      const f = X(2, -2, 0, 1.0 + 0.08 * bump(u - 0.12, 0.1) + 0.04 * bump(u - 0.6, 0.12)),
        t1 = 0.5 + 0.5 * Math.sin(TAU * 2 * u),
        t2 = 0.5 + 0.5 * Math.sin(TAU * 2 * u + 3.1);
      f(B[0], ...line(-34, 6, -12, 28), 26, 1, 1);
      f(B[1], ...line(-12, 28, 40, -28), 26, 1, 1);
      f(B[2], 50, -40, 0.01, 0, 0, 5 + 9 * t1, 1, 1);
      f(B[3], -48, -28, 0.01, 0, 0, 4 + 8 * t2, 1, 1);
    },
  },
  /* ✕ a bold cross with one damped shake */
  error: {
    k: 1.4,
    poster: 0.4,
    accent: "#fb7185",
    gaze: () => [0, 0.35],
    fn(u, B) {
      const t = u - 0.04,
        shake = t > 0 && t < 0.46 ? 5 * Math.sin(TAU * 7 * t) * Math.exp(-10 * t) : 0,
        pl = 1 + 0.06 * Math.sin(TAU * 2 * u + 1),
        r = 31 * pl;
      G(B[0], shake, 0, 2 * r * 1.414 - 24, 45, 0, 25, 1, 1);
      G(B[1], shake, 0, 2 * r * 1.414 - 24, -45, 0, 25, 1, 1);
    },
  },
  /* ⚠ a hazard triangle with an exclamation mark */
  warning: {
    k: 1.2,
    poster: 0.1,
    accent: "#f9bf67",
    gaze: () => [0, 0],
    fn(u, B) {
      const a = 0.5 + 0.5 * Math.tanh(2.2 * Math.sin(TAU * 2 * u)),
        f = X(0, 0, 0, 1.1 + 0.05 * a),
        c = 0.6 + 0.4 * a;
      f(B[0], ...line(0, -38, -46, 38), 15, 1, c);
      f(B[1], ...line(0, -38, 46, 38), 15, 1, c);
      f(B[2], ...line(-46, 38, 46, 38), 15, 1, c);
      f(B[3], 0, -4 - 2 * a, 10, 90, 0, 13, 1, 0);
      f(B[4], 0, 18, 0.01, 0, 0, 13, 1, 0);
    },
  },
  /* ✦ a star-burst that sways and shifts through warm colours */
  celebrating: {
    k: 0.9,
    poster: 0.3,
    gaze: () => [0, -0.2],
    fn(u, B) {
      const sw = 25 * Math.sin(TAU * u),
        lift = -6 * Math.abs(Math.sin(TAU * 2 * u));
      for (let j = 0; j < 4; j++) {
        const a = 90 * j + sw,
          r1 = 34 + 14 * Math.abs(Math.sin(TAU * 2 * u - j * 0.4));
        G(
          B[j],
          (Math.cos(a * DEG) * r1) / 2,
          (Math.sin(a * DEG) * r1) / 2 + lift,
          r1,
          a,
          0,
          15,
          1,
          0.9,
        );
      }
      G(B[4], 0, lift, 0.01, 0, 0, 24 + 5 * Math.sin(TAU * 2 * u), 1, 0.9);
      for (let j = 0; j < 5; j++) {
        const q = wrap(u + j * 0.2) * 4,
          k0 = Math.floor(q) % 4,
          ff = smooth(q - Math.floor(q)),
          A = CELEBRATE[k0],
          Bc = CELEBRATE[(k0 + 1) % 4];
        B[j].ar = [lerp(A[0], Bc[0], ff), lerp(A[1], Bc[1], ff), lerp(A[2], Bc[2], ff)];
      }
    },
  },
};

/* ───────────────────────────── colour helpers ───────────────────────────── */
const EYE = [248, 248, 251];
const DEFAULT_ACCENT = "#6cf4c4";
let _ctx = null;
function parseColor(input, fallback) {
  if (typeof input !== "string" || !input) return fallback;
  const m = input.trim().match(/^#([0-9a-f]{3}|[0-9a-f]{6})$/i);
  if (m) {
    let h = m[1];
    if (h.length === 3)
      h = h
        .split("")
        .map((c) => c + c)
        .join("");
    return [parseInt(h.slice(0, 2), 16), parseInt(h.slice(2, 4), 16), parseInt(h.slice(4, 6), 16)];
  }
  try {
    _ctx = _ctx || document.createElement("canvas").getContext("2d");
    _ctx.fillStyle = "#000";
    _ctx.fillStyle = input;
    const v = _ctx.fillStyle;
    return v.charAt(0) === "#"
      ? parseColor(v, fallback)
      : (v.match(/\d+(\.\d+)?/g) || []).slice(0, 3).map(Number);
  } catch (e) {
    return fallback;
  }
}
const SEMANTIC = {};
for (const id of STATE_IDS)
  if (STATES[id].accent) SEMANTIC[id] = parseColor(STATES[id].accent, null);

/* ───────────────────────────── geometry of a segment ───────────────────────────── */
const newSegs = () =>
  Array.from({ length: N }, (_, i) => ({
    i,
    cx: 200,
    cy: CY,
    L: 0.01,
    th: 90,
    k: 0,
    w: 0.01,
    o: 1,
    c: 0,
    ar: null,
  }));
const runState = (def, u, B, identity = "", face = "orb", reactionProgress = 1) => {
  for (const b of B) H(b);
  if (def === STATES.waiting && resolveAvatarFace(face) !== "orb")
    facialExpression(face, u, B, avatarPersonality(identity), reactionProgress);
  else if (def === STATES.waiting && identity)
    personalizedWaiting(u, B, avatarPersonality(identity));
  else def.fn(u, B);
};

/** Idle-only expressions keep the four capsules while changing their independent rhythm. */
function personalizedWaiting(u, B, profile) {
  const time = wrap(u + profile.phase),
    direction = profile.direction;
  const sway = 1.5 * Math.sin(TAU * time);
  for (let i = 0; i < 4; i++) {
    const wave = Math.sin(TAU * (time - i * 0.17 * direction));
    let height = REST[i],
      lift = 0,
      dx = 0;
    if (profile.pattern === 0) height += 3.5 * wave;
    else if (profile.pattern === 1) {
      height *= 0.96 + 0.04 * Math.sin(TAU * time);
      lift = 1.5 * (1 + Math.sin(TAU * (time + i * 0.2 * direction)));
    } else if (profile.pattern === 2) {
      height += 2 * wave;
      dx = sway + 0.75 * Math.sin(TAU * (time - i * 0.1));
      lift = 1.25 * Math.sin(TAU * (time + i * 0.15 * direction));
    } else {
      const bounce = Math.max(0, Math.sin(TAU * (time - i * 0.16 * direction)));
      height += 2.5 * bounce;
      lift = 3.5 * bounce;
      dx = sway * 0.5;
    }
    height = clamp(height, 30, 94);
    P(B[i], height, sit(height) - lift, 1, i === 2 ? 1 : 0, dx);
    if (i === 2) B[i].ar = [31, 212, 179];
  }
}
/** All presets share anchors, optical corrections and stroke hierarchy; only expression topology varies. */
function facialExpression(face, u, B, profile, reactionProgress = 1) {
  const T = FACE_TOKENS,
    S = T.shape,
    P = T.spacing,
    O = T.optical,
    W = T.stroke;
  const phase = wrap(u + profile.phase),
    breath = Math.sin(TAU * phase) * T.motion.breathAmplitude;
  const reaction = faceReaction(reactionProgress, face);
  const blink = Math.max(
      bump(phase - T.motion.blinkPhase, T.motion.blinkHalfDuration),
      reaction.blink,
    ),
    teal = [31, 212, 179];
  const segment = (slot, geometry, width = W.secondary, accent = false) => {
    G(B[slot], ...geometry, width, 1, accent ? 1 : 0);
    if (accent) B[slot].ar = teal;
  };
  const stroke = (slot, x0, y0, x1, y1, width = W.secondary, accent = false) =>
    segment(slot, line(x0, y0, x1, y1), width, accent);
  const curve = (slot, x, y, radius, alpha, span, width = W.secondary, accent = false) =>
    segment(slot, arc(x, y, radius, alpha, span), width, accent);
  const dot = (slot, x, y, accent = true) => segment(slot, [x, y, 0.01, 0, 0], W.indicator, accent);
  const eye = (slot, x) =>
    segment(
      slot,
      [x, P.eyeLine, (S.eyeHeight - W.primary) * (1 - blink), 90, 0],
      W.primary * (1 - (1 - T.motion.blinkStrokeRatio) * blink),
    );
  const curvedEye = (slot, x, sleepy = false, thoughtful = false) => {
    const gentleBlink = 1 - reaction.blink * 0.12;
    const correction = O.eyeArcCorrection * gentleBlink + (thoughtful ? O.thoughtfulEyeOffset : 0);
    curve(
      slot,
      x,
      P.eyeLine + (sleepy ? -correction : correction),
      S.eyeArcRadius * gentleBlink,
      sleepy ? 90 : 270,
      S.eyeArcSpan,
      W.curvedEye,
    );
  };
  const smile = (slot, laugh = false) => {
    const radius =
      (laugh
        ? (S.mouthWidth * S.laughingMouthScale - W.secondary) /
          (2 * Math.sin((S.mouthArcSpan * DEG) / 2))
        : S.mouthRadius) *
      (1 + reaction.mouth * 0.035);
    const correction = (radius * (1 + Math.cos((S.mouthArcSpan * DEG) / 2))) / 2;
    curve(slot, 0, P.mouthLine - correction + breath, radius, 90, S.mouthArcSpan);
  };
  const flatMouth = (slot, offset = 0) => {
    const half = ((S.mouthWidth * 0.72 - W.secondary) / 2) * (1 + reaction.mouth * 0.04);
    stroke(slot, -half + offset, P.mouthLine + breath, half + offset, P.mouthLine + breath);
  };
  const wink = (slot) => {
    const x = P.eyeHalfSpacing,
      y = P.eyeLine;
    stroke(slot, x + S.winkHalfWidth, y - S.winkHalfHeight, x - S.winkHalfWidth, y, W.curvedEye);
    stroke(
      slot + 1,
      x - S.winkHalfWidth,
      y,
      x + S.winkHalfWidth,
      y + S.winkHalfHeight,
      W.curvedEye,
    );
  };
  const brows = (slot, worried = false) => {
    for (let side = -1; side <= 1; side += 2) {
      const x = side * P.eyeHalfSpacing,
        y = P.browLine,
        rise = S.eyebrowRise * (worried ? 1 : -1);
      stroke(
        slot + (side === 1 ? 1 : 0),
        x - S.eyebrowLength / 2,
        y - (side * rise) / 2,
        x + S.eyebrowLength / 2,
        y + (side * rise) / 2,
        W.eyebrow,
      );
    }
  };
  const cheekMarks = (slot, side) => {
    const x = side * P.sideAccentX,
      y = P.sideAccentLine,
      reach = S.accentLength;
    stroke(slot, x, y, x + side * reach * 0.45, y - reach, W.accent, true);
    stroke(
      slot + 1,
      x - side * P.minimumSeparation,
      y - P.minimumSeparation,
      x - side * P.minimumSeparation,
      y - P.minimumSeparation - reach,
      W.accent,
      true,
    );
  };
  const x = P.eyeHalfSpacing;
  switch (face) {
    case "face-thoughtful":
      curvedEye(0, -x, true, true);
      curvedEye(1, x, true, true);
      flatMouth(2);
      dot(3, -P.accentPitch, P.accentLine);
      dot(4, 0, P.accentLine);
      dot(5, P.accentPitch, P.accentLine);
      break;
    case "face-happy":
      curvedEye(0, -x);
      curvedEye(1, x);
      smile(2);
      break;
    case "face-wink":
      eye(0, -x);
      wink(1);
      smile(3);
      break;
    case "face-sleepy": {
      curvedEye(0, -x, true);
      curvedEye(1, x, true);
      flatMouth(2);
      const cx = P.sideAccentX,
        cy = P.accentLine,
        half = S.accentRadius;
      stroke(3, cx - half, cy - half, cx + half, cy - half, W.accent, true);
      stroke(4, cx + half, cy - half, cx - half, cy + half, W.accent, true);
      stroke(5, cx - half, cy + half, cx + half, cy + half, W.accent, true);
      break;
    }
    case "face-surprised":
      eye(0, -x);
      eye(1, x);
      curve(2, 0, P.mouthLine + O.openMouthOffset + breath, S.roundMouthRadius, 0, 360);
      for (let i = -1; i <= 1; i++)
        stroke(
          4 + i,
          i * P.accentPitch,
          P.accentLine,
          i * (P.accentPitch + P.minimumSeparation),
          P.accentLine - S.accentLength,
          W.accent,
          true,
        );
      break;
    case "face-angry":
      eye(0, -x);
      eye(1, x);
      brows(2);
      flatMouth(4);
      break;
    case "face-playful":
      curvedEye(0, -x);
      curvedEye(1, x);
      smile(2);
      stroke(
        3,
        0,
        P.tongueLine - S.tongueLength / 2,
        0,
        P.tongueLine + S.tongueLength / 2,
        S.tongueWidth,
        true,
      );
      break;
    case "face-excited":
      eye(0, -x);
      wink(1);
      smile(3, true);
      cheekMarks(4, 1);
      break;
    case "face-skeptical": {
      eye(0, -x);
      curvedEye(1, x);
      dot(2, 0, P.mouthLine, false);
      const cx = 0,
        cy = P.accentLine,
        r = S.questionRadius;
      curve(3, cx, cy, r, 285, 245, W.accent, true);
      stroke(4, cx + r * 0.25, cy + r * 0.85, cx - r * 0.25, cy + r * 1.5, W.accent, true);
      dot(
        5,
        cx - r * 0.25,
        cy + r * 1.5 + W.accent + P.minimumSeparation + (W.indicator - W.accent) / 2,
      );
      break;
    }
    case "face-dreamy": {
      curvedEye(0, -x, true);
      curvedEye(1, x, true);
      smile(2);
      const cx = P.sideAccentX,
        cy = P.accentLine,
        r = S.accentRadius;
      stroke(3, cx, cy - r, cx, cy + r, W.accent, true);
      stroke(4, cx - r, cy, cx + r, cy, W.accent, true);
      break;
    }
    case "face-focused":
      eye(0, -x);
      stroke(
        1,
        x - S.closedEyeLength / 2,
        P.eyeLine,
        x + S.closedEyeLength / 2,
        P.eyeLine,
        W.curvedEye,
      );
      flatMouth(2, -O.focusedMouthOffset);
      break;
    case "face-worried": {
      eye(0, -x);
      eye(1, x);
      brows(2, true);
      curve(4, 0, P.mouthLine + O.mouthCorrection + breath, S.mouthRadius, 270, S.mouthArcSpan);
      break;
    }
    case "face-laugh":
      curvedEye(0, -x);
      curvedEye(1, x);
      smile(2, true);
      cheekMarks(3, -1);
      cheekMarks(5, 1);
      break;
    case "face-determined": {
      const half = S.closedEyeLength / 2,
        rise = S.eyebrowRise / 2;
      stroke(0, -x - half, P.eyeLine - rise, -x + half, P.eyeLine + rise, W.primary);
      stroke(1, x - half, P.eyeLine + rise, x + half, P.eyeLine - rise, W.primary);
      flatMouth(2);
      break;
    }
    default:
      eye(0, -x);
      eye(1, x);
      smile(2);
      break;
  }
}

function pointAt(cx, cy, th, k, s) {
  const t = th * DEG;
  if (Math.abs(k) < 1e-5) return [cx + s * Math.cos(t), cy + s * Math.sin(t)];
  return [
    cx + (Math.sin(t + k * s) - Math.sin(t)) / k,
    cy - (Math.cos(t + k * s) - Math.cos(t)) / k,
  ];
}
/** Points along a segment's centre-line (for tests / custom renderers). */
export function segmentPoints(s, n = 24) {
  const pts = [];
  for (let j = 0; j <= n; j++) pts.push(pointAt(s.cx, s.cy, s.th, s.k, -s.L / 2 + (s.L * j) / n));
  return pts;
}
const ID_PLAN = () => ({
  perm: Array.from({ length: N }, (_, i) => i),
  flip: new Array(N).fill(false),
  rank: Array.from({ length: N }, (_, i) => i),
  bow: new Array(N).fill(1),
});
const f1 = (n) => Math.round(n * 10) / 10;
function segPath(cx, cy, L, th, k) {
  const n = Math.min(32, Math.ceil(Math.abs(k * L) * 9) + 1);
  let d = "";
  for (let j = 0; j <= n; j++) {
    const p = pointAt(cx, cy, th, k, -L / 2 + (L * j) / n);
    d += (j ? "L" : "M") + f1(p[0]) + " " + f1(p[1]);
  }
  return d;
}
const _restB = newSegs();
runState(STATES.waiting, 0, _restB);
const _restS = (v) => 200 + (v - 200) * GLYPH_SCALE;
export const REST_PATHS = Object.freeze(
  _restB.map((q) =>
    segPath(
      _restS(q.cx),
      CY + (q.cy - CY) * GLYPH_SCALE,
      q.L * GLYPH_SCALE,
      q.th,
      q.k / GLYPH_SCALE,
    ),
  ),
);
export const REST_WIDTHS = Object.freeze(
  _restB.map((q) => Math.round(Math.max(q.w, 0.01) * GLYPH_SCALE * 100) / 100),
);
export const REST_STROKES = Object.freeze(
  _restB.map((q) => {
    const a = q.ar || [248, 248, 251];
    return (
      "rgb(" +
      Math.round(lerp(248, a[0], q.c)) +
      "," +
      Math.round(lerp(248, a[1], q.c)) +
      "," +
      Math.round(lerp(251, a[2], q.c)) +
      ")"
    );
  }),
);

/* ───────────────────────────── morph planning (pure) ───────────────────────────── */
function ends(s) {
  const a = pointAt(s.cx, s.cy, s.th, s.k, -s.L / 2),
    b = pointAt(s.cx, s.cy, s.th, s.k, s.L / 2);
  return [a[0], a[1], b[0], b[1]];
}
/** Best one-to-one assignment (and direction flips) from the shapes on screen to the new shapes. */
export function planMorph(from, to) {
  const E = from.map(ends),
    F = to.map(ends),
    cost = [],
    flipM = [];
  for (let i = 0; i < N; i++) {
    cost.push([]);
    flipM.push([]);
    for (let j = 0; j < N; j++) {
      const a = E[i],
        b = F[j];
      const d1 = Math.hypot(a[0] - b[0], a[1] - b[1]) + Math.hypot(a[2] - b[2], a[3] - b[3]);
      const d2 = Math.hypot(a[0] - b[2], a[1] - b[3]) + Math.hypot(a[2] - b[0], a[3] - b[1]);
      cost[i].push(Math.min(d1, d2));
      flipM[i].push(d2 < d1);
    }
  }
  const full = (1 << N) - 1,
    dp = new Float64Array(full + 1).fill(Infinity),
    pick = new Int8Array(full + 1).fill(-1);
  dp[0] = 0;
  for (let m = 0; m < full; m++) {
    if (dp[m] === Infinity) continue;
    let i = 0;
    for (let x = m; x; x &= x - 1) i++;
    for (let j = 0; j < N; j++)
      if (!(m & (1 << j))) {
        const nm = m | (1 << j),
          v = dp[m] + cost[i][j];
        if (v < dp[nm]) {
          dp[nm] = v;
          pick[nm] = j;
        }
      }
  }
  const perm = new Array(N);
  let m = full;
  for (let i = N - 1; i >= 0; i--) {
    const j = pick[m];
    perm[i] = j;
    m &= ~(1 << j);
  }
  const plan = { perm, flip: perm.map((j, i) => flipM[i][j]) };
  const order = Array.from({ length: N }, (_, i) => i).sort((i, j) => from[i].cx - from[j].cx),
    rank = new Array(N).fill(0);
  order.forEach((i, r) => {
    rank[i] = r;
  });
  plan.rank = rank;
  plan.bow = from.map((s, i) => {
    // bend each path toward the face centre
    const t = to[plan.perm[i]],
      dx = t.cx - s.cx,
      dy = t.cy - s.cy,
      d = Math.hypot(dx, dy) || 1;
    const px = -dy / d,
      py = dx / d,
      mx = (s.cx + t.cx) / 2,
      my = (s.cy + t.cy) / 2;
    return px * (200 - mx) + py * (CY - my) >= 0 ? 1 : -1;
  });
  return plan;
}
/** Shape of signal `i` `t` seconds into a morph (null `from` = already arrived). */
export function morphSegment(from, tgt, plan, i, t, out) {
  const s = tgt[plan.perm[i]];
  let th = s.th,
    k = s.k;
  if (plan.flip[i]) {
    th += 180;
    k = -k;
  }
  const p = from
    ? clamp((t - plan.rank[i] * MORPH_DELAY * 0.5) / (MORPH_SECONDS - 7 * MORPH_DELAY * 0.5))
    : 1;
  if (p >= 1) {
    out.cx = s.cx;
    out.cy = s.cy;
    out.L = s.L;
    out.th = th;
    out.k = k;
    out.w = s.w;
    out.o = s.o;
    return 1;
  }
  const e = inOut(p),
    dx = s.cx - from.cx,
    dy = s.cy - from.cy,
    d = Math.hypot(dx, dy),
    bow = d > 1 ? (plan.bow[i] * d * 0.09 * Math.sin(Math.PI * e)) / d : 0;
  out.cx = lerp(from.cx, s.cx, e) - dy * bow;
  out.cy = lerp(from.cy, s.cy, e) + dx * bow;
  out.L = lerp(from.L, s.L, e);
  out.th = lerpAng(from.th, th, e);
  out.k = lerp(from.k, k, e);
  out.w = lerp(from.w, s.w, e);
  out.o = lerp(from.o, s.o, e);
  return e;
}
const tint = (s, acc) => {
  const a = s.ar || acc;
  return [lerp(EYE[0], a[0], s.c), lerp(EYE[1], a[1], s.c), lerp(EYE[2], a[2], s.c)];
};

/** Pure sampler: the 4 shapes of `stateId` at loop phase u (0..1) — no DOM. */
export function poseAt(
  stateId,
  u,
  accent = DEFAULT_ACCENT,
  identity = "",
  face = "orb",
  reactionProgress = 1,
) {
  const def = STATES[stateId];
  if (!def) throw new Error("Unknown avatar state: " + stateId);
  const B = newSegs();
  runState(def, wrap(u), B, identity, face, reactionProgress);
  const acc = SEMANTIC[stateId] || parseColor(accent, parseColor(DEFAULT_ACCENT));
  return B.map((s) => {
    const c = tint(s, acc);
    return {
      cx: s.cx,
      cy: s.cy,
      L: s.L,
      th: s.th,
      k: s.k,
      w: s.w,
      o: s.o,
      r: c[0],
      g: c[1],
      b: c[2],
    };
  });
}
export const PARTICLES = N;
export const loopSeconds = (stateId, speed = 1) => (BASE_SECONDS * STATES[stateId].k) / speed;
export const MORPH = Object.freeze({ seconds: MORPH_SECONDS, delay: MORPH_DELAY });

/** Stable visual personality from the agent's ID, independent of its name or saved colour. */
export function avatarPersonality(identity = "") {
  if (!identity)
    return Object.freeze({
      phase: 0,
      direction: 1,
      tempo: 0.5,
      cycleSeconds: 24,
      spinSeconds: 2.7,
      pattern: 0,
      gazeXFrequency: 0.16,
      gazeYFrequency: 0.11,
      gazeXAmplitude: 0.42,
      gazeYAmplitude: 0.12,
    });
  let hash = 2166136261;
  for (let i = 0; i < identity.length; i++)
    hash = Math.imul(hash ^ identity.charCodeAt(i), 16777619) >>> 0;
  const direction = hash & 1 ? -1 : 1,
    pattern = (hash >>> 8) % 4;
  let seed = hash;
  const sample = () => {
    seed = (seed + 0x6d2b79f5) >>> 0;
    let value = Math.imul(seed ^ (seed >>> 15), seed | 1);
    value ^= value + Math.imul(value ^ (value >>> 7), value | 61);
    return ((value ^ (value >>> 14)) >>> 0) / 4294967296;
  };
  return Object.freeze({
    phase: sample(),
    direction,
    tempo: 0.42 + sample() * 0.22,
    cycleSeconds: 18 + sample() * 12,
    spinSeconds: 2.4 + sample() * 0.6,
    pattern,
    gazeXFrequency: 0.12 + sample() * 0.12,
    gazeYFrequency: 0.08 + sample() * 0.09,
    gazeXAmplitude: 0.28 + sample() * 0.2,
    gazeYAmplitude: 0.08 + sample() * 0.08,
  });
}

/** Face temperament: rate, amplitude, vertical bias, reaction gaze X/Y, tilt, lift, scale, blink, mouth. */
const FACE_BEHAVIOR = Object.freeze({
  "face-smile": [1, 0.8, 0, 0.1, 0, 2, 0, 0.01, 0.8, 0.3],
  "face-thoughtful": [0.65, 0.7, -0.08, -0.22, -0.22, -1, 0, -0.01, 0.35, -0.2],
  "face-happy": [1.05, 0.8, -0.02, 0.08, -0.12, 3, -1, 0.02, 0.2, 0.6],
  "face-wink": [0.9, 0.75, 0, 0.24, 0.03, -3, 0, 0.01, 0.9, 0.2],
  "face-sleepy": [0.25, 0.3, 0.12, 0, 0.18, 1, 1, -0.02, 1, -0.4],
  "face-surprised": [0.7, 0.6, -0.02, 0, -0.2, 0, -0.7, -0.025, 0.05, 0.9],
  "face-angry": [0.6, 0.55, 0.02, -0.16, 0.05, -2, 0, -0.01, 0.7, -0.6],
  "face-playful": [1.1, 0.9, 0, 0.3, -0.06, 4, -0.8, 0.025, 0.5, 0.8],
  "face-excited": [1.15, 0.85, -0.03, -0.12, -0.16, -4, -1.2, 0.03, 0.3, 1],
  "face-skeptical": [0.6, 0.8, -0.03, -0.3, -0.03, -2.5, 0, -0.005, 0.6, -0.3],
  "face-dreamy": [0.35, 0.45, -0.06, 0.12, -0.14, 2.5, -0.7, 0.008, 0.95, 0.1],
  "face-focused": [0.35, 0.35, 0, 0.02, -0.08, 0, 0.4, -0.008, 0.45, -0.1],
  "face-worried": [0.85, 0.6, 0.02, 0.2, 0.12, 1.5, 0.2, -0.015, 0.65, -0.8],
  "face-laugh": [1, 0.8, -0.01, -0.06, -0.1, 3.5, -0.9, 0.022, 0.4, 0.95],
  "face-determined": [0.45, 0.45, 0, -0.08, 0.08, -1.5, 0.7, -0.012, 0.55, -0.5],
});

/** Shared calm reaction, applied to facial content only; endpoints are visually neutral. */
export function faceReaction(progress, face = "orb", identity = "") {
  const p = clamp(Number.isFinite(progress) ? progress : 1),
    profile = avatarPersonality(identity);
  const active = p > 0 && p < 1,
    pulse = active ? Math.sin(Math.PI * p) ** 2 : 0;
  const values = FACE_BEHAVIOR[resolveAvatarFace(face)];
  if (!values)
    return {
      gazeX: 0,
      gazeY: 0,
      yaw: TAU * inOut(p) * profile.direction,
      scale: 1,
      offsetY: 0,
      tilt: 0,
      blink: 0,
      mouth: 0,
    };
  return {
    gazeX: values[3] * pulse * profile.direction,
    gazeY: values[4] * pulse,
    yaw: 0,
    tilt: values[5] * pulse * profile.direction,
    offsetY: values[6] * pulse,
    scale: 1 + values[7] * pulse,
    blink: values[8] * pulse,
    mouth: values[9] * pulse,
  };
}

/** Individual idle motion respects the selected expression as well as the bot identity. */
export function idleAvatarPose(seconds, identity = "", face = "orb") {
  const time = Number.isFinite(seconds) ? Math.max(0, seconds) : 0;
  const profile = avatarPersonality(identity),
    values = FACE_BEHAVIOR[resolveAvatarFace(face)];
  const rate = values ? values[0] : 1,
    amplitude = values ? values[1] : 1;
  const cycle = time % profile.cycleSeconds;
  const start = profile.cycleSeconds - profile.spinSeconds,
    spin = clamp((cycle - start) / profile.spinSeconds);
  const focus = values ? 1 : 1 - Math.sin(Math.PI * spin),
    phase = profile.phase * TAU;
  return {
    gazeX:
      Math.sin(time * TAU * profile.gazeXFrequency * rate + phase) *
      profile.gazeXAmplitude *
      focus *
      profile.direction *
      amplitude,
    gazeY:
      Math.sin(time * TAU * profile.gazeYFrequency * rate + phase * 0.7) *
        profile.gazeYAmplitude *
        focus *
        amplitude +
      (values ? values[2] : 0),
    yaw: values || cycle < start ? 0 : TAU * inOut(spin) * profile.direction,
  };
}

/** Spherical visor projection; the back stays hidden rather than showing mirrored eyes. */
export function avatarTurn(yaw) {
  const angle = Number.isFinite(yaw) ? yaw : 0,
    facing = Math.cos(angle);
  return {
    tx: 125 * Math.sin(angle),
    scaleX: Math.max(0.001, facing),
    opacity: smooth(clamp((facing - 0.02) / 0.12)),
  };
}

/* ───────────────────────────── 3D face ───────────────────────────── */
export function faceTransform(gx = 0, gy = 0, poke = 0) {
  const s = 1 - 0.07 * poke;
  return {
    tx: gx * 26,
    ty: gy * 15 + 3 * poke,
    rot: -gx * 5,
    skew: -gx * 4,
    sx: (1 - 0.1 * Math.abs(gx)) * s,
    sy: (1 - 0.06 * Math.abs(gy)) * s,
  };
}
const fmt = (n) => Math.round(n * 100) / 100;
const fmtT = (t) =>
  "translate(" +
  fmt(200 + t.tx) +
  " " +
  fmt(CY + t.ty) +
  ") rotate(" +
  fmt(t.rot) +
  ") skewY(" +
  fmt(t.skew) +
  ") scale(" +
  fmt(t.sx) +
  " " +
  fmt(t.sy) +
  ") translate(-200 " +
  -CY +
  ")";

/* ───────────────────────────── markup ───────────────────────────── */
let _uid = 0;
/** quality: "full" = liquid mass + glow + glossy highlight · "lite" = liquid + glow · "flat" = liquid only */
export function markup(uid, quality = "full") {
  uid = uid || "mta" + ++_uid;
  if (quality === true) quality = "full";
  if (quality === false) quality = "flat";
  const f = GEOMETRY.face;
  let bars = "";
  for (let i = 0; i < N; i++)
    bars += `<path class="mta-bar" data-mta-bar="${i}" d="${REST_PATHS[i]}" stroke-width="${REST_WIDTHS[i]}" fill="none" stroke-linecap="round" stroke-linejoin="round" style="stroke:${REST_STROKES[i]}"/>`;
  const pill = `x="${f.x}" y="${f.y}" width="${f.width}" height="${f.height}" rx="${f.rx}"`;
  const light =
    quality === "full"
      ? `<feGaussianBlur in="g" stdDeviation="2.4" result="bump"/><feSpecularLighting data-mta-light in="bump" surfaceScale="6" specularConstant=".9" specularExponent="26" lighting-color="#fff" result="sp"><fePointLight x="150" y="105" z="95"/></feSpecularLighting><feComposite in="sp" in2="g" operator="in" result="sp2"/><feFlood flood-opacity="0" result="faceNoSpec"/>`
      : "";
  const glow =
    quality === "flat"
      ? ""
      : `<feGaussianBlur data-mta-glow in="g" stdDeviation="9" result="gl0"/><feColorMatrix data-mta-glow-opacity in="gl0" type="matrix" values="1 0 0 0 0 0 1 0 0 0 0 0 1 0 0 0 0 0 .5 0" result="gl"/>`;
  const merge = `<feMerge>${quality === "flat" ? "" : '<feMergeNode in="gl"/>'}<feMergeNode in="g"/>${quality === "full" ? '<feMergeNode data-mta-specular-merge in="sp2"/>' : ""}</feMerge>`;
  return (
    `<svg class="mta-svg" viewBox="${GEOMETRY.viewBox}" preserveAspectRatio="xMidYMid meet" xmlns="http://www.w3.org/2000/svg" aria-hidden="true" focusable="false">` +
    `<defs><clipPath id="${uid}-shellclip"><circle cx="${GEOMETRY.shell.cx}" cy="${GEOMETRY.shell.cy}" r="${GEOMETRY.shell.r}"/></clipPath><clipPath id="${uid}-clip"><rect ${pill}/></clipPath>` +
    `<radialGradient id="${uid}-shade" cx=".34" cy=".27" r=".95"><stop offset="0" stop-color="#fff" stop-opacity=".4"/><stop offset=".38" stop-color="#fff" stop-opacity="0"/><stop offset=".6" stop-color="#000" stop-opacity="0"/><stop offset="1" stop-color="#000" stop-opacity=".42"/></radialGradient>` +
    `<radialGradient id="${uid}-gloss" cx=".5" cy=".5" r=".5"><stop offset="0" stop-color="#fff" stop-opacity=".5"/><stop offset="1" stop-color="#fff" stop-opacity="0"/></radialGradient>` +
    `<filter id="${uid}-goo" filterUnits="userSpaceOnUse" x="${f.x}" y="${f.y}" width="${f.width}" height="${f.height}" color-interpolation-filters="sRGB">` +
    `<feGaussianBlur data-mta-goo in="SourceGraphic" stdDeviation="1.65" result="b"/><feColorMatrix in="b" type="matrix" values="1 0 0 0 0 0 1 0 0 0 0 0 1 0 0 0 0 0 20 -9.5" result="g"/>` +
    glow +
    light +
    merge +
    `</filter></defs>` +
    `<circle class="mta-shell" cx="${GEOMETRY.shell.cx}" cy="${GEOMETRY.shell.cy}" r="${GEOMETRY.shell.r}"/><circle cx="${GEOMETRY.shell.cx}" cy="${GEOMETRY.shell.cy}" r="${GEOMETRY.shell.r}" fill="url(#${uid}-shade)"/>` +
    `<g clip-path="url(#${uid}-shellclip)"><g data-mta-turn><g data-mta-face><rect class="mta-face" ${pill}/>` +
    `<g clip-path="url(#${uid}-clip)"><g data-mta-bars><g filter="url(#${uid}-goo)">${bars}</g></g></g></g></g></g>` +
    `<g data-mta-gloss><ellipse cx="150" cy="82" rx="86" ry="38" transform="rotate(-24 150 82)" fill="url(#${uid}-gloss)" opacity=".55"/></g></svg>`
  );
}

/* ───────────────────────────── shared ticker + pointer ───────────────────────────── */
const live = new Set();
let raf = 0,
  last = 0;
function frame(now) {
  if (now - last < 1000 / 30) {
    raf = live.size ? requestAnimationFrame(frame) : 0;
    return;
  }
  const dt = Math.min(0.05, Math.max(0, (now - last) / 1000));
  last = now;
  for (const a of live) a._step(dt);
  raf = live.size ? requestAnimationFrame(frame) : 0;
}
function wake(a) {
  live.add(a);
  if (!raf) {
    last = performance.now();
    raf = requestAnimationFrame(frame);
  }
}
const ptr = { x: 0, y: 0, t: -1e9 };
let ptrBound = false,
  pointerUsers = 0,
  unbindPointer = () => {};
function bindPointer() {
  pointerUsers++;
  if (ptrBound || typeof window === "undefined") return;
  ptrBound = true;
  const move = (e) => {
    ptr.x = e.clientX;
    ptr.y = e.clientY;
    ptr.t = performance.now();
  };
  window.addEventListener("pointermove", move, { passive: true });
  window.addEventListener("pointerdown", move, { passive: true });
  const leave = () => {
    ptr.t = -1e9;
  };
  document.documentElement.addEventListener("mouseleave", leave);
  unbindPointer = () => {
    window.removeEventListener("pointermove", move);
    window.removeEventListener("pointerdown", move);
    document.documentElement.removeEventListener("mouseleave", leave);
    ptrBound = false;
    ptr.t = -1e9;
  };
}

/* ───────────────────────────── controller ───────────────────────────── */
let avatarInstances = 0;
class Avatar {
  constructor(root, o) {
    this.root = root;
    this.fallbackIdentity = "avatar-instance-" + ++avatarInstances;
    this.identity = o.identity || this.fallbackIdentity;
    this.face = resolveAvatarFace(o.face);
    this.root.setAttribute("data-face", this.face);
    this.personality = avatarPersonality(this.identity);
    const sorted = (sel, key) =>
      Array.from(root.querySelectorAll(sel)).sort((a, b) => a.dataset[key] - b.dataset[key]);
    this.els = sorted("[data-mta-bar]", "mtaBar");
    if (this.els.length !== N)
      throw new Error("TradingAvatar: expected " + N + " [data-mta-bar] elements");
    this.turnG = root.querySelector("[data-mta-turn]");
    this.faceG = root.querySelector("[data-mta-face]");
    this.barsG = root.querySelector("[data-mta-bars]");
    this.glossG = root.querySelector("[data-mta-gloss]");
    this.gooEl = root.querySelector("[data-mta-goo]");
    this.glowEl = root.querySelector("[data-mta-glow]");
    this.glowOpacityEl = root.querySelector("[data-mta-glow-opacity]");
    this.lightEl = root.querySelector("[data-mta-light]");
    this.specularMergeEl = root.querySelector("[data-mta-specular-merge]");
    this.fl = this.fl0 = this.flT = 1;
    this.cache = this.els.map(() => ({}));
    this.cg = {};
    this.speed = clamp(Number.isFinite(o.speed) ? o.speed : 1, 0.25, 4);
    this.paused = !!o.paused;
    this.look = o.look || "pointer";
    this.accent = parseColor(o.accent, parseColor(DEFAULT_ACCENT));
    this.tgt = newSegs();
    this.shown = newSegs().map((s) => Object.assign(s, { r: EYE[0], g: EYE[1], b: EYE[2] }));
    this.snap = null;
    this.bt = MORPH_SECONDS;
    this.u = 0;
    this.visible = true;
    this.plan = ID_PLAN();
    this.destroyed = false;
    this._onVisibility = () => {
      if (document.hidden) live.delete(this);
      else this._refresh(true);
    };
    document.addEventListener("visibilitychange", this._onVisibility);
    this.g = { x: 0, y: 0, vx: 0, vy: 0 };
    this.pk = 0;
    this.pv = 0;
    this.seed = this.personality.phase * 100;
    this.rect = null;
    this.rectAge = 0;
    this.mq =
      typeof matchMedia === "function" ? matchMedia("(prefers-reduced-motion: reduce)") : null;
    this._onMq = () => this._refresh();
    if (this.mq && this.mq.addEventListener) this.mq.addEventListener("change", this._onMq);
    if (typeof IntersectionObserver === "function") {
      this.io = new IntersectionObserver((e) => {
        this.visible = e[e.length - 1].isIntersecting;
        this._refresh();
      });
      this.io.observe(root);
    }
    if (o.interactive !== false) {
      this._down = () => this.poke();
      root.addEventListener("pointerdown", this._down);
    }
    bindPointer();
    this._setState(STATE_IDS.includes(o.state) ? o.state : "waiting", true);
  }
  get reduced() {
    return !!(this.mq && this.mq.matches);
  }

  _setState(id, instant, preserveMotion = false) {
    if (!STATES[id]) return;
    this.id = id;
    this.def = STATES[id];
    if (!preserveMotion) {
      this.idleTime = 0;
      this.spinTime = null;
      this.yaw = 0;
    }
    this.fl0 = this.fl;
    this.flT = this.def.fluid === undefined ? 1 : this.def.fluid;
    this.u = this.reduced ? this.def.poster : preserveMotion ? this.u : 0;
    runState(
      this.def,
      this.u,
      this.tgt,
      this.identity,
      this.face,
      this.spinTime === null ? 1 : this.spinTime / this.personality.spinSeconds,
    );
    if (instant || this.reduced) {
      this.snap = null;
      this.bt = MORPH_SECONDS;
      this.plan = ID_PLAN();
      this.fl = this.flT;
    } else {
      this.snap = this.shown.map((s) => Object.assign({}, s));
      this.plan = planMorph(this.snap, this.tgt);
      this.bt = 0;
    }
    this.root.setAttribute("data-state", id);
    this._refresh(true);
  }
  _compose() {
    runState(
      this.def,
      this.u,
      this.tgt,
      this.identity,
      this.face,
      this.spinTime === null ? 1 : this.spinTime / this.personality.spinSeconds,
    );
    const acc = SEMANTIC[this.id] || this.accent,
      morphing = this.snap && this.bt < MORPH_SECONDS;
    for (let i = 0; i < N; i++) {
      const o = this.shown[i],
        t = this.tgt[this.plan.perm[i]];
      const e = morphSegment(morphing ? this.snap[i] : null, this.tgt, this.plan, i, this.bt, o);
      const c = tint(t, acc);
      if (e >= 1) {
        o.r = c[0];
        o.g = c[1];
        o.b = c[2];
      } else {
        const s = this.snap[i];
        o.r = lerp(s.r, c[0], e);
        o.g = lerp(s.g, c[1], e);
        o.b = lerp(s.b, c[2], e);
      }
    }
    this.fl = lerp(this.fl0, this.flT, morphing ? inOut(this.bt / MORPH_SECONDS) : 1);
    this._paint();
  }
  _paint() {
    const reaction =
      this.id === "waiting" && this.spinTime !== null
        ? faceReaction(this.spinTime / this.personality.spinSeconds, this.face, this.identity)
        : faceReaction(1, "face-smile");
    const gx = clamp(this.g.x + reaction.gazeX, -1, 1),
      gy = clamp(this.g.y + reaction.gazeY, -1, 1);
    if (this.turnG) {
      const turn = avatarTurn(this.id === "waiting" ? this.yaw : 0);
      const transform =
        "translate(" +
        fmt(200 + turn.tx) +
        " " +
        CY +
        ") scale(" +
        fmt(turn.scaleX) +
        " 1) translate(-200 " +
        -CY +
        ")";
      if (this.cg.turn !== transform) {
        this.cg.turn = transform;
        this.turnG.setAttribute("transform", transform);
      }
      if (this.cg.opacity !== turn.opacity) {
        this.cg.opacity = turn.opacity;
        this.turnG.setAttribute("opacity", String(turn.opacity));
      }
      this.turnG.setAttribute("data-yaw", String(fmt(this.id === "waiting" ? this.yaw : 0)));
    }
    const facial = this.id === "waiting" && this.face !== "orb",
      render = FACE_TOKENS.render;
    if (this.gooEl) {
      const sd = facial ? String(render.gooBlur) : (1.2 + 3 * this.fl).toFixed(1);
      if (this.cg.sd !== sd) {
        this.cg.sd = sd;
        this.gooEl.setAttribute("stdDeviation", sd);
      }
    }
    if (this.cg.facialFilter !== facial) {
      this.cg.facialFilter = facial;
      if (this.glowEl)
        this.glowEl.setAttribute("stdDeviation", String(facial ? render.glowBlur : 9));
      if (this.glowOpacityEl)
        this.glowOpacityEl.setAttribute(
          "values",
          "1 0 0 0 0 0 1 0 0 0 0 0 1 0 0 0 0 0 " + (facial ? render.glowOpacity : 0.5) + " 0",
        );
      if (this.lightEl) this.lightEl.setAttribute("specularConstant", facial ? "0" : ".9");
      // Zero specular light still has opaque alpha; merge a transparent flood for facial content.
      if (this.specularMergeEl)
        this.specularMergeEl.setAttribute("in", facial ? "faceNoSpec" : "sp2");
    }
    for (let i = 0; i < N; i++) {
      const s = this.shown[i];
      const depth = (1 - gx * clamp((s.cx - 200) / 60, -1, 1) * 0.14) * GLYPH_SCALE; // far side of the turn looks smaller
      const w = s.w < 1 ? "0.01" : fmt(s.w * depth);
      const d = segPath(
        200 + (s.cx - 200) * GLYPH_SCALE,
        CY + (s.cy - CY) * GLYPH_SCALE,
        s.L * depth,
        s.th,
        s.k / depth,
      );
      const stroke = "rgb(" + Math.round(s.r) + "," + Math.round(s.g) + "," + Math.round(s.b) + ")",
        op = String(fmt(s.o));
      const el = this.els[i],
        c = this.cache[i];
      if (c.d !== d) {
        c.d = d;
        el.setAttribute("d", d);
      }
      if (c.w !== w) {
        c.w = w;
        el.setAttribute("stroke-width", w);
      }
      if (c.s !== stroke) {
        c.s = stroke;
        el.style.stroke = stroke;
      }
      if (c.o !== op) {
        c.o = op;
        el.style.opacity = op;
      }
    }
    if (this.faceG) {
      const ft = fmtT(faceTransform(gx, gy, this.pk));
      if (this.cg.f !== ft) {
        this.cg.f = ft;
        this.faceG.setAttribute("transform", ft);
      }
    }
    if (this.barsG) {
      const bt =
        "translate(" +
        fmt(gx * 6) +
        " " +
        fmt(gy * 4 + reaction.offsetY) +
        ") translate(200 " +
        CY +
        ") rotate(" +
        fmt(reaction.tilt) +
        ") scale(" +
        fmt(reaction.scale) +
        ") translate(-200 " +
        -CY +
        ")";
      if (this.cg.b !== bt) {
        this.cg.b = bt;
        this.barsG.setAttribute("transform", bt);
      }
    }
    if (this.glossG) {
      const gt = "translate(" + fmt(-gx * 12 - this.pk * 4) + " " + fmt(-gy * 9) + ")";
      if (this.cg.g !== gt) {
        this.cg.g = gt;
        this.glossG.setAttribute("transform", gt);
      }
    }
  }
  _pointerNear() {
    const r = this.root.getBoundingClientRect(),
      margin = Math.min(36, r.width * 0.4);
    this.rect = r;
    return (
      ptr.x >= r.left - margin &&
      ptr.x <= r.right + margin &&
      ptr.y >= r.top - margin &&
      ptr.y <= r.bottom + margin
    );
  }
  _gaze(dt) {
    let tx = 0,
      ty = 0;
    const sg = this.def.gaze ? this.def.gaze(this.u) : null,
      now = performance.now();
    if (this.look === "off") {
      /* centred */
    } else if (sg) {
      tx = sg[0];
      ty = sg[1];
    } else if (this.look === "pointer" && now - ptr.t < 1600 && this._pointerNear()) {
      if (!this.rect || this.rectAge++ % 30 === 0) this.rect = this.root.getBoundingClientRect();
      const r = this.rect,
        span = Math.max(r.width * 1.1, 120);
      tx = clamp((ptr.x - (r.left + r.width / 2)) / span, -1, 1);
      ty = clamp((ptr.y - (r.top + r.height / 2)) / span, -1, 1) * 0.8;
    } else if (this.id === "waiting") {
      const idle = idleAvatarPose(this.idleTime, this.identity, this.face);
      tx = idle.gazeX;
      ty = idle.gazeY;
    } else {
      const t = now / 1000 + this.seed;
      tx = 0.8 * Math.sin(t * 0.42) * (0.65 + 0.35 * Math.sin(t * 0.13));
      ty = 0.22 * Math.sin(t * 0.29 + 1.3);
    }
    const g = this.g;
    g.vx += ((tx - g.x) * 90 - g.vx * 14) * dt;
    g.x += g.vx * dt;
    g.vy += ((ty - g.y) * 90 - g.vy * 14) * dt;
    g.y += g.vy * dt;
  }
  _step(dt) {
    if (!this.visible) {
      live.delete(this);
      return;
    }
    if (!this.paused) {
      this.u = wrap(
        this.u +
          (dt * this.speed * (this.id === "waiting" ? this.personality.tempo : 1)) /
            (BASE_SECONDS * this.def.k),
      );
      if (this.id === "waiting") {
        this.idleTime += dt * this.speed;
        if (this.spinTime !== null) {
          this.spinTime += dt * this.speed;
          this.yaw = faceReaction(
            this.spinTime / this.personality.spinSeconds,
            this.face,
            this.identity,
          ).yaw;
          if (this.spinTime >= this.personality.spinSeconds) {
            this.spinTime = null;
            this.idleTime = 0;
            this.yaw = 0;
          }
        } else this.yaw = idleAvatarPose(this.idleTime, this.identity, this.face).yaw;
      }
      this._gaze(dt);
    }
    if (this.bt < MORPH_SECONDS) this.bt += dt;
    if (this.pk !== 0 || this.pv !== 0) {
      this.pv += (-160 * this.pk - 12 * this.pv) * dt;
      this.pk += this.pv * dt;
      if (Math.abs(this.pk) < 0.002 && Math.abs(this.pv) < 0.02) {
        this.pk = 0;
        this.pv = 0;
      }
    }
    this._compose();
    if (this.paused && this.bt >= MORPH_SECONDS && this.pk === 0 && this.pv === 0)
      live.delete(this);
  }
  _refresh(force) {
    if (this.destroyed || document.hidden) {
      live.delete(this);
      return;
    }
    if (this.reduced) {
      live.delete(this);
      this.bt = MORPH_SECONDS;
      this.snap = null;
      this.g.x = this.g.y = 0;
      this.yaw = 0;
      this.u = this.def.poster;
      this._compose();
      return;
    }
    if (force) this._compose();
    if (this.visible && (!this.paused || this.bt < MORPH_SECONDS)) wake(this);
  }
  setIdentity(identity) {
    const next = identity || this.fallbackIdentity;
    if (next === this.identity) return;
    this.identity = next;
    this.personality = avatarPersonality(next);
    this.seed = this.personality.phase * 100;
    if (this.id === "waiting") this._setState(this.id, false);
  }
  setFace(face) {
    const next = resolveAvatarFace(face);
    if (next === this.face) return;
    this.face = next;
    this.root.setAttribute("data-face", next);
    if (this.id === "waiting") this._setState(this.id, false, true);
  }
  setState(id) {
    if (id !== this.id) this._setState(id, false);
  }
  setSpeed(v) {
    this.speed = clamp(Number.isFinite(v) ? v : 1, 0.25, 4);
  }
  setLook(m) {
    this.look = m || "pointer";
  }
  setPaused(p) {
    this.paused = !!p;
    if (this.paused) {
      this.bt = MORPH_SECONDS;
      this._compose();
      live.delete(this);
    } else this._refresh();
  }
  setAccent(c) {
    this.accent = parseColor(c, parseColor(DEFAULT_ACCENT));
    this._compose();
  }
  poke() {
    if (this.reduced || this.paused || document.hidden || this.destroyed) return;
    this.pk = 0;
    this.pv = 6;
    if (this.id === "waiting" && this.spinTime === null) {
      this.spinTime = 0;
      this.yaw = 0;
    }
    if (this.visible) wake(this);
  }
  seek(u, gx, gy) {
    this.bt = MORPH_SECONDS;
    this.u = wrap(u);
    if (gx !== undefined) {
      this.g.x = gx;
      this.g.vx = 0;
    }
    if (gy !== undefined) {
      this.g.y = gy;
      this.g.vy = 0;
    }
    this._compose();
  }
  /** Test/demo helper: start a morph to `id` and freeze it `t` seconds in. */
  scrubMorph(id, t) {
    this._setState(id, false);
    live.delete(this);
    this.paused = true;
    this.bt = t;
    this.u = wrap(t / (BASE_SECONDS * this.def.k));
    this._compose();
  }
  destroy() {
    if (this.destroyed) return;
    this.destroyed = true;
    live.delete(this);
    if (!live.size && raf) {
      cancelAnimationFrame(raf);
      raf = 0;
    }
    document.removeEventListener("visibilitychange", this._onVisibility);
    if (--pointerUsers === 0) unbindPointer();
    if (this.io) this.io.disconnect();
    if (this._down) this.root.removeEventListener("pointerdown", this._down);
    if (this.mq && this.mq.removeEventListener) this.mq.removeEventListener("change", this._onMq);
  }
}

export function mount(root, options = {}) {
  const a = new Avatar(root, options);
  return {
    setFace: (face) => a.setFace(face),
    setIdentity: (identity) => a.setIdentity(identity),
    setState: (id) => a.setState(id),
    setSpeed: (v) => a.setSpeed(v),
    setPaused: (p) => a.setPaused(p),
    setAccent: (c) => a.setAccent(c),
    setLook: (m) => a.setLook(m),
    poke: () => a.poke(),
    seek: (u, gx, gy) => a.seek(u, gx, gy),
    scrubMorph: (id, t) => a.scrubMorph(id, t),
    getState: () => a.id,
    destroy: () => a.destroy(),
  };
}
