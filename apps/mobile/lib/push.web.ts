// Push reaches the owner's phone only; the browser build registers nothing.
export async function syncPushDevice(): Promise<void> {}
export type PushTarget = { threadId: string; around: number | null };
export function onPushOpened(_open: (target: PushTarget) => void): () => void {
  return () => undefined;
}
export function onPushTokenChange(_listener: () => void): () => void {
  return () => undefined;
}
