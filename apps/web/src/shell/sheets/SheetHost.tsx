import { t } from "@lingui/core/macro";
import { Icon } from "@lonora/ui-web";
import {
  createContext,
  type ReactNode,
  useCallback,
  useContext,
  useEffect,
  useLayoutEffect,
  useMemo,
  useRef,
  useState,
} from "react";
import { useOverlayHistory } from "../../hooks/useOverlayHistory";
import { isDesktop, reducedMotion } from "../motion";
import { haptic, type Spring, type SpringHandle, springTo } from "../spring";

/* The sheet system (q_sheet): one <dialog>. Phones: a glass bottom sheet that follows the finger
   from the handle row, the title or content scrolled to its top; release past 30% of its height
   (max 240px) or a downward flick closes it on a spring from the finger's speed, else it springs
   back; the backdrop fades with the travel. Expandable sheets rest at their content's height and
   rise to the top of the screen (drag, flick or ⤢). ≥900px: a centred modal that fades.
   The dialog is shown without the top layer (show(), a sibling backdrop, inert on #app, Escape
   on the dialog) so the Base UI popups of the screens inside it, which portal to body, paint and
   receive the pointer above it; a modal top-layer dialog would cover them. */
export type SheetOptions = {
  /** Re-rendering a sheet with the same id keeps it open and in place. */
  id: string;
  title: ReactNode;
  /** Plain text for aria-label (the title when it is a string). */
  label?: string;
  body: ReactNode;
  /** Claude-style header: handle, ✕ (or ← to `back`) at the start, the title centred. */
  bar?: boolean;
  back?: () => void;
  /** The direction a new in-sheet page slides in from. */
  dir?: "fwd" | "back";
  expand?: boolean;
  full?: boolean;
  onClose?: () => void;
};
type Sheet = SheetOptions & { page: number };
type SheetsApi = {
  open: (options: SheetOptions, extra?: { morph?: boolean }) => void;
  close: (instant?: boolean) => void;
  isOpen: () => boolean;
  current: () => string | null;
};
const Context = createContext<SheetsApi | null>(null);

const SHEET = {
  dismiss: 0.3,
  maxDismiss: 240,
  fling: 0.4,
  open: { k: 340, z: 0.9 },
  back: { k: 520, z: 0.9 },
  out: { k: 300, z: 0.85 },
  grow: { k: 430, z: 0.95 },
} satisfies Record<string, number | Spring>;

type Range = { hn: number; hf: number; range: number };
type Drag = {
  id: number;
  x0: number;
  y0: number;
  base: number;
  on: boolean;
  armed: boolean;
  grow: boolean;
  samples: { t: number; y: number }[];
  wasExpanded?: boolean;
  e0?: number;
  top?: boolean;
};

/** The gesture and spring state of the one dialog; classes it toggles are never set by React. */
class SheetMotion {
  y = 0;
  anim: SpringHandle | null = null;
  drag: Drag | null = null;
  g: Range | null = null;
  e = 0;
  to = false;
  closeTimer: ReturnType<typeof setTimeout> | undefined;
  constructor(
    readonly d: HTMLDialogElement,
    readonly hooks: { dismissed: () => void; expanded: (on: boolean) => void },
  ) {}
  paint(y: number) {
    const H = this.d.offsetHeight || 1;
    this.y = y;
    this.d.style.transform = Math.abs(y) < 0.5 ? "" : `translate3d(0,${y.toFixed(1)}px,0)`;
    // The backdrop is the dialog's sibling: the layer around both carries the variable.
    (this.d.parentElement ?? this.d).style.setProperty(
      "--bd",
      Math.max(0, Math.min(1, 1 - y / H)).toFixed(3),
    );
  }
  sync() {
    const d = this.d;
    const y = d.scrollTop;
    const head = d.querySelector<HTMLElement>(":scope>.sheet-head");
    d.classList.toggle("scrolled", y > 2);
    d.style.touchAction = isDesktop()
      ? ""
      : d.classList.contains("expandable") && !d.classList.contains("expanded")
        ? "pan-x"
        : y <= 0
          ? "pan-x pan-down"
          : "pan-x pan-y";
    if (head) {
      const p = Math.max(0, Math.min(1, y / Math.max(24, head.offsetHeight)));
      head.style.opacity = (1 - p * 1.2).toFixed(3);
      head.style.transform = p
        ? `translateY(${(p * 10).toFixed(1)}px) scale(${(1 - p * 0.05).toFixed(3)})`
        : "";
    }
  }
  spring(to: number, v: number, spec: Spring, done?: () => void) {
    this.anim?.stop();
    this.anim = springTo({
      from: this.y,
      to,
      v,
      ...spec,
      onFrame: (y) => this.paint(y),
      onDone: () => {
        this.anim = null;
        done?.();
      },
    });
  }
  in() {
    clearTimeout(this.closeTimer);
    this.d.classList.remove("closing");
    if (isDesktop() || reducedMotion()) {
      this.paint(0);
      return;
    }
    this.paint(this.d.offsetHeight);
    this.spring(0, 0, SHEET.open);
  }
  out(instant: boolean, v = 0) {
    this.anim?.stop();
    this.anim = null;
    const d = this.d;
    const done = () => {
      d.classList.remove("closing");
      if (d.open) d.close();
      this.growReset();
      this.paint(0);
      (d.parentElement ?? d).style.removeProperty("--bd");
      this.hooks.dismissed();
    };
    if (instant || reducedMotion()) return done();
    if (isDesktop()) {
      d.classList.add("closing");
      this.closeTimer = setTimeout(done, 165);
      return;
    }
    this.spring(d.offsetHeight + 24, v, SHEET.out, done);
  }
  /* Expandable sheets: extent = how far the sheet stands above its resting height (negative = pulled down). */
  range(): Range {
    const d = this.d;
    const ex = d.classList.contains("expanded");
    const rs = d.classList.contains("resizing");
    const h = d.style.height;
    d.classList.remove("expanded", "resizing");
    d.style.height = "";
    const hn = d.offsetHeight;
    const grow = d.querySelector<HTMLElement>(".grow");
    if (grow) d.style.setProperty("--grow-min", `${grow.clientHeight}px`);
    d.classList.add("expanded");
    const hf = d.offsetHeight;
    d.classList.toggle("expanded", ex);
    d.classList.toggle("resizing", rs);
    d.style.height = h;
    return { hn, hf, range: Math.max(0, hf - hn) };
  }
  extent(x: number) {
    const g = this.g;
    if (!g) return;
    this.e = x;
    const over = x - g.range;
    const h = x <= 0 ? g.hn : over <= 0 ? g.hn + x : g.hf + Math.min(28, over * 0.25);
    this.d.style.height = `${h.toFixed(1)}px`;
    this.paint(x < 0 ? -x : 0);
  }
  growStart() {
    const d = this.d;
    const ex = d.classList.contains("expanded");
    this.g = this.range();
    this.to = ex;
    d.classList.remove("expanded");
    d.classList.add("resizing");
    const x = ex ? this.g.range : -this.y;
    this.extent(x);
    return x;
  }
  growCatch(s: Drag) {
    s.wasExpanded = this.g ? this.to : this.d.classList.contains("expanded");
    s.e0 = this.g ? this.e : this.growStart();
    s.top = !!this.g && this.g.range > 0 && s.e0 >= this.g.range - 0.5;
  }
  growEnd(expand: boolean) {
    const d = this.d;
    d.classList.remove("resizing");
    d.classList.toggle("expanded", expand);
    d.style.removeProperty("height");
    this.g = null;
    this.e = 0;
    this.to = expand;
    this.paint(0);
    this.sync();
    this.hooks.expanded(expand);
  }
  growReset() {
    if (this.g) {
      this.anim?.stop();
      this.anim = null;
    }
    this.d.classList.remove("resizing", "expanded");
    this.d.style.removeProperty("height");
    this.g = null;
    this.e = 0;
    this.to = false;
  }
  growTo(expand: boolean, v = 0) {
    if (!this.g) this.growStart();
    const g = this.g as Range;
    this.to = expand;
    this.hooks.expanded(expand);
    this.anim?.stop();
    this.anim = null;
    if (reducedMotion()) {
      this.extent(expand ? g.range : 0);
      return this.growEnd(expand);
    }
    this.anim = springTo({
      from: this.e,
      to: expand ? g.range : 0,
      v,
      ...SHEET.grow,
      onFrame: (x) => this.extent(x),
      onDone: () => {
        this.anim = null;
        this.growEnd(expand);
      },
    });
  }
  growRelease(s: Drag, v: number, cancelled: boolean) {
    const g = this.g;
    const x = this.e;
    if (!g) return;
    if (x < 0) {
      const pulled = -x;
      const dismiss =
        !cancelled &&
        ((v > SHEET.fling && pulled > 8) ||
          (pulled > Math.min(g.hn * SHEET.dismiss, SHEET.maxDismiss) && v > -0.2));
      if (dismiss) return this.out(false, Math.max(0, v * 1000));
      return this.growTo(!cancelled && v < -SHEET.fling && g.range > 0, -v * 1000);
    }
    const proj = x - v * 200;
    const expand =
      g.range <= 0
        ? false
        : cancelled
          ? !!s.wasExpanded
          : v < -SHEET.fling
            ? true
            : v > SHEET.fling
              ? false
              : proj > g.range * (s.wasExpanded ? 0.75 : 0.25);
    this.growTo(expand, -v * 1000);
  }
  isExpanded() {
    return this.g ? this.to : this.d.classList.contains("expanded");
  }
  expandToggle() {
    const d = this.d;
    if (!d.open || !d.classList.contains("expandable")) return;
    const on = this.isExpanded();
    if (isDesktop()) {
      d.classList.toggle("expanded", !on);
      this.to = !on;
      this.sync();
      this.hooks.expanded(!on);
      return;
    }
    this.growTo(!on, 0);
  }
  /* Touch: follow the finger 1:1 from the handle row or title, or from content at its top. */
  pointerDown = (event: PointerEvent) => {
    const d = this.d;
    if (!d.open || isDesktop() || event.pointerType === "mouse" || !(event.target instanceof Node))
      return;
    if (!d.contains(event.target)) return;
    const target = event.target instanceof Element ? event.target : null;
    if (event.target === d) {
      const r = d.getBoundingClientRect();
      if (event.clientY < r.top) return;
    }
    if (target?.closest("input,textarea,select,[contenteditable],.switch")) return;
    const inner = target?.closest<HTMLElement>(".list-rows,.legacy-surface");
    if (inner && inner.scrollTop > 0) return;
    const grab = !!target?.closest(".sheet-top,.sheet-head");
    if (!grab && d.scrollTop > 0 && !this.anim) return;
    const caught = !!this.anim;
    this.anim?.stop();
    this.anim = null;
    this.drag = {
      id: event.pointerId,
      x0: event.clientX,
      y0: event.clientY,
      base: this.y,
      on: caught,
      armed: false,
      grow: d.classList.contains("expandable"),
      samples: [{ t: event.timeStamp, y: event.clientY }],
    };
    if (caught) {
      try {
        d.setPointerCapture(event.pointerId);
      } catch {
        /* synthetic pointers cannot be captured */
      }
      if (this.drag.grow) this.growCatch(this.drag);
    }
  };
  pointerMove = (event: PointerEvent) => {
    const s = this.drag;
    if (!s || event.pointerId !== s.id) return;
    if (!s.on) {
      const dx = event.clientX - s.x0;
      const dy = event.clientY - s.y0;
      if (Math.abs(dx) < 6 && Math.abs(dy) < 6) return;
      if (Math.abs(dx) > Math.abs(dy)) {
        this.drag = null;
        return;
      }
      if (dy <= 0 && !(s.grow && !this.d.classList.contains("expanded"))) {
        this.drag = null;
        return;
      }
      s.on = true;
      s.y0 = event.clientY;
      try {
        this.d.setPointerCapture(event.pointerId);
      } catch {
        /* synthetic pointers cannot be captured */
      }
      if (s.grow) this.growCatch(s);
    }
    s.samples.push({ t: event.timeStamp, y: event.clientY });
    while (s.samples.length > 2 && event.timeStamp - s.samples[0].t > 100) s.samples.shift();
    if (s.grow) {
      const g = this.g as Range;
      const x = (s.e0 ?? 0) - (event.clientY - s.y0);
      this.extent(x);
      const armed = -x > Math.min(g.hn * SHEET.dismiss, SHEET.maxDismiss);
      const top = g.range > 0 && x >= g.range - 0.5;
      if (armed !== s.armed) {
        s.armed = armed;
        haptic(5);
      }
      if (top !== s.top) {
        s.top = top;
        if (top) haptic(5);
      }
      return;
    }
    const y = Math.max(0, s.base + event.clientY - s.y0);
    const H = this.d.offsetHeight;
    this.paint(y);
    const armed = y > Math.min(H * SHEET.dismiss, SHEET.maxDismiss);
    if (armed !== s.armed) {
      s.armed = armed;
      haptic(5);
    }
  };
  release(event: PointerEvent, cancelled: boolean) {
    const s = this.drag;
    if (!s || event.pointerId !== s.id) return;
    this.drag = null;
    if (!s.on) return;
    suppressClicks();
    const a = s.samples[0];
    const b = s.samples[s.samples.length - 1];
    const y = this.y;
    const H = this.d.offsetHeight;
    const v = a && b && b.t > a.t && event.timeStamp - b.t < 90 ? (b.y - a.y) / (b.t - a.t) : 0;
    if (s.grow) return this.growRelease(s, v, cancelled);
    const dismiss =
      !cancelled &&
      ((v > SHEET.fling && y > 8) ||
        (y > Math.min(H * SHEET.dismiss, SHEET.maxDismiss) && v > -0.2));
    if (dismiss) this.out(false, Math.max(0, v * 1000));
    else this.spring(0, v * 1000, SHEET.back);
  }
  pointerUp = (event: PointerEvent) => this.release(event, false);
  pointerCancel = (event: PointerEvent) => this.release(event, true);
}

/* The click that ends a drag must not also tap a row or a tab. */
let suppressClickUntil = 0;
export function suppressClicks(ms = 350) {
  suppressClickUntil = Date.now() + ms;
}
document.addEventListener(
  "click",
  (event) => {
    if (Date.now() < suppressClickUntil) {
      event.preventDefault();
      event.stopPropagation();
    }
  },
  true,
);

export function SheetProvider({ children }: { children: ReactNode }) {
  const dialog = useRef<HTMLDialogElement>(null);
  const backdrop = useRef<HTMLDivElement>(null);
  /** The element focused when the sheet opened; focus returns to it when the sheet closes. */
  const opener = useRef<Element | null>(null);
  const motion = useRef<SheetMotion | null>(null);
  const [sheet, setSheet] = useState<Sheet | null>(null);
  const [expanded, setExpanded] = useState(false);
  const page = useRef(0);
  const previous = useRef<string | null>(null);
  const morphFrom = useRef<number | null>(null);
  const sheetRef = useRef<Sheet | null>(null);
  sheetRef.current = sheet;

  useEffect(() => {
    const d = dialog.current;
    if (!d) return;
    const m = new SheetMotion(d, {
      dismissed: () => {
        const closed = sheetRef.current;
        document.getElementById("app")?.removeAttribute("inert");
        const back = opener.current;
        opener.current = null;
        if (back instanceof HTMLElement && back.isConnected && !d.contains(back))
          back.focus({ preventScroll: true });
        setSheet(null);
        setExpanded(false);
        previous.current = null;
        closed?.onClose?.();
      },
      expanded: setExpanded,
    });
    motion.current = m;
    const scrolled = () => m.sync();
    // A tap on the backdrop, or Escape inside an embedded chart (its own document), dismisses.
    const dismiss = () => {
      if (d.open) m.out(false);
    };
    // Not a modal dialog: Escape reaches it from the focus inside instead of a cancel event.
    const onEscape = (event: KeyboardEvent) => {
      if (event.key !== "Escape" || event.defaultPrevented || !d.open) return;
      event.preventDefault();
      m.out(false);
    };
    const shade = backdrop.current;
    d.addEventListener("scroll", scrolled, { passive: true });
    d.addEventListener("keydown", onEscape);
    shade?.addEventListener("click", dismiss);
    window.addEventListener("lonora:chart-escape", dismiss);
    document.addEventListener("pointerdown", m.pointerDown, { passive: true });
    document.addEventListener("pointermove", m.pointerMove, { passive: true });
    document.addEventListener("pointerup", m.pointerUp);
    document.addEventListener("pointercancel", m.pointerCancel);
    return () => {
      d.removeEventListener("scroll", scrolled);
      d.removeEventListener("keydown", onEscape);
      shade?.removeEventListener("click", dismiss);
      window.removeEventListener("lonora:chart-escape", dismiss);
      document.getElementById("app")?.removeAttribute("inert");
      document.removeEventListener("pointerdown", m.pointerDown);
      document.removeEventListener("pointermove", m.pointerMove);
      document.removeEventListener("pointerup", m.pointerUp);
      document.removeEventListener("pointercancel", m.pointerCancel);
      m.anim?.stop();
      clearTimeout(m.closeTimer);
      motion.current = null;
    };
  }, []);

  const close = useCallback((instant = false) => {
    const d = dialog.current;
    const m = motion.current;
    if (!d?.open || !m) return;
    m.out(instant);
  }, []);
  const open = useCallback<SheetsApi["open"]>((options, extra) => {
    const d = dialog.current;
    if (!d || !motion.current) return;
    clearTimeout(motion.current.closeTimer);
    d.classList.remove("closing");
    morphFrom.current = extra?.morph && d.open ? d.offsetHeight : null;
    page.current += 1;
    setSheet({ ...options, page: page.current });
  }, []);
  useLayoutEffect(() => {
    const d = dialog.current;
    const m = motion.current;
    if (!d || !m || !sheet) return;
    const same = d.open && previous.current === sheet.id;
    previous.current = sheet.id;
    const opening = !d.open;
    const moving = !opening && m.y > 1;
    d.classList.toggle("expandable", !!sheet.expand);
    if (!(sheet.expand && same)) m.growReset();
    d.classList.toggle("bar-sheet", !!sheet.bar);
    d.classList.toggle("full-sheet", !!sheet.full);
    if (opening) {
      opener.current = document.activeElement;
      d.scrollTop = 0;
      d.show();
      document.getElementById("app")?.setAttribute("inert", "");
      d.querySelector<HTMLElement>(".sheet-top")?.focus({ preventScroll: true });
    }
    m.sync();
    if (sheet.expand && same) setExpanded(m.isExpanded());
    else if (!sheet.expand) setExpanded(false);
    if (opening) m.in();
    else if (moving) m.spring(0, 0, SHEET.open);
    // swap the sheet's page and let its height follow instead of jumping
    const h0 = morphFrom.current;
    morphFrom.current = null;
    if (h0 === null || opening) return;
    const h1 = d.offsetHeight;
    if (Math.abs(h1 - h0) < 2 || reducedMotion()) return;
    d.style.transition = "none";
    d.style.height = `${h0}px`;
    void d.offsetHeight;
    d.style.transition = "height .32s cubic-bezier(.2,.8,.2,1)";
    d.style.height = `${h1}px`;
    const end = () => {
      clearTimeout(timer);
      d.removeEventListener("transitionend", end);
      d.style.height = "";
      d.style.transition = "";
    };
    const timer = setTimeout(end, 420);
    d.addEventListener("transitionend", end);
  }, [sheet]);
  useOverlayHistory(sheet !== null, () => close());

  const api = useMemo<SheetsApi>(
    () => ({
      open,
      close,
      isOpen: () => !!dialog.current?.open,
      current: () => sheetRef.current?.id ?? null,
    }),
    [open, close],
  );
  const label = sheet
    ? (sheet.label ?? (typeof sheet.title === "string" ? sheet.title : sheet.id))
    : undefined;
  const expandLabel = expanded ? t`Minimize` : t`Full screen`;
  return (
    <Context.Provider value={api}>
      {children}
      <div className="sheet-layer">
        <dialog id="dialog" ref={dialog} aria-label={label}>
          {sheet?.bar ? (
            <div className="sheet-top bar" tabIndex={-1}>
              <div className="handle" aria-hidden="true" />
              <div className="sheet-bar">
                {sheet.back ? (
                  <button type="button" className="icon" aria-label={t`Back`} onClick={sheet.back}>
                    <Icon name="back" />
                  </button>
                ) : (
                  <button
                    type="button"
                    className="icon"
                    aria-label={t`Close`}
                    onClick={() => close()}
                  >
                    <Icon name="close" />
                  </button>
                )}
                <h2>{sheet.title}</h2>
                <span aria-hidden="true" />
              </div>
            </div>
          ) : (
            sheet && (
              <div className="sheet-top" tabIndex={-1}>
                <div className="handle" aria-hidden="true" />
                {sheet.expand && (
                  <button
                    type="button"
                    className="icon sheet-expand"
                    aria-label={expandLabel}
                    title={expandLabel}
                    onClick={() => motion.current?.expandToggle()}
                  >
                    <Icon name={expanded ? "collapse" : "expand"} />
                  </button>
                )}
                <button
                  type="button"
                  className="icon"
                  aria-label={t`Close`}
                  onClick={() => close()}
                >
                  <Icon name="close" />
                </button>
              </div>
            )
          )}
          {sheet?.bar ? (
            <div key={sheet.page} className={`sheet-page${sheet.dir ? ` go-${sheet.dir}` : ""}`}>
              {sheet.body}
            </div>
          ) : (
            sheet && (
              <>
                <div className="sheet-head">
                  <h2>{sheet.title}</h2>
                </div>
                {sheet.body}
              </>
            )
          )}
        </dialog>
        <div className="sheet-backdrop" ref={backdrop} aria-hidden="true" />
      </div>
    </Context.Provider>
  );
}

export function useSheets() {
  const value = useContext(Context);
  if (!value) throw new Error("sheet_context_missing");
  return value;
}
