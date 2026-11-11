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

/* The reference's popover menu (openPop): glass, fixed beside its anchor (below unless it
   does not fit), the first item focused; a press outside, a scroll, a resize or Escape
   closes it. One at a time. */
type Pop = {
  anchor: HTMLElement;
  body: ReactNode;
  label: string;
  serial: number;
  cls?: string;
  above?: boolean;
  onClose?: () => void;
};
type Api = {
  open: (
    anchor: HTMLElement,
    body: ReactNode,
    label: string,
    extra?: { cls?: string; above?: boolean; onClose?: () => void },
  ) => void;
  close: () => void;
};
const Context = createContext<Api | null>(null);

export function PopoverProvider({ children }: { children: ReactNode }) {
  const [pop, setPop] = useState<Pop | null>(null);
  const element = useRef<HTMLDivElement>(null);
  const serial = useRef(0);
  const close = useCallback(() => setPop(null), []);
  const open = useCallback<Api["open"]>((anchor, body, label, extra) => {
    serial.current += 1;
    setPop({ anchor, body, label, serial: serial.current, ...extra });
  }, []);
  useLayoutEffect(() => {
    const el = element.current;
    if (!pop || !el) return;
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
      close();
      pop.anchor.focus({ preventScroll: true });
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
  }, [pop, close]);
  const api = useMemo(() => ({ open, close }), [open, close]);
  return (
    <Context.Provider value={api}>
      {children}
      {pop && (
        <div
          key={pop.serial}
          ref={element}
          className={`pop ${pop.cls ?? "menu-pop"}`}
          role="menu"
          aria-label={pop.label}
        >
          {pop.body}
        </div>
      )}
    </Context.Provider>
  );
}

export function usePopover() {
  const value = useContext(Context);
  if (!value) throw new Error("popover_context_missing");
  return value;
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
