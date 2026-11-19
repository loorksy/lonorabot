import { t } from "@lingui/core/macro";
import { Trans } from "@lingui/react/macro";
import { Icon, type IconName } from "@lonora/ui-web";
import { type RefObject, useEffect, useRef } from "react";
import { foldNav, type LensRect, lensRect, placeLens } from "./lens";
import { ROOTS, type Root } from "./routes";
import { suppressClicks } from "./sheets/SheetHost";
import { haptic } from "./spring";

const icons: Record<Root, IconName> = {
  chats: "chat",
  updates: "bell",
  tasks: "task",
  settings: "settings",
};
export function tabLabel(root: Root) {
  switch (root) {
    case "chats":
      return t`Chats`;
    case "updates":
      return t`Needs your attention`;
    case "tasks":
      return t`Tasks`;
    default:
      return t`Settings`;
  }
}

/* Telegram-style floating tab bar: glass pill, a lens that slides under the active tab (or is
   dragged across the tabs and released), badges, and a fold to icons while scrolling down. */
export function FloatingTabBar({
  navRef,
  section,
  chatsBadge,
  updatesDot,
  onTab,
  onLensRelease,
  dragging,
}: {
  navRef: RefObject<HTMLElement | null>;
  section: Root;
  chatsBadge: number;
  updatesDot: boolean;
  onTab: (root: Root) => void;
  onLensRelease: (root: Root, lensFrom: LensRect | null) => void;
  /** Set while the lens is dragged or the pager travels, so the fold leaves the bar alone. */
  dragging: RefObject<boolean>;
}) {
  const drag = useRef<{ id: number; x0: number; moved: boolean; idx: number } | null>(null);
  useEffect(() => {
    const nav = navRef.current;
    if (!nav) return;
    void section;
    placeLens(nav, true);
    let size = `${nav.offsetWidth}x${nav.offsetHeight}`;
    const observer = new ResizeObserver(() => {
      const next = `${nav.offsetWidth}x${nav.offsetHeight}`;
      if (next !== size) {
        size = next;
        if (!drag.current && !dragging.current) placeLens(nav, false);
      }
    });
    observer.observe(nav);
    return () => observer.disconnect();
  }, [navRef, section, dragging]);
  useEffect(() => {
    const nav = navRef.current;
    if (!nav) return;
    const lens = nav.querySelector<HTMLElement>(".nav-lens");
    const buttons = () => [...nav.querySelectorAll<HTMLElement>("button")];
    const down = (event: PointerEvent) => {
      if (event.pointerType === "mouse" || dragging.current) return;
      foldNav(nav, false);
      drag.current = { id: event.pointerId, x0: event.clientX, moved: false, idx: -1 };
      try {
        nav.setPointerCapture(event.pointerId);
      } catch {
        /* synthetic pointers cannot be captured */
      }
    };
    const move = (event: PointerEvent) => {
      const d = drag.current;
      if (!d || event.pointerId !== d.id || !lens) return;
      const dx = event.clientX - d.x0;
      if (!d.moved) {
        if (Math.abs(dx) < 8) return;
        d.moved = true;
        dragging.current = true;
        nav.classList.add("dragging");
      }
      const r = nav.getBoundingClientRect();
      const btns = buttons();
      const w = btns[0].offsetWidth;
      const x = Math.max(5, Math.min(r.width - 5 - w, event.clientX - r.left - w / 2));
      lens.style.transition = "none";
      lens.style.width = `${w}px`;
      lens.style.transform = `translateX(${x}px)`;
      const i = btns.findIndex((b) => {
        const br = b.getBoundingClientRect();
        return event.clientX >= br.left && event.clientX <= br.right;
      });
      if (i >= 0 && i !== d.idx) {
        d.idx = i;
        btns.forEach((b, k) => {
          b.classList.toggle("peek", k === i);
        });
        haptic(6);
      }
    };
    const end = (event: PointerEvent) => {
      const d = drag.current;
      if (!d || event.pointerId !== d.id) return;
      drag.current = null;
      nav.classList.remove("dragging");
      if (lens) lens.style.transition = "";
      const btns = buttons();
      for (const b of btns) b.classList.remove("peek");
      if (!d.moved) return;
      dragging.current = false;
      suppressClicks();
      const root = btns[d.idx]?.dataset.root as Root | undefined;
      if (root && root !== section)
        onLensRelease(root, lensRect(btns[d.idx]) && lensPosition(lens));
      else placeLens(nav, true);
    };
    nav.addEventListener("pointerdown", down, { passive: true });
    document.addEventListener("pointermove", move, { passive: true });
    document.addEventListener("pointerup", end);
    document.addEventListener("pointercancel", end);
    return () => {
      nav.removeEventListener("pointerdown", down);
      document.removeEventListener("pointermove", move);
      document.removeEventListener("pointerup", end);
      document.removeEventListener("pointercancel", end);
    };
  }, [navRef, section, onLensRelease, dragging]);
  return (
    <nav ref={navRef as RefObject<HTMLElement>} className="tabbar" aria-label={t`Main navigation`}>
      <span className="nav-lens" aria-hidden="true" />
      {ROOTS.map((root) => {
        const badge = root === "chats" ? chatsBadge : 0;
        const dot = root === "updates" && updatesDot;
        return (
          <button
            type="button"
            key={root}
            data-root={root}
            className={section === root ? "active" : ""}
            aria-current={section === root ? "page" : undefined}
            onClick={() => onTab(root)}
          >
            <span className="nav-icon">
              <Icon name={icons[root]} />
              {dot ? (
                <span className="nav-dot" />
              ) : badge ? (
                <span className="nav-badge">{badge}</span>
              ) : null}
            </span>
            <span className="nav-label">{tabLabel(root)}</span>
            {dot ? (
              <span className="sr-only">
                {" · "}
                <Trans>new</Trans>
              </span>
            ) : badge ? (
              <span className="sr-only">
                {" · "}
                <Trans>{badge} unread</Trans>
              </span>
            ) : null}
          </button>
        );
      })}
    </nav>
  );
}
/** Where the lens currently is (its inline transform), for a pager that starts from the finger. */
function lensPosition(lens: HTMLElement | null): LensRect | null {
  if (!lens) return null;
  const match = /translateX\(([-\d.]+)px\)/.exec(lens.style.transform);
  return { x: match ? Number(match[1]) : 0, w: Number.parseFloat(lens.style.width) || 0 };
}
