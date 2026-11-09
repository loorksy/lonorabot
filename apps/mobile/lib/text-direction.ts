export type TextDirection = "rtl" | "ltr";

// Right-to-left letters (Hebrew, Arabic, Syriac, Thaana, N'Ko and their presentation
// forms) without the Arabic-Indic digits, which take the surrounding direction.
const RTL_LETTER = "֐-׿؀-ٟ٪-ۯۺ-ࣿיִ-﷿ﹰ-ﻼ";
const RTL = new RegExp(`[${RTL_LETTER}]`);
const STRONG = new RegExp(`[A-Za-zÀ-ɏͰ-ϿЀ-ӿ${RTL_LETTER}]`);

/**
 * The direction text written by an agent or person reads in: its first strong
 * letter decides, as the web's dir="auto" does, and text without one (numbers,
 * symbols) follows the interface.
 */
export function textDirection(text: string, fallback: TextDirection): TextDirection {
  const first = STRONG.exec(text)?.[0];
  if (first === undefined) return fallback;
  return RTL.test(first) ? "rtl" : "ltr";
}
