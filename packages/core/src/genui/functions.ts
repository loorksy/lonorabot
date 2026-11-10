/** The v2 card functions (GENUI_PLAN §7.3). Values mirror `genui_functions.py`; the
 * formatters (Fmt, Money, Pct, Signed, Plural, DayLabel) build display text here only, with
 * Lonora's own formatters rather than `Intl`, so web and Hermes print the same text. A bad
 * argument returns null: "" in templates, the placeholder dash in number formatters.
 */
import type { FormatContext } from "./expr";
import { groupNumber, looseEqual, show, truthy } from "./expr";
import { MAX_ITEMS, MAX_TEXT, textSize } from "./limits";

export type GenuiFunction = (context: FormatContext, ...args: unknown[]) => unknown;

export const DASH = "—";
const MAX_RANGE = MAX_ITEMS;
const MAX_LIST = 100;

const num = (value: unknown): number | null =>
  typeof value === "number" && Number.isFinite(value) ? value : null;
const nums = (values: unknown[]): number[] | null => {
  const flat = values.flatMap((value) => (Array.isArray(value) ? value : [value]));
  const numbers = flat.map(num);
  if (!numbers.length || numbers.some((item) => item === null)) return null;
  return numbers as number[];
};
const places = (value: unknown, fallback = 0): number | null => {
  if (value === null || value === undefined) return fallback;
  const number = num(value);
  return number === null || !Number.isInteger(number) || number < 0 || number > 8 ? null : number;
};
const finite = (value: number) => (Number.isFinite(value) ? value : null);
const round = (value: unknown, digits: unknown = 0) => {
  const number = num(value);
  const d = places(digits);
  if (number === null || d === null) return null;
  const precision = 10 ** d;
  return finite(Math.floor(number * precision + 0.5) / precision);
};
const unary =
  (fn: (x: number) => number): GenuiFunction =>
  (_context, value) => {
    const number = num(value);
    return number === null ? null : finite(fn(number));
  };
const series = (value: unknown): number[] | null => {
  if (!Array.isArray(value) || value.length > MAX_LIST) return null;
  const numbers = value.map(num);
  return numbers.some((item) => item === null) ? null : (numbers as number[]);
};

const CURRENCY_SIGNS: Record<string, string> = { USD: "$", EUR: "€", GBP: "£", JPY: "¥" };

function fixed(value: unknown, digits: unknown): string | null {
  const number = num(value);
  const d = places(digits);
  if (number === null || d === null) return null;
  return groupNumber(number, d);
}

/** Arabic plural category of a count (the reference's `arCount`). */
export function arCount(count: number): "zero" | "one" | "two" | "few" | "many" {
  const n = Math.abs(Math.trunc(count));
  if (n === 0) return "zero";
  if (n === 1) return "one";
  if (n === 2) return "two";
  const rest = n % 100;
  return rest >= 3 && rest <= 10 ? "few" : "many";
}

const AR_WEEKDAYS = ["الأحد", "الاثنين", "الثلاثاء", "الأربعاء", "الخميس", "الجمعة", "السبت"];
const AR_MONTHS = [
  "يناير",
  "فبراير",
  "مارس",
  "أبريل",
  "مايو",
  "يونيو",
  "يوليو",
  "أغسطس",
  "سبتمبر",
  "أكتوبر",
  "نوفمبر",
  "ديسمبر",
];
const EN_WEEKDAYS = ["Sunday", "Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday"];
const EN_MONTHS = [
  "January",
  "February",
  "March",
  "April",
  "May",
  "June",
  "July",
  "August",
  "September",
  "October",
  "November",
  "December",
];

/** The owner's local date (YYYY-MM-DD) of `now` in `timezone`, without `Intl` formatting
 * of text: only the calendar fields are read. */
export function localDate(now: Date, timezone?: string): string {
  if (!timezone) return now.toISOString().slice(0, 10);
  try {
    const parts = new Intl.DateTimeFormat("en-CA", {
      timeZone: timezone,
      year: "numeric",
      month: "2-digit",
      day: "2-digit",
    }).formatToParts(now);
    const field = (type: string) => parts.find((part) => part.type === type)?.value ?? "";
    return `${field("year")}-${field("month")}-${field("day")}`;
  } catch {
    return now.toISOString().slice(0, 10);
  }
}

function dayLabel(context: FormatContext, value: unknown): string | null {
  if (typeof value !== "string" || !/^\d{4}-\d{2}-\d{2}$/.test(value)) return null;
  const date = new Date(`${value}T12:00:00Z`);
  if (Number.isNaN(date.getTime())) return null;
  const en = context.language === "en";
  const today = localDate(context.now ?? new Date(), context.timezone);
  const tomorrow = new Date(`${today}T12:00:00Z`);
  tomorrow.setUTCDate(tomorrow.getUTCDate() + 1);
  const day = date.getUTCDate();
  const month = (en ? EN_MONTHS : AR_MONTHS)[date.getUTCMonth()];
  const name =
    value === today
      ? en
        ? "Today"
        : "اليوم"
      : value === tomorrow.toISOString().slice(0, 10)
        ? en
          ? "Tomorrow"
          : "غدًا"
        : (en ? EN_WEEKDAYS : AR_WEEKDAYS)[date.getUTCDay()];
  return en ? `${name} ${month} ${day}` : `${name} ${day} ${month}`;
}

/** How many arguments each function takes, the twin of Python's ARITY (shared fixture
 * tests/fixtures/genui/arity.json; `Random` is client-only): a call outside it fails the
 * expression on both sides. */
export const ARITY: Record<string, readonly [number, number | null]> = {
  Abs: [1, 1],
  Allocate: [2, 2],
  Avg: [1, 1],
  Ceil: [1, 1],
  Change: [1, 1],
  Clamp: [3, 3],
  Count: [1, 2],
  Cumulative: [1, 1],
  DayLabel: [1, 1],
  Default: [1, 2],
  Fact: [0, 1],
  Filter: [3, 3],
  First: [1, 1],
  Floor: [1, 1],
  Fmt: [1, 2],
  If: [1, 3],
  Includes: [2, 2],
  Join: [1, 2],
  Last: [1, 1],
  Len: [1, 1],
  Max: [0, null],
  Min: [0, null],
  Money: [1, 2],
  MovingAvg: [2, 2],
  Pct: [1, 2],
  Pick: [1, null],
  Plural: [1, 6],
  Pow: [2, 2],
  Range: [2, 3],
  Round: [1, 2],
  Score: [2, 2],
  Signed: [1, 2],
  Sqrt: [1, 1],
  Sum: [1, 1],
  Take: [2, 2],
  Random: [0, 4],
};

export const FUNCTIONS: Record<string, GenuiFunction> = {
  Round: (_c, value, digits) => round(value, digits),
  Floor: unary(Math.floor),
  Ceil: unary(Math.ceil),
  Abs: unary(Math.abs),
  Sqrt: (_c, value) => {
    const number = num(value);
    return number === null || number < 0 ? null : Math.sqrt(number);
  },
  Min: (_c, ...values) => {
    const numbers = nums(values);
    return numbers ? Math.min(...numbers) : null;
  },
  Max: (_c, ...values) => {
    const numbers = nums(values);
    return numbers ? Math.max(...numbers) : null;
  },
  Pow: (_c, base, exponent) => {
    const a = num(base);
    const b = num(exponent);
    return a === null || b === null ? null : finite(a ** b);
  },
  Clamp: (_c, value, low, high) => {
    const x = num(value);
    const a = num(low);
    const b = num(high);
    return x === null || a === null || b === null || a > b ? null : Math.min(Math.max(x, a), b);
  },
  Fmt: (_c, value, digits) => fixed(value, digits) ?? DASH,
  Money: (context, value, digits) => {
    const number = num(value);
    const text = fixed(number === null ? null : Math.abs(number), digits);
    if (text === null || number === null) return DASH;
    const code = context.currency ?? null;
    const sign = code ? (CURRENCY_SIGNS[code] ?? `${code} `) : "";
    return `${number < 0 && text.replace(/[0.,]/g, "") !== "" ? "-" : ""}${sign}${text}`;
  },
  Pct: (_c, value, digits) => {
    const text = fixed(value, digits);
    return text === null ? DASH : `${text}%`;
  },
  Signed: (_c, value, digits) => {
    const number = num(value);
    const text = fixed(number === null ? null : Math.abs(number), digits);
    return text === null || number === null ? DASH : `${number >= 0 ? "+" : "−"}${text}`;
  },
  If: (_c, condition, positive = null, negative = null) =>
    truthy(condition) ? positive : negative,
  Pick: (_c, key, ...pairs) => {
    for (let index = 0; index + 1 < pairs.length; index += 2) {
      if (looseEqual(key, pairs[index])) return pairs[index + 1];
    }
    return pairs.length % 2 === 1 ? pairs[pairs.length - 1] : null;
  },
  Len: (_c, value) => {
    if (Array.isArray(value) || typeof value === "string") return value.length;
    if (value !== null && typeof value === "object") return Object.keys(value).length;
    return value === null || value === undefined ? 0 : null;
  },
  Count: (_c, value, target = true) => {
    const items = Array.isArray(value)
      ? value
      : value !== null && typeof value === "object"
        ? Object.values(value)
        : null;
    if (!items) return value == null ? 0 : null;
    return items.filter((item) => looseEqual(item, target)).length;
  },
  Sum: (_c, value) =>
    Array.isArray(value)
      ? value.reduce<number>((total, item) => total + (num(item) ?? 0), 0)
      : null,
  Avg: (_c, value) => {
    const numbers = Array.isArray(value) && value.length ? series(value) : null;
    return numbers ? numbers.reduce((a, b) => a + b, 0) / numbers.length : null;
  },
  Range: (_c, start, stop, step = 1) => {
    const a = num(start);
    const b = num(stop);
    const s = num(step);
    if (a === null || b === null || s === null || s === 0 || (b - a) / s < 0) return null;
    const count = Math.floor((b - a) / s + 1e-9) + 1;
    if (count > MAX_RANGE) return null;
    return Array.from({ length: count }, (_, index) => a + index * s);
  },
  Includes: (_c, values, target) =>
    Array.isArray(values) ? values.some((item) => show(item) === show(target)) : false,
  Join: (_c, values, separator = "، ") => {
    if (!Array.isArray(values) || typeof separator !== "string" || values.length > MAX_ITEMS)
      return null;
    const parts = values.map((item) => (item == null ? "" : show(item)));
    // Measured before it is built, so a nested Join never expands (review S1).
    const size =
      parts.reduce((total, part) => total + textSize(part), 0) +
      textSize(separator) * Math.max(parts.length - 1, 0);
    return size > MAX_TEXT ? null : parts.join(separator);
  },
  Plural: (_c, count, one = "", two = "", few = "", many = "", zero = "") => {
    const number = num(count);
    if (number === null) return null;
    const category = arCount(number);
    const forms: Record<string, unknown> = { zero: zero || many, one, two, few, many };
    const form = forms[category];
    return form == null ? "" : show(form);
  },
  Score: (_c, answers, key) => {
    if (answers === null || typeof answers !== "object" || Array.isArray(answers)) return null;
    if (!Array.isArray(key)) return null;
    const record = answers as Record<string, unknown>;
    return key.filter(
      (expected, index) =>
        Object.hasOwn(record, String(index)) && looseEqual(record[String(index)], expected),
    ).length;
  },
  DayLabel: (context, value) => dayLabel(context, value),
  Fact: () => null,
  First: (_c, value) => (Array.isArray(value) && value.length ? value[0] : null),
  Last: (_c, value) => (Array.isArray(value) && value.length ? value[value.length - 1] : null),
  Default: (_c, value, fallback = null) =>
    value === null ||
    value === undefined ||
    value === "" ||
    (typeof value === "number" && !Number.isFinite(value))
      ? fallback
      : value,
  Take: (_c, values, count) => {
    const n = num(count);
    if (!Array.isArray(values) || n === null || !Number.isInteger(n)) return null;
    return n >= 0 ? values.slice(0, n) : values.slice(n);
  },
  Filter: (_c, values, key, target) =>
    Array.isArray(values) && typeof key === "string"
      ? values.filter(
          (item) =>
            item !== null &&
            typeof item === "object" &&
            !Array.isArray(item) &&
            looseEqual(
              Object.hasOwn(item, key) ? (item as Record<string, unknown>)[key] : null,
              target,
            ),
        )
      : null,
  Change: (_c, value) => {
    const items = series(value);
    if (!items) return null;
    return items.length
      ? [0, ...items.slice(1).map((item, index) => item - (items[index] as number))]
      : [];
  },
  Cumulative: (_c, value) => {
    const items = series(value);
    if (!items) return null;
    let total = 0;
    return items.map((item) => {
      total += item;
      return total;
    });
  },
  MovingAvg: (_c, value, window) => {
    const items = series(value);
    const size = num(window);
    if (!items || size === null || !Number.isInteger(size) || size < 1) return null;
    return items.map((_, index) => {
      const part = items.slice(Math.max(0, index - size + 1), index + 1);
      return part.reduce((a, b) => a + b, 0) / part.length;
    });
  },
  Allocate: (_c, total, weights) => {
    const amount = num(total);
    const parts = series(weights);
    if (amount === null || !parts || !parts.length || parts.some((part) => part < 0)) return null;
    const weight = parts.reduce((a, b) => a + b, 0);
    if (weight <= 0) return null;
    const cents = Math.round(amount * 100);
    const raw = parts.map((part) => (cents * part) / weight);
    const floors = raw.map(Math.floor);
    let remainder = cents - floors.reduce((a, b) => a + b, 0);
    const order = raw
      .map((value, index) => ({ index, rest: value - (floors[index] as number) }))
      .sort((a, b) => b.rest - a.rest || a.index - b.index);
    for (const { index } of order) {
      if (remainder <= 0) break;
      floors[index] = (floors[index] as number) + 1;
      remainder -= 1;
    }
    return floors.map((value) => value / 100);
  },
  Random: (_c, min = 0, max = 1, integer = false, count = null) => {
    const a = num(min);
    const b = num(max);
    if (a === null || b === null || a > b) return null;
    const draw = () => {
      const value = a + Math.random() * (b - a);
      return integer ? Math.floor(a + Math.random() * (Math.floor(b) - Math.ceil(a) + 1)) : value;
    };
    const n = count === null ? null : num(count);
    if (n === null) return count === null ? draw() : null;
    if (!Number.isInteger(n) || n < 1 || n > 50) return null;
    return Array.from({ length: n }, draw);
  },
};

export const KNOWN_FUNCTIONS = new Set(Object.keys(FUNCTIONS));
