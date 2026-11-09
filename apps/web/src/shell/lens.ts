import { flip } from "./flip";

/** The tab bar's lens: it sits under the active tab and slides when the section changes. */
export type LensRect = { x: number; w: number };
export const lensRect = (button: HTMLElement | null | undefined): LensRect | null =>
  button ? { x: button.offsetLeft, w: button.offsetWidth } : null;
export function placeLens(nav: HTMLElement | null, animate: boolean): LensRect | null {
  if (!nav) return null;
  const lens = nav.querySelector<HTMLElement>(".nav-lens");
  const active = nav.querySelector<HTMLElement>("button.active");
  if (!lens || !active) return null;
  const rect = lensRect(active) as LensRect;
  if (!animate) lens.style.transition = "none";
  lens.style.width = `${rect.w}px`;
  lens.style.transform = `translateX(${rect.x}px)`;
  if (!animate) {
    void lens.offsetWidth;
    lens.style.transition = "";
  }
  return rect;
}

/** Fold the tab bar to its icons (or back): the bar's box changes at once and the glass, the
 * icons, the labels and the lens travel from where they were with transforms only. */
export function foldNav(nav: HTMLElement | null, compact: boolean) {
  if (!nav || nav.classList.contains("compact") === compact) return;
  const lens = nav.querySelector<HTMLElement>(".nav-lens");
  const parts = [...nav.querySelectorAll<HTMLElement>(".nav-icon, .nav-label")];
  flip(
    [
      { el: nav, pseudo: "::before", scale: true },
      ...parts.map((el) => ({ el })),
      ...(lens ? [{ el: lens, scale: true }] : []),
    ],
    () => {
      nav.classList.toggle("compact", compact);
      placeLens(nav, false);
    },
  );
}
