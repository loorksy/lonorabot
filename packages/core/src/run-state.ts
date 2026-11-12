import type { Run, RunStatus } from "@lonora/contracts";

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

export type FailureFamily = NonNullable<Run["failure"]>["family"];
/** Why a reply failed (Q22): the server's family, else one read from the error code. */
export function runFailure(run: Run): { family: FailureFamily; retryAfter: number | null } {
  if (run.failure?.family)
    return { family: run.failure.family, retryAfter: run.failure.retry_after_seconds ?? null };
  const code = run.error_code ?? "";
  if (/quota|budget|insufficient|billing/.test(code)) return { family: "quota", retryAfter: null };
  if (/rate/.test(code)) return { family: "rate", retryAfter: 30 };
  if (/timeout|timed_out|deadline/.test(code)) return { family: "timeout", retryAfter: null };
  if (/model|provider/.test(code)) return { family: "model", retryAfter: null };
  return { family: "other", retryAfter: null };
}

/**
 * The failed reply a Retry may re-ask (Q22): the conversation's newest run, when it failed in
 * a provider family (an "other" failure may have touched the executor and is never retried),
 * and no run names it in ``retry_of``. `ready` is false while the provider's Retry-After lasts.
 */
export function retryableFailure(
  runs: readonly Run[],
  now: number,
): { run: Run; ready: boolean } | null {
  const newest = [...runs].sort((a, b) => Date.parse(b.created_at) - Date.parse(a.created_at))[0];
  if (newest?.status !== "failed" || retriedRunIds(runs).has(newest.id)) return null;
  const { family, retryAfter } = runFailure(newest);
  if (family === "other") return null;
  const until = retryAfter ? Date.parse(newest.updated_at) + retryAfter * 1000 : 0;
  return { run: newest, ready: now >= until };
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
