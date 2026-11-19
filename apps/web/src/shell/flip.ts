import { reference } from "@lonora/ui-tokens";
import { reducedMotion } from "./motion";

/* Layout changes the chrome makes (the tab bar folding, the chats header giving the search its
   room, a sheet changing pages) happen at once; the motion that carries each element from where
   it was is transform only (FLIP: first, last, invert, play), on the compositor, on the
   reference's --ease. EASE is the curve of a sheet's height change and the desktop list collapse. */
export const EASE = "cubic-bezier(.2,.8,.2,1)";
export type FlipItem = {
  el: HTMLElement;
  /** Also carry the size (a scale); position only otherwise. */
  scale?: boolean;
  /** Animate this pseudo-element of `el` (it covers the element's box). */
  pseudo?: string;
};

export function flip(
  items: readonly FlipItem[],
  change: () => void,
  { duration = 320, easing = reference.motion.ease }: { duration?: number; easing?: string } = {},
) {
  if (reducedMotion()) return change();
  const first = items.map((item) => item.el.getBoundingClientRect());
  change();
  items.forEach((item, index) => {
    const a = first[index];
    const b = item.el.getBoundingClientRect();
    if (!a.width || !a.height || !b.width || !b.height) return;
    const sx = item.scale ? a.width / b.width : 1;
    const sy = item.scale ? a.height / b.height : 1;
    const dx = a.left - b.left;
    const dy = a.top - b.top;
    if (
      Math.abs(dx) < 0.5 &&
      Math.abs(dy) < 0.5 &&
      Math.abs(sx - 1) < 0.004 &&
      Math.abs(sy - 1) < 0.004
    )
      return;
    // The element's own transform (the lens's translateX) stays under the inverted one.
    const own = item.pseudo ? "none" : getComputedStyle(item.el).transform;
    const base = own === "none" ? "" : ` ${own}`;
    item.el.animate(
      [
        {
          transformOrigin: "0 0",
          transform: `translate(${dx}px, ${dy}px) scale(${sx}, ${sy})${base}`,
        },
        { transformOrigin: "0 0", transform: base.trim() || "none" },
      ],
      { duration, easing, pseudoElement: item.pseudo },
    );
  });
}
