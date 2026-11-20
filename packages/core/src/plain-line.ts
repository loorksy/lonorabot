/**
 * A message as one plain line, for the places that show it small (the chat list, quotes,
 * the reply bar, the heads-up banner, search), and the direction a text reads in. Shared by
 * Web and Mobile (the v38 reference's mdPlain and latinOnly). Arabic is first: one Arabic
 * letter makes a text right-to-left, and a signed number keeps its sign on its left.
 */

// Right-to-left letters (Hebrew, Arabic, Syriac, Thaana, N'Ko and their presentation
// forms) without the Arabic-Indic digits and the Arabic number signs and punctuation
// (، ؛ ؟ ٪ ۔ and the like), which take the surrounding direction.
const RTL =
  /[\u0590-\u05ff\u0610-\u061a\u0620-\u065f\u066e-\u06d3\u06d5-\u06ef\u06fa-\u08ff\ufb1d-\ufdff\ufe70-\ufefc]/;
// Latin, Greek and Cyrillic letters; × and ÷ are signs, not letters.
const LTR = /[A-Za-z\u00c0-\u00d6\u00d8-\u00f6\u00f8-\u024f\u0370-\u03ff\u0400-\u04ff]/;
// Embedded direction controls would end an isolate early and reorder the rest of the line.
const CONTROLS = /[\u202a-\u202e\u2066-\u2069]/g;

/**
 * A signed number («+3.1%», «-$239», «−0.5») after the start, a space, a bracket, «, :, the
 * Arabic comma, a table pipe or «·» (group 1); group 2 is the number. Global: use it with
 * `replace` or `matchAll` only.
 */
export const SIGNED_NUMBER = /(^|[\s([«:،|·])([+\-−][$€£]?\d[\d,]*(?:\.\d+)?%?)/g;

/**
 * rtl when the text has a right-to-left letter, ltr when its letters are all left-to-right
 * (Latin, Greek, Cyrillic), undefined when it has none (numbers, symbols: it takes its
 * surroundings).
 */
export function textDirection(text: string): "rtl" | "ltr" | undefined {
  if (RTL.test(text)) return "rtl";
  return LTR.test(text) ? "ltr" : undefined;
}

/**
 * Markdown as one plain line: no «**», «`», «###», quote or list marks, no link targets;
 * a table's pipes become « · » and its separator row goes; a signed number is isolated
 * left-to-right (LRI … PDI). Longer than `max`, the line is cut with «…» before the numbers
 * are isolated, so a cut never leaves an isolate open; the cut falls between words, so a
 * figure is never shown in part (a single word longer than `max` is cut where it stands).
 */
export function plainLine(text: string, max = Number.POSITIVE_INFINITY): string {
  const line = String(text ?? "")
    .replace(CONTROLS, "")
    .replace(/```[\s\S]*?(```|$)/g, " ")
    .replace(/`([^`\n]+)`/g, "$1")
    .replace(/\*\*([^*\n]+)\*\*/g, "$1")
    .replace(/(^|[\s(])_([^_\n]+)_(?=[\s.,،)!?؟]|$)/g, "$1$2")
    .replace(/\[([^\]\n]+)\]\((https?:\/\/[^\s)]+)\)/g, "$1")
    .replace(/^[ \t]*\|?[ \t]*:?-{2,}[-:| \t]*$/gm, "")
    .replace(/^[ \t]*\|[ \t]*|[ \t]*\|[ \t]*$/gm, "")
    .replace(/[ \t]*\|[ \t]*/g, " · ")
    .replace(/^[ \t]*(#{1,3}[ \t]+|>[ \t]?|[-*•][ \t]+)/gm, "")
    .replace(/\s+/g, " ")
    .trim();
  let cut = line;
  if (line.length > max) {
    const space = line.lastIndexOf(" ", max);
    cut = `${line.slice(0, space > 0 ? space : max).trimEnd()}…`;
  }
  return cut.replace(SIGNED_NUMBER, "$1\u2066$2\u2069");
}
