import { useEffect } from "react";
import { reducedMotion } from "./motion";

/* On-screen keyboard: --app-height follows the visual viewport so the app and the composer stay
   above it; top-layer sheets get --kb (the height the keyboard hides; 0 while pinch-zoomed) and
   html.kb-open, and a field focused inside a sheet is brought into view once the keyboard opened. */
function measure() {
  const root = document.documentElement;
  const view = window.visualViewport;
  if (!view) return;
  const height = Math.round(view.height);
  if (root.style.getPropertyValue("--app-height") !== `${height}px`)
    root.style.setProperty("--app-height", `${height}px`);
  const kb =
    view.scale > 1.01 ? 0 : Math.max(0, Math.round(innerHeight - view.height - view.offsetTop));
  if (root.style.getPropertyValue("--kb") !== `${kb}px`) root.style.setProperty("--kb", `${kb}px`);
  root.classList.toggle("kb-open", kb > 80);
}
function focused(event: FocusEvent) {
  const target = event.target;
  if (
    !(target instanceof HTMLElement) ||
    !target.matches("input:not([type=checkbox]):not([type=radio]):not([type=range]),textarea") ||
    !target.closest("dialog")
  )
    return;
  setTimeout(() => {
    if (document.activeElement === target)
      (target.closest(".field,.list-form") ?? target).scrollIntoView({
        block: "nearest",
        behavior: reducedMotion() ? "auto" : "smooth",
      });
  }, 360);
}
export function useViewportVars() {
  useEffect(() => {
    const view = window.visualViewport;
    measure();
    view?.addEventListener("resize", measure, { passive: true });
    view?.addEventListener("scroll", measure, { passive: true });
    window.addEventListener("resize", measure, { passive: true });
    document.addEventListener("focusin", focused);
    return () => {
      view?.removeEventListener("resize", measure);
      view?.removeEventListener("scroll", measure);
      window.removeEventListener("resize", measure);
      document.removeEventListener("focusin", focused);
      const root = document.documentElement;
      root.style.removeProperty("--app-height");
      root.style.removeProperty("--kb");
      root.classList.remove("kb-open");
    };
  }, []);
}
