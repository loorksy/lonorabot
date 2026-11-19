import { useEffect, useState } from "react";

/* The pacing of a reply while it streams (reference streamAnswer, Desktop-37 5806-5830): the
   text is shown a word and its gap at a time, every 34 to 68 ms, instead of in the bursts the
   server sends. It only paces the live preview: a finished reply is never held back, and the
   reveal never trails what has arrived by more than REVEAL_LAG parts. */
export const REVEAL_LAG = 24;

/** Words and the gaps between them, as separate parts. */
export const revealParts = (text: string): string[] => text.split(/(\s+)/);

/** How many parts to show after one tick: two more, or enough to stay within the lag. */
export const nextReveal = (shown: number, total: number, lag = REVEAL_LAG): number =>
  Math.min(total, Math.max(shown + 2, total - lag));

/** The wait before the next tick, from a random number in [0, 1). */
export const revealDelay = (random: number): number => 34 + random * 34;

/** The part of `text` to show now. Inactive (not streaming, or motion reduced): all of it. */
export function useRevealedText(text: string, active: boolean): string {
  const total = active ? revealParts(text).length : 0;
  const [shown, setShown] = useState(0);
  // A text that was replaced by a shorter one is not read past its end.
  const visible = Math.min(shown, total);
  useEffect(() => {
    if (!active || visible >= total) return;
    const timer = setTimeout(
      () => setShown((current) => nextReveal(Math.min(current, total), total)),
      revealDelay(Math.random()),
    );
    return () => clearTimeout(timer);
  }, [active, visible, total]);
  return active ? revealParts(text).slice(0, visible).join("") : text;
}
