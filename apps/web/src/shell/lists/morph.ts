import { isDesktop, reducedMotion } from "../motion";
import { springCurve } from "../spring";

/* The permission menu forms out of the composer (reference ah_morph). A drop rises from the
   composer's top edge and spreads into a panel joined to it by two fillets. One under-damped
   spring (ζ 0.66, ω 17.5: about 6% over, settled in 330 ms) drives the outline, the rows fade up
   from 80% one after another, and it folds back into the composer in 190 ms. Each frame rewrites
   one clip-path and one SVG line on a flat fill; the blurred glass comes on once it has settled.
   With a finger, a drag down folds it away (28% or a flick) and a drag sideways on the second
   page returns to the first (35% or a flick); the first 8px decide. Reduced motion: it fades. */
export const MORPH = {
  open: 330,
  close: 190,
  rc: 14,
  fillet: 12,
  padY: 12,
  seed: 96,
  zeta: 0.66,
  omega: 17.5,
};
const spring = springCurve(MORPH);
const lerp = (a: number, b: number, t: number) => a + (b - a) * t;
const clamp = (x: number) => Math.max(0, Math.min(1, x));

export type MorphGeom = {
  left: number;
  width: number;
  Yc: number;
  top: number;
  L: number;
  W: number;
  H: number;
};

/** The panel over a composer card: full width less the card's corners on a phone, at most 440 on the chip's side on a desktop. */
export function morphGeom(
  card: { left: number; top: number; width: number },
  chip: { left: number; right: number },
  head: number,
  desktop: boolean,
  content: number,
): MorphGeom {
  const inset = MORPH.rc + MORPH.fillet;
  const full = card.width - 2 * inset;
  const W = desktop ? Math.min(full, 440) : full;
  const end = (chip.left + chip.right) / 2 > card.left + card.width / 2;
  const L = desktop && W < full && end ? card.left + card.width - inset - W : card.left + inset;
  const H = Math.max(120, Math.min(content, card.top - head - 8));
  return { left: card.left, width: card.width, Yc: card.top, top: card.top - H, L, W, H };
}

/** The outline at progress p (a little past 1 while it overshoots), in the menu box's coordinates: the closed fill and the open line. */
export function morphOutline(g: MorphGeom, p: number, bulge: number) {
  const { padY, fillet, seed } = MORPH;
  const f = (n: number) => n.toFixed(1);
  const k = 0.45;
  const Yc = g.Yc - (g.top - padY);
  const q = clamp(p);
  const over = Math.max(0, p - 1);
  const h = Math.max(0, g.H * (p < 1 ? p : 1 + over * 0.35));
  // the width lags the rise a little: a drop first
  const wq = 1 - (1 - clamp(p * 1.12 - 0.06)) ** 2.2;
  const w = Math.max(2, lerp(Math.min(seed, g.W), g.W, wq) + over * g.W * 0.04);
  const cx = g.L + g.W / 2 - g.left;
  const xl = cx - w / 2;
  const xr = cx + w / 2;
  const yt = Yc - h;
  const rt = Math.min(lerp(w / 2, 24, clamp(q * 1.25)), w / 2, h);
  const rf = Math.min(fillet * clamp(q * 3), w / 4, Math.max(0, h - rt));
  const b = Math.max(-3, Math.min(10, bulge));
  const start = `M${f(xl - rf)} ${f(Yc)}Q${f(xl)} ${f(Yc)} ${f(xl)} ${f(Yc - rf)}`;
  const side = `L${f(xl)} ${f(yt + rt)}C${f(xl)} ${f(yt + rt * k)} ${f(xl + rt * k)} ${f(yt)} ${f(xl + rt)} ${f(yt)}Q${f(cx)} ${f(yt - b)} ${f(xr - rt)} ${f(yt)}C${f(xr - rt * k)} ${f(yt)} ${f(xr)} ${f(yt + rt * k)} ${f(xr)} ${f(yt + rt)}L${f(xr)} ${f(Yc - rf)}Q${f(xr)} ${f(Yc)} ${f(xr + rf)} ${f(Yc)}`;
  return {
    fill: `${start}${side}L${f(xr + rf)} ${f(Yc + 2)}L${f(xl - rf)} ${f(Yc + 2)}Z`,
    line: `${start}${side}`,
  };
}

type Drag = {
  id: number;
  x0: number;
  y0: number;
  mode: "back" | "fold" | null;
  pages: HTMLElement | null;
  page: HTMLElement;
  w: number;
  sign: number;
  ty: number;
  samples: { t: number; x: number; y: number }[];
};

/** Runs the morph on a menu element (.mp-glass, svg.mp-line, .mp-in) anchored in a .composer-card. */
export function morphOpen(
  el: HTMLElement,
  anchor: HTMLElement,
  scrim: HTMLElement,
  on: { fold: () => void; back: () => void },
) {
  const card = anchor.closest<HTMLElement>(".composer-card") as HTMLElement;
  const glass = el.querySelector<HTMLElement>(".mp-glass") as HTMLElement;
  const svg = el.querySelector<SVGSVGElement>(".mp-line") as SVGSVGElement;
  const path = svg.querySelector("path") as SVGPathElement;
  const inn = el.querySelector<HTMLElement>(".mp-in") as HTMLElement;
  const listen = new AbortController();
  const signal = listen.signal;
  let g: MorphGeom | null = null;
  let p = 0;
  let raf = 0;
  let timer: ReturnType<typeof setTimeout> | undefined;
  let dirty = false;
  let content = 9999;
  let drag: Drag | null = null;
  let quiet = 0;

  const geom = () =>
    morphGeom(
      card.getBoundingClientRect(),
      anchor.getBoundingClientRect(),
      document.querySelector(".chat-head")?.getBoundingClientRect().bottom ?? 56,
      isDesktop(),
      content,
    );
  const place = () => {
    g = geom();
    const top = g.top - MORPH.padY;
    const height = g.Yc + 2 - top;
    Object.assign(el.style, {
      left: `${g.left}px`,
      top: `${top}px`,
      width: `${g.width}px`,
      height: `${height}px`,
    });
    svg.setAttribute("viewBox", `0 0 ${g.width} ${height}`);
    Object.assign(inn.style, {
      left: `${g.L - g.left}px`,
      top: `${MORPH.padY}px`,
      width: `${g.W}px`,
      height: `${g.H}px`,
    });
  };
  const draw = (at: number, bulge = 0) => {
    if (!g) return;
    const outline = morphOutline(g, at, bulge);
    glass.style.clipPath = `path("${outline.fill}")`;
    path.setAttribute("d", outline.line);
  };
  const settle = () => {
    place();
    p = 1;
    draw(1);
    el.classList.add("settled", "in");
  };
  const run = (dir: 1 | -1, done: () => void) => {
    cancelAnimationFrame(raf);
    const from = p;
    let t0: number | null = null;
    let last = from;
    const step = (now: number) => {
      t0 ??= now;
      const ms = now - t0;
      if (dirty) {
        dirty = false;
        place();
      }
      let finished: boolean;
      if (dir > 0) {
        p = spring(ms / 1000);
        finished = ms >= MORPH.open + 40;
      } else {
        const u = Math.min(1, ms / (MORPH.close * Math.max(0.45, from)));
        p = from * (1 - u * u * (3 - 2 * u) * 0.35 - u * u * 0.65);
        finished = u >= 1;
      }
      // a fast-rising top bows a little
      const speed = (p - last) * (g?.H ?? 0);
      last = p;
      draw(Math.max(0, p), dir > 0 ? speed * 0.55 : 0);
      if (dir > 0 && p >= 0.8) el.classList.add("in");
      if (finished) {
        raf = 0;
        done();
        return;
      }
      raf = requestAnimationFrame(step);
    };
    raf = requestAnimationFrame(step);
  };
  // Where the browser scrolls a page natively, and where a drag is the menu's own.
  const touch = (page: HTMLElement) => {
    const top = page.scrollTop <= 0;
    page.style.touchAction = page.classList.contains("p2")
      ? top
        ? "pan-down"
        : "pan-y"
      : top
        ? "pan-x pan-down"
        : "pan-x pan-y";
  };
  const pagesOf = () => {
    const pages = inn.querySelector<HTMLElement>(".mp-pages");
    return {
      pages,
      p1: pages?.querySelector<HTMLElement>(".p1") ?? null,
      p2: pages?.querySelector<HTMLElement>(".p2") ?? null,
      second: pages?.dataset.page === "2",
    };
  };
  const unfold = (ty: number) => {
    cancelAnimationFrame(raf);
    const from = p;
    let t0: number | null = null;
    inn.style.transition = "opacity .18s";
    inn.style.opacity = "";
    const step = (now: number) => {
      t0 ??= now;
      const u = Math.min(1, (now - t0) / 220);
      const e = 1 - (1 - u) ** 3;
      p = from + (1 - from) * e;
      draw(p);
      inn.style.transform = `translateY(${ty * (1 - e)}px)`;
      if (u < 1) {
        raf = requestAnimationFrame(step);
        return;
      }
      raf = 0;
      inn.style.transition = "";
      inn.style.transform = "";
      settle();
    };
    raf = requestAnimationFrame(step);
  };

  inn.addEventListener(
    "pointerdown",
    (event) => {
      if (!el.classList.contains("settled") || event.pointerType === "mouse") return;
      const { pages, p1, p2, second } = pagesOf();
      drag = {
        id: event.pointerId,
        x0: event.clientX,
        y0: event.clientY,
        mode: null,
        pages,
        page: (second ? p2 : p1) ?? inn,
        w: inn.offsetWidth,
        sign: getComputedStyle(inn).direction === "rtl" ? -1 : 1,
        ty: 0,
        samples: [{ t: event.timeStamp, x: event.clientX, y: event.clientY }],
      };
    },
    { signal, passive: true },
  );
  inn.addEventListener(
    "pointermove",
    (event) => {
      const s = drag;
      if (!s || event.pointerId !== s.id) return;
      const { p1, p2, second } = pagesOf();
      const dx = event.clientX - s.x0;
      const dy = event.clientY - s.y0;
      if (!s.mode) {
        if (Math.abs(dx) < 8 && Math.abs(dy) < 8) return;
        if (Math.abs(dx) > Math.abs(dy)) {
          if (!second || !p1 || !p2 || Math.sign(dx) !== s.sign) {
            drag = null;
            return;
          }
          s.mode = "back";
          s.x0 = event.clientX;
          s.pages?.classList.add("swiping");
          p1.style.transition = "none";
          p2.style.transition = "none";
        } else {
          if (dy < 0 || s.page.scrollTop > 0) {
            drag = null;
            return;
          }
          s.mode = "fold";
          s.y0 = event.clientY;
          el.classList.remove("settled");
          inn.style.transition = "none";
        }
        try {
          inn.setPointerCapture(event.pointerId);
        } catch {
          // A synthetic or already released pointer cannot be captured; the drag still follows it here.
        }
      }
      s.samples.push({ t: event.timeStamp, x: event.clientX, y: event.clientY });
      while (s.samples.length > 2 && event.timeStamp - s.samples[0].t > 100) s.samples.shift();
      if (s.mode === "back" && p1 && p2) {
        const k = clamp(((event.clientX - s.x0) * s.sign) / s.w);
        p2.style.transform = `translateX(${s.sign * k * 100}%)`;
        p1.style.transform = `translateX(${-s.sign * (1 - k) * 30}%)`;
        p1.style.opacity = String(0.35 + 0.65 * k);
      } else if (s.mode === "fold" && g) {
        s.ty = Math.max(0, event.clientY - s.y0);
        const k = Math.min(1, s.ty / g.H);
        p = 1 - k;
        draw(p);
        inn.style.transform = `translateY(${s.ty}px)`;
        inn.style.opacity = String(Math.max(0, 1 - k * 1.6));
      }
    },
    { signal },
  );
  const release = (event: PointerEvent) => {
    const s = drag;
    if (!s || event.pointerId !== s.id) return;
    drag = null;
    if (!s.mode) return;
    quiet = event.timeStamp + 350;
    const a = s.samples[0];
    const b = s.samples[s.samples.length - 1];
    const dt = b.t - a.t;
    const cancel = event.type === "pointercancel";
    if (s.mode === "back") {
      const { p1, p2 } = pagesOf();
      for (const page of [p1, p2]) {
        if (!page) continue;
        page.style.transition = "";
        page.style.transform = "";
        page.style.opacity = "";
      }
      s.pages?.classList.remove("swiping");
      const v = dt > 0 ? ((b.x - a.x) / dt) * s.sign : 0;
      const k = ((b.x - s.x0) * s.sign) / s.w;
      if (!cancel && (k > 0.35 || v > 0.45)) on.back();
      return;
    }
    const v = dt > 0 ? (b.y - a.y) / dt : 0;
    const k = s.ty / (g?.H ?? 1);
    if (!cancel && (k > 0.28 || (v > 0.4 && k > 0.04))) {
      // it folds away from where the finger left it
      inn.style.transition = "opacity .12s";
      inn.style.opacity = "0";
      on.fold();
      return;
    }
    unfold(s.ty);
  };
  inn.addEventListener("pointerup", release, { signal });
  inn.addEventListener("pointercancel", release, { signal });
  // The press that ends a drag does not also choose the row under it.
  el.addEventListener(
    "click",
    (event) => {
      if (event.timeStamp > quiet) return;
      event.preventDefault();
      event.stopPropagation();
    },
    { signal, capture: true },
  );
  el.addEventListener(
    "scroll",
    (event) => {
      const target = event.target as HTMLElement;
      if (target.classList?.contains("mp-page")) touch(target);
    },
    { signal, capture: true },
  );
  // The composer moves (keyboard, rotation): a settled panel follows; a moving one re-measures.
  const follow = () => {
    if (el.classList.contains("settled")) settle();
    else dirty = true;
  };
  window.addEventListener("resize", follow, { signal });
  window.visualViewport?.addEventListener("resize", follow, { signal });

  const lit = requestAnimationFrame(() => scrim.classList.add("on"));
  card.classList.add("mp-open");
  inn.style.width = `${geom().W}px`;
  content = Math.ceil(inn.scrollHeight) + 2;
  const rows = inn.querySelector(".p1")?.children ?? inn.children;
  for (const [i, row] of [...rows].entries())
    (row as HTMLElement).style.setProperty("--i", String(i));
  for (const page of inn.querySelectorAll<HTMLElement>(".mp-page")) touch(page);
  place();
  if (reducedMotion()) {
    settle();
    el.classList.add("fade");
  } else {
    draw(0);
    run(1, settle);
  }

  return {
    /** Folds back into the composer (or fades), then calls done. */
    close(done: () => void) {
      listen.abort();
      cancelAnimationFrame(lit);
      card.classList.remove("mp-open");
      scrim.classList.remove("on");
      if (!card.isConnected) return done();
      if (reducedMotion()) {
        el.classList.add("leaving");
        timer = setTimeout(done, 220);
        return;
      }
      // flat fill again: cheap to reshape
      el.classList.remove("in", "settled");
      raf = requestAnimationFrame(() => {
        timer = setTimeout(() => run(-1, done), 40);
      });
    },
    destroy() {
      listen.abort();
      cancelAnimationFrame(lit);
      cancelAnimationFrame(raf);
      clearTimeout(timer);
      card.classList.remove("mp-open");
    },
  };
}
export type Morph = ReturnType<typeof morphOpen>;
