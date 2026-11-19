/** A card's typed number (docs/genui.md, review M7). The card's hints group thousands
 * with «,», so the owner may type the same: «2,400», «2،400», «2 400», Arabic-Indic or
 * Persian digits, «٬» and «٫». Grouping must be exact (1 to 3 digits, then groups of 3);
 * anything else is not a number, so a partial or malformed draft never becomes a value. */
const DIGITS = /[٠-٩۰-۹]/gu;
const GROUP = /[,،٬\s  ]/u;
const PLAIN = /^[+-]?(?:\d+(?:\.\d+)?|\.\d+)$/;
const GROUPED = /^[+-]?\d{1,3}(?:[,،٬\s  ]\d{3})+(?:\.\d+)?$/u;

/** A number, ``null`` for an empty draft, ``undefined`` when it cannot be read. */
export function parseCardNumber(text: string): number | null | undefined {
  const normalized = text
    .trim()
    .replace(DIGITS, (digit) =>
      String(
        "٠١٢٣٤٥٦٧٨٩".includes(digit) ? "٠١٢٣٤٥٦٧٨٩".indexOf(digit) : "۰۱۲۳۴۵۶۷۸۹".indexOf(digit),
      ),
    )
    .replace(/٫/g, ".");
  if (!normalized) return null;
  if (normalized.length > 64) return undefined;
  if (!PLAIN.test(normalized) && !GROUPED.test(normalized)) return undefined;
  const parsed = Number(normalized.split(GROUP).join(""));
  return Number.isFinite(parsed) ? parsed : undefined;
}
