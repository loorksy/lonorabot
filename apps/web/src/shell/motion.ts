import { useEffect, useState } from "react";

export const DESKTOP_QUERY = "(min-width: 900px)";
const motionQuery = "(prefers-reduced-motion: reduce)";

export const isDesktop = () => matchMedia(DESKTOP_QUERY).matches;
// «تقليل الحركة» in سهولة الاستخدام (body.rm) counts like the system setting.
export const reducedMotion = () =>
  matchMedia(motionQuery).matches || document.body.classList.contains("rm");

export function useMedia(query: string) {
  const [matches, setMatches] = useState(() => matchMedia(query).matches);
  useEffect(() => {
    const media = matchMedia(query);
    const changed = () => setMatches(media.matches);
    media.addEventListener("change", changed);
    setMatches(media.matches);
    return () => media.removeEventListener("change", changed);
  }, [query]);
  return matches;
}
export const useDesktop = () => useMedia(DESKTOP_QUERY);
export const useReducedMotion = () => useMedia(motionQuery);

/** Keep the --top-h / --bottom-h overlay insets of a scroller's host measured. */
export function layoutOverlays(host: HTMLElement) {
  const top = host.querySelector<HTMLElement>(":scope>.topbar");
  const low =
    host.querySelector<HTMLElement>(":scope>nav") ??
    host.querySelector<HTMLElement>(":scope>.composer");
  const th = top && getComputedStyle(top).display !== "none" ? top.offsetHeight : 0;
  let bh = 0;
  if (low) bh = low.offsetHeight + (Number.parseFloat(getComputedStyle(low).bottom) || 0);
  host.style.setProperty("--top-h", `${th}px`);
  host.style.setProperty("--bottom-h", `${bh}px`);
}
