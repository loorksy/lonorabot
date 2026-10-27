/** Local component state is scoped to the signed-in owner and document identity. */
import { Platform } from "react-native";
import { registerSessionTeardown } from "./session-lifecycle";

export type StoredVisualState = { state: unknown; expanded: Record<string, boolean> };
const PREFIX = "lonora.visual.";
const MAX_STATE_BYTES = 100000;
const memory = new Map<string, StoredVisualState>();
registerSessionTeardown(async () => memory.clear());

function filename(key: string) {
  let first = 2166136261,
    second = 2654435769;
  for (const char of key) {
    first = Math.imul(first ^ char.charCodeAt(0), 16777619);
    second = Math.imul(second ^ char.charCodeAt(0), 2246822507);
  }
  return `${(first >>> 0).toString(16)}-${(second >>> 0).toString(16)}.json`;
}

export async function loadVisualState(key: string): Promise<StoredVisualState | null> {
  const cached = memory.get(key);
  if (cached) return cached;
  try {
    let raw: string | null;
    if (Platform.OS === "web") raw = globalThis.localStorage?.getItem(PREFIX + key) ?? null;
    else {
      const { Directory, File, Paths } = await import("expo-file-system");
      const directory = new Directory(Paths.document, "lonora-visual-state");
      const file = new File(directory, filename(key));
      raw = file.exists ? await file.text() : null;
    }
    if (!raw || raw.length > MAX_STATE_BYTES) return null;
    const value: unknown = JSON.parse(raw);
    if (!value || typeof value !== "object" || Array.isArray(value)) return null;
    const item = value as Record<string, unknown>;
    if (Platform.OS !== "web" && item.key !== key) return null;
    const expanded = item.expanded;
    return {
      state: item.state,
      expanded:
        expanded && typeof expanded === "object" && !Array.isArray(expanded)
          ? Object.fromEntries(
              Object.entries(expanded).filter(
                ([key, value]) => key.length <= 48 && typeof value === "boolean",
              ),
            )
          : {},
    };
  } catch {
    return null;
  }
}

export async function saveVisualState(key: string, value: StoredVisualState): Promise<void> {
  memory.set(key, value);
  while (memory.size > 100) {
    const oldest = memory.keys().next().value;
    if (oldest !== undefined) memory.delete(oldest);
  }
  try {
    const raw = JSON.stringify({ key, ...value });
    if (raw.length > MAX_STATE_BYTES) return;
    if (Platform.OS === "web") globalThis.localStorage?.setItem(PREFIX + key, raw);
    else {
      const { Directory, File, Paths } = await import("expo-file-system");
      const directory = new Directory(Paths.document, "lonora-visual-state");
      directory.create({ intermediates: true, idempotent: true });
      const file = new File(directory, filename(key));
      file.write(raw);
    }
  } catch {
    // A local persistence failure must not disable the conversation or actions.
  }
}
