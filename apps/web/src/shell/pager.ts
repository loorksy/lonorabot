import { type RefObject, useCallback, useEffect, useRef } from "react";
import { flushSync } from "react-dom";
import { type EdgeOptions, placeScroll, syncEdge } from "./chrome";
import { foldNav, type LensRect, lensRect, placeLens, setLens } from "./lens";
import { isDesktop, reducedMotion } from "./motion";
import { ROOTS, type Root, rootPath } from "./routes";
import { suppressClicks } from "./sheets/SheetHost";
import { haptic, rubber, type Spring, type SpringHandle, springTo } from "./spring";

/* Main-tab pager (WhatsApp structure, Lonora motion). The page follows the finger 1:1 with the
   neighbouring tab rendered beside it as a real page (the ghost). Release settles on a spring from
   the finger's own velocity: a flick carries through, a slow drag eases in. While travelling, pages
   take on depth (scale, rounded corners, shade) and the lens slides with the progress, stretching
   like liquid mid-way. A settling page can be caught again. Tab taps and lens drags use the same
   motion. prefers-reduced-motion: tabs switch instantly. */
const PAGER = {
  scale: 0.035,
  radius: 26,
  shade: 0.34,
  slop: 10,
  commit: 0.5,
  fling: 0.35,
  project: 160,
  swipe: { k: 380, z: 0.88 },
  tap: { k: 320, z: 0.88 },
  back: { k: 460, z: 0.9 },
} satisfies Record<string, number | Spring>;

type Unit = { top: HTMLElement | null; main: HTMLElement; shade: HTMLElement };
type State = {
  id: number | null;
  dragging: boolean;
  on: boolean;
  o: number;
  vel: number;
  side: number;
  base: number;
  x0: number;
  y0: number;
  samples: { t: number; x: number }[];
  W: number;
  H: number;
  i: number;
  rtl: boolean;
  cur: Unit | null;
  nav: HTMLElement | null;
  btns: HTMLElement[];
  fromBtn: HTMLElement | null;
  toBtn: HTMLElement | null;
  fromFixed: LensRect | null;
  route: Root | null;
  ghost: Unit | null;
  anim: SpringHandle | null;
  done: (() => void) | null;
  will: boolean;
};

export type PagerRefs = {
  app: RefObject<HTMLElement | null>;
  main: RefObject<HTMLElement | null>;
  top: RefObject<HTMLElement | null>;
  nav: RefObject<HTMLElement | null>;
  ghostTop: RefObject<HTMLElement | null>;
  ghostMain: RefObject<HTMLElement | null>;
};

type Live = {
  root: Root | null;
  edgeOptions: (root: Root) => EdgeOptions;
  setGhost: (root: Root | null) => void;
  commit: (root: Root) => void;
  blocked: () => boolean;
};

function createPager(refs: PagerRefs, live: RefObject<Live>, busy: RefObject<boolean>) {
  let pager: State | null = null;
  const shadeEl = () => {
    const d = document.createElement("div");
    d.className = "pager-shade";
    refs.app.current?.appendChild(d);
    return d;
  };
  const paintUnit = (u: Unit, o: number, W: number, H: number) => {
    const d = Math.min(1, Math.abs(o) / W);
    const k = reducedMotion() ? 0 : 1;
    const sc = 1 - PAGER.scale * d * k;
    const rad = `${(PAGER.radius * d * k).toFixed(1)}px`;
    const tf =
      Math.abs(o) < 0.01 ? "" : `translate3d(${o.toFixed(2)}px,0,0) scale(${sc.toFixed(4)})`;
    u.main.style.transform = tf;
    u.main.style.borderRadius = rad;
    if (u.top) {
      u.top.style.transform = tf;
      u.top.style.transformOrigin = `50% ${H / 2}px`;
      u.top.style.setProperty("--pr", rad);
    }
    u.shade.style.transform = tf;
    u.shade.style.borderRadius = rad;
    u.shade.style.opacity = (PAGER.shade * d * d * k).toFixed(3);
  };
  const paintTabs = (s: State, o: number, vel: number) => {
    const lens = s.nav?.querySelector<HTMLElement>(".nav-lens");
    if (!lens) return;
    const fr = s.fromFixed || lensRect(s.fromBtn);
    const tr = lensRect(s.toBtn);
    if (!fr) return;
    const p = tr ? Math.min(1, Math.abs(o) / s.W) : 0;
    let x = fr.x;
    let w = fr.w;
    let stretch: number;
    let shift = 0;
    if (tr) {
      x += (tr.x - fr.x) * p;
      w += (tr.w - fr.w) * p;
      stretch = Math.sin(Math.PI * p) * 0.22 * w;
    } else {
      stretch = Math.min(12, Math.abs(o) * 0.05);
      shift = -Math.sign(o) * Math.min(7, Math.abs(o) * 0.03);
    }
    stretch += Math.min(14, Math.abs(vel) * 0.006);
    lens.style.transition = "none";
    lens.style.width = `${(w + stretch).toFixed(1)}px`;
    lens.style.transform = `translateX(${(x - stretch / 2 + shift).toFixed(1)}px)`;
    if (s.toBtn) {
      s.fromBtn?.style.setProperty("--on", (1 - p).toFixed(3));
      s.toBtn.style.setProperty("--on", p.toFixed(3));
      s.toBtn.classList.toggle("peek", p > 0.5);
      s.fromBtn?.classList.toggle("unpeek", p > 0.5);
    }
  };
  const paint = (o: number, vel = 0) => {
    const s = pager;
    if (!s?.cur) return;
    s.o = o;
    paintUnit(s.cur, o, s.W, s.H);
    if (s.ghost) paintUnit(s.ghost, o - s.side * s.W, s.W, s.H);
    paintTabs(s, o, vel);
    const will = !!s.ghost && Math.abs(o) > s.W * PAGER.commit;
    if (will !== s.will) {
      s.will = will;
      if (s.dragging) haptic(6);
    }
  };
  const dropGhost = (s: State) => {
    if (!s.ghost) return;
    s.ghost.shade.remove();
    s.ghost = null;
    live.current.setGhost(null);
    for (const el of [refs.ghostTop.current, refs.ghostMain.current])
      if (el) {
        el.style.transform = "";
        el.style.borderRadius = "";
      }
  };
  const buildGhost = (route: Root): Unit | null => {
    flushSync(() => live.current.setGhost(route));
    const top = refs.ghostTop.current;
    const main = refs.ghostMain.current;
    if (!main) return null;
    if (top) {
      top.setAttribute("aria-hidden", "true");
      top.inert = true;
      main.style.setProperty("--top-h", `${top.offsetHeight}px`);
    }
    main.inert = true;
    placeScroll(main, rootPath(route));
    syncEdge(main, top, live.current.edgeOptions(route));
    return { top, main, shade: shadeEl() };
  };
  const begin = (s: State, pointerId: number | null) => {
    const app = refs.app.current;
    const m = refs.main.current;
    if (!app || !m) return false;
    s.W = app.clientWidth;
    s.H = app.clientHeight;
    s.i = ROOTS.indexOf(live.current.root as Root);
    s.rtl = getComputedStyle(app).direction === "rtl";
    s.cur = { top: refs.top.current, main: m, shade: shadeEl() };
    s.nav = refs.nav.current;
    s.btns = s.nav ? [...s.nav.querySelectorAll<HTMLElement>("button")] : [];
    s.fromBtn = s.btns[s.i] ?? null;
    foldNav(s.nav, false);
    s.nav?.classList.add("paging");
    busy.current = true;
    app.classList.add("paging");
    m.style.overflowY = "hidden";
    if (pointerId != null)
      try {
        m.setPointerCapture(pointerId);
      } catch {
        /* synthetic pointers cannot be captured */
      }
    return true;
  };
  const side = (s: State, next: number) => {
    if (next === s.side) return;
    dropGhost(s);
    s.side = next;
    const route = next ? ROOTS[s.i + (s.rtl ? next : -next)] : undefined;
    for (const b of s.btns) {
      b.classList.remove("peek", "unpeek");
      b.style.removeProperty("--on");
    }
    s.route = route ?? null;
    s.toBtn = route ? (s.btns[ROOTS.indexOf(route)] ?? null) : null;
    if (route) s.ghost = buildGhost(route);
  };
  const track = (s: State, raw: number) => {
    if (raw) side(s, raw > 0 ? 1 : -1);
    const o = s.ghost ? Math.max(-s.W, Math.min(s.W, raw)) : rubber(raw, s.W);
    paint(o, s.vel);
  };
  const clearUnit = (u: Unit | null) => {
    if (!u) return;
    for (const el of [u.top, u.main]) {
      if (!el) continue;
      el.style.transform = "";
      el.style.borderRadius = "";
      el.style.transformOrigin = "";
      el.style.removeProperty("--pr");
    }
    u.shade.remove();
    u.main.style.overflowY = "";
  };
  const settleTabs = (s: State) => {
    s.nav?.classList.remove("paging");
    for (const b of s.btns) {
      b.classList.remove("peek", "unpeek");
      b.style.removeProperty("--on");
    }
    busy.current = false;
    refs.app.current?.classList.remove("paging");
  };
  const reset = () => {
    const s = pager;
    if (!s) return;
    pager = null;
    dropGhost(s);
    clearUnit(s.cur);
    settleTabs(s);
    placeLens(s.nav, false);
  };
  /* The incoming page is already in place, so the real route change must not animate anything. */
  const finish = () => {
    const s = pager;
    if (!s?.route) return;
    pager = null;
    const route = s.route;
    flushSync(() => {
      live.current.commit(route);
      live.current.setGhost(null);
    });
    s.ghost?.shade.remove();
    clearUnit(s.cur);
    settleTabs(s);
    setLens(s.nav, lensRect(s.toBtn), false);
  };
  const settle = (s: State, commit: boolean, v0: number, spec: Spring) => {
    const to = commit ? s.side * s.W : 0;
    s.done = commit ? finish : reset;
    s.anim = springTo({
      from: s.o,
      to,
      v: v0,
      ...spec,
      onFrame: (x, vel) => paint(x, vel),
      onDone: () => {
        s.anim = null;
        s.done?.();
      },
    });
  };
  /** Jump an in-flight transition to its end (another tab tapped mid-way). */
  const complete = () => {
    const s = pager;
    if (!s) return;
    s.anim?.stop();
    s.anim = null;
    if (s.done) {
      paint(s.done === finish ? s.side * s.W : 0);
      s.done();
    } else reset();
  };
  const fresh = (): State => ({
    id: null,
    dragging: false,
    on: false,
    o: 0,
    vel: 0,
    side: 0,
    base: 0,
    x0: 0,
    y0: 0,
    samples: [],
    W: 0,
    H: 0,
    i: 0,
    rtl: false,
    cur: null,
    nav: null,
    btns: [],
    fromBtn: null,
    toBtn: null,
    fromFixed: null,
    route: null,
    ghost: null,
    anim: null,
    done: null,
    will: false,
  });
  /** Taps on the tab bar and lens drags slide the pages the same way. */
  const pagerTo = (route: Root, lensFrom: LensRect | null = null) => {
    if (pager) complete();
    const current = live.current.root;
    const i = current ? ROOTS.indexOf(current) : -1;
    const ti = ROOTS.indexOf(route);
    if (isDesktop() || i < 0 || ti < 0 || i === ti || reducedMotion() || live.current.blocked()) {
      live.current.commit(route);
      return;
    }
    const s = { ...fresh(), on: true, fromFixed: lensFrom, route };
    pager = s;
    if (!begin(s, null)) {
      pager = null;
      live.current.commit(route);
      return;
    }
    s.side = (ti > i ? 1 : -1) * (s.rtl ? 1 : -1);
    s.toBtn = s.btns[ti] ?? null;
    s.ghost = buildGhost(route);
    paint(0);
    settle(s, true, 0, PAGER.tap);
  };
  const down = (event: PointerEvent) => {
    if (event.pointerType === "mouse" || isDesktop()) return;
    const target = event.target instanceof Element ? event.target : null;
    const app = refs.app.current;
    if (!app || !target || !app.contains(target)) return;
    const s = pager;
    // Catch a page that is still settling: the finger takes over from wherever it is.
    if (s?.anim && !s.dragging && !target.closest("nav.tabbar,.topbar button,.topbar input")) {
      s.anim.stop();
      s.anim = null;
      s.done = null;
      Object.assign(s, {
        id: event.pointerId,
        dragging: true,
        on: true,
        base: s.o,
        x0: event.clientX,
        y0: event.clientY,
        samples: [{ t: event.timeStamp, x: event.clientX }],
        vel: 0,
      });
      try {
        (target.closest("main") ?? s.cur?.main)?.setPointerCapture(event.pointerId);
      } catch {
        /* synthetic pointers cannot be captured */
      }
      return;
    }
    if (s || !live.current.root || live.current.blocked()) return;
    if (!target.closest("#view-scroll")) return;
    if (
      target.closest(
        ".list-filters,.tabs,input,textarea,select,label,.switch,.select-trigger,.chart",
      )
    )
      return;
    pager = {
      ...fresh(),
      id: event.pointerId,
      x0: event.clientX,
      y0: event.clientY,
      dragging: true,
      samples: [{ t: event.timeStamp, x: event.clientX }],
    };
  };
  const move = (event: PointerEvent) => {
    const s = pager;
    if (!s || !s.dragging || event.pointerId !== s.id) return;
    if (!s.on) {
      const dx = event.clientX - s.x0;
      const dy = event.clientY - s.y0;
      if (Math.abs(dy) > PAGER.slop && Math.abs(dy) > Math.abs(dx)) {
        pager = null;
        return;
      }
      if (Math.abs(dx) < PAGER.slop || Math.abs(dx) < Math.abs(dy) * 1.3) return;
      s.on = true;
      s.x0 = event.clientX;
      if (!begin(s, event.pointerId)) {
        pager = null;
        return;
      }
    }
    const prev = s.samples[s.samples.length - 1];
    s.samples.push({ t: event.timeStamp, x: event.clientX });
    while (s.samples.length > 2 && event.timeStamp - s.samples[0].t > 100) s.samples.shift();
    if (prev && event.timeStamp > prev.t)
      s.vel = s.vel * 0.6 + ((event.clientX - prev.x) / (event.timeStamp - prev.t)) * 1000 * 0.4;
    track(s, s.base + event.clientX - s.x0);
  };
  const release = (event: PointerEvent, cancelled: boolean) => {
    const s = pager;
    if (!s || !s.dragging || event.pointerId !== s.id) return;
    s.dragging = false;
    if (!s.on) {
      pager = null;
      return;
    }
    suppressClicks();
    const a = s.samples[0];
    const b = s.samples[s.samples.length - 1];
    const v = a && b && b.t > a.t && event.timeStamp - b.t < 90 ? (b.x - a.x) / (b.t - a.t) : 0;
    let commit = false;
    if (!cancelled && s.ghost && s.o) {
      const same = Math.sign(v) === Math.sign(s.o) || !v;
      const proj = s.o + v * PAGER.project;
      commit = Math.abs(v) > PAGER.fling ? same : Math.abs(proj) > s.W * PAGER.commit && same;
    }
    settle(s, commit, v * 1000, commit ? PAGER.swipe : PAGER.back);
  };
  /** Something navigated underneath while a page travelled: drop the gesture quietly. */
  const routeChanged = () => {
    const s = pager;
    if (!s || !s.anim || s.done === finish) return;
    s.anim.stop();
    reset();
  };
  const dispose = () => pager?.anim?.stop();
  return { pagerTo, down, move, release, routeChanged, dispose };
}

export function usePager({
  refs,
  root,
  edgeOptions,
  setGhost,
  commit,
  blocked,
  busy,
}: Live & {
  refs: PagerRefs;
  /** Shared with the tab bar: while set, the scroll fold leaves the bar alone. */
  busy: RefObject<boolean>;
}) {
  const live = useRef<Live>({ root, edgeOptions, setGhost, commit, blocked });
  live.current = { root, edgeOptions, setGhost, commit, blocked };
  const controller = useRef<ReturnType<typeof createPager> | null>(null);
  if (!controller.current) controller.current = createPager(refs, live, busy);
  useEffect(() => {
    const c = controller.current;
    if (!c) return;
    const up = (event: PointerEvent) => c.release(event, false);
    const cancel = (event: PointerEvent) => c.release(event, true);
    document.addEventListener("pointerdown", c.down, { passive: true });
    document.addEventListener("pointermove", c.move, { passive: true });
    document.addEventListener("pointerup", up);
    document.addEventListener("pointercancel", cancel);
    return () => {
      document.removeEventListener("pointerdown", c.down);
      document.removeEventListener("pointermove", c.move);
      document.removeEventListener("pointerup", up);
      document.removeEventListener("pointercancel", cancel);
      c.dispose();
    };
  }, []);
  useEffect(() => {
    void root;
    controller.current?.routeChanged();
  }, [root]);
  return useCallback(
    (route: Root, lensFrom: LensRect | null = null) => controller.current?.pagerTo(route, lensFrom),
    [],
  );
}
