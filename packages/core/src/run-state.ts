import type { RunStatus } from "@lonora/contracts";

export const activeStatuses: readonly RunStatus[] = ["queued", "leased", "running"];
export function isWorking(status: RunStatus): boolean {
  return activeStatuses.includes(status);
}
export function canResume(status: RunStatus): boolean {
  return status === "waiting_input" || status === "waiting_takeover" || status === "failed";
}
export function canCancel(status: RunStatus): boolean {
  return isWorking(status) || status === "waiting_input" || status === "waiting_takeover";
}
/** Stop cancels EVERY cancellable run of the thread, a queued card submit included. */
export function stopTargets<T extends { status: RunStatus; thread_id: string }>(
  runs: readonly T[],
  threadId: string,
): T[] {
  return runs.filter((run) => run.thread_id === threadId && canCancel(run.status));
}

/** Failed replies already retried (a run names them in ``retry_of``): their error card
    settles, so it never offers a second Retry. */
export function retriedRunIds(
  runs: readonly { model_metadata?: Record<string, unknown> | null }[],
) {
  const ids = new Set<string>();
  for (const run of runs) {
    const source = run.model_metadata?.retry_of;
    if (typeof source === "string") ids.add(source);
  }
  return ids;
}
