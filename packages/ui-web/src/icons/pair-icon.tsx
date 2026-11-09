import { cn } from "@lonora/ui-web/lib/utils";
import "./pair-icon.css";
import { PAIR_IMAGES } from "./pair-images";

/** An index shows its country's currency instead of a base/quote split. */
const PAIR_ONE: Readonly<Record<string, string>> = {
  US30: "USD",
  NAS100: "USD",
  SPX500: "USD",
  UK100: "GBP",
  GER40: "EUR",
  JPN225: "JPY",
};

/** EURUSD → ["EUR", "USD"] (base first); US30 → ["USD"]; anything else → its first three letters. */
export function pairCodes(symbol: string): string[] {
  const s = symbol.toUpperCase();
  if (PAIR_ONE[s]) return [PAIR_ONE[s]];
  if (/^[A-Z]{6}$/.test(s)) return [s.slice(0, 3), s.slice(3)];
  return [s.slice(0, 3)];
}

export type PairIconProps = { symbol: string; className?: string };

/**
 * The icon beside a pair: base over quote, metals and Bitcoin by code, an index by its country;
 * an unknown code gets its first letter in a plain circle. `className="sm"` is the 26px variant.
 */
function PairIcon({ symbol, className }: PairIconProps) {
  const images = pairCodes(symbol)
    .map((code) => PAIR_IMAGES[code])
    .filter(Boolean);
  if (images.length === 0) {
    return (
      <span className={cn("pair-ic none", className)} aria-hidden="true">
        {symbol.slice(0, 1) || "?"}
      </span>
    );
  }
  return (
    <span className={cn("pair-ic", `n${images.length}`, className)} aria-hidden="true">
      {images.map((src) => (
        <img key={src} src={src} alt="" decoding="async" />
      ))}
    </span>
  );
}

export { PairIcon };
