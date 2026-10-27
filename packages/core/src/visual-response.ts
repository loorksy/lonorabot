/** Shared validation and local calculations for native visual responses.
 * No expression or action is executed as JavaScript, HTML, a URL or a broker call.
 */
import type {
  RichContent,
  VisualAction,
  VisualDocument,
  VisualNode,
  VisualNodeKind,
  VisualScalar,
  VisualState,
  VisualValue,
} from "@lonora/contracts";
import { unsafeVisualText } from "./visual-private-text";

export const MAX_VISUAL_BYTES = 64000;
export const MAX_VISUAL_NODES = 120;
export const MAX_VISUAL_DEPTH = 10;
const keyPattern = /^[A-Za-z][A-Za-z0-9_-]{0,47}$/;
const resourcePattern = /^[0-9a-f]{8}-(?:[0-9a-f]{4}-){3}[0-9a-f]{12}$/i;
const own = (value: object, key: PropertyKey) => Object.hasOwn(value, key);
const isKey = (value: unknown): value is string =>
  typeof value === "string" &&
  keyPattern.test(value) &&
  !["constructor", "prototype", "__proto__"].includes(value);
const isScalar = (value: unknown): value is VisualScalar =>
  value === null ||
  typeof value === "string" ||
  typeof value === "boolean" ||
  (typeof value === "number" && Number.isFinite(value));
const hasPlaceholder = (value: unknown) => typeof value === "string" && value.includes("{{");
const text = (value: unknown, maximum: number, nullable = false) =>
  (nullable && value === null) ||
  (typeof value === "string" && value.length <= maximum && !hasPlaceholder(value));
const literal = (value: unknown, choices: readonly string[]) =>
  typeof value === "string" && choices.includes(value);
const object = (value: unknown): value is Record<string, unknown> => {
  if (value === null || typeof value !== "object" || Array.isArray(value)) return false;
  const prototype = Object.getPrototypeOf(value);
  return (
    (prototype === null || prototype === Object.prototype) &&
    Object.values(Object.getOwnPropertyDescriptors(value)).every(
      (property) => !property.get && !property.set,
    )
  );
};
const fieldsOnly = (value: Record<string, unknown>, fields: readonly string[]) =>
  Object.keys(value).every((key) => fields.includes(key));
const array = (value: unknown, maximum: number): value is unknown[] =>
  Array.isArray(value) &&
  Object.getPrototypeOf(value) === Array.prototype &&
  value.length <= maximum &&
  Object.keys(value).length === value.length &&
  Object.entries(Object.getOwnPropertyDescriptors(value)).every(
    ([key, property]) =>
      (key === "length" || (/^(0|[1-9]\d*)$/.test(key) && Number(key) < value.length)) &&
      !property.get &&
      !property.set,
  );
const numeric = (
  value: unknown,
  minimum = Number.NEGATIVE_INFINITY,
  maximum = Number.POSITIVE_INFINITY,
) => typeof value === "number" && Number.isFinite(value) && value >= minimum && value <= maximum;
const common = ["id", "type", "visible", "tone"];
const layout = ["children", "label", "gap"];
const allowed: Record<VisualNodeKind, string[]> = {
  column: layout,
  row: layout,
  container: layout,
  card: layout,
  list: layout,
  timeline: layout,
  disclosure: layout,
  form: layout,
  grid: ["children", "columns", "gap"],
  divider: [],
  text: ["text", "value"],
  heading: ["text", "level"],
  badge: ["text", "value"],
  icon: ["text"],
  metric: ["label", "value", "unit"],
  table: ["label", "fields", "rows", "filter_key"],
  progress: ["label", "value", "maximum"],
  diagram: ["label", "vertices", "edges"],
  chart: ["label", "chart_kind", "points"],
  image: ["artifact_id", "label"],
  tabs: ["children", "options", "state_key"],
  button: ["label", "action"],
  select: ["label", "options", "state_key"],
  checkbox: ["label", "state_key"],
  slider: ["label", "state_key", "minimum", "maximum", "step"],
  input: ["label", "state_key", "input_kind", "minimum", "maximum", "step"],
};
const operatorArity: Record<string, [number, number]> = {
  add: [1, 8],
  sub: [2, 2],
  mul: [1, 8],
  div: [2, 2],
  min: [1, 8],
  max: [1, 8],
  round: [1, 2],
  abs: [1, 1],
  eq: [2, 2],
  gt: [2, 2],
  gte: [2, 2],
  lt: [2, 2],
  lte: [2, 2],
  and: [1, 8],
  or: [1, 8],
  not: [1, 1],
  if: [3, 3],
  floor: [1, 1],
  ceil: [1, 1],
  sqrt: [1, 1],
  pow: [2, 2],
  clamp: [3, 3],
  percent: [2, 2],
  change: [2, 2],
  concat: [1, 8],
};

/** Read old text bindings as explicit expressions over existing declared state.
 * Other fields and unknown bindings still fail validation. No input is mutated.
 */
function legacyBindings(document: Record<string, unknown>): Record<string, unknown> {
  const state = document.state ?? {};
  if (!object(state)) return document;
  const concat = (initial: unknown[]): unknown => {
    let parts = initial;
    while (parts.length > 8) {
      const next: unknown[] = [];
      for (let index = 0; index < parts.length; index += 8)
        next.push({ op: "concat", args: parts.slice(index, index + 8) });
      parts = next;
    }
    return { op: "concat", args: parts };
  };
  const walk = (node: unknown, depth = 0): unknown => {
    if (!object(node) || depth > MAX_VISUAL_DEPTH) return node;
    const result = { ...node };
    if (
      (node.type === "text" || node.type === "badge") &&
      !own(node, "value") &&
      typeof node.text === "string" &&
      node.text.length <= 4000 &&
      hasPlaceholder(node.text)
    ) {
      const parts: unknown[] = [];
      let position = 0;
      let valid = true;
      for (const match of node.text.matchAll(/\{\{([^{}]+)\}\}/g)) {
        const key = match[1];
        if (!isKey(key) || !own(state, key) || !isScalar(state[key])) {
          valid = false;
          break;
        }
        if (match.index > position) parts.push(node.text.slice(position, match.index));
        parts.push({ state: key });
        position = match.index + match[0].length;
      }
      if (position < node.text.length) parts.push(node.text.slice(position));
      if (valid && parts.length && !parts.some(hasPlaceholder)) {
        delete result.text;
        result.value = concat(parts);
      }
    }
    if (array(node.children, 40)) {
      const children = node.children.map((child) => walk(child, depth + 1));
      if (children.some((child, index) => child !== (node.children as unknown[])[index]))
        result.children = children;
    }
    return Object.keys(result).some((key) => result[key] !== node[key]) ||
      (!own(result, "text") && own(node, "text"))
      ? result
      : node;
  };
  const root = walk(document.root);
  return root === document.root ? document : { ...document, root };
}

/** Empty is null; an unfinished/invalid number keeps its draft without a state update. */
export function parseVisualNumberDraft(text: string): number | null | undefined {
  const normalized = text
    .trim()
    .replace(/[٠-٩۰-۹]/gu, (digit) =>
      String(
        "٠١٢٣٤٥٦٧٨٩".includes(digit) ? "٠١٢٣٤٥٦٧٨٩".indexOf(digit) : "۰۱۲۳۴۵۶۷۸۹".indexOf(digit),
      ),
    )
    .replace(/٫/g, ".")
    .replace(/٬/g, "");
  if (!normalized) return null;
  if (
    normalized.length > 2000 ||
    !/^[+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d+)?$/.test(normalized)
  )
    return undefined;
  const parsed = Number(normalized);
  return Number.isFinite(parsed) ? parsed : undefined;
}

function byteLength(value: string): number {
  let size = 0;
  for (const character of value) {
    const point = character.codePointAt(0) ?? 0;
    size += point <= 0x7f ? 1 : point <= 0x7ff ? 2 : point <= 0xffff ? 3 : 4;
  }
  return size;
}

function validValue(value: unknown, state: Set<string>, facts: Set<string>, depth = 0): boolean {
  if (depth > 8) return false;
  if (isScalar(value)) return !hasPlaceholder(value);
  if (!object(value)) return false;
  if (fieldsOnly(value, ["state"]) && typeof value.state === "string")
    return state.has(value.state);
  if (fieldsOnly(value, ["source"]) && typeof value.source === "string")
    return facts.has(value.source);
  // A browser/native client never resolves model-requested evidence. Only the
  // server can compile a fact reference into a validated, bounded source value.
  if (
    !fieldsOnly(value, ["op", "args"]) ||
    typeof value.op !== "string" ||
    !own(operatorArity, value.op) ||
    !array(value.args, 8)
  )
    return false;
  const [minimum, maximum] = operatorArity[value.op];
  return (
    value.args.length >= minimum &&
    value.args.length <= maximum &&
    value.args.every((item) => validValue(item, state, facts, depth + 1))
  );
}

function validAction(value: unknown): value is VisualAction {
  if (!object(value) || !fieldsOnly(value, ["kind", "text", "resource_id"])) return false;
  if (value.kind === "follow_up")
    return (
      typeof value.text === "string" &&
      Boolean(value.text.trim()) &&
      value.text.length <= 2000 &&
      (value.resource_id === undefined || value.resource_id === null)
    );
  return (
    literal(value.kind, ["open_chart", "open_artifact"]) &&
    typeof value.resource_id === "string" &&
    resourcePattern.test(value.resource_id) &&
    (value.text === undefined || value.text === null)
  );
}

/** Validate compiled wire data. Unknown properties and draft facts fail closed. */
export function validateVisualDocument(value: unknown): VisualDocument | null {
  try {
    if (
      !object(value) ||
      !fieldsOnly(value, ["version", "mode", "root", "state", "facts"]) ||
      value.version !== 1 ||
      !literal(value.mode, ["observed", "example", "estimate"])
    )
      return null;
    value = legacyBindings(value);
    if (!object(value)) return null;
    const state = value.state ?? {};
    const facts = value.facts ?? {};
    if (
      !object(state) ||
      Object.keys(state).length > 20 ||
      !Object.entries(state).every(
        ([key, item]) => isKey(key) && isScalar(item) && !hasPlaceholder(item),
      )
    )
      return null;
    if (
      !object(facts) ||
      Object.keys(facts).length > 200 ||
      !Object.entries(facts).every(
        ([key, fact]) =>
          isKey(key) &&
          object(fact) &&
          fieldsOnly(fact, ["value", "source", "observed_at"]) &&
          own(fact, "value") &&
          isScalar(fact.value) &&
          !hasPlaceholder(fact.value) &&
          text(fact.source, 100) &&
          (fact.observed_at === undefined || text(fact.observed_at, 80, true)),
      )
    )
      return null;
    const stateKeys = new Set(Object.keys(state));
    const factKeys = new Set(Object.keys(facts));
    const seen = new Set<string>();
    const expressions = (item: unknown) => validValue(item, stateKeys, factKeys);
    const walk = (node: unknown, depth: number): boolean => {
      if (
        depth > MAX_VISUAL_DEPTH ||
        !object(node) ||
        !isKey(node.id) ||
        seen.has(node.id) ||
        seen.size >= MAX_VISUAL_NODES ||
        typeof node.type !== "string" ||
        !own(allowed, node.type)
      )
        return false;
      const kind = node.type as VisualNodeKind;
      if (!fieldsOnly(node, [...common, ...allowed[kind]])) return false;
      seen.add(node.id);
      for (const field of ["text", "label"])
        if (own(node, field) && !text(node[field], field === "text" ? 4000 : 300, true))
          return false;
      if (
        own(node, "tone") &&
        !literal(node.tone, ["neutral", "info", "success", "warning", "danger"])
      )
        return false;
      if (own(node, "gap") && !literal(node.gap, ["small", "normal", "large"])) return false;
      if (own(node, "level") && (!numeric(node.level, 1, 4) || !Number.isInteger(node.level)))
        return false;
      if (own(node, "columns") && (!numeric(node.columns, 1, 3) || !Number.isInteger(node.columns)))
        return false;
      if (own(node, "chart_kind") && !literal(node.chart_kind, ["line", "bar", "pie"]))
        return false;
      if (own(node, "input_kind") && !literal(node.input_kind, ["text", "number"])) return false;
      for (const field of ["value", "unit", "visible"])
        if (own(node, field) && !expressions(node[field])) return false;
      if (["metric", "progress"].includes(kind) && !own(node, "value")) return false;
      for (const field of ["state_key", "filter_key"])
        if (
          node[field] !== undefined &&
          node[field] !== null &&
          (!isKey(node[field]) || !stateKeys.has(node[field]))
        )
          return false;
      if (
        ["select", "checkbox", "slider", "input", "tabs"].includes(kind) &&
        (typeof node.state_key !== "string" || !stateKeys.has(node.state_key))
      )
        return false;
      if (own(node, "minimum") && !numeric(node.minimum)) return false;
      if (own(node, "maximum") && !numeric(node.maximum)) return false;
      if (own(node, "step") && (!numeric(node.step) || (node.step as number) <= 0)) return false;
      if ((node.maximum ?? 100) < (node.minimum ?? 0)) return false;
      if (node.options !== undefined) {
        if (
          !array(node.options, 20) ||
          !node.options.every(
            (item) =>
              object(item) &&
              fieldsOnly(item, ["value", "label"]) &&
              text(item.value, 100) &&
              text(item.label, 160),
          )
        )
          return false;
        if (
          new Set(node.options.map((option) => (option as { value: string }).value)).size !==
          node.options.length
        )
          return false;
      }
      if (
        ["select", "tabs"].includes(kind) &&
        (!Array.isArray(node.options) || !node.options.length)
      )
        return false;
      const initial = typeof node.state_key === "string" ? state[node.state_key] : undefined;
      if (
        ["select", "tabs"].includes(kind) &&
        !(node.options as { value: string }[]).some((option) => option.value === initial)
      )
        return false;
      if (kind === "checkbox" && typeof initial !== "boolean") return false;
      if (
        (kind === "slider" || (kind === "input" && node.input_kind === "number")) &&
        !numeric(
          initial,
          (node.minimum as number | undefined) ?? 0,
          (node.maximum as number | undefined) ?? 100,
        )
      )
        return false;
      if (kind === "input" && (node.input_kind ?? "text") === "text" && typeof initial !== "string")
        return false;
      if (typeof node.filter_key === "string" && typeof state[node.filter_key] !== "string")
        return false;
      if (
        node.children !== undefined &&
        (!array(node.children, 40) || !node.children.every((child) => walk(child, depth + 1)))
      )
        return false;
      if (
        kind === "tabs" &&
        (node.options as unknown[]).length !== ((node.children ?? []) as unknown[]).length
      )
        return false;
      if (
        node.fields !== undefined &&
        (!array(node.fields, 12) ||
          !node.fields.every(
            (item) =>
              object(item) &&
              fieldsOnly(item, ["key", "label"]) &&
              isKey(item.key) &&
              text(item.label, 160),
          ))
      )
        return false;
      const columnKeys = new Set(
        ((node.fields ?? []) as { key: string }[]).map((column) => column.key),
      );
      if (columnKeys.size !== ((node.fields ?? []) as unknown[]).length) return false;
      if (kind === "table" && !columnKeys.size) return false;
      if (
        node.rows !== undefined &&
        (!array(node.rows, 100) ||
          !node.rows.every(
            (row) =>
              object(row) &&
              Object.entries(row).every(([key, item]) => columnKeys.has(key) && expressions(item)),
          ))
      )
        return false;
      if (
        node.points !== undefined &&
        (!array(node.points, 100) ||
          !node.points.every(
            (point) =>
              object(point) &&
              fieldsOnly(point, ["label", "value"]) &&
              own(point, "label") &&
              own(point, "value") &&
              expressions(point.label) &&
              expressions(point.value),
          ))
      )
        return false;
      if (
        node.vertices !== undefined &&
        (!array(node.vertices, 20) ||
          !node.vertices.every(
            (vertex) =>
              object(vertex) &&
              fieldsOnly(vertex, ["id", "label"]) &&
              isKey(vertex.id) &&
              text(vertex.label, 160),
          ))
      )
        return false;
      const vertices = new Set(
        ((node.vertices ?? []) as { id: string }[]).map((vertex) => vertex.id),
      );
      if (vertices.size !== ((node.vertices ?? []) as unknown[]).length) return false;
      if (
        node.edges !== undefined &&
        (!array(node.edges, 30) ||
          !node.edges.every(
            (edge) =>
              object(edge) &&
              fieldsOnly(edge, ["source", "target", "label"]) &&
              typeof edge.source === "string" &&
              vertices.has(edge.source) &&
              typeof edge.target === "string" &&
              vertices.has(edge.target) &&
              (edge.label === undefined || text(edge.label, 100)),
          ))
      )
        return false;
      if (node.action !== undefined && node.action !== null && !validAction(node.action))
        return false;
      if (
        object(node.action) &&
        node.action.kind === "follow_up" &&
        typeof node.action.text === "string"
      ) {
        const template = node.action.text.replace(/\{\{([^{}]+)\}\}/g, (_, key: string) =>
          stateKeys.has(key) && isKey(key) ? "" : "{{invalid}}",
        );
        if (/\{\{|\}\}/.test(template)) return false;
      }
      if (kind === "button" && (!node.label || !validAction(node.action))) return false;
      if (
        node.artifact_id !== undefined &&
        node.artifact_id !== null &&
        (typeof node.artifact_id !== "string" || !resourcePattern.test(node.artifact_id))
      )
        return false;
      if (kind === "image" && !node.artifact_id) return false;
      return true;
    };
    if (!walk(value.root, 0)) return null;
    const serialized = JSON.stringify(value);
    return serialized.length <= MAX_VISUAL_BYTES && byteLength(serialized) <= MAX_VISUAL_BYTES
      ? (value as unknown as VisualDocument)
      : null;
  } catch {
    return null;
  }
}

export function validateRichContent(value: unknown): RichContent | null {
  try {
    if (
      !object(value) ||
      !fieldsOnly(value, ["version", "parts"]) ||
      value.version !== 1 ||
      !array(value.parts, 24) ||
      !value.parts.length
    )
      return null;
    const parts: RichContent["parts"] = [];
    for (const part of value.parts) {
      if (!object(part)) return null;
      if (part.type === "text") {
        if (
          !fieldsOnly(part, ["type", "text"]) ||
          typeof part.text !== "string" ||
          part.text.length > 32000
        )
          return null;
        parts.push({ type: "text", text: part.text });
      } else {
        if (part.type !== "ui" || !fieldsOnly(part, ["type", "document"])) return null;
        const document = validateVisualDocument(part.document);
        if (!document) return null;
        parts.push({ type: "ui", document });
      }
    }
    const result: RichContent = { version: 1, parts };
    return byteLength(JSON.stringify(result)) <= 128000 ? result : null;
  } catch {
    return null;
  }
}

/** Pure bounded expression evaluation, shared by DOM and native renderers. */
export function evaluateVisualValue(
  value: VisualValue | undefined,
  document: VisualDocument,
  state: VisualState,
): VisualScalar {
  const evaluate = (item: VisualValue | undefined, depth: number): VisualScalar => {
    if (depth > 8 || item === undefined) return null;
    if (isScalar(item)) return item;
    if ("state" in item)
      return own(state, item.state) ? state[item.state] : (document.state?.[item.state] ?? null);
    if ("source" in item) return document.facts?.[item.source]?.value ?? null;
    if (!("op" in item) || !own(operatorArity, item.op)) return null;
    const range = operatorArity[item.op];
    if (item.args.length < range[0] || item.args.length > range[1]) return null;
    if (item.op === "if")
      return evaluate(item.args[0], depth + 1)
        ? evaluate(item.args[1], depth + 1)
        : evaluate(item.args[2], depth + 1);
    const args = item.args.map((argument) => evaluate(argument, depth + 1));
    if (item.op === "concat") {
      if (args.some((argument) => argument === null)) return null;
      const result = args.map(String).join("");
      return Array.from(result).length <= 4000 ? result : null;
    }
    if (item.op === "eq") return args[0] === args[1];
    if (item.op === "and") return args.every(Boolean);
    if (item.op === "or") return args.some(Boolean);
    if (item.op === "not") return !args[0];
    if (
      !args.every(
        (argument): argument is number => typeof argument === "number" && Number.isFinite(argument),
      )
    )
      return null;
    let result: VisualScalar;
    switch (item.op) {
      case "add":
        result = args.reduce((total, item) => total + item, 0);
        break;
      case "sub":
        result = args[0] - args[1];
        break;
      case "mul":
        result = args.reduce((total, item) => total * item, 1);
        break;
      case "div":
        result = args[1] === 0 ? null : args[0] / args[1];
        break;
      case "min":
        result = Math.min(...args);
        break;
      case "max":
        result = Math.max(...args);
        break;
      case "abs":
        result = Math.abs(args[0]);
        break;
      case "floor":
        result = Math.floor(args[0]);
        break;
      case "ceil":
        result = Math.ceil(args[0]);
        break;
      case "sqrt":
        result = Math.sqrt(args[0]);
        break;
      case "pow":
        result = args[0] ** args[1];
        break;
      case "clamp":
        result = args[1] > args[2] ? null : Math.min(args[2], Math.max(args[1], args[0]));
        break;
      case "percent":
        result = args[1] === 0 ? null : (args[0] / args[1]) * 100;
        break;
      case "change":
        result = args[1] === 0 ? null : ((args[0] - args[1]) / Math.abs(args[1])) * 100;
        break;
      case "round": {
        const places = args[1] ?? 0;
        if (!Number.isInteger(places) || places < 0 || places > 8) return null;
        const precision = 10 ** places;
        result = Math.round((args[0] + Number.EPSILON) * precision) / precision;
        break;
      }
      case "gt":
        result = args[0] > args[1];
        break;
      case "gte":
        result = args[0] >= args[1];
        break;
      case "lt":
        result = args[0] < args[1];
        break;
      case "lte":
        result = args[0] <= args[1];
        break;
      default:
        return null;
    }
    return isScalar(result) ? result : null;
  };
  const result = evaluate(value, 0);
  return typeof result === "string" && unsafeVisualText(result) ? null : result;
}

function controlValue(node: VisualNode, value: unknown, fallback: VisualScalar): VisualScalar {
  if (node.type === "checkbox")
    return typeof value === "boolean" ? value : typeof fallback === "boolean" ? fallback : false;
  if (node.type === "select" || node.type === "tabs") {
    const options = node.options ?? [];
    if (typeof value === "string" && options.some((option) => option.value === value)) return value;
    return options.some((option) => option.value === fallback)
      ? fallback
      : (options[0]?.value ?? null);
  }
  if (node.type === "slider" || (node.type === "input" && node.input_kind === "number")) {
    if (node.type === "input" && (value === null || value === "")) return null;
    const parsed =
      typeof value === "number"
        ? value
        : typeof value === "string" && value.trim()
          ? Number(value)
          : Number.NaN;
    const minimum = node.minimum ?? 0;
    const maximum = node.maximum ?? 100;
    const step = node.step ?? 1;
    const number = Number.isFinite(parsed)
      ? parsed
      : typeof fallback === "number" && Number.isFinite(fallback)
        ? fallback
        : minimum;
    const bounded = Math.min(maximum, Math.max(minimum, number));
    // Numeric text fields preserve decimal amounts. A step is a keyboard hint,
    // whereas a slider actually selects discrete ticks.
    if (node.type === "input") return bounded;
    const snapped = minimum + Math.round((bounded - minimum) / step) * step;
    return Math.min(maximum, Math.max(minimum, Number(snapped.toPrecision(12))));
  }
  if (node.type === "input")
    return typeof value === "string"
      ? value.slice(0, 2000)
      : typeof fallback === "string"
        ? fallback
        : "";
  return isScalar(value) ? value : fallback;
}

function walkNodes(node: VisualNode, visit: (node: VisualNode) => void): void {
  visit(node);
  for (const child of node.children ?? []) walkNodes(child, visit);
}

/** Restore only declared scalar keys; previous messages/documents cannot add state. */
export function initialVisualState(document: VisualDocument, saved?: unknown): VisualState {
  const stored = object(saved) ? saved : {};
  const result: VisualState = {};
  for (const [key, fallback] of Object.entries(document.state ?? {})) {
    if (!isKey(key)) continue;
    const value = own(stored, key) && isScalar(stored[key]) ? stored[key] : fallback;
    result[key] = typeof value === "string" ? value.slice(0, 2000) : value;
  }
  walkNodes(document.root, (node) => {
    if (node.state_key && own(result, node.state_key))
      result[node.state_key] = controlValue(
        node,
        result[node.state_key],
        document.state?.[node.state_key] ?? null,
      );
  });
  return result;
}

/** Only the actual declared control can update its state; no generic mutation path. */
export function updateVisualState(
  document: VisualDocument,
  state: VisualState,
  node: VisualNode,
  next: VisualScalar,
): VisualState {
  let declared: VisualNode | undefined;
  walkNodes(document.root, (candidate) => {
    if (candidate.id === node.id) declared = candidate;
  });
  const result = initialVisualState(document, state);
  // A table's built-in search input belongs to the table itself, rather than an
  // invented input node. It can only change that table's declared text filter.
  if (declared?.type === "table" && declared.filter_key) {
    const key = declared.filter_key;
    if (own(result, key) && typeof result[key] === "string" && typeof next === "string")
      result[key] = next.slice(0, 2000);
    return result;
  }
  if (
    !declared?.state_key ||
    !own(result, declared.state_key) ||
    !["checkbox", "select", "tabs", "slider", "input"].includes(declared.type)
  )
    return result;
  result[declared.state_key] = controlValue(declared, next, result[declared.state_key]);
  return result;
}

/** Expand data placeholders only; the caller uses its existing authenticated route. */
export function expandVisualAction(
  action: VisualAction,
  document: VisualDocument,
  state: VisualState,
): VisualAction | null {
  if (!validAction(action)) return null;
  if (action.kind !== "follow_up") return { kind: action.kind, resource_id: action.resource_id };
  let invalid = false;
  const known = initialVisualState(document, state);
  const expanded = action.text.replace(/\{\{([^{}]+)\}\}/g, (_, key: string) => {
    if (!isKey(key) || !own(known, key)) {
      invalid = true;
      return "";
    }
    return String(known[key] ?? "");
  });
  const template = action.text.replace(/\{\{([^{}]+)\}\}/g, "");
  if (invalid || /\{\{|\}\}/.test(template) || !expanded.trim() || expanded.length > 2000)
    return null;
  return { kind: "follow_up", text: expanded };
}

export function filterVisualRows(
  node: VisualNode,
  document: VisualDocument,
  state: VisualState,
): Record<string, VisualValue>[] {
  const rows = node.rows ?? [];
  const query = node.filter_key
    ? String(state[node.filter_key] ?? "")
        .trim()
        .toLocaleLowerCase()
    : "";
  return !query
    ? rows
    : rows.filter((row) =>
        Object.values(row).some((value) =>
          String(evaluateVisualValue(value, document, state) ?? "")
            .toLocaleLowerCase()
            .includes(query),
        ),
      );
}

function canonical(value: unknown): string {
  if (Array.isArray(value)) return `[${value.map(canonical).join(",")}]`;
  if (object(value))
    return `{${Object.keys(value)
      .sort()
      .map((key) => `${JSON.stringify(key)}:${canonical(value[key])}`)
      .join(",")}}`;
  return JSON.stringify(value) ?? "null";
}

/** Cache identity only, not a signature or authorization proof. */
export function visualDocumentKey(document: VisualDocument): string {
  const source = canonical(document);
  let left = 0x811c9dc5;
  let right = 0x9e3779b9;
  for (let index = 0; index < source.length; index++) {
    left = Math.imul(left ^ source.charCodeAt(index), 0x01000193);
    right = Math.imul(right ^ source.charCodeAt(source.length - index - 1), 0x85ebca6b);
  }
  return `${(left >>> 0).toString(16).padStart(8, "0")}${(right >>> 0).toString(16).padStart(8, "0")}`;
}

export function visualStateStorageKey(
  ownerId: string,
  threadId: string,
  messageId: string,
  document: VisualDocument,
): string {
  return ["lonora", "visual", "v1", ownerId, threadId, messageId, visualDocumentKey(document)]
    .map(encodeURIComponent)
    .join(":");
}
