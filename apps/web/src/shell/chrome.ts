import { type RefObject, useEffect, useLayoutEffect } from "react";
import { flip } from "./flip";
import { foldNav } from "./lens";
import { isDesktop, layoutOverlays, reducedMotion } from "./motion";
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

/* WhatsApp: the chat list's filters sit above the first row and show when the list is
   pulled down a little; they snap open or closed and stay while a filter other than الكل
   is on (data-rest="0"). Phones only. */
const listFilters = (main: HTMLElement) =>
  main.querySelector<HTMLElement>(":scope #chat-rows>.list-filters");
/** How far the chat list rests scrolled: the filters' height while they hide. */
export function chatsRest(main: HTMLElement) {
  const filters = listFilters(main);
  if (!filters || isDesktop() || filters.dataset.rest !== "1") return 0;
  return filters.offsetHeight;
}
export function syncFilters(main: HTMLElement) {
  const filters = listFilters(main);
  if (!filters || isDesktop()) return;
  const h = filters.offsetHeight || 1;
  const v = filters.dataset.rest !== "1" ? 1 : Math.max(0, Math.min(1, 1 - main.scrollTop / h));
  filters.style.opacity = v.toFixed(2);
  filters.style.transform =
    v < 1
      ? `translateY(${((1 - v) * 10).toFixed(1)}px) scale(${(0.95 + 0.05 * v).toFixed(3)})`
      : "";
  filters.style.pointerEvents = v < 0.4 ? "none" : "";
}
/** Short lists get room to rest with the filters hidden, on every visit. */
export function roomForFilters(main: HTMLElement) {
  const filters = listFilters(main);
  const rows = main.querySelector<HTMLElement>("#chat-rows");
  if (!filters || !rows || isDesktop()) return null;
  const style = getComputedStyle(main);
  const pad = Number.parseFloat(style.paddingTop) + Number.parseFloat(style.paddingBottom);
  rows.style.minHeight = `${Math.max(0, main.clientHeight - pad + filters.offsetHeight)}px`;
  return filters;
}
/** A fresh visit rests with the filters hidden. */
export function hideFiltersInitially(main: HTMLElement) {
  const filters = roomForFilters(main);
  if (filters?.dataset.rest !== "1") return false;
  main.scrollTop = filters.offsetHeight;
  return true;
}
export function snapFilters(main: HTMLElement) {
  const h = chatsRest(main);
  const y = main.scrollTop;
  if (!h || y <= 0 || y >= h) return;
  main.scrollTo({ top: y < h * 0.5 ? 0 : h, behavior: reducedMotion() ? "auto" : "smooth" });
}

export type EdgeOptions = {
  /** The main tabs and bare detail pages have a scroll edge; the chat and desktop keep --edge 1. */
  edge: boolean;
  chats: boolean;
  searchExpanded: boolean;
};
export function syncEdge(main: HTMLElement, top: HTMLElement | null, options: EdgeOptions) {
  if (!top) return;
  const header = options.chats ? top.querySelector<HTMLElement>("header.chats-header") : null;
  const off = !options.searchExpanded && !isDesktop() && main.scrollTop > chatsRest(main) + 20;
  if (header && header.classList.contains("title-off") !== off)
    flip(
      [...header.querySelectorAll<HTMLElement>(":scope > h1, :scope > .header-search")].map(
        (el) => ({ el, scale: el.classList.contains("header-search") }),
      ),
      () => header.classList.toggle("title-off", off),
      { duration: 340 },
    );
  if (isDesktop() || !options.edge || (options.chats && options.searchExpanded)) {
    top.style.removeProperty("--edge");
    return;
  }
  const title = main.querySelector<HTMLElement>(":scope>.large-title");
  const rest = title ? title.offsetHeight * 0.6 : options.chats ? chatsRest(main) : 0;
  top.style.setProperty(
    "--edge",
    Math.max(0, Math.min(1, (main.scrollTop - rest) / 16)).toFixed(3),
  );
}

/** Where a freshly painted page is scrolled to (the real page and the pager's incoming page). */
export function placeScroll(main: HTMLElement, viewKey: string) {
  const remembered = rememberedScroll(viewKey);
  if (remembered !== undefined || !hideFiltersInitially(main)) main.scrollTop = remembered ?? 0;
  syncFilters(main);
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
    // The top bar is watched; the tab bar is not (as in the reference): its fold leaves the
    // page's bottom inset where it was, so a list scrolled to its end stays put.
    const observer = new ResizeObserver(() => {
      layoutOverlays(h);
    });
    const t = top.current;
    if (t) observer.observe(t);
    return () => observer.disconnect();
  }, [host, main, top, options, viewKey]);
  useEffect(() => {
    const m = main.current;
    if (!m) return;
    let lastY = m.scrollTop;
    let snap: ReturnType<typeof setTimeout> | undefined;
    const onScroll = () => {
      syncTitle(m);
      syncEdge(m, top.current, options);
      if (options.chats && !options.searchExpanded) {
        syncFilters(m);
        clearTimeout(snap);
        snap = setTimeout(() => {
          if (!paused.current) snapFilters(m);
        }, 140);
      }
      const n = nav.current;
      if (!n || paused.current) return;
      const y = m.scrollTop;
      const d = y - lastY;
      lastY = y;
      // Folding the bar shortens the page's bottom inset at once, and the browser pulls a page
      // scrolled to its end back up: that clamp is not the owner scrolling up.
      if (d < 0 && y + m.clientHeight >= m.scrollHeight - 1) return;
      if (y < chatsRest(m) + 30) foldNav(n, false);
      else if (d > 6) foldNav(n, true);
      else if (d < -8) foldNav(n, false);
    };
    m.addEventListener("scroll", onScroll, { passive: true });
    return () => {
      clearTimeout(snap);
      m.removeEventListener("scroll", onScroll);
    };
  }, [main, top, nav, options, paused]);
}
