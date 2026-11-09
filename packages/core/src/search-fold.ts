/**
 * The owner's search folding, identical to `lonora_core.search_fold`: lower case, the
 * alef variants become ا, ى becomes ي, ة becomes ه, tashkeel and tatweel are removed and
 * whitespace runs collapse. Web and Mobile highlight a hit by finding the folded query
 * inside the folded text and mapping the match back onto the original characters.
 */
const ALEF_VARIANTS = "أإآٱ";
const TASHKEEL = "ًٌٍَُِّْٰ";
const TATWEEL = "ـ";
const FOLD_FROM = `${ALEF_VARIANTS}ىة${TASHKEEL}${TATWEEL}`;
const FOLD_TO = `${"ا".repeat(ALEF_VARIANTS.length)}يه`;
const TABLE = new Map<string, string>(
  [...FOLD_FROM].map((source, index) => [source, index < FOLD_TO.length ? FOLD_TO[index] : ""]),
);

/** One character folded (it may fold to nothing). */
function foldChar(char: string): string {
  let out = "";
  for (const unit of char.toLowerCase()) out += TABLE.get(unit) ?? unit;
  return out;
}

export function foldSearch(text: string): string {
  let out = "";
  for (const char of text) out += /\s/.test(char) ? " " : foldChar(char);
  return out.trim().replace(/\s+/g, " ");
}

/**
 * Where the folded query first occurs in the text, as [start, end) over the original
 * string, or null. A whitespace run in the text matches one space in the query.
 */
export function highlightRange(text: string, query: string): [number, number] | null {
  const needle = foldSearch(query);
  if (!needle) return null;
  const folded: string[] = [];
  const origins: number[] = [];
  let index = 0;
  let lastSpace = true;
  for (const char of text) {
    if (/\s/.test(char)) {
      if (!lastSpace) {
        folded.push(" ");
        origins.push(index);
      }
      lastSpace = true;
    } else {
      lastSpace = false;
      // One entry per UTF-16 unit, so indexOf over the joined string maps back exactly.
      const out = foldChar(char);
      for (let unit = 0; unit < out.length; unit++) {
        folded.push(out[unit]);
        origins.push(index);
      }
    }
    index += char.length;
  }
  const at = folded.join("").indexOf(needle);
  if (at < 0) return null;
  const lastOrigin = origins[at + needle.length - 1];
  const lastChar = [...text.slice(lastOrigin)][0] ?? "";
  return [origins[at], lastOrigin + lastChar.length];
}
