// Push reaches the owner's phone only; the browser build registers nothing.
export async function syncPushDevice(): Promise<void> {}
export function onPushTokenChange(_listener: () => void): () => void {
  return () => undefined;
}
