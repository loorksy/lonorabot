import { type RefObject, useEffect, useLayoutEffect } from "react";
import { isDesktop, layoutOverlays } from "./motion";
import { rememberedScroll } from "./navigation";

/* The scroll-driven chrome: the section title inside the page dissolves (parallax, scale,
   cross-fade into a pre-blurred copy — transform and opacity only), the top bar turns to glass
   once content slides under it, the chats title folds away, the tab bar folds while scrolling. */
export function syncTitle(main: HTMLElement) {
  const title = main.querySelector<HTMLElement>(":scope>.large-title");
  if (!title) return;
  const h = title.offsetHeight || 40;
  const p = Math.max(0, Math.min(1, main.scrollTop / h));
  title.style.opacity = Math.max(0, 1 - p * 1.3).toFixed(3);
  title.style.transform = p
    ? `translateY(${(p * h * 0.45).toFixed(1)}px) scale(${(1 - p * 0.08).toFixed(3)})`
    : "";
  const crisp = title.querySelector<HTMLElement>(".lt-crisp");
  const blur = title.querySelector<HTMLElement>(".lt-blur");
  if (crisp) crisp.style.opacity = (1 - p).toFixed(3);
  if (blur) blur.style.opacity = p.toFixed(3);
}

export type EdgeOptions = {
  /** The main tabs and bare detail pages have a scroll edge; the chat and desktop keep --edge 1. */
  edge: boolean;
  chats: boolean;
  searchExpanded: boolean;
};
export function syncEdge(main: HTMLElement, top: HTMLElement | null, options: EdgeOptions) {
  if (!top) return;
  if (options.chats)
    top
      .querySelector("header.chats-header")
      ?.classList.toggle(
        "title-off",
        !options.searchExpanded && !isDesktop() && main.scrollTop > 20,
      );
  if (isDesktop() || !options.edge || (options.chats && options.searchExpanded)) {
    top.style.removeProperty("--edge");
    return;
  }
  const title = main.querySelector<HTMLElement>(":scope>.large-title");
  const rest = title ? title.offsetHeight * 0.6 : 0;
  top.style.setProperty(
    "--edge",
    Math.max(0, Math.min(1, (main.scrollTop - rest) / 16)).toFixed(3),
  );
}

/** Where a freshly painted page is scrolled to (the real page and the pager's incoming page). */
export function placeScroll(main: HTMLElement, viewKey: string) {
  main.scrollTop = rememberedScroll(viewKey) ?? 0;
  syncTitle(main);
}

export function useScrollChrome({
  host,
  main,
  top,
  nav,
  options,
  viewKey,
  paused,
}: {
  host: RefObject<HTMLElement | null>;
  main: RefObject<HTMLElement | null>;
  top: RefObject<HTMLElement | null>;
  nav: RefObject<HTMLElement | null>;
  options: EdgeOptions;
  viewKey: string;
  /** While the pager travels or the lens is dragged the tab bar keeps its fold. */
  paused: RefObject<boolean>;
}) {
  useLayoutEffect(() => {
    const h = host.current;
    const m = main.current;
    if (!h || !m) return;
    void viewKey;
    layoutOverlays(h);
    syncEdge(m, top.current, options);
    syncTitle(m);
    const observer = new ResizeObserver(() => {
      layoutOverlays(h);
    });
    const t = top.current;
    const n = nav.current;
    if (t) observer.observe(t);
    if (n) observer.observe(n);
    return () => observer.disconnect();
  }, [host, main, top, nav, options, viewKey]);
  useEffect(() => {
    const m = main.current;
    if (!m) return;
    let lastY = m.scrollTop;
    const onScroll = () => {
      syncTitle(m);
      syncEdge(m, top.current, options);
      const n = nav.current;
      if (!n || paused.current) return;
      const y = m.scrollTop;
      const d = y - lastY;
      lastY = y;
      if (y < 30) n.classList.remove("compact");
      else if (d > 6) n.classList.add("compact");
      else if (d < -8) n.classList.remove("compact");
    };
    m.addEventListener("scroll", onScroll, { passive: true });
    return () => m.removeEventListener("scroll", onScroll);
  }, [main, top, nav, options, paused]);
}
