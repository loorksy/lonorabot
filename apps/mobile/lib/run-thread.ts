import type { Run } from "@lonora/contracts";

/** The conversation a run's output reaches: the origin a run in a hidden work thread
 * reports to (a routine, watch, broker event, Task or their follow-up), otherwise its own
 * thread. The server sets the origin; the client keeps no list of triggers. */
export function reportThread(run: Pick<Run, "thread_id" | "model_metadata">): string {
  const origin = run.model_metadata?.origin_thread_id;
  return typeof origin === "string" && origin ? origin : run.thread_id;
}
