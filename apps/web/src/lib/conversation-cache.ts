/** Bounded, session-only read projections. The server always reconciles on mount. */
const entries = new Map<string, unknown>();
const MAX_ENTRIES = 96;
export function conversationKey(owner: string, path: string) {
  return JSON.stringify([owner, path]);
}
export function readConversation<T>(key: string): T | undefined {
  const value = entries.get(key);
  if (value !== undefined) {
    entries.delete(key);
    entries.set(key, value);
  }
  return value as T | undefined;
}
export function retainConversation<T>(key: string, value: T) {
  entries.delete(key);
  entries.set(key, value);
  while (entries.size > MAX_ENTRIES) {
    const oldest = entries.keys().next().value;
    if (oldest !== undefined) entries.delete(oldest);
  }
  return value;
}
if (typeof window !== "undefined")
  window.addEventListener("lonora:session-reset", () => entries.clear());
