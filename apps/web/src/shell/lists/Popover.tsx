import { Icon, type IconName } from "@lonora/ui-web";
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
import { type Morph, morphOpen } from "./morph";

/* The reference's popover menu (openPop): glass, fixed beside its anchor (below unless it
   does not fit), the first item focused; a press outside, a scroll, a resize or Escape
   closes it, and the press that closes it does nothing else. One at a time. It takes one
   history layer: Back and Escape return from a second page (usePopoverPage), else close.
   A `morph` menu anchored in the composer forms out of it instead (morph.ts) and folds back. */
type Pop = {
  anchor: HTMLElement;
  body: ReactNode;
  label: string;
  serial: number;
  cls?: string;
  above?: boolean;
  match?: boolean;
  morph?: boolean;
  onClose?: () => void;
};
type Api = {
  open: (
    anchor: HTMLElement,
    body: ReactNode,
    label: string,
    extra?: {
      cls?: string;
      above?: boolean;
      match?: boolean;
      morph?: boolean;
      onClose?: () => void;
    },
  ) => void;
  close: () => void;
  back: () => boolean;
  page: { current: (() => void) | null };
  live: boolean;
};
const Context = createContext<Api | null>(null);

export function PopoverProvider({ children }: { children: ReactNode }) {
  const [pop, setPop] = useState<Pop | null>(null);
  // A closed morph menu stays until it has folded back into the composer.
  const [leaving, setLeaving] = useState<Pop | null>(null);
  const element = useRef<HTMLDivElement>(null);
  const scrim = useRef<HTMLDivElement>(null);
  const morph = useRef<Morph | null>(null);
  const serial = useRef(0);
  const shown = useRef<Pop | null>(null);
  const page = useRef<(() => void) | null>(null);
  const close = useCallback(() => {
    const current = shown.current;
    if (current?.morph) {
      // The folding menu is inert: focus goes back to its button instead of being lost.
      if (element.current?.contains(document.activeElement))
        current.anchor.focus({ preventScroll: true });
      setLeaving(current);
    }
    setPop(null);
  }, []);
  const open = useCallback<Api["open"]>(
    (anchor, body, label, extra) => {
      // A menu button toggles its own menu.
      if (shown.current?.anchor === anchor && anchor.matches("[aria-haspopup]")) return close();
      serial.current += 1;
      setLeaving(null);
      // Only a composer can form a menu; anywhere else it is a plain popover.
      const forms = extra?.morph === true && anchor.closest(".composer-card") !== null;
      setPop({ anchor, body, label, serial: serial.current, ...extra, morph: forms });
    },
    [close],
  );
  const back = useCallback(() => {
    const current = shown.current;
    if (!current) return false;
    if (page.current) page.current();
    else {
      close();
      current.anchor.focus({ preventScroll: true });
    }
    return true;
  }, [close]);
  useOverlayHistory(pop !== null, close);
  const view = pop ?? leaving;
  useLayoutEffect(() => {
    const el = element.current;
    const shade = scrim.current;
    if (!view?.morph || !el || !shade) return;
    const shaping = morphOpen(el, view.anchor, shade, { fold: close, back });
    morph.current = shaping;
    return () => {
      morph.current = null;
      shaping.destroy();
    };
  }, [view, close, back]);
  useEffect(() => {
    if (!leaving) return;
    const gone = () => setLeaving((current) => (current === leaving ? null : current));
    if (morph.current) morph.current.close(gone);
    else gone();
  }, [leaving]);
  useLayoutEffect(() => {
    shown.current = pop;
    const el = element.current;
    if (!pop || !el) return;
    // A morph menu is placed by the morph.
    if (!pop.morph) {
      if (pop.match)
        el.style.minWidth = `${Math.round(pop.anchor.getBoundingClientRect().width)}px`;
      const r = pop.anchor.getBoundingClientRect();
      const w = el.offsetWidth;
      const h = el.offsetHeight;
      const gap = 10;
      const below = r.bottom + 6;
      const above = r.top - 6 - h;
      let top = pop.above
        ? above >= gap
          ? above
          : below
        : below + h <= innerHeight - gap
          ? below
          : above;
      top = Math.max(gap, Math.min(top, innerHeight - h - gap));
      let left = (r.left + r.right) / 2 < innerWidth / 2 ? r.left : r.right - w;
      left = Math.max(gap, Math.min(left, innerWidth - w - gap));
      el.style.top = `${top}px`;
      el.style.left = `${left}px`;
    }
    pop.anchor.setAttribute("aria-expanded", "true");
    const frame = requestAnimationFrame(() => {
      el.classList.add("show");
      el.querySelector<HTMLButtonElement>("button:not(:disabled)")?.focus({ preventScroll: true });
    });
    const anchor = pop.anchor;
    const onClose = pop.onClose;
    return () => {
      onClose?.();
      cancelAnimationFrame(frame);
      if (anchor.getAttribute("aria-expanded") === "true")
        anchor.setAttribute("aria-expanded", "false");
    };
  }, [pop]);
  useEffect(() => {
    if (!pop) return;
    const outside = (event: Event) => {
      const target = event.target as Node | null;
      if (element.current?.contains(target) || pop.anchor.contains(target)) return;
      close();
      // The click that follows this press only dismisses: it must not reach the row beneath.
      const swallow = (click: Event) => {
        click.preventDefault();
        click.stopPropagation();
      };
      const release = () => {
        document.removeEventListener("click", swallow, true);
        document.removeEventListener("pointerup", settle, true);
        document.removeEventListener("pointercancel", release, true);
      };
      const settle = () => setTimeout(release);
      document.addEventListener("click", swallow, { capture: true, once: true });
      document.addEventListener("pointerup", settle, { capture: true, once: true });
      document.addEventListener("pointercancel", release, { capture: true, once: true });
    };
    const scrolled = (event: Event) => {
      if (!element.current?.contains(event.target as Node | null)) close();
    };
    const resized = () => {
      if (!element.current?.contains(document.activeElement)) close();
    };
    const onEscape = (event: KeyboardEvent) => {
      if (event.key !== "Escape") return;
      event.preventDefault();
      event.stopPropagation();
      back();
    };
    document.addEventListener("pointerdown", outside, true);
    document.addEventListener("scroll", scrolled, true);
    window.addEventListener("resize", resized);
    window.addEventListener("keydown", onEscape, true);
    return () => {
      document.removeEventListener("pointerdown", outside, true);
      document.removeEventListener("scroll", scrolled, true);
      window.removeEventListener("resize", resized);
      window.removeEventListener("keydown", onEscape, true);
    };
  }, [pop, close, back]);
  const live = pop !== null;
  const api = useMemo(() => ({ open, close, back, page, live }), [open, close, back, live]);
  return (
    <Context.Provider value={api}>
      {children}
      {view?.morph && <div key={`s${view.serial}`} ref={scrim} className="mp-scrim" />}
      {view && (
        <div
          key={view.serial}
          ref={element}
          className={`pop ${view.cls ?? "menu-pop"}${view.morph ? " morph" : ""}`}
          role="menu"
          aria-label={view.label}
          aria-hidden={view === pop ? undefined : true}
          inert={view === pop ? undefined : true}
        >
          {view.morph ? (
            <>
              <div className="mp-glass" />
              <svg className="mp-line" aria-hidden="true" preserveAspectRatio="none">
                <path />
              </svg>
              <div className="mp-in">{view.body}</div>
            </>
          ) : (
            view.body
          )}
        </div>
      )}
    </Context.Provider>
  );
}

function usePopoverContext() {
  const value = useContext(Context);
  if (!value) throw new Error("popover_context_missing");
  return value;
}

export function usePopover(): Omit<Api, "page" | "live"> {
  return usePopoverContext();
}

/** A second page inside the open popover: Back and Escape return from it to the first page. */
export function usePopoverPage(open: boolean, onBack: () => void) {
  const { page, live } = usePopoverContext();
  const latest = useRef(onBack);
  latest.current = onBack;
  // A menu folding away after it closed holds no history layer.
  useOverlayHistory(open && live, onBack);
  useEffect(() => {
    if (!open || !live) return;
    page.current = () => latest.current();
    return () => {
      page.current = null;
    };
  }, [open, live, page]);
}

export function PopItem({
  icon,
  label,
  danger = false,
  onSelect,
}: {
  icon: IconName;
  label: ReactNode;
  danger?: boolean;
  onSelect: () => void;
}) {
  const { close } = usePopover();
  return (
    <button
      type="button"
      className={`pop-item${danger ? " danger" : ""}`}
      role="menuitem"
      onClick={() => {
        close();
        onSelect();
      }}
    >
      <Icon name={icon} />
      <span>{label}</span>
    </button>
  );
}
export const PopSep = () => <hr className="pop-sep" />;
