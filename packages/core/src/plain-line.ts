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
  const line = plainWords(text);
  let cut = line;
  if (line.length > max) {
    const space = line.lastIndexOf(" ", max);
    cut = `${line.slice(0, space > 0 ? space : max).trimEnd()}…`;
  }
  return isolateNumbers(cut);
}

const isolateNumbers = (line: string) => line.replace(SIGNED_NUMBER, "$1\u2066$2\u2069");

// An upper bound of each character's advance, in em, in the apps' system fonts (measured at
// 12 to 16 px in the test browser, where wide glyphs are widest): the wide Latin letters and
// signs, the other capitals, the narrow marks, lower case, the rest of ASCII, the widest Arabic
// letters (seen, sheen, sad, dad) and the other Arabic letters; Arabic vowel marks take no
// room. Anything else counts as wide. The GenUI compiler counts slot heights by the same bound
// (genui_compile.wrapped_lines).
const WIDE = /[WMmw%@]/;
const CAPITAL = /[A-Z]/;
const NARROW = /[ijlI.,:;!'|()[\]frt]/;
const LOWER = /[a-z]/;
const LATIN = /[\x21-\x7e]/;
const SEEN = /[\u0633-\u0636]/;
const ARABIC = /[\u0600-\u06ff\ufb50-\ufdff\ufe70-\ufeff]/;
const MARK = /[\u064b-\u065f\u0670\u06d6-\u06ed]/;

function advance(char: string): number {
  if (char === " ") return 0.3;
  if (WIDE.test(char)) return 1;
  if (CAPITAL.test(char)) return 0.78;
  if (NARROW.test(char)) return 0.4;
  if (LOWER.test(char)) return 0.62;
  if (LATIN.test(char)) return 0.66;
  if (MARK.test(char)) return 0;
  if (SEEN.test(char)) return 0.96;
  if (ARABIC.test(char)) return 0.5;
  return 1;
}

/** A text's width in px at `fontSize` by the bound above: never narrower than it is drawn. */
export function textWidth(text: string, fontSize: number): number {
  let em = 0;
  for (const char of String(text ?? "").replace(CONTROLS, "")) em += advance(char);
  return em * fontSize;
}

/**
 * `plainLine` cut to what `lines` lines of `width` px hold at `fontSize` px, wrapped word by
 * word as a line is drawn, with «…» when words are left out. For a client whose own line
 * limit cuts where the box ends (React Native's numberOfLines), which could fall inside a
 * signed number: this line always fits, so that cut never comes, and a figure is shown whole
 * or not at all. A single word longer than a line is cut where it stands.
 */
export function fittedLine(
  text: string,
  { width, fontSize, lines = 1 }: { width: number; fontSize: number; lines?: number },
): string {
  const words = plainWords(text).split(" ").filter(Boolean);
  const fits = (line: string) => textWidth(line, fontSize) <= width;
  const rows = [""];
  for (const word of words) {
    const last = rows.length - 1;
    if (fits(rows[last] ? `${rows[last]} ${word}` : word)) {
      rows[last] = rows[last] ? `${rows[last]} ${word}` : word;
    } else if (rows[last] && rows.length < lines && fits(word)) {
      rows.push(word);
    } else {
      // Words are left out: the last line keeps the words that fit beside «…».
      const kept = rows[last].split(" ").filter(Boolean);
      while (kept.length && !fits(`${kept.join(" ")}…`)) kept.pop();
      let line = kept.join(" ");
      if (!line && last === 0)
        for (const char of word) {
          if (!fits(`${line}${char}…`)) break;
          line += char;
        }
      rows[last] = line;
      return isolateNumbers(`${rows.filter(Boolean).join(" ")}…`);
    }
  }
  return isolateNumbers(rows.join(" "));
}

/** Markdown as plain words on one line: no marks, a table's pipes as « · ». */
function plainWords(text: string): string {
  return String(text ?? "")
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
}
