import { type BarPose, segmentPoints } from "./trading-avatar-motion";

export { CAT_AVATAR_ASSETS } from "./cat-avatar-assets";

/** Shared projection of the supplied matte 3D cat. Both renderers use the same artwork and glyphs. */
export const CAT_AVATAR_VIEWBOX = "0 0 400 400";
export const CAT_AVATAR_PALETTES = {
  night: { shell: "#eae3df", signal: "#eae3df", visor: "#151515" },
  day: { shell: "#303032", signal: "#303032", visor: "#f6f1eb" },
} as const;
export type CatAvatarTheme = keyof typeof CAT_AVATAR_PALETTES;
export type CatAvatarSignal = { path: string; width: number; opacity: number };

// The reference visor contour, sampled every 2.8125 degrees from its actual 3D mesh.
// This shared fit preserves moving arrows and morphs without cutting them at the visor lip.
const SCREEN_RADII: readonly number[] = [
  3.95423, 3.9467, 3.93723, 3.92318, 3.90416, 3.88032, 3.85258, 3.8188, 3.77447, 3.72488, 3.67464,
  3.61595, 3.54707, 3.47596, 3.40246, 3.32476, 3.24437, 3.16546, 3.08979, 3.01668, 2.94859, 2.88669,
  2.83114, 2.78213, 2.73915, 2.70178, 2.66945, 2.64182, 2.61866, 2.60002, 2.5868, 2.57895, 2.57634,
  2.57895, 2.5868, 2.60002, 2.61866, 2.64182, 2.66945, 2.70178, 2.73915, 2.78213, 2.83114, 2.88669,
  2.94859, 3.01668, 3.08979, 3.16546, 3.24437, 3.32476, 3.40246, 3.47596, 3.54707, 3.61595, 3.67464,
  3.72488, 3.77447, 3.8188, 3.85258, 3.88032, 3.90416, 3.92318, 3.93723, 3.9467, 3.95423, 3.96487,
  3.9725, 3.97188, 3.96522, 3.95364, 3.93851, 3.91824, 3.88821, 3.84858, 3.79872, 3.73971, 3.67318,
  3.59735, 3.51396, 3.42849, 3.34088, 3.25172, 3.16579, 3.08479, 3.00808, 2.9388, 2.8774, 2.82269,
  2.77394, 2.73071, 2.69355, 2.66281, 2.63815, 2.61925, 2.60595, 2.59805, 2.59542, 2.59805, 2.60595,
  2.61925, 2.63815, 2.66281, 2.69355, 2.73071, 2.77394, 2.82269, 2.8774, 2.9388, 3.00808, 3.08479,
  3.16579, 3.25172, 3.34088, 3.42849, 3.51396, 3.59735, 3.67318, 3.73971, 3.79872, 3.84858, 3.88821,
  3.91824, 3.93851, 3.95364, 3.96522, 3.97188, 3.9725, 3.96487,
];
const TAU = Math.PI * 2;
const SIGNAL_SCALE = 0.0375;
const PIXELS_PER_UNIT = 250 / 6.15;

function screenRadius(angle: number) {
  const sample =
    ((((angle / TAU) * SCREEN_RADII.length) % SCREEN_RADII.length) + SCREEN_RADII.length) %
    SCREEN_RADII.length;
  const index = Math.floor(sample);
  const t = sample - index;
  return SCREEN_RADII[index] * (1 - t) + SCREEN_RADII[(index + 1) % SCREEN_RADII.length] * t;
}
function smoothLimit(value: number, limit: number) {
  if (limit <= 0.0001) return 0;
  const amount = Math.abs(value),
    knee = limit * 0.6;
  return (
    Math.sign(value) *
    (amount <= knee ? amount : limit - (limit - knee) * Math.exp(-(amount - knee) / (limit - knee)))
  );
}
function fitSignals(bars: readonly BarPose[]) {
  let minX = Infinity,
    maxX = -Infinity,
    minY = Infinity,
    maxY = -Infinity;
  const outlines: { points: number[][]; half: number }[] = [];
  for (const bar of bars) {
    if (bar.o <= 0.012 || bar.w <= 0.01) continue;
    const half = bar.w * SIGNAL_SCALE * 0.5;
    const points = segmentPoints(bar, 24).map(([x, y]) => [
      (x - 200) * SIGNAL_SCALE,
      -(y - 200.5) * SIGNAL_SCALE,
    ]);
    for (const [x, y] of points) {
      minX = Math.min(minX, x - half);
      maxX = Math.max(maxX, x + half);
      minY = Math.min(minY, y - half);
      maxY = Math.max(maxY, y + half);
    }
    outlines.push({ points, half });
  }
  if (!outlines.length) return { scale: 1, dx: 0, dy: 0 };
  const midX = (minX + maxX) * 0.5,
    midY = (minY + maxY) * 0.5;
  const halfX = (maxX - minX) * 0.5,
    halfY = (maxY - minY) * 0.5;
  const scale = Math.min(1, 3.1 / Math.max(0.01, halfX), 2.04 / Math.max(0.01, halfY));
  const dx = smoothLimit(midX * scale, Math.max(0, 3.35 - halfX * scale)) - midX * scale;
  const dy = smoothLimit(midY * scale, Math.max(0, 2.13 - halfY * scale)) - midY * scale;
  let outermost = 0;
  for (const group of outlines)
    for (const [x, y] of group.points) {
      const vx = x * scale + dx,
        vy = y * scale + dy;
      outermost = Math.max(
        outermost,
        (Math.hypot(vx, vy) + group.half * scale) / Math.max(0.1, screenRadius(Math.atan2(vy, vx))),
      );
    }
  const extra = outermost > 0.865 ? 0.865 / outermost : 1;
  return { scale: scale * extra, dx: dx * extra, dy: dy * extra };
}

/** Original reference signal fit, projected into the cropped 400px frontal shell artwork. */
export function catAvatarSignals(bars: readonly BarPose[]): CatAvatarSignal[] {
  const fit = fitSignals(bars);
  return bars.map((bar) => {
    if (bar.w <= 0.01 || bar.o <= 0.002) return { path: "", width: 0, opacity: 0 };
    const path = segmentPoints(bar, 38)
      .map(([x, y], index) => {
        const vx = (x - 200) * SIGNAL_SCALE * fit.scale + fit.dx;
        const vy = -(y - 200.5) * SIGNAL_SCALE * fit.scale + fit.dy;
        // Original vertex shader: x *= .93, viewport=1/6.15, vertical camera offset=.30.
        // Capture crops source rectangle (40,20,320,320), scaled to a 400px square.
        const px = 200 + vx * 0.93 * PIXELS_PER_UNIT;
        const py = 225 + (0.3 - vy) * PIXELS_PER_UNIT;
        return `${index ? "L" : "M"}${px.toFixed(2)} ${py.toFixed(2)}`;
      })
      .join(" ");
    return {
      path,
      width: Math.max(0.01, bar.w * SIGNAL_SCALE * fit.scale * PIXELS_PER_UNIT * 0.965),
      opacity: Math.max(0, Math.min(1, bar.o)),
    };
  });
}
