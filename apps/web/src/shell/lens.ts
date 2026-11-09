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
