/** The lonora-ui v2 expression language (GENUI_PLAN §2.2, §7.3), the reference grammar
 * (Desktop-37 6287-6356). Mirrors `lonora_contracts/genui_expr.py` for values; the shared
 * vectors in `tests/fixtures/genui/expr-vectors.json` hold the two equal. Nothing here is
 * executed as JavaScript: expressions are parsed into a small AST and walked.
 */
import { FUNCTIONS, type GenuiFunction } from "./functions";

export const MAX_EXPRESSION_CHARS = 400;
export const MAX_EXPRESSION_DEPTH = 12;
const MAX_PARSE_NESTING = 160;
const BLOCKED = new Set(["__proto__", "prototype", "constructor"]);

export type Node =
  | readonly ["c", unknown]
  | readonly ["v", string]
  | readonly ["l", string]
  | readonly ["a", readonly Node[]]
  | readonly ["u", "!" | "-", Node]
  | readonly ["?", Node, Node, Node]
  | readonly ["g", Node, Node]
  | readonly ["b", string, Node, Node]
  | readonly ["f", string, readonly Node[]];

type Token = { kind: "num" | "str" | "var" | "fn" | "id" | "op" | "end"; value: string | number };

const TOKEN =
  /\s*(?:(\d+(?:\.\d+)?)|'([^']*)'|"([^"]*)"|\$([A-Za-z_][A-Za-z0-9_]*)|@([A-Za-z][A-Za-z0-9]*)|([A-Za-z_][A-Za-z0-9_]*)|(&&|\|\||==|!=|<=|>=|[-+*/%<>!?:().,[\]]))/y;

export class ExpressionError extends Error {}

function tokenize(source: string): Token[] {
  if (typeof source !== "string" || source.length > MAX_EXPRESSION_CHARS) {
    throw new ExpressionError("genui_expression_too_long");
  }
  const tokens: Token[] = [];
  let position = 0;
  while (position < source.length) {
    if (source.slice(position).trim() === "") break;
    TOKEN.lastIndex = position;
    const match = TOKEN.exec(source);
    if (!match || match.index !== position || TOKEN.lastIndex === position) {
      throw new ExpressionError("genui_expression_invalid");
    }
    position = TOKEN.lastIndex;
    const [, num, sq, dq, variable, fn, id, op] = match;
    if (num !== undefined) tokens.push({ kind: "num", value: Number(num) });
    else if (sq !== undefined) tokens.push({ kind: "str", value: sq });
    else if (dq !== undefined) tokens.push({ kind: "str", value: dq });
    else if (variable !== undefined) tokens.push({ kind: "var", value: variable });
    else if (fn !== undefined) tokens.push({ kind: "fn", value: fn });
    else if (id !== undefined) tokens.push({ kind: "id", value: id });
    else tokens.push({ kind: "op", value: op as string });
  }
  tokens.push({ kind: "end", value: "" });
  return tokens;
}

const LEVELS: readonly (readonly string[])[] = [
  ["||"],
  ["&&"],
  ["==", "!="],
  ["<", "<=", ">", ">="],
  ["+", "-"],
  ["*", "/", "%"],
];

class Parser {
  private index = 0;
  private depth = 0;
  constructor(private readonly tokens: Token[]) {}

  private peek(value: string) {
    const token = this.tokens[this.index] as Token;
    return token.kind === "op" && token.value === value;
  }
  private take(value: string) {
    if (!this.peek(value)) return false;
    this.index += 1;
    return true;
  }
  private expect(value: string) {
    if (!this.take(value)) throw new ExpressionError("genui_expression_invalid");
  }
  private enter() {
    this.depth += 1;
    if (this.depth > MAX_PARSE_NESTING) throw new ExpressionError("genui_expression_too_deep");
  }
  private leave() {
    this.depth -= 1;
  }

  parse(): Node {
    const node = this.ternary();
    if ((this.tokens[this.index] as Token).kind !== "end") {
      throw new ExpressionError("genui_expression_invalid");
    }
    return node;
  }

  private ternary(): Node {
    this.enter();
    let node = this.binary(0);
    if (this.take("?")) {
      const positive = this.ternary();
      this.expect(":");
      node = ["?", node, positive, this.ternary()];
    }
    this.leave();
    return node;
  }

  private binary(level: number): Node {
    if (level === LEVELS.length) return this.unary();
    this.enter();
    let left = this.binary(level + 1);
    for (;;) {
      const token = this.tokens[this.index] as Token;
      if (token.kind === "op" && (LEVELS[level] as readonly string[]).includes(String(token.value))) {
        this.index += 1;
        left = ["b", String(token.value), left, this.binary(level + 1)];
      } else break;
    }
    this.leave();
    return left;
  }

  private unary(): Node {
    for (const op of ["!", "-"] as const) {
      if (this.take(op)) {
        this.enter();
        const node: Node = ["u", op, this.unary()];
        this.leave();
        return node;
      }
    }
    return this.postfix();
  }

  private postfix(): Node {
    let node = this.primary();
    for (;;) {
      if (this.take(".")) {
        const token = this.tokens[this.index] as Token;
        if (token.kind !== "id") throw new ExpressionError("genui_expression_invalid");
        this.index += 1;
        node = ["g", node, ["c", token.value]];
      } else if (this.take("[")) {
        this.enter();
        node = ["g", node, this.ternary()];
        this.leave();
        this.expect("]");
      } else return node;
    }
  }

  private list(close: string): Node[] {
    const items: Node[] = [];
    this.enter();
    if (!this.take(close)) {
      for (;;) {
        items.push(this.ternary());
        if (this.take(close)) break;
        this.expect(",");
      }
    }
    this.leave();
    return items;
  }

  private primary(): Node {
    const token = this.tokens[this.index] as Token;
    this.index += 1;
    switch (token.kind) {
      case "num":
      case "str":
        return ["c", token.value];
      case "var":
        return ["v", String(token.value)];
      case "fn":
        this.expect("(");
        return ["f", String(token.value), this.list(")")];
      case "id":
        if (token.value === "true") return ["c", true];
        if (token.value === "false") return ["c", false];
        if (token.value === "null") return ["c", null];
        return ["l", String(token.value)];
      case "op":
        if (token.value === "(") {
          this.enter();
          const node = this.ternary();
          this.leave();
          this.expect(")");
          return node;
        }
        if (token.value === "[") return ["a", this.list("]")];
    }
    throw new ExpressionError("genui_expression_invalid");
  }
}

function astDepth(node: Node): number {
  let deepest = 0;
  for (const item of node.slice(1)) {
    if (Array.isArray(item)) {
      if (typeof item[0] === "string") deepest = Math.max(deepest, astDepth(item as unknown as Node));
      else for (const child of item as Node[]) deepest = Math.max(deepest, astDepth(child));
    }
  }
  return 1 + deepest;
}

const cache = new Map<string, Node | null>();

export function parse(source: string): Node {
  const cached = cache.get(source);
  if (cached) return cached;
  if (cached === null) throw new ExpressionError("genui_expression_invalid");
  try {
    const node = new Parser(tokenize(source)).parse();
    if (astDepth(node) > MAX_EXPRESSION_DEPTH) throw new ExpressionError("genui_expression_too_deep");
    if (cache.size < 4096) cache.set(source, node);
    return node;
  } catch (error) {
    if (cache.size < 4096) cache.set(source, null);
    throw error;
  }
}

// --- values ---------------------------------------------------------------------------------

export const isNumber = (value: unknown): value is number => typeof value === "number";
const isPlain = (value: unknown): value is Record<string, unknown> =>
  value !== null && typeof value === "object" && !Array.isArray(value);

export function toNumber(value: unknown): number {
  if (value === null || value === undefined) return 0;
  if (typeof value === "boolean") return value ? 1 : 0;
  if (typeof value === "number") return value;
  if (typeof value === "string") {
    const text = value.trim();
    if (text === "") return 0;
    return /^[+-]?(\d+\.?\d*|\.\d+)([eE][+-]?\d+)?$/.test(text) ? Number(text) : Number.NaN;
  }
  return Number.NaN;
}

export function truthy(value: unknown): boolean {
  if (value === null || value === undefined || value === false) return false;
  if (typeof value === "number") return value !== 0 && !Number.isNaN(value);
  if (typeof value === "string") return value !== "";
  return true;
}

export function show(value: unknown): string {
  if (value === null || value === undefined) return "null";
  if (Array.isArray(value)) return value.map((item) => (item == null ? "" : show(item))).join(",");
  if (isPlain(value)) return "[object Object]";
  return String(value);
}

export function looseEqual(left: unknown, right: unknown): boolean {
  if (left == null || right == null) return left == null && right == null;
  if (typeof left === "object" || typeof right === "object") return left === right;
  if (typeof left === "string" && typeof right === "string") return left === right;
  if (typeof left === "boolean" && typeof right === "boolean") return left === right;
  const a = toNumber(left);
  const b = toNumber(right);
  return !Number.isNaN(a) && !Number.isNaN(b) && a === b;
}

/** Non-finite numbers are null; everything else is as computed. */
export function normal(value: unknown): unknown {
  if (typeof value === "number" && !Number.isFinite(value)) return null;
  if (value === undefined) return null;
  return value;
}

function compare(op: string, left: unknown, right: unknown): boolean {
  let a: number | string;
  let b: number | string;
  if (typeof left === "string" && typeof right === "string") {
    a = left;
    b = right;
  } else {
    a = toNumber(left);
    b = toNumber(right);
    if (Number.isNaN(a) || Number.isNaN(b)) return false;
  }
  return op === "<" ? a < b : op === "<=" ? a <= b : op === ">" ? a > b : a >= b;
}

function binary(op: string, left: unknown, right: unknown): unknown {
  if (op === "+") {
    if (typeof left === "string" || typeof right === "string") return show(left) + show(right);
    return toNumber(left || 0) + toNumber(right || 0);
  }
  if (op === "-" || op === "*" || op === "/" || op === "%") {
    const a = toNumber(left);
    const b = toNumber(right);
    if (op === "-") return a - b;
    if (op === "*") return a * b;
    if (b === 0 || Number.isNaN(b)) return 0;
    return op === "/" ? a / b : a % b;
  }
  if (op === "==") return looseEqual(left, right);
  if (op === "!=") return !looseEqual(left, right);
  return compare(op, left, right);
}

export type Env = {
  values: Record<string, unknown>;
  facts: Record<string, unknown>;
  names: Record<string, unknown>;
  functions?: Record<string, GenuiFunction>;
  context?: FormatContext;
};

export type FormatContext = {
  currency?: string | null;
  timezone?: string;
  language?: "ar" | "en";
  now?: Date;
  /** Only a `set` action value may draw. */
  allowRandom?: boolean;
};

/** Own properties only; a missing key reads as null, as Python's `dict.get` does. */
const ownGet = (record: Record<string, unknown>, key: string) =>
  Object.hasOwn(record, key) ? (record[key] ?? null) : null;

function get(container: unknown, key: unknown): unknown {
  if (typeof key === "string" && BLOCKED.has(key)) throw new ExpressionError("genui_expression_blocked");
  if (isPlain(container)) return ownGet(container, typeof key === "string" ? key : show(key));
  if (Array.isArray(container) || typeof container === "string") {
    if (key === "length") return container.length;
    const index = typeof key === "number" ? key : typeof key === "string" && /^\d+$/.test(key) ? Number(key) : Number.NaN;
    if (Number.isInteger(index) && index >= 0 && index < container.length) return container[index];
  }
  return null;
}

export function evaluateNode(node: Node, env: Env): unknown {
  switch (node[0]) {
    case "c":
      return node[1];
    case "v":
      if (BLOCKED.has(node[1])) throw new ExpressionError("genui_expression_blocked");
      return ownGet(env.values, node[1]);
    case "l":
      if (BLOCKED.has(node[1])) throw new ExpressionError("genui_expression_blocked");
      return ownGet(env.names, node[1]);
    case "a":
      return node[1].map((item) => evaluateNode(item, env));
    case "u": {
      const value = evaluateNode(node[2], env);
      return node[1] === "!" ? !truthy(value) : -toNumber(value);
    }
    case "?":
      return evaluateNode(truthy(evaluateNode(node[1], env)) ? node[2] : node[3], env);
    case "g":
      return get(evaluateNode(node[1], env), evaluateNode(node[2], env));
    case "b": {
      const left = evaluateNode(node[2], env);
      if (node[1] === "&&") return truthy(left) ? evaluateNode(node[3], env) : left;
      if (node[1] === "||") return truthy(left) ? left : evaluateNode(node[3], env);
      return binary(node[1], left, evaluateNode(node[3], env));
    }
    case "f": {
      const functions = env.functions ?? FUNCTIONS;
      const fn = Object.hasOwn(functions, node[1]) ? functions[node[1]] : undefined;
      if (!fn) throw new ExpressionError("genui_function_unknown");
      if (node[1] === "Fact") {
        const key = node[2][0] ? evaluateNode(node[2][0], env) : null;
        return typeof key === "string" ? ownGet(env.facts, key) : null;
      }
      if (node[1] === "Random" && !env.context?.allowRandom) {
        throw new ExpressionError("genui_random_outside_set");
      }
      return fn(env.context ?? {}, ...node[2].map((arg) => evaluateNode(arg, env)));
    }
  }
}

/** `uxExpr`: non-strings are literals; a failure, undefined or non-finite is `fallback`. */
export function evaluate(source: unknown, env: Env, fallback: unknown = null): unknown {
  if (typeof source !== "string") return source;
  let value: unknown;
  try {
    value = normal(evaluateNode(parse(source), env));
  } catch {
    return fallback;
  }
  return value === null && fallback !== null ? fallback : value;
}

const TEMPLATE = /\{([^{}]*)\}/g;

export function templateExpressions(text: string): string[] {
  return [...text.matchAll(TEMPLATE)].map((match) => match[1] as string);
}

/** `uxShow`: numbers with en-US grouping, integers with no decimals, else at most 2. */
export function display(value: unknown): string {
  if (value === null || value === undefined) return "";
  if (typeof value === "number") {
    if (!Number.isFinite(value)) return "";
    return groupNumber(value, Number.isInteger(value) ? 0 : 2, true);
  }
  if (Array.isArray(value)) return value.map(display).join("، ");
  if (typeof value === "boolean") return String(value);
  if (typeof value === "string") return value;
  return "";
}

/** Latin digits, en-US grouping; `trim` drops trailing zeros (uxShow), else fixed. */
export function groupNumber(value: number, digits: number, trim = false): string {
  const negative = value < 0;
  const factor = 10 ** digits;
  const rounded = Math.round(Math.abs(value) * factor) / factor;
  let [whole = "0", fraction = ""] = rounded.toFixed(digits).split(".");
  whole = whole.replace(/\B(?=(\d{3})+(?!\d))/g, ",");
  if (trim) fraction = fraction.replace(/0+$/, "");
  return `${negative && rounded !== 0 ? "-" : ""}${whole}${fraction ? `.${fraction}` : ""}`;
}

export function renderTemplate(text: string, env: Env): string {
  return text.replace(TEMPLATE, (_match, source: string) => display(evaluate(source, env, "")));
}

/** `values` over `state`, then each calc in order into the same `$` namespace. */
export function environment(
  state: Record<string, unknown>,
  calc: Record<string, string>,
  facts: Record<string, unknown>,
  values?: Record<string, unknown>,
  context?: FormatContext,
): Env {
  const current: Record<string, unknown> = Object.create(null);
  for (const [key, value] of Object.entries(state)) current[key] = value;
  for (const [key, value] of Object.entries(values ?? {})) current[key] = value;
  const env: Env = { values: current, facts, names: Object.create(null), context };
  for (const [name, source] of Object.entries(calc)) current[name] = evaluate(source, env);
  return env;
}

/** State keys, function names, local names and fact keys an expression reads. */
export function references(source: string) {
  const state = new Set<string>();
  const functions = new Set<string>();
  const names = new Set<string>();
  const facts = new Set<string>();
  const walk = (node: Node) => {
    switch (node[0]) {
      case "v":
        state.add(node[1]);
        return;
      case "l":
        names.add(node[1]);
        return;
      case "f":
        functions.add(node[1]);
        if (node[1] === "Fact" && node[2][0]?.[0] === "c") facts.add(String(node[2][0][1]));
        node[2].forEach(walk);
        return;
      case "a":
        node[1].forEach(walk);
        return;
      case "c":
        return;
      case "u":
        walk(node[2]);
        return;
      case "?":
        walk(node[1]);
        walk(node[2]);
        walk(node[3]);
        return;
      case "g":
        walk(node[1]);
        walk(node[2]);
        return;
      case "b":
        walk(node[2]);
        walk(node[3]);
    }
  };
  walk(parse(source));
  return { state, functions, names, facts };
}
