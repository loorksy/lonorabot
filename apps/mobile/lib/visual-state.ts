/** Local component state is scoped to the signed-in owner and document identity. */
import { Platform } from "react-native";

export type StoredVisualState = { state: unknown; expanded: Record<string, boolean> };
const PREFIX = "lonora.visual.";
const MAX_STATE_BYTES = 100000;

function filename(key: string) {
  return `${key.replace(/[^A-Za-z0-9_.-]/g, "_").slice(0, 220)}.json`;
}

export async function loadVisualState(key: string): Promise<StoredVisualState | null> {
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
  try {
    const raw = JSON.stringify(value);
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
