// Adapted for Lonora; source and license attribution in THIRD_PARTY_NOTICES.md.
export type Panel =
  | "settings"
  | "knowledge"
  | "routines"
  | "goals"
  | "workspace"
  | "charts"
  | "create"
  | "create-group"
  | "group-settings"
  | null;
const durable: readonly Panel[] = [
  "settings",
  "knowledge",
  "routines",
  "goals",
  "workspace",
  "charts",
  "group-settings",
  null,
];
export function rightPanelStorageKey(owner: string, kind: "agent" | "group", id: string) {
  return `lonora:right-panel-state:${owner}:${kind}:${id}`;
}
export function readRightPanelState(key: string): Panel {
  try {
    const panel: unknown = JSON.parse(localStorage.getItem(key) ?? "null");
    return durable.includes(panel as Panel) ? (panel as Panel) : null;
  } catch {
    return null;
  }
}
export function writeRightPanelState(key: string, panel: Panel) {
  if (panel === "create" || panel === "create-group") return;
  try {
    localStorage.setItem(key, JSON.stringify(panel));
  } catch {
    /* Private-mode storage is optional. */
  }
}
