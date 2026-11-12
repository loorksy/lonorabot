/** Fail-closed validation of compiled v2 cards on the client (docs/genui.md).
 * The server compiles and checks every card; this guards the render path against anything
 * malformed: own properties only, no getters, no prototype keys, bounded sizes, and only
 * the node types and actions of the catalog (`@lonora/contracts` genui-catalog). */
import {
  UI_ACTIONS,
  UI_NODE_TYPES,
  UI_SERVER_NODE_TYPES,
  type UiDocument,
  type UiPart,
} from "@lonora/contracts";
import { parse } from "./expr";

const KINDS = new Set([
  "calculator",
  "form",
  "picker",
  "chart",
  "choice",
  "checklist",
  "quiz",
  "timer",
  "diagram",
  "receipt",
]);
/** The catalog's node set plus the server's delivery row (mandate 10.1.5). */
export const UI_NODES: ReadonlySet<string> = new Set<string>([
  ...UI_NODE_TYPES,
  ...UI_SERVER_NODE_TYPES,
]);
const ACTIONS: ReadonlySet<string> = new Set<string>(UI_ACTIONS);
const BLOCKED = new Set(["__proto__", "prototype", "constructor"]);
const MAX_BYTES = 64000;

function plain(value: unknown): value is Record<string, unknown> {
  if (value === null || typeof value !== "object" || Array.isArray(value)) return false;
  const prototype = Object.getPrototypeOf(value);
  if (prototype !== null && prototype !== Object.prototype) return false;
  return Object.entries(Object.getOwnPropertyDescriptors(value)).every(
    ([key, property]) => !BLOCKED.has(key) && !property.get && !property.set,
  );
}

function json(value: unknown, depth = 0): boolean {
  if (depth > 12) return false;
  if (value === null || typeof value === "string" || typeof value === "boolean") return true;
  if (typeof value === "number") return Number.isFinite(value);
  if (Array.isArray(value)) {
    return (
      Object.getPrototypeOf(value) === Array.prototype &&
      value.length <= 200 &&
      value.every((item) => json(item, depth + 1))
    );
  }
  return plain(value) && Object.values(value).every((item) => json(item, depth + 1));
}

function expression(value: unknown): boolean {
  if (typeof value !== "string") return true;
  try {
    parse(value);
    return true;
  } catch {
    return false;
  }
}

function block(value: unknown, depth = 0): boolean {
  if (!plain(value) || typeof value.type !== "string" || !UI_NODES.has(value.type)) return false;
  if (depth > 4 || !expression(value.when)) return false;
  if (value.type === "Delivery") {
    return (
      Array.isArray(value.channels) &&
      value.channels.every((c) => c === "app" || c === "push" || c === "call")
    );
  }
  if ("children" in value) {
    if (!Array.isArray(value.children) || value.children.length > 8) return false;
    if (!value.children.every((child) => block(child, depth + 1))) return false;
  }
  if ("action" in value && value.action !== undefined) {
    const action = value.action;
    if (!plain(action) || !ACTIONS.has(String(action.do))) {
      return false;
    }
    if (
      action.do === "open" &&
      !(typeof action.url === "string" && action.url.startsWith("https://"))
    )
      return false;
  }
  return true;
}

export function validateUiDocument(value: unknown): UiDocument | null {
  try {
    if (!plain(value) || value.v !== 2 || !json(value)) return null;
    if (!KINDS.has(String(value.kind)) || typeof value.title !== "string") return null;
    if (typeof value.fallback !== "string" || value.fallback.length > 1500) return null;
    if (!plain(value.facts) || !plain(value.state) || !plain(value.calc)) return null;
    if (
      !Object.values(value.calc).every(
        (source) =>
          source === null ||
          typeof source === "boolean" ||
          (typeof source === "number" && Number.isFinite(source)) ||
          (typeof source === "string" && expression(source)),
      )
    ) {
      return null;
    }
    if (!Array.isArray(value.blocks) || value.blocks.length > 14) return null;
    if (!value.blocks.every((item) => block(item))) return null;
    if (new TextEncoder().encode(JSON.stringify(value)).length > MAX_BYTES) return null;
    return value as unknown as UiDocument;
  } catch {
    return null;
  }
}

export function validateUiPart(value: Record<string, unknown>): UiPart | null {
  const allowed = new Set(["type", "document", "building", "cut"]);
  if (!Object.keys(value).every((key) => allowed.has(key))) return null;
  if (value.building !== undefined && typeof value.building !== "boolean") return null;
  if (value.cut !== undefined && !(Number.isInteger(value.cut) && (value.cut as number) >= 0))
    return null;
  const document = validateUiDocument(value.document);
  if (!document) return null;
  return {
    type: "ui",
    document,
    ...(value.building ? { building: true } : {}),
    ...(value.cut !== undefined ? { cut: value.cut as number } : {}),
  };
}

export function isUiPart(part: { type: string; document?: unknown }): part is UiPart {
  return (
    part.type === "ui" && plain(part.document) && (part.document as Record<string, unknown>).v === 2
  );
}
