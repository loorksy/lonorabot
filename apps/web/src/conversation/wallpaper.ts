// biome-ignore-all lint/style/useTemplate: ported verbatim from the reference
// biome-ignore-all lint/complexity/useArrowFunction: ported verbatim from the reference
// biome-ignore-all lint/style/useConst: ported verbatim from the reference
/* The chat wallpaper of docs/ui-reference/Lonora-Desktop-37.html (4832-4960), ported line for
   line: a seeded Poisson-disc doodle on a 432px torus, one ink (currentColor), built once into a
   hidden sprite (#lw-defs); the chat paints one <rect fill="url(#lw-p-…)">. */
type WallPoint = { x: number; y: number; n: string; rot: number; s: number; R: number };
const WALL = { tile: 432, gap: 47, size: 1.06, sw: 1.15, tilt: 14 };
const wallGear = (() => {
  const n = 8,
    o = 9.4,
    i = 7.1,
    h = Math.PI / n,
    p: string[] = [];
  for (let k = 0; k < n; k++) {
    const a = (k / n) * Math.PI * 2 - Math.PI / 2;
    [
      [i, a - h * 0.62],
      [o, a - h * 0.34],
      [o, a + h * 0.34],
      [i, a + h * 0.62],
    ].forEach(([r, t]) =>
      p.push((12 + r * Math.cos(t)).toFixed(2) + " " + (12 + r * Math.sin(t)).toFixed(2)),
    );
  }
  return "M" + p.join("L") + "z";
})();
const dots = (d: string, w = 1.8) => `<path stroke-width="${w}" d="${d}"/>`;
/* the icons — the same subjects and details as the Lonora illustration, redrawn as one-weight line art */
const WI = {
  calendar: `<path d="M13.6 20H6a3 3 0 0 1-3-3V8a3 3 0 0 1 3-3h10a3 3 0 0 1 3 3v5.2M3 9.6h16M7.5 3.2v3.6M14.5 3.2v3.6"/><circle cx="18.6" cy="18.4" r="3.9"/><path d="M16.9 18.5l1.1 1.1 2.2-2.3"/>${dots("M7 13.2h.01M11 13.2h.01M15 13.2h.01M7 16.6h.01M11 16.6h.01")}`,
  chartUp: `<path d="M4.2 20.5v-4.3h3v4.3zM10.2 20.5v-7h3v7zM16.2 20.5v-9.8h3v9.8zM3.4 12.3C8 11.4 12.6 8.4 17.4 3.6M13.2 3.4h4.4v4.4"/>`,
  candles: `<path d="M2.6 21.4l18.8-3.6M5.6 8.8v2.4M5.6 16.6v2.2M4.2 11.2h2.8v5.4H4.2zM11 6v2.4M11 13.6v2.2M9.6 8.4h2.8v5.2H9.6zM16.4 2.6v2.2M16.4 10.6v2.4M15 4.8h2.8v5.8H15z"/>`,
  bulb: `<path d="M9.6 15.8c0-1.4-.6-2.2-1.3-2.9a5.3 5.3 0 1 1 7.4 0c-.7.7-1.3 1.5-1.3 2.9zM9.8 18.2h4.4M10.7 20.6h2.6M10.4 11.6l1.6 1.8 1.6-1.8M12 13.4v2.4M12 .9v1.6M5.3 3.3l1.1 1.1M18.7 3.3l-1.1 1.1M3 9.4h1.6M19.4 9.4H21"/>`,
  robot: `<path d="M8.8 8.6h6.4a4.6 4.6 0 0 1 4.6 4.6v1.6a4.6 4.6 0 0 1-4.6 4.6H8.8a4.6 4.6 0 0 1-4.6-4.6v-1.6a4.6 4.6 0 0 1 4.6-4.6zM12 8.6V6.1M4.2 12.4h-.9a1 1 0 0 0-1 1v1.2a1 1 0 0 0 1 1h.9M19.8 12.4h.9a1 1 0 0 1 1 1v1.2a1 1 0 0 1-1 1h-.9M18.6 5.6l1.3-1.3M20.2 7.7h1.7"/><circle cx="12" cy="4.7" r="1.4"/>${dots("M9.6 13v1.6M14.4 13v1.6", 2)}`,
  chip: `<path d="M8.2 6h7.6A2.2 2.2 0 0 1 18 8.2v7.6a2.2 2.2 0 0 1-2.2 2.2H8.2A2.2 2.2 0 0 1 6 15.8V8.2A2.2 2.2 0 0 1 8.2 6zM9.5 3v3M12 3v3M14.5 3v3M9.5 18v3M12 18v3M14.5 18v3M3 9.5h3M3 12h3M3 14.5h3M18 9.5h3M18 12h3M18 14.5h3M8.9 15l1.8-5.8 1.8 5.8M9.5 13h2.4M15 9.2V15"/>`,
  target: `<path d="M18.7 11.3A8.5 8.5 0 1 1 12.7 5.3M15.1 12.3A4.8 4.8 0 1 1 11.7 8.9M10.5 13.5l6-6M16.5 7.5V4.6l2.9-2.9v2.9h2.9l-2.9 2.9z"/><circle cx="10.5" cy="13.5" r="1.2" fill="currentColor" stroke="none"/>`,
  chat: `<path d="M6.2 4.5h11.6a3.6 3.6 0 0 1 3.6 3.6v6.6a3.6 3.6 0 0 1-3.6 3.6h-6.3l-4.3 3.3v-3.3h-1a3.6 3.6 0 0 1-3.6-3.6V8.1a3.6 3.6 0 0 1 3.6-3.6z"/>${dots("M8 11.4h.01M12 11.4h.01M16 11.4h.01", 2)}`,
  coins: `<path d="M2.2 6.6a4.8 2 0 1 0 9.6 0a4.8 2 0 1 0-9.6 0M2.2 6.6v7a4.8 2 0 0 0 9.6 0v-7M2.2 10.1a4.8 2 0 0 0 9.6 0M12.2 13.4a4.8 2 0 1 0 9.6 0a4.8 2 0 1 0-9.6 0M12.2 13.4v6.8a4.8 2 0 0 0 9.6 0v-6.8M12.2 16.8a4.8 2 0 0 0 9.6 0"/>`,
  briefcase: `<path d="M4.6 8.2h14.8a2.1 2.1 0 0 1 2.1 2.1v8.2a2.1 2.1 0 0 1-2.1 2.1H4.6a2.1 2.1 0 0 1-2.1-2.1v-8.2a2.1 2.1 0 0 1 2.1-2.1zM9 8.2V6.4A1.4 1.4 0 0 1 10.4 5h3.2A1.4 1.4 0 0 1 15 6.4v1.8M2.5 13.6H10M14 13.6h7.5M10 12.2h4V15h-4z"/>`,
  cloud: `<path d="M7 18.5h10.2a4.3 4.3 0 0 0 .5-8.6 6 6 0 0 0-11.5 1.8A3.5 3.5 0 0 0 7 18.5z"/>`,
  cloudUp: `<path d="M8.2 18.5H7a3.5 3.5 0 0 1-.8-6.8 6 6 0 0 1 11.5-1.8 4.3 4.3 0 0 1-.5 8.6h-1.4M12 20.8v-7.4M9.2 16.1l2.8-2.8 2.8 2.8"/>`,
  checklist: `<path d="M5.2 3.6h13.6a2.6 2.6 0 0 1 2.6 2.6v11.6a2.6 2.6 0 0 1-2.6 2.6H5.2a2.6 2.6 0 0 1-2.6-2.6V6.2a2.6 2.6 0 0 1 2.6-2.6zM11 8.4h7M11 12h7M11 15.6h4.6M5.8 8.4l1.1 1.1 2-2.2M5.8 12l1.1 1.1 2-2.2M5.8 15.6l1.1 1.1 2-2.2"/>`,
  mic: `<path d="M12 2.6a3.2 3.2 0 0 1 3.2 3.2v5a3.2 3.2 0 0 1-6.4 0v-5A3.2 3.2 0 0 1 12 2.6zM6.6 10.4a5.4 5.4 0 0 0 10.8 0M12 15.8v4.4M8.8 20.2h6.4"/>${dots("M11 6.3h.01M13 6.3h.01M11 8.6h.01M13 8.6h.01", 1.4)}`,
  bell: `<path d="M12 4.2a5.4 5.4 0 0 1 5.4 5.4v3.1c0 1.8.8 3.2 2 4.1H4.6c1.2-.9 2-2.3 2-4.1V9.6A5.4 5.4 0 0 1 12 4.2zM12 4.2V2.8M10.3 19.4a1.9 1.9 0 0 0 3.4 0M19.3 4.4l1.2-1.1M20.4 7.4l1.6-.4"/>`,
  shield: `<path d="M12 2.8l7.4 2.8v5.6c0 4.6-3.1 8.2-7.4 9.8-4.3-1.6-7.4-5.2-7.4-9.8V5.6zM8.8 12l2.2 2.2 4.2-4.5"/>`,
  doc: `<path d="M6.6 2.6H14l5 5v11.8a2 2 0 0 1-2 2H6.6a2 2 0 0 1-2-2V4.6a2 2 0 0 1 2-2zM14 2.6v5h5M8 12.2h8M8 15.2h8M8 18.2h5"/>`,
  database: `<path d="M5 5.6a7 2.6 0 1 0 14 0a7 2.6 0 1 0-14 0M5 5.6v12.8a7 2.6 0 0 0 14 0V5.6M5 9.9a7 2.6 0 0 0 14 0M5 14.2a7 2.6 0 0 0 14 0"/>`,
  magnifier: `<circle cx="10.2" cy="10.2" r="6.4"/><path d="M7.1 9.3a3.3 3.3 0 0 1 2.3-2.3"/><path stroke-width="2.1" d="M15 15l5.4 5.4"/>`,
  gear: `<path d="${wallGear}"/><circle cx="12" cy="12" r="3"/>`,
  laptop: `<path d="M5.2 4.6h13.6a1.6 1.6 0 0 1 1.6 1.6v9.4H3.6V6.2a1.6 1.6 0 0 1 1.6-1.6zM1.8 15.6h20.4l-.9 2.2a1.6 1.6 0 0 1-1.5 1H4.2a1.6 1.6 0 0 1-1.5-1z"/>${dots("M9.2 12.8v-1.6M12 12.8v-3M14.8 12.8v-4.6", 1.7)}`,
  lineWin: `<path d="M4.4 4.4h15.2a2 2 0 0 1 2 2v11.2a2 2 0 0 1-2 2H4.4a2 2 0 0 1-2-2V6.4a2 2 0 0 1 2-2zM2.4 8.4h19.2M5.4 15.4l2.8-2.8 2.4 2 3.2-3.8 2.4 1.8 2.6-2.8"/>`,
  trend: `<path d="M2.6 18.6l5.6-5.6 4 3.6 8.6-9.4M15.4 7.2h5.4v5.4"/>`,
  code: `<path d="M5.1 4.8h13.8a2.6 2.6 0 0 1 2.6 2.6v9.2a2.6 2.6 0 0 1-2.6 2.6H5.1a2.6 2.6 0 0 1-2.6-2.6V7.4a2.6 2.6 0 0 1 2.6-2.6zM9 9.4L6.6 12 9 14.6M15 9.4l2.4 2.6-2.4 2.6M13.1 8.8l-2.2 6.4"/>`,
  layers: `<path d="M12 3.2l8.6 4.3-8.6 4.3-8.6-4.3zM3.4 12l8.6 4.3 8.6-4.3M3.4 16.4l8.6 4.3 8.6-4.3"/>`,
  globe: `<circle cx="12" cy="12" r="9.3"/><path d="M12 2.7c-2.6 2.6-3.9 5.7-3.9 9.3s1.3 6.7 3.9 9.3c2.6-2.6 3.9-5.7 3.9-9.3S14.6 5.3 12 2.7zM2.7 12h18.6M4 7.3h16M4 16.7h16"/>`,
  logo: `<path d="M7.2 6.6h9.6a5.4 5.4 0 0 1 0 10.8H7.2a5.4 5.4 0 0 1 0-10.8z"/>${dots("M8.4 14.2v-1.4M10.9 14.2v-2.8M13.4 14.2v-4.6M15.9 14.2v-1.6", 1.9)}`,
};
/* small fillers for the gaps */
const WF = {
  sparkle: `<path d="M12 6.5c.4 3 2 4.7 5 5-3 .4-4.6 2-5 5-.4-3-2-4.6-5-5 3-.3 4.6-2 5-5z"/>`,
  ring: `<circle cx="12" cy="12" r="3"/>`,
  dot: `<circle cx="12" cy="12" r="1.15" fill="currentColor" stroke="none"/>`,
  arc: `<path d="M6.5 15.5a8 8 0 0 1 9-8"/>`,
  plus: `<path d="M12 9.6v4.8M9.6 12h4.8"/>`,
  wave: `<path d="M6.4 13.2c1.4-1.6 2.8-1.6 4.2 0s2.8 1.6 4.2 0 2.8-1.6 4.2 0"/>`,
};
const WALLS = {
  lonora: {
    name: "Lonora",
    icons: [
      "logo",
      "calendar",
      "chartUp",
      "bulb",
      "candles",
      "robot",
      "code",
      "layers",
      "globe",
      "chip",
      "target",
      "chat",
      "laptop",
      "coins",
      "gear",
      "magnifier",
      "cloudUp",
      "briefcase",
      "checklist",
      "doc",
      "database",
      "mic",
      "bell",
      "shield",
      "trend",
      "cloud",
      "lineWin",
    ],
  },
  agents: {
    name: "الوكلاء",
    icons: [
      "robot",
      "chip",
      "code",
      "bulb",
      "gear",
      "layers",
      "database",
      "magnifier",
      "chat",
      "globe",
      "laptop",
      "cloudUp",
      "doc",
      "shield",
      "logo",
      "checklist",
      "mic",
      "bell",
      "cloud",
    ],
  },
  market: {
    name: "السوق",
    icons: [
      "candles",
      "chartUp",
      "coins",
      "target",
      "trend",
      "lineWin",
      "laptop",
      "briefcase",
      "calendar",
      "shield",
      "doc",
      "database",
      "globe",
      "bell",
      "checklist",
      "logo",
      "magnifier",
    ],
  },
  calm: { name: "هادئ", icons: [] },
  none: { name: "بدون", icons: [] },
};
/* layer opacity per level, [dark, light] */
const WALL_LV = {
  light: { name: "خفيفة", a: [0.1, 0.085] },
  mid: { name: "متوسطة", a: [0.15, 0.12] },
  strong: { name: "أوضح", a: [0.21, 0.17] },
};
function wallRand(seed: number) {
  let s = seed >>> 0;
  return () => {
    s = (s + 0x6d2b79f5) >>> 0;
    let t = s;
    t = Math.imul(t ^ (t >>> 15), t | 1);
    t ^= t + Math.imul(t ^ (t >>> 7), t | 61);
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}
/* Positions on a torus (distances wrap around the tile), so the pattern has no seams. */
function wallLayout(id: WallId): WallPoint[] {
  const T = WALL.tile,
    set = WALLS[id],
    rand = wallRand([...id].reduce((h, c) => Math.imul(h ^ c.charCodeAt(0), 16777619), 2166136261));
  const d2 = (a: WallPoint, b: WallPoint) => {
    let x = Math.abs(a.x - b.x),
      y = Math.abs(a.y - b.y);
    x = Math.min(x, T - x);
    y = Math.min(y, T - y);
    return x * x + y * y;
  };
  const icons: WallPoint[] = [],
    fill: WallPoint[] = [],
    r = WALL.gap;
  if (set.icons.length) {
    const active: WallPoint[] = [{ x: rand() * T, y: rand() * T } as WallPoint];
    icons.push(active[0]);
    while (active.length) {
      // Bridson: grow from live points
      const i = Math.floor(rand() * active.length),
        p = active[i];
      let found = false;
      for (let k = 0; k < 30 && !found; k++) {
        const a = rand() * Math.PI * 2,
          rr = r * (1 + rand() * 0.6),
          q: WallPoint = {
            x: (((p.x + Math.cos(a) * rr) % T) + T) % T,
            y: (((p.y + Math.sin(a) * rr) % T) + T) % T,
          } as WallPoint;
        if (icons.every((o) => d2(o, q) >= r * r)) {
          icons.push(q);
          active.push(q);
          found = true;
        }
      }
      if (!found) active.splice(i, 1);
    }
    const used: Record<string, number> = Object.fromEntries(set.icons.map((n) => [n, 0]));
    icons.forEach((p, i) => {
      // least used first, never twice side by side
      const near = new Set(
        icons
          .slice(0, i)
          .filter((o) => d2(o, p) < (r * 2.2) ** 2)
          .map((o) => o.n),
      );
      let pool = set.icons.filter((n) => !near.has(n));
      if (!pool.length) pool = set.icons;
      const m = Math.min(...pool.map((n) => used[n])),
        best = pool.filter((n) => used[n] === m);
      p.n = best[Math.floor(rand() * best.length)];
      used[p.n]++;
      Object.assign(p, {
        rot: (rand() * 2 - 1) * WALL.tilt,
        s: WALL.size * (0.94 + rand() * 0.12),
        R: 16,
      });
    });
  }
  const calm = !icons.length,
    gapIcon = 24,
    gapOwn = calm ? 30 : 26,
    max = calm ? 999 : Math.round(icons.length * 0.9);
  const kinds = calm
    ? ["sparkle", "ring", "dot", "arc", "plus", "sparkle", "dot", "wave"]
    : ["sparkle", "dot", "ring", "sparkle", "arc", "dot", "plus", "ring", "wave"];
  for (let t = 0; t < 6000 && fill.length < max; t++) {
    const q = { x: rand() * T, y: rand() * T } as WallPoint;
    if (
      icons.some((o) => d2(o, q) < gapIcon * gapIcon) ||
      fill.some((o) => d2(o, q) < gapOwn * gapOwn)
    )
      continue;
    Object.assign(q, {
      n: kinds[Math.floor(rand() * kinds.length)],
      rot: rand() * 360,
      s: WALL.size * (calm ? 1.18 : 1) * (0.9 + rand() * 0.2),
      R: 9,
    });
    fill.push(q);
  }
  return [...icons, ...fill];
}
function wallUse(p: WallPoint) {
  const T = WALL.tile,
    xs = [0],
    ys = [0];
  if (p.x < p.R) xs.push(T);
  if (p.x > T - p.R) xs.push(-T);
  if (p.y < p.R) ys.push(T);
  if (p.y > T - p.R) ys.push(-T);
  let out = "";
  for (const dx of xs)
    for (const dy of ys)
      out += `<use href="#lw-i-${p.n}" transform="translate(${(p.x + dx).toFixed(1)} ${(p.y + dy).toFixed(1)}) rotate(${p.rot.toFixed(1)}) scale(${p.s.toFixed(3)}) translate(-12 -12)" stroke-width="${(WALL.sw / p.s).toFixed(2)}"/>`;
  return out;
}
function wallPattern(id: WallId) {
  const T = WALL.tile;
  return `<pattern id="lw-p-${id}" patternUnits="userSpaceOnUse" width="${T}" height="${T}"><g fill="none" stroke="currentColor" stroke-linecap="round" stroke-linejoin="round">${wallLayout(id).map(wallUse).join("")}</g></pattern>`;
}
/* The sprite is built once and lives outside #app, so re-renders only redraw one <rect>. */
export type WallId = keyof typeof WALLS;
export const WALL_LEVELS = WALL_LV;
/** Builds the sprite once, outside the app root. */
export function wallDefs() {
  if (document.getElementById("lw-defs")) return;
  const icons = Object.entries({ ...WI, ...WF })
    .map(([n, d]) => `<g id="lw-i-${n}">${d}</g>`)
    .join("");
  const pats = (Object.keys(WALLS) as WallId[])
    .filter((id) => WALLS[id].icons.length || id === "calm")
    .map(wallPattern)
    .join("");
  document.body.insertAdjacentHTML(
    "beforeend",
    `<svg id="lw-defs" aria-hidden="true" focusable="false"><defs>${icons}${pats}</defs></svg>`,
  );
}
